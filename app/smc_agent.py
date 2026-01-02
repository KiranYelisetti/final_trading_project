import pandas as pd
import numpy as np

def identify_swings(df, swing_length=5):
    """
    Identify Swing Highs and Swing Lows.
    Returns df with 'swing_high' and 'swing_low' columns (boolean).
    """
    df = df.copy()
    df['swing_high'] = False
    df['swing_low'] = False
    
    for i in range(swing_length, len(df) - swing_length):
        # Swing High
        if df['High'].iloc[i] == df['High'].iloc[i-swing_length:i+swing_length+1].max():
            df.at[df.index[i], 'swing_high'] = True
            
        # Swing Low
        if df['Low'].iloc[i] == df['Low'].iloc[i-swing_length:i+swing_length+1].min():
            df.at[df.index[i], 'swing_low'] = True
            
    return df

def identify_fvg(df):
    """
    Identify Fair Value Gaps.
    Bullish FVG: Low[0] > High[2]
    Bearish FVG: High[0] < Low[2]
    """
    df['bullish_fvg'] = False
    df['bearish_fvg'] = False
    df['fvg_top'] = np.nan
    df['fvg_bottom'] = np.nan
    
    # Vectorized check
    # Bullish FVG
    # Condition: Current Low > 2 days ago High
    # Usually FVG is identified at the close of the 3rd candle involved (candle index i).
    # Candles: i-2, i-1, i. Gap is between i-2 and i.
    # Logic: Low[i] > High[i-2]
    
    lows = df['Low']
    highs = df['High']
    
    # Shifted arrays for comparison
    # i is current, i-2 is 2 periods ago
    prev_high_2 = highs.shift(2)
    prev_low_2 = lows.shift(2)
    
    # Bullish FVG (Gap Up between High[i-2] and Low[i])
    bull_cond = lows > prev_high_2
    
    # Bearish FVG (Gap Down between Low[i-2] and High[i])
    bear_cond = highs < prev_low_2
    
    df.loc[bull_cond, 'bullish_fvg'] = True
    df.loc[bull_cond, 'fvg_top'] = lows # The bottom of the top candle
    df.loc[bull_cond, 'fvg_bottom'] = prev_high_2 # The top of the bottom candle
    
    df.loc[bear_cond, 'bearish_fvg'] = True
    df.loc[bear_cond, 'fvg_top'] = prev_low_2
    df.loc[bear_cond, 'fvg_bottom'] = highs

    return df

def identify_ob(df, swings):
    """
    Simple Order Block detection.
    Bullish OB: The last bearish candle before a break of structure (Swing High break).
    For simplicity: The last down candle before a significant move up that created a FVG or broke a high.
    We will use a simplified logic: 
    Bullish OB = Down candle (Close < Open) followed by a Bullish FVG.
    Bearish OB = Up candle (Close > Open) followed by a Bearish FVG.
    """
    df['bullish_ob'] = False
    df['bearish_ob'] = False
    
    # Need FVG data first
    if 'bullish_fvg' not in df.columns:
        df = identify_fvg(df)
        
    for i in range(2, len(df)):
        # If we have a Bullish FVG at i, then the candle at i-2 or i-1 responsible for the move might be the OB.
        # Ideally, OB is the candle BEFORE the explosive move.
        # If Candle i completes an FVG, the move started at i-1. The OB is likely i-2.
        
        if df['bullish_fvg'].iloc[i]:
            # Check candle i-2. Is it bearish?
            if df['Close'].iloc[i-2] < df['Open'].iloc[i-2]:
                df.at[df.index[i-2], 'bullish_ob'] = True
                
        if df['bearish_fvg'].iloc[i]:
             # Check candle i-2. Is it bullish?
            if df['Close'].iloc[i-2] > df['Open'].iloc[i-2]:
                df.at[df.index[i-2], 'bearish_ob'] = True
                
    return df

def analyze_ticker(ticker, df):
    """
    Main entry point for SMC analysis.
    """
    if df.empty:
        return None, df, None, None, None # Match signature roughly

    # Ensure Columns Title Case
    df = df.rename(columns={
        'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'
    })
    
    # 1. Swings
    df = identify_swings(df)
    
    # 2. FVG
    df = identify_fvg(df)
    
    # 3. OB
    df = identify_ob(df, None)
    
    # Prepare Result Summary
    latest_close = df['Close'].iloc[-1]
    
    # Check for active patterns near price?
    # For now just return the annotated dataframe
    
    results = {
        'ticker': ticker,
        'latest_close': latest_close,
        'last_bull_ob': df[df['bullish_ob']].index[-1] if df['bullish_ob'].any() else None,
        'last_bear_ob': df[df['bearish_ob']].index[-1] if df['bearish_ob'].any() else None,
        'last_bull_fvg': df[df['bullish_fvg']].index[-1] if df['bullish_fvg'].any() else None
    }
    
    return results, df
