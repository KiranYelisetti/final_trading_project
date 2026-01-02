from backtesting import Strategy
from app.smc_agent import analyze_ticker
import pandas as pd
import numpy as np

# --- helper to get signals ---
def get_trend_ob_signals(df):
    """
    Returns Buy Signals for Trend Continuation (OB + EMA200).
    """
    # Clean DF
    df_clean = df.copy()
    if 'Close' not in df_clean.columns: 
        df_clean.columns = [c.capitalize() for c in df_clean.columns]
        
    _, annotated_df = analyze_ticker("DUMMY", df_clean)
    
    # Calculate EMA 200 locally if not present (Backtesting usually calculates indicators inside Strategy, but we need it for pre-calc signal)
    # Actually, we have EMA_200 in our DB! DailyPrice has ema_200. 
    # But analyze_ticker might not preserve it or we pass a fresh DF?
    # Let's verify if 'ema_200' is in df. db query returns 'ema_200'.
    # If not, calc it.
    
    if 'ema_200' not in annotated_df.columns and 'EMA_200' not in annotated_df.columns:
        annotated_df['EMA_200'] = annotated_df['Close'].ewm(span=200).mean() # Approx or use pandas_ta
    
    ema_col = 'EMA_200' if 'EMA_200' in annotated_df.columns else 'ema_200'
    
    buy_signals = np.full(len(df), np.nan)
    sl_signals = np.full(len(df), np.nan)
    
    # Logic: 
    # 1. New Bullish OB confirmed (at i, meaning OB is at i-2).
    # 2. Trend is UP at i (Close[i] > EMA[i]).
    
    bull_fvg_mask = annotated_df['bullish_fvg'].values
    closes = annotated_df['Close'].values
    emas = annotated_df[ema_col].values
    highs = annotated_df['High'].values
    lows = annotated_df['Low'].values
    
    # Shifted for OB location (i-2)
    highs_shifted_2 = pd.Series(highs).shift(2).values
    lows_shifted_2 = pd.Series(lows).shift(2).values
    
    for i in range(len(df)):
        if bull_fvg_mask[i]:
            # OB Confirmed. Check Trend.
            if closes[i] > emas[i]:
                # Trend OK. Signal Entry at OB High.
                buy_signals[i] = highs_shifted_2[i]
                sl_signals[i] = lows_shifted_2[i]
                
    return buy_signals, sl_signals

def get_fvg_signals(df):
    """
    Returns Buy Signals for Pure FVG Reversion.
    Entry: Top of the FVG (which is Low of Candle i, no wait? No, FVG is between i-2 and i).
    Bullish FVG: Low[i] > High[i-2]. The Gap is (High[i-2], Low[i]).
    We want to buy when price dips back into this gap.
    Entry Limit: Low[i] (Top of the gap). 
    Stop: High[i-2] (Bottom of the gap) - Wait, if gap fills completely, trade fails? 
    Or Stop below Candle i-2? Let's use Candle i-2 Low for safer stop.
    """
    df_clean = df.copy()
    if 'Close' not in df_clean.columns: 
        df_clean.columns = [c.capitalize() for c in df_clean.columns]
    _, annotated_df = analyze_ticker("DUMMY", df_clean)
    
    buy_signals = np.full(len(df), np.nan)
    sl_signals = np.full(len(df), np.nan)
    
    bull_fvg_mask = annotated_df['bullish_fvg'].values
    lows = annotated_df['Low'].values
    lows_shifted_2 = pd.Series(lows).shift(2).values # Low of i-2
    
    for i in range(len(df)):
        if bull_fvg_mask[i]:
            # FVG Identified. Gap is from High[i-2] to Low[i].
            # We place Limit Buy at Low[i] (Top of Gap).
            buy_signals[i] = lows[i]
            # Stop Loss below the setup candle (i-2)
            sl_signals[i] = lows_shifted_2[i]
            
    return buy_signals, sl_signals


class TrendSMCStrategy(Strategy):
    risk_reward = 2.0
    
    def init(self):
        self.buy_limits, self.stop_losses = self.I(get_trend_ob_signals, self.data.df)
        
    def next(self):
        signal = self.buy_limits[-1]
        sl_price = self.stop_losses[-1]
        
        if not np.isnan(signal):
            entry_price = signal
            risk = entry_price - sl_price
            if risk > 0:
                self.buy(limit=entry_price, sl=sl_price, tp=entry_price + (risk * self.risk_reward))

class PureFVGStrategy(Strategy):
    risk_reward = 1.5 # Lower RR for quick gap plays?
    
    def init(self):
        self.buy_limits, self.stop_losses = self.I(get_fvg_signals, self.data.df)
        
    def next(self):
        signal = self.buy_limits[-1]
        sl_price = self.stop_losses[-1]
        
        if not np.isnan(signal):
            entry_price = signal
            risk = entry_price - sl_price
            if risk > 0:
                self.buy(limit=entry_price, sl=sl_price, tp=entry_price + (risk * self.risk_reward))
