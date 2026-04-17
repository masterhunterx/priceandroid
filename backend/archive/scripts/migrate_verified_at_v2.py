
import os
import sys

# Ensure backend is in path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from sqlalchemy import text
from core.db import engine

def migrate():
    print(f"Engine URL: {engine.url}")
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE branches ADD COLUMN verified_at DATETIME"))
            conn.commit()
            print("FluxEngine: Column verified_at added successfully via SQLAlchemy.")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("FluxEngine: Column verified_at already exists.")
            else:
                print(f"Error: {e}")

if __name__ == "__main__":
    migrate()
