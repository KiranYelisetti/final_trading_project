from backtesting import Strategy
from app.smc_agent import analyze_ticker
import pandas as pd
import numpy as np

def get_smc_signals(df):
    """
    Wrapper to run SMC analysis and return aligned signal arrays.
    Returns: (bullish_ob_price, bearish_ob_price)
    Values are prices (Top/Bottom) or NaN.
    """
    # Run Agent
    # We pass the full DF. identify_ob returns the DF with 'bullish_ob' True/False columns
    # 'bullish_ob' is True at the Candle i-2.
    
    # We need to reconstruct the "Event".
    # If bullish_ob is detected at index i (which is actually the candle i), 
    # it means the *formation* is complete.
    
    # Actually, my identify_ob function modifies the DF to set 'bullish_ob'=True at the *source* candle.
    # But in backtesting, we only know this *later*. 
    # Logic in analyze_ticker:
    # if df['bullish_fvg'].iloc[i]: ... df.at[i-2, 'bullish_ob'] = True
    
    # So, at time `i`, we realize `i-2` was an OB.
    # We should signal "New OB Found" at time `i`.
    
    # Let's extract the "detection time" signals.
    # Re-run logic slightly adapted for vectorized/backtest friendly return
    
    # Hack: Just run the agent function
    # It modifies DF in place? Or returns new DF.
    # The agent returns 'annotated_df'
    
    # Let's clean the keys first as Backtesting passes Upper Case usually
    df_clean = df.copy()
    if 'Close' not in df_clean.columns: # Backtesting might use 'Close'
        df_clean.columns = [c.capitalize() for c in df_clean.columns]
        
    _, annotated_df = analyze_ticker("DUMMY", df_clean)
    
    # Now, annotated_df has 'bullish_fvg' at index `i`.
    # If `bullish_fvg` is True at `i`, it means at the CLOSE of `i`, we confirmed an OB at `i-2`.
    # So we should set our "Buy Limit Price" to the High of `i-2`.
    
    # Let's create an array of "Limit Prices"
    # shift(2) of High? Not exactly.
    # If FVG at i is True, then OB is at i-2. OB Top is High[i-2] (if bearish OB) or Low?
    # Bullish OB is a DOWN candle. Entry is usually at the OPEN or HIGH of that down candle.
    # Let's use the High of the OB candle (i-2) as the entry for a Bullish setup (retest).
    
    # signal array
    buy_limit_signals = np.full(len(df), np.nan)
    stop_loss_signals = np.full(len(df), np.nan)
    
    # We iterate to map FVG trigger to OB price
    # Vectorized:
    # If bullish_fvg[i] is True -> We set signal at i to be High[i-2]
    
    bull_fvg_mask = annotated_df['bullish_fvg'].values
    highs = annotated_df['High'].values
    lows = annotated_df['Low'].values
    
    # Shifted arrays to get i-2 values aligned at i
    # At index i, we want High[i-2]
    # We can just shift High array by 2?
    highs_shifted_2 = pd.Series(highs).shift(2).values
    lows_shifted_2 = pd.Series(lows).shift(2).values
    
    # We only care where mask is True
    # At index i, signal = High[i-2]
    buy_limit_signals[bull_fvg_mask] = highs_shifted_2[bull_fvg_mask]
    
    # Stop loss = Low[i-2] ? (Bottom of OB)
    stop_loss_signals[bull_fvg_mask] = lows_shifted_2[bull_fvg_mask]
    
    return buy_limit_signals, stop_loss_signals

class SMCStrategy(Strategy):
    """
    SMC Strategy:
    1. Wait for Bullish OB confirmation (Triggered by FVG).
    2. Place Buy Limit Order at OB Top (High of OB candle).
    3. Stop Loss at OB Bottom (Low of OB candle).
    4. Target 2R.
    """
    
    risk_reward = 2.0
    
    def init(self):
        # Compute indicators
        # Backtesting.py requires indicators to be wrappers/arrays
        # We compute the whole array of "Limit Prices" (non-NaN when a new OB is found)
        self.buy_limits, self.stop_losses = self.I(get_smc_signals, self.data.df)
        
    def next(self):
        # Check if a new OB was confirmed YESTERDAY (at the close of previous candle)
        # self.buy_limits is an array aligned with data.
        # self.buy_limits[-1] is the value for the *current* candle (which just closed? No, Backtesting next runs on new bar).
        # Actually usually [-1] is the just-closed bar value.
        
        signal = self.buy_limits[-1]
        sl_price = self.stop_losses[-1]
        
        if not np.isnan(signal):
            # Found a new setup!
            # Current price is likely away from OB (since it formed an FVG gap up).
            # We place a LIMIT order waiting for pullback.
            
            entry_price = signal
            risk = entry_price - sl_price
            
            if risk <= 0:
                return # Invalid OB (High < Low?)
                
            tp_price = entry_price + (risk * self.risk_reward)
            
            # Place Order
            # Valid for 10 days?
            self.buy(limit=entry_price, sl=sl_price, tp=tp_price)
            
            # Note: Backtesting.py manages active orders.
