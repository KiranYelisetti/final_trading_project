import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import sys
import os

# Add project root to path so 'app.database' is found
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import get_db, DailyPrice, Stock
from app.smc_agent import analyze_ticker
import numpy as np

# Page Config
st.set_page_config(page_title="Sniper Trading Dashboard", layout="wide", page_icon="🎯")

# --- DATA LOADING ---
@st.cache_data
def load_tracked_stocks():
    db = next(get_db())
    stocks = db.query(Stock).all()
    # Convert to list of dicts
    data = []
    for s in stocks:
        data.append({
            'Ticker': s.ticker,
            'Sector': s.sector,
            'PE': s.current_pe,
            'PEG': s.peg_ratio,
            'Growth%': s.quarterly_earnings_growth * 100 if s.quarterly_earnings_growth else None
        })
    db.close()
    return pd.DataFrame(data)

def load_price_data(ticker):
    db = next(get_db())
    query = db.query(DailyPrice).filter(DailyPrice.ticker == ticker).order_by(DailyPrice.date.asc())
    df = pd.read_sql(query.statement, db.bind)
    db.close()
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        # Rename for consistency
        df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume', 'ema_200': 'EMA_200'})
    return df

# --- UI COMPONENTS ---
st.title("🎯 Techno-Fundamental Sniper | Indian Markets")

# Sidebar
st.sidebar.header("Stock Selection")
input_file = load_tracked_stocks()
selected_ticker = st.sidebar.selectbox("Select Ticker", input_file['Ticker'].unique())

# --- MAIN ANALYSIS ---
if selected_ticker:
    df = load_price_data(selected_ticker)
    
    if df.empty:
        st.error("No data found for this ticker.")
    else:
        # Run SMC Analysis
        results, smc_df = analyze_ticker(selected_ticker, df)
        
        # Latest Values
        latest = smc_df.iloc[-1]
        close_price = latest['Close']
        ema_200 = latest['EMA_200'] if 'EMA_200' in latest else list(smc_df['Close'].ewm(span=200).mean())[-1]
        
        # Trend Check
        trend = "BULLISH 🟢" if close_price > ema_200 else "BEARISH 🔴"
        
        # Fundamental Check
        # Get fundy data from input_file
        fund_data = input_file[input_file['Ticker'] == selected_ticker].iloc[0]
        
        # --- TOP METRICS ---
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Current Price", f"₹{close_price:.2f}")
        col2.metric("Trend (200 EMA)", trend, delta=f"Above EMA by {close_price - ema_200:.1f}" if close_price > ema_200 else f"{close_price - ema_200:.1f}")
        col3.metric("PE Ratio", f"{fund_data['PE']:.1f}" if fund_data['PE'] else "N/A")
        col4.metric("PEG Ratio", f"{fund_data['PEG']:.2f}" if fund_data['PEG'] else "N/A") # using stored peg, might be None
        
        # --- SMC ALERTS ---
        st.subheader("Technical Analysis (SMC)")
        
        # Check for Active OB/FVG
        # Latest 5 candles for "Fresh" alerts
        recent = smc_df.tail(5)
        
        if recent['bullish_fvg'].any():
            last_fvg_date = recent[recent['bullish_fvg']].index[-1]
            st.warning(f"🔔 Bullish Fair Value Gap detected on {last_fvg_date.date()}!")
        
        if recent['bullish_ob'].any():
            last_ob_date = recent[recent['bullish_ob']].index[-1]
            st.success(f"🚀 Bullish Order Block confirmed on {last_ob_date.date()}! (Potential Entry)")
            
        # --- CHART ---
        st.subheader("Price Chart with Order Blocks")
        
        # Filter for plotting (last 200 days)
        plot_df = smc_df.tail(200)
        
        fig = go.Figure()
        
        # Candlestick
        fig.add_trace(go.Candlestick(
            x=plot_df.index,
            open=plot_df['Open'],
            high=plot_df['High'],
            low=plot_df['Low'],
            close=plot_df['Close'],
            name='Price'
        ))
        
        # EMA
        # Calc EMA
        plot_df['EMA_200_Plot'] = plot_df['Close'].ewm(span=200).mean()
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['EMA_200_Plot'], mode='lines', name='200 EMA', line=dict(color='orange')))
        
        # SMC Annotations (Markers)
        # Bullish OB
        bull_obs = plot_df[plot_df['bullish_ob']]
        if not bull_obs.empty:
            fig.add_trace(go.Scatter(
                x=bull_obs.index, 
                y=bull_obs['Low'], 
                mode='markers', 
                marker=dict(symbol='triangle-up', size=12, color='green'),
                name='Bullish OB'
            ))
            
        # Bullish FVG
        bull_fvgs = plot_df[plot_df['bullish_fvg']]
        if not bull_fvgs.empty:
            fig.add_trace(go.Scatter(
                x=bull_fvgs.index,
                y=bull_fvgs['Low'],
                mode='markers',
                marker=dict(symbol='circle', size=8, color='blue'),
                name='Bullish FVG'
            ))
            
        fig.update_layout(height=600, xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)

# --- WATCHLIST SCAN ---
st.header("🔍 Market Scanner")
st.write("Checking all tracked stocks for **Trend + OB** signals today...")

if st.button("Run Scanner"):
    alerts = []
    progress = st.progress(0)
    total = len(input_file)
    
    for i, row in input_file.iterrows():
        t = row['Ticker']
        d = load_price_data(t)
        if d.empty: continue
        
        # Fast Analyze
        # Only need last few rows? No, analyze_ticker needs context.
        # But we can limit history passed if it helps speed. 
        # analyze_ticker is fast enough for 5 years data on 10 stocks.
        _, s_df = analyze_ticker(t, d)
        
        # Logic: 
        # 1. Trend UP (Latest Close > EMA200)
        # 2. Bullish OB within last 3 days?
        
        curr = s_df.iloc[-1]
        ema = s_df['Close'].ewm(span=200).mean().iloc[-1]
        
        if curr['Close'] > ema:
            # Check for OB in last 3 days
            recent_3 = s_df.tail(3)
            if recent_3['bullish_ob'].any():
                alerts.append({
                    'Ticker': t,
                    'Signal': 'BULLISH OB 🚀',
                    'Price': curr['Close'],
                    'Date': recent_3[recent_3['bullish_ob']].index[-1].date()
                })
        
        progress.progress((i + 1) / total)
        
    if alerts:
        st.success(f"Found {len(alerts)} High Confidence Setups!")
        st.table(pd.DataFrame(alerts))
    else:
        st.info("No 'Trend + OB' signals found today.")
