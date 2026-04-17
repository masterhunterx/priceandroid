"""
Scraper Health Agent
====================
Dos responsabilidades autónomas que corren en background:

1. HEALTH CHECK (cada hora)
   Prueba un scrape de "leche" en cada tienda activa.
   Si falla 2 veces seguidas → alerta a Discord.
   Si se recupera → notifica la recuperación.

2. RETRY not_found (cada 30 min)
   Busca StoreProducts marcados not_found (in_stock=False) en las últimas 6h.
   Los reintenta usando el nombre del producto como query de búsqueda.
   Si los encuentra → actualiza precio y marca in_stock=True.
   Solo afecta a tiendas con circuito CERRADO.
"""

import os
import time
import logging
import threading
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("AntigravityAPI")
UTC = timezone.utc

DISCORD_WEBHOOK      = os.getenv("DISCORD_WEBHOOK_URL", "")
HEALTH_INTERVAL_SEC  = 3600   # 1h entre health checks
RETRY_INTERVAL_SEC   = 1800   # 30min entre ciclos de retry
RETRY_WINDOW_HOURS   = 6      # solo reintenta not_found de las últimas 6h
RETRY_BATCH_SIZE     = 30     # máx productos a reintentar por ciclo por tienda


def _discord(msg: str) -> None:
    if not DISCORD_WEBHOOK:
        return
    try:
        import requests as _r
        _r.post(DISCORD_WEBHOOK, json={"content": msg}, timeout=10)
    except Exception as e:
        logger.warning(f"[HealthAgent] Discord send failed: {e}")


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------

_consecutive_failures: dict[str, int] = {}
_store_alerted: dict[str, bool] = {}

SCRAPERS = {
    "jumbo":         "data.sources.jumbo_scraper",
    "santa_isabel":  "data.sources.santa_isabel_scraper",
    "lider":         "data.sources.lider_scraper",
    "unimarc":       "data.sources.unimarc_scraper",
}


def _check_store(store_slug: str) -> tuple[bool, str]:
    """Hace un scrape de 'leche' (1 página) y verifica que devuelva resultados."""
    try:
        mod = __import__(SCRAPERS[store_slug], fromlist=["create_session", "search_products"])
        session = mod.create_session()
        results = mod.search_products(session, "leche", max_pages=1)
        if results and len(results) > 0:
            return True, f"{len(results)} productos"
        return False, "0 resultados"
    except Exception as e:
        return False, str(e)[:120]


def run_health_checks() -> None:
    logger.info("[HealthAgent] Iniciando health checks de scrapers...")
    from core.circuit_breaker import record_success, record_failure

    for store in SCRAPERS:
        ok, detail = _check_store(store)
        if ok:
            _consecutive_failures[store] = 0
            record_success(store)
            if _store_alerted.get(store):
                _store_alerted[store] = False
                _discord(
                    f"✅ **[HealthAgent] {store.upper()} recuperado**\n"
                    f"El scraper responde correctamente ({detail})."
                )
                logger.info(f"[HealthAgent] {store} recuperado — {detail}")
        else:
            _consecutive_failures[store] = _consecutive_failures.get(store, 0) + 1
            failures = _consecutive_failures[store]
            tripped = record_failure(store)

            logger.warning(f"[HealthAgent] {store} falló health check ({failures} consecutivos): {detail}")

            if failures >= 2 and not _store_alerted.get(store):
                _store_alerted[store] = True
                _discord(
                    f"🚨 **[HealthAgent] {store.upper()} NO RESPONDE**\n"
                    f"Fallos consecutivos: `{failures}`\n"
                    f"Error: `{detail}`\n"
                    f"{'⚡ Circuito abierto — sync pausado 2h.' if tripped else ''}"
                )

    logger.info("[HealthAgent] Health checks completados.")


def health_check_loop() -> None:
    logger.info("[HealthAgent] Loop de health checks iniciado (cada 1h).")
    time.sleep(120)  # esperar arranque del servidor
    while True:
        try:
            run_health_checks()
        except Exception as e:
            logger.error(f"[HealthAgent] Error en health check loop: {e}")
        time.sleep(HEALTH_INTERVAL_SEC)


