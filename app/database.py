import os
from sqlalchemy import create_engine, Column, Integer, String, Date, Float, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

Base = declarative_base()

class Stock(Base):
    __tablename__ = 'stocks'
    
    ticker = Column(String, primary_key=True)
    company_name = Column(String)
    sector = Column(String, nullable=True)
    industry = Column(String, nullable=True)
    
    # Fundamental Metrics
    current_pe = Column(Float, nullable=True)
    peg_ratio = Column(Float, nullable=True)
    quarterly_earnings_growth = Column(Float, nullable=True)
    
    prices = relationship("DailyPrice", back_populates="stock")
    trades = relationship("Trade", back_populates="stock")

class DailyPrice(Base):
    __tablename__ = 'daily_prices'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String, ForeignKey('stocks.ticker'), index=True)
    date = Column(Date, index=True)
    
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Integer)
    
    # Indicators
    rsi_14 = Column(Float, nullable=True)
    ema_200 = Column(Float, nullable=True)
    ema_50 = Column(Float, nullable=True)
    ema_20 = Column(Float, nullable=True)
    
    stock = relationship("Stock", back_populates="prices")

class Trade(Base):
    __tablename__ = "trades"
    
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, ForeignKey('stocks.ticker'), index=True)
    signal_date = Column(Date)
    entry_date = Column(Date, nullable=True)
    entry_price = Column(Float)
    sl_price = Column(Float)
    tp_price = Column(Float)
    status = Column(String, default="PENDING") # PENDING, OPEN, CLOSED, CANCELLED
    outcome = Column(String, nullable=True) # WIN, LOSS
    exit_date = Column(Date, nullable=True)
    exit_price = Column(Float, nullable=True)
    pnl = Column(Float, nullable=True)
    ema_50 = Column(Float, nullable=True)
    ema_20 = Column(Float, nullable=True)
    
    stock = relationship("Stock", back_populates="trades")

# Create database connection
# Ensure data directory exists
os.makedirs("data", exist_ok=True)
DB_PATH = "sqlite:///data/market_data.db"
engine = create_engine(DB_PATH, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)
    print("Database initialized.")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
