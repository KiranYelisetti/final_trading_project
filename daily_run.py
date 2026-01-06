import argparse
from app.database import get_db, init_db, Stock, DailyPrice, Trade
from app.fetcher import update_market_data
from app.smc_agent import analyze_ticker
from datetime import date
import pandas as pd
import os
import requests
from nsepython import nse_eq

# Telegram Settings
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def get_live_price(ticker):
    """
    Fetches Day High, Day Low, and Current Price from NSE directly.
    Returns: (day_low, day_high, current_price) or (None, None, None)
    """
    try:
        data = nse_eq(ticker)
        if 'priceInfo' in data:
            curr = data['priceInfo']['lastPrice']
            d_high = data['priceInfo']['intraDayHighLow']['max']
            d_low = data['priceInfo']['intraDayHighLow']['min']
            print(f"[{ticker}] Live NSE Data: Price={curr}, High={d_high}, Low={d_low}")
            return d_low, d_high, curr
    except Exception as e:
        print(f"Failed to fetch NSE data for {ticker}: {e}")
    return None, None, None

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

def run_intraday_cycle():
    print("Starting INTRADAY Cycle (Real-time Scan)...")
    init_db()
    db = next(get_db())
    today = date.today()
    
    # Intraday does NOT run full update_market_data to save time/bandwidth
    # It relies on existing DB + Live Price
    stocks = db.query(Stock).all()
    tickers = [s.ticker for s in stocks]
    
    # 1. Manage Active Trades (Fills/Exits)
    # Check "PENDING" for Entry
    # Check "OPEN" for SL/TP
    active_trades = db.query(Trade).filter(Trade.status.in_(["PENDING", "OPEN"])).all()
    
    for trade in active_trades:
        nse_low, nse_high, nse_curr = get_live_price(trade.ticker)
        if not nse_curr: continue
        
        if trade.status == "PENDING":
            # Check Entry: If Price drops below Entry Limit
            # Note: We use 'Low' to see if price *touched* the limit
            if nse_low <= trade.entry_price:
                trade.status = "OPEN"
                trade.entry_date = today
                msg = f"✅ **ENTRY FILLED**: {trade.ticker}\nPrice: {trade.entry_price}\nSL: {trade.sl_price}\nTP: {trade.tp_price}"
                send_alert(msg)
                
        elif trade.status == "OPEN":
            # Check SL (Price drops below SL)
            if nse_low <= trade.sl_price:
                trade.status = "CLOSED"
                trade.outcome = "LOSS"
                trade.exit_price = trade.sl_price
                trade.exit_date = today
                trade.pnl = trade.exit_price - trade.entry_price
                msg = f"🛑 **STOP LOSS HIT**: {trade.ticker}\nExit: {trade.exit_price}\nPnL: {trade.pnl:.2f}"
                send_alert(msg)
                
            # Check TP (Price rises above TP)
            elif nse_high >= trade.tp_price:
                trade.status = "CLOSED"
                trade.outcome = "WIN"
                trade.exit_price = trade.tp_price
                trade.exit_date = today
                trade.pnl = trade.exit_price - trade.entry_price
                msg = f"💰 **TARGET HIT**: {trade.ticker}\nExit: {trade.exit_price}\nPnL: {trade.pnl:.2f}"
                send_alert(msg)
    
    db.commit()
    
    # 2. Scan for NEW Signals (Intraday)
    # Strategy: Pure FVG (Technically based on Daily Candle Close, but we scan for potential formation)
    print("Scanning for fresh signals...")
    for ticker in tickers:
        try:
            # We need history to find FVG setup (High[i-2])
            query = db.query(DailyPrice).filter(DailyPrice.ticker == ticker).order_by(DailyPrice.date.asc())
            df = pd.read_sql(query.statement, db.bind)
            if df.empty: continue
            
            # Prepare Data
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume', 'ema_200': 'EMA_200'})
            
            # Fetch Live Data to form "Provisional Daily Candle"
            nse_low, nse_high, nse_curr = get_live_price(ticker)
            if not nse_curr: continue
            
            # Create a provisional row for "Today"
            live_idx = pd.Timestamp(today)
            live_row = pd.DataFrame([{
                'Open': nse_curr, # Approx
                'High': nse_high,
                'Low': nse_low,
                'Close': nse_curr, # Current Price acting as Close
                'Volume': 0 # Not used for FVG logic
            }], index=[live_idx])
            
            # If today is already in df (partially updated DB), drop it to use live data
            if live_idx in df.index:
                df = df.drop(live_idx)
            
            # Append live row
            df_combined = pd.concat([df, live_row])
            
            # Analyze
            _, s_df = analyze_ticker(ticker, df_combined)
            latest = s_df.iloc[-1]
            
            # Pure FVG Logic
            if latest['bullish_fvg']: # If currently forming a Bullish FVG
                # Check duplication
                existing = db.query(Trade).filter(Trade.ticker == ticker, Trade.status.in_(["PENDING", "OPEN"])).first()
                if not existing:
                    entry = latest['Low'] # Top of Gap (Current Low)
                    
                    # Risk Management
                    if len(s_df) >= 3:
                        sl = s_df['Low'].iloc[-3] # i-2 Low
                    else:
                        sl = entry * 0.95
                        
                    risk = entry - sl
                    if risk > 0:
                        tp = entry + (2 * risk)
                        
                        new_trade = Trade(
                            ticker=ticker,
                            signal_date=today,
                            entry_price=entry,
                            sl_price=sl,
                            tp_price=tp,
                            status="PENDING"
                        )
                        db.add(new_trade)
                        db.commit() # Commit immediately for Intraday to avoid duplicates in next 5 min run
                        
                        msg = f"🚀 **NEW SIGNAL**: {ticker}\nEntry: {entry:.2f}\nSL: {sl:.2f}\nTP: {tp:.2f}"
                        send_alert(msg)
                        
        except Exception as e:
            print(f"Error scanning {ticker}: {e}")
            
    db.close()
    print("Intraday Cycle Complete.")

