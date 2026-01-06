from backtesting import Backtest
from app.backtest_strategies import TrendSMCStrategy, PureFVGStrategy
from app.database import get_db, DailyPrice
import pandas as pd

STOCKS = ['WIPRO', 'MOTHERSON', 'DABUR', 'BEL', 'ICICIBANK', 'GLENMARK', 'ADANIENT']

def load_data(ticker):
    db_gen = get_db()
    db = next(db_gen)
    try:
        query = db.query(DailyPrice).filter(DailyPrice.ticker == ticker).order_by(DailyPrice.date.asc())
        df = pd.read_sql(query.statement, db.bind)
        if df.empty: return None
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume', 'ema_200': 'EMA_200'})
        return df
    finally:
        db.close()

def run_batch():
    db_gen = get_db()
    db = next(db_gen)
    stocks = db.query(DailyPrice.ticker).distinct().all()
    tickers = [s[0] for s in stocks]
    print(f"Found {len(tickers)} tickers in DB.")
    db.close()
    
    results = []
    
    print(f"{'Ticker':<12} | {'Strategy':<15} | {'Return%':<10} | {'WinRate%':<10} | {'Trades':<8}")
    print("-" * 70)
    
    for ticker in tickers:
        df = load_data(ticker)
        if df is None: continue
        
        # Test PureFVG (Our Primary Strategy)
        try:
            bt_fvg = Backtest(df, PureFVGStrategy, cash=100000, commission=.002)
            stats_fvg = bt_fvg.run()
            results.append({
                'Ticker': ticker, 'Strategy': 'PureFVG', 
                'Return': stats_fvg['Return [%]'], 
                'WinRate': stats_fvg['Win Rate [%]'], 
                'Trades': stats_fvg['# Trades']
            })
            print(f"{ticker:<12} | {'PureFVG':<15} | {stats_fvg['Return [%]']:<10.2f} | {stats_fvg['Win Rate [%]']:<10.2f} | {stats_fvg['# Trades']:<8}")
        except Exception as e:
            print(f"Error {ticker}: {e}")

    # Summary
    if results:
        df_res = pd.DataFrame(results)
        print("\n=== Universe Backtest Summary (PureFVG) ===")
        print(f"Total Stocks Tested: {len(df_res)}")
        print(f"Average Return:      {df_res['Return'].mean():.2f}%")
        print(f"Median Return:       {df_res['Return'].median():.2f}%")
        print(f"Average Win Rate:    {df_res['WinRate'].mean():.2f}%")
        print(f"Profitable Stocks:   {len(df_res[df_res['Return'] > 0])} / {len(df_res)}")
        
        print("\nTop 10 Performers:")
        print(df_res.sort_values('Return', ascending=False).head(10)[['Ticker', 'Return', 'WinRate']])

if __name__ == "__main__":
    run_batch()
