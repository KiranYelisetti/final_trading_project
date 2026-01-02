from app.database import get_db, Stock
import pandas as pd

def inspect_fundamentals():
    db = next(get_db())
    query = db.query(Stock).statement
    df = pd.read_sql(query, db.bind)
    
    print(f"Total Stocks: {len(df)}")
    
    # Check nulls
    print("\nMissing Values:")
    print(df[['current_pe', 'peg_ratio', 'quarterly_earnings_growth']].isnull().sum())
    
    # Show sample
    print("\nSample Data (First 20):")
    print(df[['ticker', 'sector', 'current_pe', 'peg_ratio', 'quarterly_earnings_growth']].head(20).to_string())
    
    # Check non-null distribution
    print("\nDistribution of PEG Ratio (where not null):")
    print(df['peg_ratio'].describe())

if __name__ == "__main__":
    inspect_fundamentals()
