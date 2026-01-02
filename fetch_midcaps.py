from app.database import get_db, init_db
from app.fetcher import update_market_data, update_fundamentals

MIDCAPS = ['TATAELXSI', 'KPITTECH', 'POLYCAB', 'TRENT', 'CANBK', 'COFORGE', 'L&TFH']

def fetch_midcaps():
    print(f"Fetching data for Mid-Caps: {MIDCAPS}")
    
    # Init DB
    init_db()
    
    db_gen = get_db()
    db = next(db_gen)
    try:
        # Market Data
        update_market_data(db, MIDCAPS)
        
        # Fundamentals
        update_fundamentals(db, MIDCAPS)
    finally:
        db.close()
    
    print("Mid-Cap Data update complete.")

if __name__ == "__main__":
    fetch_midcaps()
