from backtesting import Backtest
from app.backtest_strategy import SMCStrategy
from app.database import get_db, DailyPrice
import pandas as pd

def run_simulation(ticker='TATASTEEL'):
    print(f"Running Backtest for {ticker}...")
    
    # Load Data
    db = next(get_db())
    query = db.query(DailyPrice).filter(DailyPrice.ticker == ticker).order_by(DailyPrice.date.asc())
    df = pd.read_sql(query.statement, db.bind)
    
    if df.empty:
        print("No data.")
        return
        
    # Format for Backtesting: Date index, Capital Case columns
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    df = df.rename(columns={
        'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'
    })
    
    # Run
    bt = Backtest(df, SMCStrategy, cash=100000, commission=.002)
    stats = bt.run()
    
    print("\n=== Backtest Results ===")
    print(stats)
    
    # Verify Trades
    print(f"\nNumber of Trades: {stats['_trades'].shape[0]}")
    if not stats['_trades'].empty:
        print(stats['_trades'].head())
        
    # Plot?
    # bt.plot(filename=f"charts/{ticker}_backtest.html")
    # print(f"Plot saved to charts/{ticker}_backtest.html")

if __name__ == "__main__":
    run_simulation()
