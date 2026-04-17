import os
import sys

# Add backend to path so imports work correctly
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from core.db import get_session, init_db
from core.models import Product, StoreProduct, ProductMatch
from domain.matcher import compute_match_score, enrich_with_weight

def cleanup_invalid_matches():
    init_db()
    with get_session() as s:
        sps = s.query(StoreProduct).filter(StoreProduct.product_id.isnot(None)).all()
        invalid_count = 0
        
        for sp in sps:
            canonical = s.query(Product).filter_by(id=sp.product_id).first()
            if not canonical: continue
            
            prod_a = {
                "name": canonical.canonical_name,
                "brand": canonical.brand,
                "top_category": canonical.category,
                "weight_value": canonical.weight_value,
                "weight_unit": canonical.weight_unit,
            }
            
            prod_b = {
                "name": sp.name,
                "brand": sp.brand,
                "top_category": sp.top_category,
                "image_url": sp.image_url,
            }
            enrich_with_weight(prod_b)
            
            score = compute_match_score(prod_a, prod_b)
            
            if score < 0.75: # Auto match threshold
                # INVALID MATCH! Delete ProductMatch and clear sp.product_id
                pm = s.query(ProductMatch).filter_by(store_product_id=sp.id).first()
                if pm:
                    s.delete(pm)
                sp.product_id = None
                invalid_count += 1
                print(f"[REMOVED] '{canonical.canonical_name}' =/=> '{sp.name}' (Score: {score})")
                
        s.commit()
        print(f"Total invalid links broken: {invalid_count}")

if __name__ == "__main__":
    cleanup_invalid_matches()
