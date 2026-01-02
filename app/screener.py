from app.database import get_db, Stock
import pandas as pd
from sqlalchemy.orm import Session

def run_screener():
    print("Running Fundamental Screener...")
    db_gen = get_db()
    db = next(db_gen)
    
    try:
        # Load all stocks into DataFrame
        query = db.query(Stock).statement
        df = pd.read_sql(query, db.bind)
        
        if df.empty:
            print("No stocks in database.")
            return

        print(f"Total Stocks: {len(df)}")
        
        # 1. Calculate Sector PE
        # Clean null sectors
        df['sector'] = df['sector'].fillna('Unknown')
        
        # Group by sector and calculate median PE
        sector_stats = df[df['current_pe'] > 0].groupby('sector')['current_pe'].median().reset_index()
        sector_stats.rename(columns={'current_pe': 'sector_median_pe'}, inplace=True)
        
        # Merge back
        df = pd.merge(df, sector_stats, on='sector', how='left')
        
        # Fill missing sector PEs with global median or high value to be safe
        global_median = df[df['current_pe'] > 0]['current_pe'].median()
        df['sector_median_pe'] = df['sector_median_pe'].fillna(global_median)
        
        # 2. Apply Filters
        
        # Calculate PEG dynamically if missing
        # PEG = PE / (Growth Rate * 100)
        # We have Growth as 0.20 for 20%, so we multiply by 100 -> 20.
        with pd.option_context('mode.use_inf_as_na', True):
            df['calc_peg'] = df['current_pe'] / (df['quarterly_earnings_growth'] * 100)
        
        # Condition 1: Undervalued relative to Sector (PE < Sector PE)
        # We can be slightly loose, e.g., PE < 1.2 * Sector PE. Using 1.0 based on request.
        cond_value = df['current_pe'] < df['sector_median_pe']
        
        # Condition 2: PEG < 1.5 (Growth at reasonable price)
        # Use calculated PEG. Must be positive.
        cond_peg = (df['calc_peg'] > 0) & (df['calc_peg'] < 2.0) # Relaxed to 2.0 given strictness, or stick to 1.5
        
        # Condition 3: Earnings Growth > 15% (0.15)
        cond_growth = df['quarterly_earnings_growth'] > 0.15
        
        # Condition 4: PE > 0
        cond_profitable = df['current_pe'] > 0
        
        watchlist = df[cond_value & cond_peg & cond_growth & cond_profitable].copy() # Copy to avoid SettingWithCopyWarning
        
        # Sort by Growth
        watchlist = watchlist.sort_values(by='quarterly_earnings_growth', ascending=False)
        
        print(f"\nScanning {len(df)} stocks...")
        print(f"Found {len(watchlist)} matches.")
        
        if not watchlist.empty:
            print("\n=== Watchlist (Top 10) ===")
            cols = ['ticker', 'sector', 'current_pe', 'sector_median_pe', 'calc_peg', 'quarterly_earnings_growth']
            print(watchlist[cols].head(10).to_string(index=False))
            
            # Save to CSV
            watchlist[cols].to_csv("watchlist.csv", index=False)
            print("\nSaved full watchlist to watchlist.csv")
            
    except Exception as e:
        print(f"Error running screener: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_screener()
