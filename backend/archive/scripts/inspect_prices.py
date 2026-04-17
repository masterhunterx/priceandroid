
import os
import sys
# Add backend to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from core.db import get_session
from core.models import Product, StoreProduct, Price

def inspect_product(product_id):
    with get_session() as session:
        # Check if virtual ID
        if product_id >= 1000000:
            sp_id = product_id - 1000000
            sp = session.get(StoreProduct, sp_id)
            if not sp:
                print(f"StoreProduct {sp_id} not found.")
                return
            sps = [sp]
            print(f"--- Virtual Product (StoreProduct ID: {sp_id}) ---")
        else:
            product = session.get(Product, product_id)
            if not product:
                print(f"Product {product_id} not found.")
                return
            print(f"--- Product ---")
            print(f"ID: {product.id}, Name: {product.canonical_name}, Brand: {product.brand}")
            sps = session.query(StoreProduct).filter_by(product_id=product.id).all()
        
        for sp in sps:
            print(f"\n  --- StoreProduct ---")
            print(f"  ID: {sp.id}, Store: {sp.store.name}, Name: {sp.name}, SKU: {sp.sku_id}")
            
            # Latest price
            latest = session.query(Price).filter_by(store_product_id=sp.id).order_by(Price.scraped_at.desc()).first()
            if latest:
                print(f"    In DB: Price={latest.price}, Reg={latest.list_price}, Card={latest.promo_price}")
                print(f"    Sync: {latest.scraped_at}")
            else:
                print(f"    No prices recorded.")

if __name__ == "__main__":
    # Based on URL from screenshot http://localhost:5000/#/product/1000009
    inspect_product(1000009)
