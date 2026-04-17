from sqlalchemy import create_engine, text
import time

DB_PATH = "c:/Users/Cris/Desktop/Price/backend/price.db"
engine = create_engine(f"sqlite:///{DB_PATH}")

def run_update():
    max_retries = 5
    for i in range(max_retries):
        try:
            with engine.connect() as conn:
                print(f"Attempt {i+1}: Updating schema...")
                
                # Check current columns
                res = conn.execute(text("PRAGMA table_info(branches);"))
                cols = [row[1] for row in res.fetchall()]
                print(f"Current columns: {cols}")
                
                if 'latitude' not in cols:
                    conn.execute(text("ALTER TABLE branches ADD COLUMN latitude FLOAT;"))
                    print("Added latitude column.")
                else:
                    print("latitude column already exists.")

                if 'longitude' not in cols:
                    conn.execute(text("ALTER TABLE branches ADD COLUMN longitude FLOAT;"))
                    print("Added longitude column.")
                else:
                    print("longitude column already exists.")
                
                conn.commit()
                print("Schema update SUCCESS.")
                return True
        except Exception as e:
            print(f"Error on attempt {i+1}: {e}")
            if "locked" in str(e).lower():
                print("DB is locked, retrying in 2 seconds...")
                time.sleep(2)
            else:
                break
    return False

if __name__ == "__main__":
    run_update()
