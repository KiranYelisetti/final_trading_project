from app.database import get_db, init_db, Stock
from app.fetcher import get_fno_tickers, update_market_data, update_fundamentals
import time

def populate_db():
    print("Initialize Database...")
    init_db()
    db = next(get_db())
    
    try:
        # 1. Fetch F&O List
        tickers = get_fno_tickers()
        print(f"Found {len(tickers)} stocks in F&O Segment.")
        
        if not tickers:
            print("Failed to fetch tickers. Exiting.")
            return

        # 2. Add to DB if missing
        existing = db.query(Stock).all()
        existing_tickers = {s.ticker for s in existing}
        
        new_count = 0
        for t in tickers:
            if t not in existing_tickers:
                # Add basic record
                stock = Stock(ticker=t, company_name=t)
                db.add(stock)
                new_count += 1
        
        db.commit()
        print(f"Added {new_count} new stocks to database.")
        
        # 3. Update Market Data (OHLCV)
        print("Starting Market Data Update for ALL stocks (History)...")
        # To avoid rate limits or huge processing time, we process in chunks
        chunk_size = 20 
        
        # Re-fetch all tickers to include new ones
        all_stocks = db.query(Stock).all()
        all_tickers = [s.ticker for s in all_stocks]
        
        for i in range(0, len(all_tickers), chunk_size):
            chunk = all_tickers[i:i+chunk_size]
            print(f"Processing chunk {i} to {i+chunk_size}...")
            update_market_data(db, chunk)
            print("Cooling down for 2 seconds...")
            time.sleep(2) 
            
        # 4. Update Fundamentals
        print("Updating Fundamentals...")
        for i in range(0, len(all_tickers), chunk_size):
            chunk = all_tickers[i:i+chunk_size]
            update_fundamentals(db, chunk)
        
    finally:
        db.close()
        print("Population Complete.")

if __name__ == "__main__":
    populate_db()
