import sys
import os
import traceback

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from core.db import get_session
from core.models import Product, StoreProduct, Store, Price
from api.main import SearchResponse, ProductOut, PricePointOut, _build_price_points, _best_price_info, _get_price_insight, _check_favorite
from sqlalchemy import func

def debug_search(q="leche"):
    print(f"--- DEBUG SEARCH FOR '{q}' ---")
    try:
        with get_session() as session:
            # Replicating main.py logic
            main_query = session.query(StoreProduct)
            if q:
                tokens = q.strip().split()
                for token in tokens:
                    term = f"%{token.lower()}%"
                    main_query = main_query.filter(
                        (func.lower(StoreProduct.name).like(term)) |
                        (func.lower(StoreProduct.brand).like(term))
                    )
            
            all_store_products = main_query.all()
            print(f"[+] Found {len(all_store_products)} matching StoreProducts.")
            
            results = []
            seen_canonical_ids = set()
            seen_sp_names = set()
            
            for sp in all_store_products:
                print(f"[*] Processing SP {sp.id}: {sp.name[:20]}")
                if sp.product_id:
                    if sp.product_id in seen_canonical_ids:
                        continue
                    
                    p = session.get(Product, sp.product_id)
                    if p:
                        seen_canonical_ids.add(p.id)
                        price_points = _build_price_points(session, p.id)
                        if price_points:
                            results.append(ProductOut(
                                id=p.id,
                                name=p.canonical_name,
                                brand=p.brand or "",
                                category=p.category or "",
                                image_url=p.image_url or "",
                                prices=price_points,
                                best_price=0, # Simplified
                                best_store="",
                                best_store_slug="",
                                price_insight=None,
                                is_favorite=False,
                            ))
                            continue
                
                # Standalone
                latest = sp.latest_price
                price = latest.price if latest else 0
                price_point = PricePointOut(
                    store_id=sp.store_id,
                    store_name=sp.store.name,
                    store_slug=sp.store.slug,
                    store_logo=sp.store.logo_url or "",
                    price=price,
                    list_price=latest.list_price if latest else 0,
                    last_sync=sp.last_sync.isoformat() if sp.last_sync else "",
                )
                results.append(ProductOut(
                    id=1000000 + sp.id,
                    name=sp.name,
                    brand=sp.brand or "",
                    category=sp.top_category or "",
                    image_url=sp.image_url or "",
                    prices=[price_point],
                    best_price=price,
                    best_store=sp.store.name,
                    best_store_slug=sp.store.slug,
                    price_insight=None,
                    is_favorite=False,
                ))
                if len(results) >= 20: break
            
            print(f"[SUCCESS] Search returned {len(results)} results.")
            
    except Exception as e:
        print("\n--- CRASH DETECTED ---")
        traceback.print_exc()

if __name__ == "__main__":
    debug_search()
