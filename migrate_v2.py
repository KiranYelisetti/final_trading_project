from sqlalchemy import create_engine, text
import os

DB_PATH = "sqlite:///data/market_data.db"
engine = create_engine(DB_PATH)

def migrate():
    print("Migrating database schema...")
    with engine.connect() as conn:
        try:
            # Check if column exists
            result = conn.execute(text("PRAGMA table_info(trades)")).fetchall()
            columns = [row[1] for row in result]
            
            if 'reason' not in columns:
                print("Adding 'reason' column to trades table...")
                conn.execute(text("ALTER TABLE trades ADD COLUMN reason TEXT"))
                print("Column added.")
            else:
                print("'reason' column already exists.")
                
        except Exception as e:
            print(f"Migration failed: {e}")

if __name__ == "__main__":
    migrate()
