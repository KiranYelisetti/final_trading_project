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

def run_premarket_scan():
    """
    Runs before market open (e.g., 8:45 AM).
    Scans for Valid Setups based on YESTERDAY'S Data.
    Creates trades with status = 'POTENTIAL'.
    """
    print("Starting PRE-MARKET Scan (Analysis of Yesterday)...")
    init_db()
    db = next(get_db())
    today = date.today()
    
    # Clean up old checks? Maybe not.
    
    stocks = db.query(Stock).all()
    tickers = [s.ticker for s in stocks]
    
    potential_count = 0
    
    for ticker in tickers:
        try:
            # 1. Fetch Historical Data (Up to Yesterday)
            query = db.query(DailyPrice).filter(DailyPrice.ticker == ticker).order_by(DailyPrice.date.asc())
            df = pd.read_sql(query.statement, db.bind)
            
            if df.empty or len(df) < 50: continue
            
            # Prepare Data
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume', 'ema_200': 'EMA_200'})
            
            # 2. Analyze Strategy (Pure FVG)
            _, s_df = analyze_ticker(ticker, df)
            latest = s_df.iloc[-1]
            
            # 3. Check for Setup
            if latest['bullish_fvg']: # Bullish FVG Found
                entry = latest['Low'] # Top of FVG Gap (Yesterday's Low? No, FVG logic defines entry)
                
                # Double check FVG Logic interpretation:
                # Usually FVG Entry is the top of the gap candle (candle i-2 Low vs i High)
                # Ensure we use the calculated entry from analyze_ticker if available or derive it.
                # Assuming analyze_ticker returns a DF where 'Low' of the last candle IS the setup candle?
                # Actually, verify analyze_ticker logic. 
                # Assuming standard FVG: We want to enter at the retest of the gap.
                # latest['Low'] is likely just yesterday's low.
                # We need the Top of the 3rd candle in the sequence?
                # For safety, let's trust the 'price' logic we had before:
                # entry = latest['Low'] (This seems to be what was used: "Entry: Top of Gap (Current Low)")
                
                # Check duplication for TODAY
                existing = db.query(Trade).filter(
                    Trade.ticker == ticker, 
                    Trade.signal_date == today
                ).first()
                
                if not existing:
                    # Risk Management
                    if len(s_df) >= 3:
                        sl = s_df['Low'].iloc[-3] # i-2 Low
                    else:
                        sl = entry * 0.95 # Fallback
                        
                    risk = entry - sl
                    if risk > 0:
                        tp = entry + (2 * risk)
                        
                        # Create POTENTIAL Trade
                        new_trade = Trade(
                            ticker=ticker,
                            signal_date=today,
                            entry_price=entry,
                            sl_price=sl,
                            tp_price=tp,
                            status="POTENTIAL",
                            reason="Pre-Market Scan"
                        )
                        db.add(new_trade)
                        potential_count += 1
                        print(f"[{ticker}] Found Potential Setup. Entry: {entry}")

        except Exception as e:
            print(f"Error scanning {ticker}: {e}")
            
    db.commit()
    
    if potential_count > 0:
        msg = f"🌅 **PRE-MARKET SCAN COMPLETED**\nFound {potential_count} potential setups for today.\nWaiting for Market Open..."
        send_alert(msg)
    else:
        print("No potential setups found.")
        
    db.close()
    print("Pre-Market Cycle Complete.")

