from app.database import get_db, Trade, DailyPrice
from nselib import capital_market
from datetime import date, timedelta
import pandas as pd
import time

def audit_trades():
    print("Starting Trade Audit (NSE Data)...")
    db = next(get_db())
    trades = db.query(Trade).filter(Trade.status.in_(["PENDING", "OPEN"])).all()
    
    if not trades:
        print("No active trades to audit.")
        return

    print(f"Auditing {len(trades)} trades...")
    
    for t in trades:
        print(f"\nChecking {t.ticker} (ID: {t.id}) | Status: {t.status} | Entry: {t.entry_price} | SL: {t.sl_price} | TP: {t.tp_price}")
        
        # 1. Fetch Data from Signal Date to Today
        start_dt = t.signal_date
        end_dt = date.today()
        
        if start_dt == end_dt:
            print("  Signal is from today. No history to check.")
            continue
            
        from_str = start_dt.strftime("%d-%m-%Y")
        to_str = end_dt.strftime("%d-%m-%Y")
        
        try:
            # Fetch NSE Data
            data = capital_market.price_volume_and_deliverable_position_data(symbol=t.ticker, from_date=from_str, to_date=to_str)
            if data is None or data.empty:
                print("  No data found from NSE.")
                continue
                
            # Clean Data
            if 'Series' in data.columns:
                data = data[data['Series'] == 'EQ']
            
            # Rename and Convert
            rename_map = {'HighPrice': 'High', 'LowPrice': 'Low', 'Date': 'DateStr'}
            data = data.rename(columns=rename_map)
            data['date'] = pd.to_datetime(data['DateStr'], format='%d-%b-%Y').dt.date
            data['High'] = data['High'].astype(str).str.replace(',', '').astype(float)
            data['Low'] = data['Low'].astype(str).str.replace(',', '').astype(float)
            
            # Sort by date asc
            data = data.sort_values('date')
            
            # Traverse
            current_status = t.status
            
            for _, row in data.iterrows():
                d = row['date']
                h = row['High']
                l = row['Low']
                
                if current_status == "PENDING":
                    # Check for Entry trigger (Price dropped to Limit)
                    # Assuming Limit Buy: If Low <= Entry
                    if l <= t.entry_price:
                        print(f"  [{d}] ✅ Entry Triggered! Low {l} <= Limit {t.entry_price}")
                        current_status = "OPEN"
                        t.status = "OPEN"
                        t.entry_date = d
                        # Check if SL/TP hit same day? Usually safe to assume entry first, but severe move could hit SL.
                        # Conservatively check SL same day if candle range covers it?
                        # If Low <= SL, it's an immediate loss? 
                        # Let's check next iteration usually, but for granular:
                        if l <= t.sl_price:
                             print(f"  [{d}] 🛑 Stopped out same day! Low {l} <= SL {t.sl_price}")
                             current_status = "CLOSED"
                             t.status = "CLOSED"
                             t.outcome = "LOSS"
                             t.exit_date = d
                             t.exit_price = t.sl_price
                             t.pnl = t.sl_price - t.entry_price
                             break
                        
                        if h >= t.tp_price:
                             # Rare: Entry low and TP high same day
                             print(f"  [{d}] 💰 TP Hit same day! High {h} >= TP {t.tp_price}")
                             current_status = "CLOSED"
                             t.status = "CLOSED"
                             t.outcome = "WIN"
                             t.exit_date = d
                             t.exit_price = t.tp_price
                             t.pnl = t.tp_price - t.entry_price
                             break

                elif current_status == "OPEN":
                    # Check SL (Safety First)
                    if l <= t.sl_price:
                         print(f"  [{d}] 🛑 Stop Loss Hit! Low {l} <= SL {t.sl_price}")
                         current_status = "CLOSED"
                         t.status = "CLOSED"
                         t.outcome = "LOSS"
                         t.exit_date = d
                         t.exit_price = t.sl_price
                         t.pnl = t.sl_price - t.entry_price
                         break
                    
                    # Check TP
                    if h >= t.tp_price:
                         print(f"  [{d}] 💰 Target Hit! High {h} >= TP {t.tp_price}")
                         current_status = "CLOSED"
                         t.status = "CLOSED"
                         t.outcome = "WIN"
                         t.exit_date = d
                         t.exit_price = t.tp_price
                         t.pnl = t.tp_price - t.entry_price
                         break
            
            # Commit changes for this trade if any
            if t.status != current_status or t.status != trades[0].status: # simplistic check
                 db.commit()
                 
        except Exception as e:
            print(f"  Error auditing {t.ticker}: {e}")
            
    print("\nAudit Complete.")

if __name__ == "__main__":
    audit_trades()
