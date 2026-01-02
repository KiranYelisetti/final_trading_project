from nselib import capital_market
import pandas as pd

try:
    print("Fetching Nifty 500 list...")
    data = capital_market.nifty500_equity_list()
    print("Columns:", data.columns)
    print("First 5 rows:")
    print(data.head())
    print(f"Total rows: {len(data)}")
except Exception as e:
    print("Available attributes in capital_market:", dir(capital_market))

