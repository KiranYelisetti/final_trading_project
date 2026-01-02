import yfinance as yf
import pandas as pd
import pandas_ta as ta
from nselib import capital_market
from app.database import get_db, Stock, DailyPrice
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import time

def update_fundamentals(db: Session, tickers: list):
    """Fetch fundamental data for stocks."""
    print(f"Updating fundamentals for {len(tickers)} stocks...")
    
    for ticker in tickers:
        try:
            symbol = f"{ticker}.NS"
            print(f"Fetching fundamentals for {symbol}...")
            
            t = yf.Ticker(symbol)
            info = t.info
            
            # Extract metrics
            # yfinance keys can vary, use .get with defaults
            current_pe = info.get('trailingPE', None)
            peg_ratio = info.get('pegRatio', None)
            earnings_growth = info.get('earningsQuarterlyGrowth', None) 
            sector = info.get('sector', None)
            industry = info.get('industry', None)
            
            # Update DB
            stock = db.query(Stock).filter(Stock.ticker == ticker).first()
            if stock:
                if current_pe is not None: stock.current_pe = current_pe
                if peg_ratio is not None: stock.peg_ratio = peg_ratio
                if earnings_growth is not None: stock.quarterly_earnings_growth = earnings_growth
                if sector: stock.sector = sector
                if industry: stock.industry = industry
                
                db.commit()
                print(f"Updated {ticker}: PE={current_pe}, PEG={peg_ratio}, Gr={earnings_growth}")
            
            # Be nice to API
            time.sleep(0.5)
            
        except Exception as e:
            print(f"Failed fundamentals for {ticker}: {e}")


def get_tickers():
    """Fetch list of tickers. Currently uses Nifty 50."""
    try:
        print("Fetching Nifty 50 list from NSE...")
        df = capital_market.nifty50_equity_list()
        return df['Symbol'].tolist()
    except Exception as e:
        print(f"Error fetching Nifty 50 list: {e}")
        return []

def get_fno_tickers():
    """Fetch list of F&O stocks (approx 200 liquid stocks)."""
    try:
        print("Fetching F&O Equity list from NSE...")
        # Clean column names as nselib sometimes has whitespace
        df = capital_market.fno_equity_list()
        # The column is usually 'symbol' or 'Symbol'
        col = 'symbol' if 'symbol' in df.columns else 'Symbol'
        return df[col].tolist()
    except Exception as e:
        print(f"Error fetching F&O list: {e}")
        return []

def process_stock_data(ticker, df):
    """Calculate indicators."""
    if df.empty:
        return df
    
    # Ensure MultiIndex columns are flattened if using yfinance < 0.2, but 0.2+ is standard.
    # yfinance often returns columns as (Price, Ticker) or just Price.
    # We downloaded single ticker so it should be flat or simple index.
    
    # Calculate Indicators
    # RSI 14
    df['RSI_14'] = ta.rsi(df['Close'], length=14)
    # EMAs
    df['EMA_200'] = ta.ema(df['Close'], length=200)
    df['EMA_50'] = ta.ema(df['Close'], length=50)
    df['EMA_20'] = ta.ema(df['Close'], length=20)
    
    return df

def update_market_data(db: Session, tickers: list):
    print(f"Start updating data for {len(tickers)} stocks...")
    
    for ticker in tickers:
        try:
            symbol = f"{ticker}.NS"
            print(f"Processing {symbol}...")
            
            # Get or Create Stock
            stock = db.query(Stock).filter(Stock.ticker == ticker).first()
            if not stock:
                stock = Stock(ticker=ticker, company_name=ticker, sector="Unknown")
                db.add(stock)
                db.commit()
            
            # Find last date
            last_entry = db.query(DailyPrice.date).filter(DailyPrice.ticker == ticker).order_by(DailyPrice.date.desc()).first()
            start_date = None
            if last_entry:
                start_date = last_entry[0] + timedelta(days=1)
            
            # Fetch data
            # If start_date is provided, use it. Else default to 2 years (enough for 200 EMA + backtest)
            if start_date:
                data = yf.download(symbol, start=start_date, progress=False, multi_level_index=False)
            else:
                data = yf.download(symbol, period="5y", progress=False, multi_level_index=False)
            
            if data.empty:
                print(f"No new data for {symbol}")
                continue
            
            # Clean data columns - yfinance sometimes returns tickers as column headers even for single download
            # Fix column names if needed
            # if isinstance(data.columns, pd.MultiIndex):
            #     data = data.xs(symbol, axis=1, level=1)
            
            # Calculate Indicators
            data = process_stock_data(ticker, data)
            
            # Find existing dates to avoid duplicates
            existing_dates = {row[0] for row in db.query(DailyPrice.date).filter(DailyPrice.ticker == ticker).all()}
            
            # Prepare objects
            new_records = []
            for date, row in data.iterrows():
                # Skip if already exists
                if date.date() in existing_dates:
                    continue
                
                # Also skip if essential data is missing
                if pd.isna(row['Close']):
                    continue
                    
                record = DailyPrice(
                    ticker=ticker,
                    date=date.date(),
                    open=row.get('Open', 0),
                    high=row.get('High', 0),
                    low=row.get('Low', 0),
                    close=row.get('Close', 0),
                    volume=int(row.get('Volume', 0)),
                    rsi_14=row.get('RSI_14', None),
                    ema_200=row.get('EMA_200', None),
                    ema_50=row.get('EMA_50', None),
                    ema_20=row.get('EMA_20', None)
                )
                new_records.append(record)
            
            if new_records:
                db.bulk_save_objects(new_records)
                db.commit()
                print(f"Added {len(new_records)} records for {ticker}")
                
        except Exception as e:
            print(f"Failed {ticker}: {e}")
            db.rollback()