def run_eod_report():
    print("Generating EOD Report...")
    init_db()
    db = next(get_db())
    today = date.today()
    
    # 1. Update Market Data (Ensure we have final EOD data for history)
    stocks = db.query(Stock).all()
    tickers = [s.ticker for s in stocks]
    print(f"Updating EOD data for {len(tickers)} stocks...")
    # Update logic here or rely on Intraday to have captured moves?
    # Better to run proper update for history accuracy
    update_market_data(db, tickers)
    
    # 2. Compile Report from DB
    fills = db.query(Trade).filter(Trade.entry_date == today).all()
    exits = db.query(Trade).filter(Trade.exit_date == today).all()
    signals = db.query(Trade).filter(Trade.signal_date == today).all()
    
    msg = f"🔔 **EOD Summary ({today})**\n"
    
    events = False
    
    wins = [t for t in exits if t.outcome == "WIN"]
    losses = [t for t in exits if t.outcome == "LOSS"]
    
    if wins:
        msg += "\n🎉 **Wins Today:**\n"
        for t in wins: 
            pnl_pct = (t.pnl / t.entry_price) * 100
            msg += f"{t.ticker}: {t.pnl:.2f} ({pnl_pct:.2f}%)\n"
        events = True
        
    if losses:
        msg += "\n💀 **Losses Today:**\n"
        for t in losses: 
            pnl_pct = (t.pnl / t.entry_price) * 100
            msg += f"{t.ticker}: {t.pnl:.2f} ({pnl_pct:.2f}%)\n"
        events = True
        
    if fills:
        msg += "\n✅ **Entries Filled:**\n"
        for t in fills: 
            msg += f"{t.ticker} @ {t.entry_price} (SL: {t.sl_price}, TP: {t.tp_price})\n"
        events = True
        
    if signals:
        msg += "\n🎯 **New Signals:**\n"
        for t in signals: 
            msg += f"{t.ticker} Buy: {t.entry_price:.2f} | SL: {t.sl_price:.2f} | TP: {t.tp_price:.2f}\n"
        events = True
        
    if events:
        send_alert(msg)
    else:
        print("No events to report for EOD.")
        
    db.close()
    print("EOD Cycle Complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["intraday", "eod"], default="intraday", help="Operational mode")
    args = parser.parse_args()
    
    if args.mode == "intraday":
        run_intraday_cycle()
    elif args.mode == "eod":
        run_eod_report()
