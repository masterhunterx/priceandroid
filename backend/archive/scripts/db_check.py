import os
import sys

# Add current directory to path
sys.path.append(os.getcwd())

from core.db import get_session
from core.models import Product, StoreProduct

def check_db():
    try:
        with get_session() as s:
            p_count = s.query(Product).count()
            sp_count = s.query(StoreProduct).count()
            unmatched = s.query(StoreProduct).filter(StoreProduct.product_id == None).count()
            
            print(f"Products (Canonical): {p_count}")
            print(f"StoreProducts (Raw): {sp_count}")
            print(f"Unmatched StoreProducts: {unmatched}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_db()
