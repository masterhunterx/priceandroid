
import os
import sys
# Add backend to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from core.db import get_session
from core.models import StoreProduct, Product, Price

def check_chiquitin():
    with get_session() as session:
        # Search for StoreProducts containing 'Chiquitin'
        sps = session.query(StoreProduct).filter(StoreProduct.name.like('%Chiquitin%')).all()
        print(f"Found {len(sps)} StoreProducts for 'Chiquitin':")
        for sp in sps:
            latest = session.query(Price).filter_by(store_product_id=sp.id).order_by(Price.scraped_at.desc()).first()
            p_id = sp.product_id
            print(f" - [{sp.store.name}] ID: {sp.id}, Name: {sp.name}, Canonical ID: {p_id}, Price: {latest.price if latest else 'N/A'}")
            
        # Search for Products (canonical) containing 'Chiquitin'
        products = session.query(Product).filter(Product.canonical_name.like('%Chiquitin%')).all()
        print(f"\nFound {len(products)} Canonical Products for 'Chiquitin':")
        for p in products:
            stores = session.query(StoreProduct).filter_by(product_id=p.id).all()
            store_names = [sp.store.name for sp in stores]
            print(f" - ID: {p.id}, Name: {p.canonical_name}, Stores: {', '.join(store_names)}")

if __name__ == "__main__":
    check_chiquitin()
