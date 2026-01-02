from app.database import get_db, init_db, Stock, DailyPrice, Trade
from app.fetcher import update_market_data
from app.smc_agent import analyze_ticker
from datetime import date
import pandas as pd
import os

import requests

# Telegram Settings
# User provided Token. Chat ID must be set in Environment or Config.
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_alert(message):
    print(f"ALERT: {message}")
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            data = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
            requests.post(url, data=data)
        except Exception as e:
            print(f"Failed to send Telegram alert: {e}")
    else:
        print("Telegram Chat ID not found. Set TELEGRAM_CHAT_ID env var.")

def run_daily_cycle():
    print("Starting Daily Cycle...")
    init_db()
    db = next(get_db())
    
    # 1. Update Data
    stocks = db.query(Stock).all()
    tickers = [s.ticker for s in stocks]
    print(f"Updating data for {len(tickers)} stocks...")
    update_market_data(db, tickers)
    
    # 2. Manage Existing Trades
    active_trades = db.query(Trade).filter(Trade.status.in_(["PENDING", "OPEN"])).all()
    
    for trade in active_trades:
        # Get latest price
        price_rec = db.query(DailyPrice).filter(DailyPrice.ticker == trade.ticker).order_by(DailyPrice.date.desc()).first()
        if not price_rec: continue
        
        curr_low = price_rec.low
        curr_high = price_rec.high
        curr_date = price_rec.date
        
        if trade.status == "PENDING":
            # Check for Entry (Limit Buy)
            # If price dipped below Entry, we got filled
            if curr_low <= trade.entry_price:
                trade.status = "OPEN"
                trade.entry_date = curr_date
                alert = f"✅ ENTRY FILLED: {trade.ticker} @ {trade.entry_price}"
                send_alert(alert)
                
        elif trade.status == "OPEN":
            # Check SL
            if curr_low <= trade.sl_price:
                trade.status = "CLOSED"
                trade.outcome = "LOSS"
                trade.exit_price = trade.sl_price
                trade.exit_date = curr_date
                trade.pnl = trade.exit_price - trade.entry_price
                alert = f"🛑 STOP LOSS HIT: {trade.ticker} @ {trade.exit_price}"
                send_alert(alert)
                
            # Check TP
            elif curr_high >= trade.tp_price:
                trade.status = "CLOSED"
                trade.outcome = "WIN"
                trade.exit_price = trade.tp_price
                trade.exit_date = curr_date
                trade.pnl = trade.exit_price - trade.entry_price
                alert = f"💰 TARGET HIT: {trade.ticker} @ {trade.exit_price}"
                send_alert(alert)
    
    db.commit()
    
    # 3. Scan for New Signals
    print("Scanning for new signals...")
    for ticker in tickers:
        # Load Data
        query = db.query(DailyPrice).filter(DailyPrice.ticker == ticker).order_by(DailyPrice.date.asc())
        df = pd.read_sql(query.statement, db.bind)
        if df.empty: continue
        
        # Analyze
        df['date'] = pd.to_datetime(df['date'])
        
        # Remove duplicates if any (keep last)
        df = df.drop_duplicates(subset=['date'], keep='last')
        
        df.set_index('date', inplace=True)
        df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume', 'ema_200': 'EMA_200'})
        
        _, s_df = analyze_ticker(ticker, df)
        
        # Logic: Trend + OB
        latest = s_df.iloc[-1]
        ema = latest['EMA_200'] if 'EMA_200' in latest else s_df['Close'].ewm(span=200).mean().iloc[-1]
        
        if latest['Close'] > ema:
            # Check last 3 days for OB
            recent = s_df.tail(3)
            if recent['bullish_ob'].any():
                # Found Signal
                # Check if we already have a PENDING/OPEN trade for this ticker to avoid dupes
                existing = db.query(Trade).filter(Trade.ticker == ticker, Trade.status.in_(["PENDING", "OPEN"])).first()
                if not existing:
                    # Create Trade
                    # Entry: High of OB Candle.
                    # Which candle was OB? The one marked True.
                    ob_idx = recent[recent['bullish_ob']].index[-1]
                    ob_row = recent.loc[ob_idx]
                    
                    entry = ob_row['High']
                    sl = ob_row['Low']
                    risk = entry - sl
                    tp = entry + (2 * risk)
                    
                    new_trade = Trade(
                        ticker=ticker,
                        signal_date=date.today(),
                        entry_price=entry,
                        sl_price=sl,
                        tp_price=tp,
                        status="PENDING"
                    )
                    db.add(new_trade)
                    alert = f"🚀 NEW SIGNAL: {ticker} | Buy Limit: {entry} | SL: {sl} | TP: {tp}"
                    send_alert(alert)
    
    db.commit()
    db.close()
    print("Daily Cycle Complete.")

if __name__ == "__main__":
    run_daily_cycle()
