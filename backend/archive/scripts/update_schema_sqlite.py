import sqlite3
import os

# Base directory for the project
BASE_DIR = "c:/Users/Cris/Desktop/Price/backend"
DB_PATH = os.path.join(BASE_DIR, "data", "grocery.db")

def update():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: DB not found at {DB_PATH}")
        return False
        
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check current columns
        cursor.execute("PRAGMA table_info(branches);")
        cols = [row[1] for row in cursor.fetchall()]
        print(f"Current columns (branches): {cols}")
        
        if not cols:
            print("ERROR: Table 'branches' not found. Run init_db first.")
            return False

        if 'latitude' not in cols:
            cursor.execute("ALTER TABLE branches ADD COLUMN latitude REAL;")
            print("Added latitude.")
        if 'longitude' not in cols:
            cursor.execute("ALTER TABLE branches ADD COLUMN longitude REAL;")
            print("Added longitude.")
            
        conn.commit()
        conn.close()
        print("SQLITE3 UPDATE SUCCESS.")
        return True
    except Exception as e:
        print(f"SQLITE3 ERROR: {e}")
        return False

if __name__ == "__main__":
    update()
