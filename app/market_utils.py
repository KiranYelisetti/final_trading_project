import yfinance as yf
import pandas as pd
import pandas_ta as ta

class MarketAnalyzer:
    def __init__(self):
        self.nifty_ticker = "^NSEI"
        self.nifty_data = None
        
    def fetch_nifty_data(self):
        """Fetches Nifty 50 data if not already cached."""
        if self.nifty_data is not None:
            return
            
        try:
            # Fetch last 6 months to ensure enough data for EMA 50
            df = yf.download(self.nifty_ticker, period="6mo", progress=False)
            
            # Handle MultiIndex if present
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(1)
                
            # Calculate EMA 50
            df['EMA_50'] = ta.ema(df['Close'], length=50)
            self.nifty_data = df
        except Exception as e:
            print(f"Error fetching Nifty data: {e}")
            self.nifty_data = pd.DataFrame() # Empty to prevent crashes

    def get_nifty_trend(self):
        """Returns 'UPTREND' if Nifty Close > EMA 50, else 'DOWNTREND'."""
        self.fetch_nifty_data()
        
        if self.nifty_data is None or self.nifty_data.empty:
            return "UNKNOWN"
            
        last_row = self.nifty_data.iloc[-1]
        close = last_row['Close']
        ema_50 = last_row['EMA_50']
        
        if pd.isna(ema_50):
            return "UNKNOWN"
            
        if close > ema_50:
            return "UPTREND"
        else:
            return "DOWNTREND"
            
    def get_relative_strength(self, ticker_symbol, db_session, window=5):
        """
        Checks if the ticker is performing better than Nifty 50 over a specific window (default 5 days).
        Uses LOCAL DATABASE for Ticker Data (Accuracy) and YFinance for Nifty Data (Proxy).
        Returns True if Ticker % Change > Nifty % Change.
        """
        try:
            # 1. Fetch Ticker Data from DB
            from app.database import DailyPrice
            
            # Query last (window + 1) days
            # We need to sort DESC to get latest, then take top N
            prices = db_session.query(DailyPrice).filter(
                DailyPrice.ticker == ticker_symbol
            ).order_by(DailyPrice.date.desc()).limit(window + 1).all()
            
            if len(prices) < window + 1:
                # Not enough data (e.g. new listing or data gap)
                return False
                
            # Sort back to ASC for calculation
            prices.sort(key=lambda x: x.date)
            
            # Start and End Prices
            t_start = prices[0].close
            t_end = prices[-1].close
            t_start_date = prices[0].date
            t_end_date = prices[-1].date
            
            if t_start == 0: return False
            
            t_pct = (t_end - t_start) / t_start
            
            # 2. Fetch Nifty Data (Aligned to Dates)
            self.fetch_nifty_data()
            if self.nifty_data is None or self.nifty_data.empty:
                return False
                
            # We need Nifty prices for t_start_date and t_end_date
            # Nifty Index from YFinance is datetime, prices from DB are date.
            # Convert Nifty index to date for lookup
            
            # Helper to find closest available date in Nifty data
            def get_nifty_close(target_date):
                # Search for exact match
                if target_date in self.nifty_data.index:
                    return self.nifty_data.loc[target_date]['Close']
                # If not found (e.g. db has date but yf missing?), try closest previous
                # Actually, index lookup should work if normalized.
                return None
            
            # Re-index Nifty by simple date if not already
            # In fetch_nifty_data, we didn't set index to date column, it might be auto date index.
            # Let's ensure access is easy.
            
            # Lookup
            # Note: yfinance dates might differ slightly due to timezones, but usually match day.
            # Let's simple check the last 'window' days of Nifty independent of exact date sync 
            # OR strict sync. Strict is better for RS.
            
            # Filter Nifty to the date range
            mask = (self.nifty_data.index.date >= t_start_date) & (self.nifty_data.index.date <= t_end_date)
            nifty_subset = self.nifty_data[mask]
            
            if nifty_subset.empty:
                return False
                
            n_start = nifty_subset.iloc[0]['Close']
            n_end = nifty_subset.iloc[-1]['Close']
            
            if n_start == 0: return False
            
            n_pct = (n_end - n_start) / n_start
            
            # Debug
            # print(f"[{ticker_symbol}] Stock: {t_pct:.2%} ({t_start}->{t_end}), Nifty: {n_pct:.2%} ({n_start}->{n_end})")
            
            return t_pct > n_pct
            
        except Exception as e:
            print(f"Error checking RS for {ticker_symbol}: {e}")
            return False
