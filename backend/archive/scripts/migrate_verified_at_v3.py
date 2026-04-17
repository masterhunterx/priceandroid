
import os
import sys

# Ensure backend is in path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from sqlalchemy import text
from core.db import get_engine

def migrate():
    engine = get_engine()
    print(f"Engine URL: {engine.url}")
    with engine.connect() as conn:
        try:
            # SQLAlchemy 2.0+ requires commit() for DDL in some cases, or autocommit
            conn.execute(text("ALTER TABLE branches ADD COLUMN verified_at DATETIME"))
            conn.commit()
            print("FluxEngine: Column 'verified_at' added successfully.")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("FluxEngine: Column 'verified_at' already exists.")
            else:
                print(f"Error: {e}")

if __name__ == "__main__":
    migrate()
