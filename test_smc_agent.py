from app.database import get_db, Stock, DailyPrice
from app.smc_agent import analyze_ticker
from utils.plotter import plot_ticker_smc
import pandas as pd

def test_smc():
    db = next(get_db())
    
    # Pick a stock
    ticker = "TATASTEEL"
    print(f"Testing SMC for {ticker}...")
    
    # Load Data
    query = db.query(DailyPrice).filter(DailyPrice.ticker == ticker).order_by(DailyPrice.date.asc())
    df = pd.read_sql(query.statement, db.bind)
    
    if df.empty:
        print("No data found.")
        return
        
    df.set_index('date', inplace=True)
    
    # Analyze
    results, annotated_df = analyze_ticker(ticker, df)
    
    print("\nResults Summary:")
    print(results)
    
    # Check counts
    bull_obs = annotated_df['bullish_ob'].sum()
    bull_fvgs = annotated_df['bullish_fvg'].sum()
    print(f"\nDetected {bull_obs} Bullish OBs and {bull_fvgs} Bullish FVGs in history.")
    
    # Plot
    plot_ticker_smc(ticker, annotated_df)

if __name__ == "__main__":
    test_smc()
