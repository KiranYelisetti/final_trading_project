from app.database import get_db, init_db
from app.fetcher import update_market_data, update_fundamentals

def fetch_legacy():
    print("Fetching missing legacy tickers...")
    init_db()
    db = next(get_db())
    
    # List of missing tickers from check
    targets = ['MOTHERSON', 'DABUR', 'GLENMARK', 'ALKEM']
    
    # 1. Market Data
    update_market_data(db, targets)
    
    # 2. Fundamentals
    update_fundamentals(db, targets)
    
    db.close()
    print("Legacy fetch complete.")

if __name__ == "__main__":
    fetch_legacy()
