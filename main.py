from app.database import init_db, get_db
from app.database import init_db, get_db
from app.fetcher import get_tickers, update_market_data, update_fundamentals

def main():
    print("Project: Techno-Fundamental Swing Trader")
    
    # 1. Init DB
    init_db()
    
    # 2. Get Tickers
    tickers = get_tickers()
    print(f"Total Tickers found: {len(tickers)}")
    
    if not tickers:
        print("No tickers found. Exiting.")
        return

    db_gen = get_db()
    db = next(db_gen)
    try:
        # Market Data
        # update_market_data(db, tickers) # optimizing time for this run
        
        # Fundamentals
        update_fundamentals(db, tickers)
    finally:
        db.close()
    
    print("Data update complete.")

if __name__ == "__main__":
    main()
