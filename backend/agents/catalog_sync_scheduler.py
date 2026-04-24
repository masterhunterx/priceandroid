"""
Catalog Sync Scheduler — Resincronización periódica por tienda
==============================================================
Mantiene el catálogo de cada supermercado alineado con su sitio web.
Corre en background con horarios escalonados para no saturar las APIs.

Estrategia por tienda (configurable via env vars):
  - Jumbo       → resync completo cada 24h, por categorías principales
  - Santa Isabel → cada 24h
  - Lider       → cada 24h
  - Unimarc     → cada 24h

Qué hace en cada ciclo por tienda:
  1. Consulta las categorías top de la BD (top_category más frecuentes)
  2. Ejecuta scraper para cada categoría (máx N páginas)
  3. Upsert de productos nuevos y actualizados
  4. Marca como out_of_stock los que desaparecieron del sitio
  5. Reporta a Discord lo que cambió
"""

import os
import time
import logging
import threading
from datetime import datetime, timezone

logger = logging.getLogger("AntigravityAPI")
UTC = timezone.utc

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "")

# Intervalo base por tienda (horas). Escalonado para no atacar a todas a la vez.
STORE_SCHEDULES = {
    "jumbo":         int(os.getenv("SYNC_INTERVAL_JUMBO",         "24")),
    "santa_isabel":  int(os.getenv("SYNC_INTERVAL_SANTA_ISABEL",  "24")),
    "lider":         int(os.getenv("SYNC_INTERVAL_LIDER",         "24")),
    "unimarc":       int(os.getenv("SYNC_INTERVAL_UNIMARC",       "24")),
}

# Arranque escalonado para no golpear todas las tiendas al mismo tiempo
STORE_STARTUP_DELAY = {
    "jumbo":        120,    # 2 min — arranca rápido tras deploy
    "santa_isabel": 300,    # 5 min
    "lider":        600,    # 10 min (circuit breaker lo pausará igual si está OPEN)
    "unimarc":      480,    # 8 min
}

MAX_PAGES_PER_CATEGORY = int(os.getenv("SYNC_MAX_PAGES", "3"))
MAX_CATEGORIES         = int(os.getenv("SYNC_MAX_CATEGORIES", "15"))


def _send_discord(content: str) -> None:
    if not DISCORD_WEBHOOK:
        return
    try:
        import requests as _req
        _req.post(DISCORD_WEBHOOK, json={"content": content}, timeout=10)
    except Exception as e:
        logger.warning(f"[CatalogSync] Discord send failed: {e}")


def _get_top_categories(db, store_slug: str) -> list[str]:
    """Obtiene las categorías más frecuentes de una tienda para guiar el scraper."""
    from sqlalchemy import text
    rows = db.execute(text("""
        SELECT sp.top_category, COUNT(*) as cnt
        FROM store_products sp
        JOIN stores s ON sp.store_id = s.id
        WHERE s.slug = :slug
          AND sp.top_category IS NOT NULL
          AND sp.top_category != ''
        GROUP BY sp.top_category
        ORDER BY cnt DESC
        LIMIT :limit
    """), {"slug": store_slug, "limit": MAX_CATEGORIES}).fetchall()
    return [r[0] for r in rows]


def sync_store(store_slug: str) -> dict:
    """
    Ejecuta un ciclo completo de resync para una tienda.
    Devuelve estadísticas del ciclo.
    """
    from core.db import get_session
    from core.models import Store
    from domain.ingest import scrape_store, upsert_store_products

    stats = {"store": store_slug, "categories": 0, "scraped": 0, "upserted": 0, "errors": 0}
    logger.info(f"[CatalogSync] Iniciando resync de {store_slug}...")

    try:
        with get_session() as db:
            store = db.query(Store).filter_by(slug=store_slug).first()
            if not store:
                logger.warning(f"[CatalogSync] Tienda no encontrada: {store_slug}")
                return stats

            categories = _get_top_categories(db, store_slug)

        if not categories:
            logger.warning(f"[CatalogSync] Sin categorías para {store_slug}")
            return stats

        stats["categories"] = len(categories)

        for category in categories:
            try:
                logger.info(f"[CatalogSync] {store_slug} → '{category}'")
                products = scrape_store(store_slug, category, pages=MAX_PAGES_PER_CATEGORY)
                stats["scraped"] += len(products)

                if products:
                    with get_session() as db:
                        store = db.query(Store).filter_by(slug=store_slug).first()
                        saved = upsert_store_products(db, store, products)
                        stats["upserted"] += len(saved)

                # Pausa entre categorías para no saturar la API de la tienda
                time.sleep(3)

            except Exception as e:
                logger.error(f"[CatalogSync] Error en categoría '{category}' ({store_slug}): {e}")
                stats["errors"] += 1
                time.sleep(10)

    except Exception as e:
        logger.error(f"[CatalogSync] Error general en {store_slug}: {e}", exc_info=True)
        stats["errors"] += 1

    logger.info(
        f"[CatalogSync] {store_slug} completado — "
        f"{stats['scraped']} scraped, {stats['upserted']} upserted, {stats['errors']} errores"
    )
    return stats


def _discord_report(stats: dict) -> None:
    ts = datetime.now(UTC).strftime("%d/%m %H:%M")
    icon = "✅" if stats["errors"] == 0 else "⚠️"
    _send_discord(
        f"**{icon} CatalogSync — {stats['store'].title()}** `{ts} UTC`\n"
        f"```\n"
        f"Categorías escaneadas : {stats['categories']}\n"
        f"Productos encontrados : {stats['scraped']:,}\n"
        f"Registros actualizados: {stats['upserted']:,}\n"
        f"Errores               : {stats['errors']}\n"
        f"```"
    )


def _store_loop(store_slug: str):
    """Loop independiente por tienda con su propio intervalo."""
    delay = STORE_STARTUP_DELAY.get(store_slug, 600)
    interval_h = STORE_SCHEDULES.get(store_slug, 24)

    logger.info(f"[CatalogSync] {store_slug} arrancará en {delay//60} min, luego cada {interval_h}h.")
    time.sleep(delay)

    while True:
        try:
            stats = sync_store(store_slug)
            _discord_report(stats)
        except Exception as e:
            logger.error(f"[CatalogSync] Error inesperado en loop de {store_slug}: {e}", exc_info=True)
        time.sleep(interval_h * 3600)


def start_catalog_sync_scheduler():
    """Lanza un hilo daemon por cada tienda registrada."""
    stores = list(STORE_SCHEDULES.keys())
    for slug in stores:
        t = threading.Thread(
            target=_store_loop,
            args=(slug,),
            name=f"CatalogSync_{slug}",
            daemon=True,
        )
        t.start()
        logger.info(f"[CatalogSync] Scheduler iniciado para {slug}.")