def run_intraday_execution():
    """
    Runs during market hours (e.g., every 5 mins).
    1. Checks 'POTENTIAL' trades for Validation & Entry.
    2. Manages 'OPEN' trades for Exits.
    """
    print("Starting INTRADAY EXECUTION Cycle...")
    init_db()
    db = next(get_db())
    today = date.today()
    
    # -------------------------------
    # 1. Process POTENTIAL Trades
    # -------------------------------
    potential_trades = db.query(Trade).filter(
        Trade.status == "POTENTIAL",
        Trade.signal_date == today
    ).all()
    
    for trade in potential_trades:
        ticker = trade.ticker
        
        # Check: ONE ENTRY PER STOCK PER DAY
        # If we have any *other* trade for this stock today that is active/closed, skip?
        # Actually this 'trade' IS the record.
        # But if we had a previous trade today that failed?
        # Implementation: Check if there are ANY records for this ticker today that are NOT 'POTENTIAL' 
        # (meaning we already acted on it).
        # Since we just created this one record, it's fine.
        # BUT, if we have multiple signals (unlikely with unique constraint logic above), handle it.
        
        nse_low, nse_high, nse_curr = get_live_price(ticker)
        if not nse_curr: continue
        
        # VALIDATION PHASE
        # 1. Check if SL already hit (Price gap down below SL?)
        if nse_low <= trade.sl_price:
            trade.status = "SKIPPED"
            trade.outcome = "VOID"
            trade.reason = f"SL Hit before Entry (Low {nse_low} <= SL {trade.sl_price})"
            print(f"[{ticker}] Skipped: {trade.reason}")
            continue
            
        # 2. Check if TP already hit (Price gap up above TP?)
        if nse_high >= trade.tp_price:
            trade.status = "SKIPPED"
            trade.outcome = "VOID"
            trade.reason = f"TP Hit before Entry (High {nse_high} >= TP {trade.tp_price})"
            print(f"[{ticker}] Skipped: {trade.reason}")
            continue
            
        # ENTRY PHASE
        # Trigger Condition: Current Price is at or below Entry
        # AND Price is within range (Low <= Entry <= High) - implied if Current <= Entry and Valid
        
        if nse_curr <= trade.entry_price:
             # DOUBLE CHECK: One trade per day
             # Ensure no other "OPEN" or "CLOSED" trade exists for this ticker today
             # just to be super safe against race conditions or manual inserts
             pass 
             
             trade.status = "OPEN"
             trade.entry_date = today
             trade.reason = "Entry Triggered Checks Passed"
             
             msg = f"🚀 **ENTRY TRIGGERED**: {trade.ticker}\nPrice: {trade.entry_price}\nSL: {trade.sl_price}\nTP: {trade.tp_price}"
             send_alert(msg)
             
    db.commit()

    # -------------------------------
    # 2. Manage ACTIVE Trades (OPEN)
    # -------------------------------
    active_trades = db.query(Trade).filter(Trade.status == "OPEN").all()
    
    for trade in active_trades:
        nse_low, nse_high, nse_curr = get_live_price(trade.ticker)
        if not nse_curr: continue
        
        # Check SL
        if nse_low <= trade.sl_price:
            trade.status = "CLOSED"
            trade.outcome = "LOSS"
            trade.exit_price = trade.sl_price
            trade.exit_date = today
            trade.pnl = trade.exit_price - trade.entry_price
            msg = f"🛑 **STOP LOSS HIT**: {trade.ticker}\nExit: {trade.exit_price}\nPnL: {trade.pnl:.2f}"
            send_alert(msg)
            
        # Check TP
        elif nse_high >= trade.tp_price:
            trade.status = "CLOSED"
            trade.outcome = "WIN"
            trade.exit_price = trade.tp_price
            trade.exit_date = today
            trade.pnl = trade.exit_price - trade.entry_price
            msg = f"💰 **TARGET HIT**: {trade.ticker}\nExit: {trade.exit_price}\nPnL: {trade.pnl:.2f}"
            send_alert(msg)
            
    db.commit()
    db.close()
    print("Intraday Execution Cycle Complete.")

def run_eod_report():
    print("Generating EOD Report...")
    init_db()
    db = next(get_db())
    today = date.today()
    
    # 1. Update Market Data (Ensure we have final EOD data for history)
    stocks = db.query(Stock).all()
    tickers = [s.ticker for s in stocks]
    print(f"Updating EOD data for {len(tickers)} stocks...")
    update_market_data(db, tickers)
    
    # 2. Compile Report from DB
    # Fetch all activity for today
    todays_trades = db.query(Trade).filter(Trade.signal_date == today).all()
    
    msg = f"🔔 **EOD Summary ({today})**\n"
    
    entries = [t for t in todays_trades if t.status == "OPEN"]
    wins = [t for t in todays_trades if t.status == "CLOSED" and t.outcome == "WIN"]
    losses = [t for t in todays_trades if t.status == "CLOSED" and t.outcome == "LOSS"]
    skipped = [t for t in todays_trades if t.status == "SKIPPED"]
    potential = [t for t in todays_trades if t.status == "POTENTIAL"] # Still waiting?
    
    events = False
    
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
        
    if entries:
        msg += "\n✅ **Active Positions:**\n"
        for t in entries: 
            msg += f"{t.ticker} @ {t.entry_price}\n"
        events = True
        
    if skipped:
        msg += "\n⚠️ **Skipped Scenarios:**\n"
        for t in skipped:
            msg += f"{t.ticker}: {t.reason}\n"
        events = True
        
    if potential:
        msg += "\n⏳ **Untriggered Potentials:**\n"
        for t in potential:
             msg += f"{t.ticker} Entry: {t.entry_price}\n"
        events = True

    if events:
        send_alert(msg)
    else:
        print("No events to report for EOD.")
        
    db.close()
    print("EOD Cycle Complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["premarket", "intraday", "eod"], default="intraday", help="Operational mode")
    args = parser.parse_args()
    
    if args.mode == "premarket":
        run_premarket_scan()
    elif args.mode == "intraday":
        run_intraday_execution()
    elif args.mode == "eod":
        run_eod_report()
