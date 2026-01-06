from app.database import get_db, DailyPrice, Stock
import pandas as pd

def check_tickers():
    db = next(get_db())
    targets = ['WIPRO', 'MOTHERSON', 'DABUR', 'BEL', 'ICICIBANK', 'GLENMARK', 'ALKEM']
    print(f"{'Ticker':<12} | {'Exists':<8} | {'Records':<8}")
    print("-" * 30)
    
    for t in targets:
        # Check Stock table
        s = db.query(Stock).filter(Stock.ticker == t).first()
        exists = "YES" if s else "NO"
        
        # Check Records
        count = db.query(DailyPrice).filter(DailyPrice.ticker == t).count()
        print(f"{t:<12} | {exists:<8} | {count:<8}")

if __name__ == "__main__":
    check_tickers()
