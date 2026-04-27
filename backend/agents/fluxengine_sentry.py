
import logging
import time
import os
import sys
import random
from datetime import datetime, timezone

sys.path.append(os.path.join(os.getcwd(), 'backend'))

from core.db import get_session
from core.models import StoreProduct, UserPreference, Price
from domain.ingest import sync_single_store_product
from core.shield import Shield3

logger = logging.getLogger("AntigravityAPI")


def fluxengine_sentry_loop():
    """
    FluxEngine Sentry Agent Loop
    Continuous scan logic that monitors favorites and high-priority products.
    """
    logger.info("FluxEngine Sentry: Iniciando guardian de precios autonomo...")

    while True:
        try:
            with get_session() as session:
                # Priority 1: User Favorites
                favorites = session.query(UserPreference).all()
                fav_product_ids = [f.product_id for f in favorites]

                # Priority 2: Daily Deals (Has discount)
                deals = session.query(StoreProduct).join(Price).filter(Price.has_discount == True).limit(10).all()
                deal_ids = [d.product_id for d in deals if d.product_id]

                target_ids = list(set(fav_product_ids + deal_ids))
                random.shuffle(target_ids)

                if not target_ids:
                    from core.circuit_breaker import is_open as _cb_is_open
                    random_probs = (
                        session.query(StoreProduct)
                        .filter(StoreProduct.in_stock == True)
                        .order_by(StoreProduct.last_sync.asc().nullsfirst())
                        .limit(20)
                        .all()
                    )
                    for sp in random_probs[:5]:
                        if _cb_is_open(sp.store.slug):
                            continue
                        logger.debug(f"Sentry [Audit Extra]: Revisando {sp.name}...")
                        sync_single_store_product(session, sp.id)
                else:
                    # Batch-load StoreProducts para todos los target_ids — evita N+1
                    sp_list_all = (
                        session.query(StoreProduct)
                        .filter(StoreProduct.product_id.in_(target_ids[:15]))
                        .all()
                    )
                    sp_ids = [sp.id for sp in sp_list_all]

                    # Batch-load historial de precios para anomaly detection
                    from sqlalchemy import func as _func
                    recent_prices: dict[int, list] = {}
                    if sp_ids:
                        price_rows = (
                            session.query(Price.store_product_id, Price.price)
                            .filter(Price.store_product_id.in_(sp_ids))
                            .order_by(Price.store_product_id, Price.scraped_at.desc())
                            .limit(len(sp_ids) * 5)
                            .all()
                        )
                        for sp_id, price_val in price_rows:
                            recent_prices.setdefault(sp_id, []).append(price_val)

                    for sp in sp_list_all:
                        logger.debug(f"Sentry [Audit Prioritario]: Sincronizando {sp.name} en {sp.store.name}...")
                        old_price = sp.latest_price.price if sp.latest_price else None
                        sync_single_store_product(session, sp.id)

                        session.refresh(sp)
                        new_price = sp.latest_price.price if sp.latest_price else None

                        if old_price and new_price and old_price != new_price:
                            history = recent_prices.get(sp.id, [])
                            is_anomaly, anomaly_msg = Shield3.detect_anomalous_price(history, new_price)
                            if is_anomaly:
                                logger.warning(f"[INTEGRITY ALERT] {sp.name}: {anomaly_msg}")

                        time.sleep(1)

                session.commit()

            time.sleep(30)

        except Exception as e:
            logger.error(f"FluxEngine Sentry Error: {e}", exc_info=True)
            time.sleep(10)


if __name__ == "__main__":
    fluxengine_sentry_loop()
