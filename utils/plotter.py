import mplfinance as mpf
import pandas as pd
import os

def plot_ticker_smc(ticker, df):
    """
    Plots the candlestick chart with SMC annotations.
    """
    # Ensure index is Datetime
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
        
    # Filter last 100 candles for clarity
    plot_df = df.tail(100)
    
    # Create AddPlots
    apds = []
    
    # Highlight Bullish OBs (Green Markers)
    # We can use a scatter plot.
    # Where bullish_ob is True, plot a marker at Low?
    if 'bullish_ob' in plot_df.columns and plot_df['bullish_ob'].any():
        bull_ob_mask = plot_df['bullish_ob']
        # Set values
        bull_ob_points = plot_df['Low'].copy()
        bull_ob_points[~bull_ob_mask] = float('nan')
        
        apds.append(mpf.make_addplot(bull_ob_points, type='scatter', markersize=100, marker='^', color='green', label='Bull OB'))

    # FVG
    # Maybe shade the FVG area? Or just marker.
    # Let's use scatter for now for Bullish FVG
    if 'bullish_fvg' in plot_df.columns and plot_df['bullish_fvg'].any():
        bull_fvg_mask = plot_df['bullish_fvg']
        bull_fvg_points = plot_df['Low'].copy()
        bull_fvg_points[~bull_fvg_mask] = float('nan')
        # Offset slightly
        bull_fvg_points = bull_fvg_points * 0.99 
        
        apds.append(mpf.make_addplot(bull_fvg_points, type='scatter', markersize=50, marker='o', color='blue', label='Bull FVG'))

    # Plot
    # Style
    style = mpf.make_mpf_style(base_mpf_style='yahoo', rc={'font.size': 10})
    
    filename = f"charts/{ticker}_smc.png"
    os.makedirs("charts", exist_ok=True)
    
    print(f"Generating chart for {ticker}...")
    mpf.plot(
        plot_df,
        type='candle',
        style=style,
        title=f"{ticker} - SMC Analysis",
        addplot=apds if apds else None,
        volume=True,
        savefig=filename
    )
    print(f"Saved chart to {filename}")
