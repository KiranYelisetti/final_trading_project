from backtesting import Backtest
from app.backtest_strategies import PureFVGStrategy
from app.database import get_db, DailyPrice, Stock
import pandas as pd
import numpy as np

def load_data(ticker, db):
    query = db.query(DailyPrice).filter(DailyPrice.ticker == ticker).order_by(DailyPrice.date.asc())
    df = pd.read_sql(query.statement, db.bind)
    if df.empty: return None
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume', 'ema_200': 'EMA_200'})
    return df

def run_comparison():
    print("Starting Comparative Backtest...")
    db = next(get_db())
    
    # 1. Fetch Stocks and PE Data
    stocks = db.query(Stock).all()
    print(f"Total Universe: {len(stocks)} stocks")
    
    # 2. Define Groups
    # Group A: All Stocks (Pure Technical)
    group_a = [s.ticker for s in stocks]
    
    # Group B: Fundamental Filter (PE > 0 and PE < 85)
    # Filter out loss making (PE < 0 or None) and extremely overvalued (PE > 85)
    group_b = []
    skipped_reasons = {}
    
    for s in stocks:
        pe = s.current_pe
        if pe is None:
            skipped_reasons[s.ticker] = "Missing Data"
            continue
        if pe < 0:
            skipped_reasons[s.ticker] = "Negative PE"
            continue
        if pe > 85:
            skipped_reasons[s.ticker] = f"Overvalued (PE {pe:.1f})"
            continue
            
        group_b.append(s.ticker)
        
    print(f"Group A (Pure Tech): {len(group_a)} stocks")
    print(f"Group B (Fund + Tech): {len(group_b)} stocks (Filtered {len(group_a) - len(group_b)})")
    
    # 3. Run Backtest Helper
    def run_group(tickers, name):
        results = []
        print(f"\nRunning {name}...")
        for t in tickers:
            try:
                df = load_data(t, db)
                if df is None: continue
                # Basic check for data length
                if len(df) < 50: continue
                
                bt = Backtest(df, PureFVGStrategy, cash=100000, commission=.002)
                stats = bt.run()
                results.append({
                    'Ticker': t, 
                    'Return': stats['Return [%]'], 
                    'WinRate': stats['Win Rate [%]'],
                    'Trades': stats['# Trades']
                })
            except Exception as e:
                pass # Silent fail for speed
                
        return pd.DataFrame(results)

    # Execute
    res_a = run_group(group_a, "Pure FVG (All Stocks)")
    res_b = run_group(group_b, "Techno-Fundamental (Filtered)")
    
    db.close()
    
    # 4. Compare Stats
    print("\n" + "="*50)
    print("COMPARISON RESULTS")
    print("="*50)
    
    def get_summary(df):
        if df.empty: return "No Data"
        return {
            'Avg Return': f"{df['Return'].mean():.2f}%",
            'Median Return': f"{df['Return'].median():.2f}%",
            'Avg Win Rate': f"{df['WinRate'].mean():.2f}%",
            'Profitable %': f"{(len(df[df['Return'] > 0]) / len(df)) * 100:.1f}%",
            'Total Trades': df['Trades'].sum()
        }

    sum_a = get_summary(res_a)
    sum_b = get_summary(res_b)
    
    comp_df = pd.DataFrame([sum_a, sum_b], index=["Pure FVG (All)", "Fund + FVG (Filtered)"])
    print(comp_df.to_markdown())
    
    print("\n\nExcluded Stocks Analysis (Sample):")
    for k, v in list(skipped_reasons.items())[:10]:
        print(f"{k}: {v}")

if __name__ == "__main__":
    run_comparison()
