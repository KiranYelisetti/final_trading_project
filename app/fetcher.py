# import yfinance as yf # REMOVED
import pandas as pd
import pandas_ta as ta
from nselib import capital_market
from nsepython import nse_eq
from app.database import get_db, Stock, DailyPrice
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, date
import time

def update_fundamentals(db: Session, tickers: list):
    """Fetch fundamental data for stocks using NSEPython."""
    print(f"Updating fundamentals for {len(tickers)} stocks (NSE)...")
    
    for ticker in tickers:
        try:
            print(f"Fetching fundamentals for {ticker}...")
            # Use nse_eq from nsepython
            data = nse_eq(ticker)
            
            # Default values
            current_pe = None
            industry = None
            sector = None
            
            if 'metadata' in data:
                meta = data['metadata']
                current_pe = meta.get('pdSymbolPe')
                industry = meta.get('industry')
                # sector = meta.get('pdSectorInd') # This is often an index name
                sector = industry # Fallback
                
            # Update DB
            stock = db.query(Stock).filter(Stock.ticker == ticker).first()
            if stock:
                if current_pe is not None and current_pe != '-': 
                     try:
                        stock.current_pe = float(current_pe)
                     except: pass
                if industry: stock.industry = industry
                if sector: stock.sector = sector
                
                # PEG and Earnings Growth not readily available in simple nse_eq
                # Leaving them as is or None
                
                db.commit()
                print(f"Updated {ticker}: PE={current_pe}, Ind={industry}")
            
            # Be nice to API
            time.sleep(0.5)
            
        except Exception as e:
            print(f"Failed fundamentals for {ticker}: {e}")


def get_tickers():
    """Fetch list of tickers. Uses NSE F&O list (Large + Mid Cap)."""
    try:
        print("Fetching F&O Equity list from NSE...")
        df = capital_market.fno_equity_list()
        
        # Normalize column name
        col = 'symbol' if 'symbol' in df.columns else 'Symbol'
        tickers = df[col].tolist()
        
        # Ensure clean list
        tickers = [t.strip().upper() for t in tickers]
        return tickers
    except Exception as e:
        print(f"Error fetching F&O list: {e}")
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
    
    # Calculate Indicators
    # RSI 14
    df['RSI_14'] = ta.rsi(df['Close'], length=14)
    # EMAs
    df['EMA_200'] = ta.ema(df['Close'], length=200)
    df['EMA_50'] = ta.ema(df['Close'], length=50)
    df['EMA_20'] = ta.ema(df['Close'], length=20)
    
    return df

def update_market_data(db: Session, tickers: list):
    print(f"Start updating data for {len(tickers)} stocks (NSE Source)...")
    
    # Check if we need to fetch history or just append
    today = date.today()
    
    for ticker in tickers:
        try:
            print(f"Processing {ticker}...")
            
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
            else:
                # Default to 2 years ago if no data
                start_date = today - timedelta(days=365*2)
            
            if start_date > today:
                print(f"Data up to date for {ticker}")
                continue
                
            # Convert to dd-mm-yyyy for nselib
            from_str = start_date.strftime("%d-%m-%Y")
            to_str = today.strftime("%d-%m-%Y")
            
            print(f"Fetching {ticker} from {from_str} to {to_str}...")
            try:
                data = capital_market.price_volume_and_deliverable_position_data(symbol=ticker, from_date=from_str, to_date=to_str)
            except Exception as e:
                 print(f"NSE Download Error for {ticker}: {e}")
                 continue
            
            if data is None or data.empty:
                print(f"No new data for {ticker}")
                continue
            
            # Map NSE Columns to Standard
            # NSE Cols: 'Symbol', 'Series', 'Date', 'PrevClose', 'OpenPrice', 'HighPrice', 'LowPrice', 'LastPrice', 'ClosePrice', 'AveragePrice', 'TotalTradedQuantity', ...
            # We want: Open, High, Low, Close, Volume
            
            # Filter Only EQ Series usually? 
            if 'Series' in data.columns:
                data = data[data['Series'] == 'EQ']
                
            if data.empty:
                print("No EQ data found.")
                continue

            # Rename
            rename_map = {
                'OpenPrice': 'Open',
                'HighPrice': 'High',
                'LowPrice': 'Low',
                'ClosePrice': 'Close', # 'ClosePrice' is usually the settled close
                'TotalTradedQuantity': 'Volume',
                'Date': 'DateStr'
            }
            data = data.rename(columns=rename_map)
            
            # Parse Date
            # NSE returns '08-Dec-2025'
            data['date'] = pd.to_datetime(data['DateStr'], format='%d-%b-%Y').dt.date
            
            # Ensure numeric
            cols = ['Open', 'High', 'Low', 'Close', 'Volume']
            for c in cols:
                # Remove commas
                data[c] = data[c].astype(str).str.replace(',', '').astype(float)
                
            # Process Indicators
            data = process_stock_data(ticker, data)
            
            # Find existing dates to avoid duplicates
            existing_dates = {row[0] for row in db.query(DailyPrice.date).filter(DailyPrice.ticker == ticker).all()}
            
            # Prepare objects
            new_records = []
            for _, row in data.iterrows():
                row_date = row['date']
                
                # Skip if already exists
                if row_date in existing_dates:
                    continue
                
                # Also skip if essential data is missing
                if pd.isna(row['Close']):
                    continue
                    
                record = DailyPrice(
                    ticker=ticker,
                    date=row_date,
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
                
            time.sleep(1) # Rate limit
                
        except Exception as e:
            print(f"Failed {ticker}: {e}")
            db.rollback()

