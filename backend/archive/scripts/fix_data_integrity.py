import os
import sys

# Setup path so it can import from backend
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.db import get_session
from core.models import StoreProduct, Product, Store, ProductMatch
from domain.matcher import compute_match_score, enrich_with_weight

def fix_integrity_errors():
    print("\n=== DATA INTEGRITY CLEANUP SCRIPT ===")
    with get_session() as s:
        # Find all ProductMatch entries
        matches = s.query(ProductMatch).all()
        print(f"Checking {len(matches)} match links...")
        
        broken_links = 0
        separated_products = 0
        
        for m in matches:
            sp = s.get(StoreProduct, m.store_product_id)
            canonical = s.get(Product, m.product_id)
            
            if not sp or not canonical:
                continue
                
            # Simulate a match between the store product and its current canonical product info
            # We treat the canonical as a pseudo-product for scoring
            canonical_dict = {
                "name": canonical.canonical_name,
                "brand": canonical.brand,
                "top_category": canonical.category,
                "weight_value": canonical.weight_value,
                "weight_unit": canonical.weight_unit
            }
            sp_dict = {
                "name": sp.name,
                "brand": sp.brand,
                "top_category": sp.top_category
            }
            enrich_with_weight(sp_dict)
            
            score = compute_match_score(sp_dict, canonical_dict)
            
            # If score is now 0.0 (strict mismatch), break the link
            if score == 0.0:
                print(f"[FIX] Breaking Mismatch ID {m.id}: {sp.name} <==X==> {canonical.canonical_name}")
                
                # 1. Unlink store product
                sp.product_id = None
                
                # 2. Delete the match record
                s.delete(m)
                broken_links += 1
                
                # 3. Create a NEW canonical product for the orphaned StoreProduct
                new_p = Product(
                    canonical_name=sp.name,
                    brand=sp.brand,
                    category=sp.top_category,
                    category_path=sp.category_path,
                    weight_value=sp_dict.get("weight_value"),
                    weight_unit=sp_dict.get("weight_unit"),
                    image_url=sp.image_url
                )
                s.add(new_p)
                s.flush()
                
                sp.product_id = new_p.id
                separated_products += 1
        
        s.commit()
        print(f"\nSummary:")
        print(f"  - Broken links: {broken_links}")
        print(f"  - New canonical products created: {separated_products}")
        print("Cleanup complete!")

if __name__ == "__main__":
    fix_integrity_errors()
