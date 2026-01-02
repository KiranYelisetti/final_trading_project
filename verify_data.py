from app.database import get_db, DailyPrice, Stock
from sqlalchemy import func

def verify():
    db = next(get_db())
    
    total_stocks = db.query(func.count(Stock.ticker)).scalar()
    total_records = db.query(func.count(DailyPrice.id)).scalar()
    
    print(f"Total Stocks: {total_stocks}")
    print(f"Total Daily Records: {total_records}")
    
    # Latest dates
    latest_date = db.query(func.max(DailyPrice.date)).scalar()
    print(f"Latest Date in DB: {latest_date}")
    
    # Check nulls in indicators
    # Note: RSI is null for first 14 days, EMA 200 for first 200.
    null_rsi = db.query(func.count(DailyPrice.id)).filter(DailyPrice.rsi_14 == None).scalar()
    print(f"Records with NULL RSI: {null_rsi}")
    
    null_ema200 = db.query(func.count(DailyPrice.id)).filter(DailyPrice.ema_200 == None).scalar()
    print(f"Records with NULL EMA 200: {null_ema200}")

    # Sample
    # Find a stock that likely exists, e.g., RELIANCE or INFY or TCS
    # Check which stocks we have first
    first_stock = db.query(Stock).first()
    if first_stock:
        symbol = first_stock.ticker
        sample = db.query(DailyPrice).filter(DailyPrice.ticker == symbol).order_by(DailyPrice.date.desc()).first()
        if sample:
            print(f"Sample {symbol}: Date={sample.date} Close={sample.close} RSI={sample.rsi_14} EMA200={sample.ema_200}")
    
    db.close()

if __name__ == "__main__":
    verify()