# ---------------------------------------------------------------------------
# Retry not_found
# ---------------------------------------------------------------------------

def run_not_found_retry() -> None:
    """
    Busca StoreProducts marcados not_found recientemente y los reintenta
    usando el nombre del producto como query de búsqueda.
    """
    from core.db import get_session
    from core.models import StoreProduct, Store
    from core.circuit_breaker import is_open
    from sqlalchemy import text

    logger.info("[HealthAgent] Iniciando retry de productos not_found...")
    cutoff = datetime.now(UTC) - timedelta(hours=RETRY_WINDOW_HOURS)
    retried = recovered = 0

    with get_session() as db:
        rows = db.execute(text("""
            SELECT sp.id, sp.name, sp.sku_id, sp.external_id, s.slug
            FROM store_products sp
            JOIN stores s ON sp.store_id = s.id
            WHERE sp.in_stock = FALSE
              AND sp.last_sync >= :cutoff
              AND sp.name IS NOT NULL
              AND sp.name != ''
            ORDER BY sp.last_sync DESC
            LIMIT :limit
        """), {"cutoff": cutoff, "limit": RETRY_BATCH_SIZE * len(SCRAPERS)}).fetchall()

    # Agrupar por tienda
    by_store: dict[str, list] = {}
    for row in rows:
        by_store.setdefault(row.slug, []).append(row)

    for store_slug, products in by_store.items():
        if store_slug not in SCRAPERS:
            continue
        if is_open(store_slug):
            logger.info(f"[HealthAgent] Retry {store_slug} omitido — circuito abierto.")
            continue

        mod = __import__(SCRAPERS[store_slug], fromlist=["create_session", "fetch_single_product"])
        session = mod.create_session()

        for row in products[:RETRY_BATCH_SIZE]:
            retried += 1
            try:
                sku = row.sku_id or row.external_id
                # Llamar con nombre si el scraper lo soporta
                fn = mod.fetch_single_product
                import inspect
                supports_name = "product_name" in inspect.signature(fn).parameters
                result = fn(session, sku, product_name=row.name) if supports_name else fn(session, sku)

                if result:
                    with get_session() as db:
                        sp = db.get(StoreProduct, row.id)
                        if sp:
                            sp.in_stock = True
                            sp.last_sync = datetime.now(UTC)
                            if result.get("price"):
                                from domain.ingest import upsert_store_products
                                store_obj = db.query(Store).filter_by(slug=store_slug).first()
                                if store_obj:
                                    upsert_store_products(db, store_obj, [result])
                            db.commit()
                            recovered += 1
                            logger.info(f"[HealthAgent] Recuperado: {row.name[:40]} en {store_slug}")
            except Exception as e:
                logger.debug(f"[HealthAgent] Retry falló para {row.name[:30]}: {e}")
            time.sleep(0.5)

    if retried:
        logger.info(f"[HealthAgent] Retry completado: {retried} intentados, {recovered} recuperados.")
        if recovered:
            _discord(
                f"♻️ **[HealthAgent] Retry not_found completado**\n"
                f"Recuperados: `{recovered}` / intentados: `{retried}`"
            )


def retry_loop() -> None:
    logger.info("[HealthAgent] Loop de retry not_found iniciado (cada 30min).")
    time.sleep(300)  # esperar arranque
    while True:
        try:
            run_not_found_retry()
        except Exception as e:
            logger.error(f"[HealthAgent] Error en retry loop: {e}")
        time.sleep(RETRY_INTERVAL_SEC)


def start_scraper_health_agent() -> None:
    threading.Thread(target=health_check_loop, name="ScraperHealthCheck", daemon=True).start()
    threading.Thread(target=retry_loop,        name="ScraperRetry",       daemon=True).start()
    logger.info("[HealthAgent] Agente de salud de scrapers iniciado (health check + retry).")
