from nselib import capital_market
import pandas as pd

try:
    print("Fetching F&O List...")
    data = capital_market.fno_equity_list()
    print(data.head())
    print(f"Count: {len(data)}")
    # Check column name for symbol
    print(data.columns)
except Exception as e:
    print(f"Error: {e}")
