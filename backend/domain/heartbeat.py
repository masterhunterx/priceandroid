"""
Heartbeat Service: Priority Price Sync
========================================
Synchronizes prices for user-favorited products 
more frequently than the full catalog crawl.
"""

from datetime import datetime, timezone
import time
from core.db import get_session
from core.models import UserPreference, Product, StoreProduct, Store, Price
from domain.ingest import scrape_store, upsert_store_products

UTC = timezone.utc

def sync_favorites():
    """Update prices for all products favorited by users."""
    print(f"\n  [HEARTBEAT] Starting priority sync for favorites...")
    start_time = datetime.now()
    
    with get_session() as session:
        # Get all distinct favorited products
        favorites = session.query(UserPreference).all()
        fav_product_ids = sorted(list(set(fav.product_id for fav in favorites)))
        
        if not fav_product_ids:
            print("  [HEARTBEAT] No favorites to sync.")
            return

        print(f"  [HEARTBEAT] Found {len(fav_product_ids)} favorite product(s) to update.")
        
        updated_count = 0
        for pid in fav_product_ids:
            product = session.get(Product, pid)
            if not product:
                continue
            
            print(f"\n  Updating: {product.canonical_name} ({product.brand})")
            
            # Find all store products linked to this canonical product
            store_links = session.query(StoreProduct).filter_by(product_id=pid).all()
            
            for sp in store_links:
                store = sp.store
                print(f"    - Scraping {store.name} for: {sp.name[:40]}...")
                
                try:
                    # Use the specific product name as a search query (1 page)
                    # This is the most reliable way to get the current price for that item
                    results = scrape_store(store.slug, sp.name, pages=1)
                    
                    if results:
                        # Find the exact match in results by external_id
                        match = next((r for r in results if str(r.get("product_id")) == sp.external_id), None)
                        
                        if match:
                            # Use ingest's upsert logic (handles hashes and lazy pricing)
                            upsert_store_products(session, store, [match])
                            updated_count += 1
                        else:
                            print(f"      [WARNING] Could not find exact ID {sp.external_id} in search results.")
                    else:
                        print(f"      [WARNING] No results found for '{sp.name}'.")
                        
                except Exception as e:
                    print(f"      [ERROR] Sync failed for {store.slug}: {e}")
                
                # Sleep briefly to avoid rate limits
                time.sleep(1)
            
            session.commit() # Commit after each canonical product
            
    elapsed = datetime.now() - start_time
    print(f"\n  [HEARTBEAT] Priority sync completed. Updated {updated_count} price points.")
    print(f"  [HEARTBEAT] Duration: {elapsed.total_seconds():.2f}s")

if __name__ == "__main__":
    sync_favorites()
