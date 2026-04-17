import os
DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "grocery.db"
)
print(f"PATH: {DEFAULT_DB_PATH}")
print(f"EXISTS: {os.path.exists(DEFAULT_DB_PATH)}")
