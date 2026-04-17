
import time
import os
import sys
from datetime import datetime, timezone
import random

# Ensure backend is in path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from core.db import get_session
from core.models import StoreProduct, UserPreference, Price
from domain.ingest import sync_single_store_product
from core.shield import Shield3

def fluxengine_sentry_loop():
    """
    FluxEngine Sentry Agent Loop
    Continuous scan logic that monitors favorites and high-priority products.
    """
    print("FluxEngine Sentry: Iniciando guardian de precios autonomo...")
    
    while True:
        try:
            with get_session() as session:
                # Priority 1: User Favorites
                favorites = session.query(UserPreference).all()
                fav_product_ids = [f.product_id for f in favorites]
                
                # Priority 2: Daily Deals (Has discount)
                deals = session.query(StoreProduct).join(Price).filter(Price.has_discount == True).limit(10).all()
                deal_ids = [d.product_id for d in deals if d.product_id]
                
                # Combine and shuffle to avoid getting stuck
                target_ids = list(set(fav_product_ids + deal_ids))
                random.shuffle(target_ids)
                
                if not target_ids:
                    # If nothing to watch, pick some random products
                    random_probs = session.query(StoreProduct).order_by(StoreProduct.last_sync.asc()).limit(5).all()
                    for sp in random_probs:
                        print(f"Sentry [Audit Extra]: Revisando {sp.name}...")
                        sync_single_store_product(session, sp.id)
                else:
                    # Scaling up for KAIROS v2.0
                    for pid in target_ids[:15]: # Increased batch size
                        sp_list = session.query(StoreProduct).filter_by(product_id=pid).all()
                        for sp in sp_list:
                            print(f"Sentry [Audit Prioritario]: Sincronizando {sp.name} en {sp.store.name}...")
                            
                            # Pre-sync snapshot for integrity check
                            old_price = sp.latest_price.price if sp.latest_price else None
                            
                            sync_single_store_product(session, sp.id)
                            
                            # Shield 3.0: Integrity Check
                            session.refresh(sp)
                            new_price = sp.latest_price.price if sp.latest_price else None
                            
                            if old_price and new_price and old_price != new_price:
                                history = [p.price for p in session.query(Price).filter_by(store_product_id=sp.id).order_by(Price.scraped_at.desc()).limit(5).all()]
                                is_anomaly, anomaly_msg = Shield3.detect_anomalous_price(history, new_price)
                                if is_anomaly:
                                    print(f"  [CRITICAL INTEGRITY ALERT] {sp.name}: {anomaly_msg}")
                                    # Here, a Mythos-level agent would trigger a re-verification or block the price update
                            
                            time.sleep(1) # Tiny sleep to avoid being blocked by store
                
                session.commit()
            
            # Wait between cycles
            time.sleep(30)
            
        except Exception as e:
            print(f"FluxEngine Sentry Error: {str(e)}")
            time.sleep(10)

if __name__ == "__main__":
    fluxengine_sentry_loop()
