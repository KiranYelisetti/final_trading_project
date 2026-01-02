from nselib import capital_market
import pandas as pd

try:
    print("Fetching Nifty 100...")
    data = capital_market.nifty100_equity_list()
    print(data.head())
    print(f"Count: {len(data)}")
    print(data['Symbol'].tolist()[:10])
except Exception as e:
    print(f"Error: {e}")
