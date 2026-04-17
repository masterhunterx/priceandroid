import os
import sys

# Setup path so it can import from backend
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.db import get_session
from core.models import StoreProduct, Product, Store

def verify_fix():
    print("\n=== FINAL VERIFICATION AFTER CLEANUP ===")
    with get_session() as s:
        # 1. Check a known previously broken product
        p_molida = s.query(Product).filter(Product.canonical_name.like('%molida%')).all()
        for p in p_molida:
            sps = s.query(StoreProduct).filter_by(product_id=p.id).all()
            print(f"\nCanonical Product: {p.canonical_name} (ID: {p.id})")
            for sp in sps:
                st = s.query(Store).get(sp.store_id)
                print(f"  - {st.name}: {sp.name}")
                if "choclo" in sp.name.lower():
                    print("  [ERROR] Mismatch still remains!")
                else:
                    print("  [OK] No cross-category detected.")

        # 2. Find Choclo products as separate entities
        p_choclo = s.query(Product).filter(Product.canonical_name.like('%choclo%')).all()
        print(f"\nNow found {len(p_choclo)} separate Choclo canonical products.")
        for p in p_choclo:
            sps = s.query(StoreProduct).filter_by(product_id=p.id).all()
            print(f"  - {p.canonical_name} (Links: {len(sps)})")

if __name__ == "__main__":
    verify_fix()
