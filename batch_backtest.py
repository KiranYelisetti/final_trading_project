from backtesting import Backtest
from app.backtest_strategies import TrendSMCStrategy, PureFVGStrategy
from app.database import get_db, DailyPrice
import pandas as pd

STOCKS = ['TATASTEEL', 'WIPRO', 'ADANIENT', 'HINDALCO', 'M&M', 'TATAELXSI', 'KPITTECH', 'POLYCAB', 'TRENT', 'CANBK', 'COFORGE']

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
    results = []
    
    print(f"{'Ticker':<12} | {'Strategy':<15} | {'Return%':<10} | {'WinRate%':<10} | {'Trades':<8}")
    print("-" * 70)
    
    for ticker in STOCKS:
        df = load_data(ticker)
        if df is None: continue
        
        # Test TrendSMC
        bt_trend = Backtest(df, TrendSMCStrategy, cash=100000, commission=.002)
        stats_trend = bt_trend.run()
        results.append({
            'Ticker': ticker, 'Strategy': 'TrendSMC', 
            'Return': stats_trend['Return [%]'], 
            'WinRate': stats_trend['Win Rate [%]'], 
            'Trades': stats_trend['# Trades']
        })
        print(f"{ticker:<12} | {'TrendSMC':<15} | {stats_trend['Return [%]']:<10.2f} | {stats_trend['Win Rate [%]']:<10.2f} | {stats_trend['# Trades']:<8}")
        
        # Test PureFVG
        bt_fvg = Backtest(df, PureFVGStrategy, cash=100000, commission=.002)
        stats_fvg = bt_fvg.run()
        results.append({
            'Ticker': ticker, 'Strategy': 'PureFVG', 
            'Return': stats_fvg['Return [%]'], 
            'WinRate': stats_fvg['Win Rate [%]'], 
            'Trades': stats_fvg['# Trades']
        })
        print(f"{ticker:<12} | {'PureFVG':<15} | {stats_fvg['Return [%]']:<10.2f} | {stats_fvg['Win Rate [%]']:<10.2f} | {stats_fvg['# Trades']:<8}")

if __name__ == "__main__":
    run_batch()
