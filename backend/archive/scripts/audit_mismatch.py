import os
import sys

# Setup path so it can import from backend
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.db import get_session
from core.models import StoreProduct, Product, Store

def audit_all_matches():
    print("\n=== Auditing ALL Matches for Cross-Category Errors ===")
    with get_session() as s:
        products = s.query(Product).all()
        found_mismatch = False
        for p in products:
            sps = s.query(StoreProduct).filter_by(product_id=p.id).all()
            if len(sps) > 1:
                names = [sp.name.lower() for sp in sps]
                # Detection: One name has meat terms, another has veg terms
                has_meat = any("molida" in n or "vacuno" in n or "carne" in n or "sobrecostilla" in n for n in names)
                has_corn_or_other = any("choclo" in n or "maiz" in n or "arroz" in n or "leche" in n for n in names)
                
                # Check for "Carne" vs anything else completely different
                if has_meat and has_corn_or_other:
                    found_mismatch = True
                    print(f"\n[CRITICAL MISMATCH] Product ID {p.id}: {p.canonical_name}")
                    for sp in sps:
                        st = s.query(Store).get(sp.store_id)
                        print(f"  - {st.name}: {sp.name} | SKU: {sp.sku_id} | URL: {sp.product_url}")
        
        if not found_mismatch:
            print("No obvious meat-vs-corn mismatches found using keyword detection.")
            # Search specifically for the user's reported names
            p_molida = s.query(Product).filter(Product.canonical_name.like('%Molida%')).all()
            for p in p_molida:
                 print(f"\n[INFO] Checking links for: {p.canonical_name} (ID: {p.id})")
                 sps = s.query(StoreProduct).filter_by(product_id=p.id).all()
                 for sp in sps:
                     st = s.query(Store).get(sp.store_id)
                     print(f"  - {st.name}: {sp.name} | URL: {sp.product_url}")

if __name__ == "__main__":
    audit_all_matches()
