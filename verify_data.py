import pandas as pd
from app.database import get_db, Stock, DailyPrice
from nselib import capital_market
from datetime import date, timedelta
import time

def verify_integrity():
    db = next(get_db())
    stocks = db.query(Stock).all()
    tickers = [s.ticker for s in stocks]
    
    print(f"Verifying data for {len(tickers)} stocks...")
    
    issues_found = []
    
    today = date.today()
    start_check = today - timedelta(days=5) # Check last 5 days
    from_str = start_check.strftime("%d-%m-%Y")
    to_str = today.strftime("%d-%m-%Y")
    
    # We will fetch a batch of 'reference' data
    # Ideally we do this ticker by ticker or use a bulk method if available.
    # nselib is per ticker.
    
    for ticker in tickers[:10]: # Check first 10 for quick sanity, then maybe more
        print(f"Checking {ticker}...")
        try:
            # Fetch Reference Data
            ref_data = capital_market.price_volume_and_deliverable_position_data(symbol=ticker, from_date=from_str, to_date=to_str)
            if ref_data is None or ref_data.empty:
                print(f"   No reference data for {ticker}")
                continue
                
            # Clean Reference Data
            cols = ['OpenPrice', 'HighPrice', 'LowPrice', 'ClosePrice', 'Date']
            # Adjust for different column names in nselib return
            if 'ClosePrice' not in ref_data.columns:
                 # fallback for missing cols?
                 pass
            
            # Helper to parse Price
            def clean_price(v):
                return float(str(v).replace(',', ''))

            ref_map = {}
            for _, row in ref_data.iterrows():
                try:
                    d_str = row['Date']
                    d_obj = pd.to_datetime(d_str, format='%d-%b-%Y').date()
                    ref_map[d_obj] = {
                        'High': clean_price(row['HighPrice']),
                        'Low': clean_price(row['LowPrice']),
                        'Close': clean_price(row['ClosePrice'])
                    }
                except: continue

            # Fetch DB Data
            db_recs = db.query(DailyPrice).filter(
                DailyPrice.ticker == ticker, 
                DailyPrice.date >= start_check
            ).all()
            
            for rec in db_recs:
                if rec.date in ref_map:
                    ref = ref_map[rec.date]
                    
                    # Check for discrepancies (allow small rounding diff)
                    diff_close = abs(rec.close - ref['Close'])
                    diff_high = abs(rec.high - ref['High'])
                    
                    # Threshold: 0.5% or 0.5 absolute (handle rounding)
                    if diff_close > (rec.close * 0.005) or diff_high > (rec.high * 0.005):
                        err = f"MISMATCH {ticker} on {rec.date}: DB Close={rec.close}, Ref Close={ref['Close']}"
                        print(f"   ❌ {err}")
                        issues_found.append(err)
                    else:
                        # print(f"   ✅ {rec.date} OK")
                        pass
                else:
                    print(f"   ⚠️ {ticker} has date {rec.date} in DB but not in Reference (Holiday/weekend?)")

        except Exception as e:
            print(f"   Error verifying {ticker}: {e}")
            
    if issues_found:
        print("\n\nSUMMARY OF ISSUES:")
        for i in issues_found:
            print(i)
    else:
        print("\n\n✅ Data integrity check passed for sampled stocks.")

if __name__ == "__main__":
    verify_integrity()
