"""
FluxEngine CatalogBot - Agente de Cobertura de Catálogo
=========================================================
Agente autónomo que patrulla los supermercados de forma continua,
compara el catálogo scrapeado contra la base de datos de la app,
detecta productos faltantes e inserta los gaps automáticamente.

Filosofía:
  - NO re-ingesta lo que ya existe (hash-based change detection).
  - SÍ encuentra productos que existen en la tienda pero NOT en la app.
  - Foco en categorías esenciales: lácteos, aceites, harinas, conservas, etc.
  
Integración:
  - Se ejecuta como daemon thread al arrancar el backend.
  - Ciclo completo: cada SCAN_INTERVAL horas.
  - Logs estructurados con métricas de cobertura.
"""

import os
import sys
import time
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

# ─────────────────────────────────────────────
# Logging setup
# ─────────────────────────────────────────────
logger = logging.getLogger("catalog_bot")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _ch = logging.StreamHandler()
    _ch.setFormatter(logging.Formatter(
        "%(asctime)s [CatalogBot] %(levelname)s %(message)s",
        datefmt="%H:%M:%S"
    ))
    logger.addHandler(_ch)

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────

UTC = timezone.utc

# Hours between full catalog scans
SCAN_INTERVAL_HOURS = 6

# Queries to scan — estas cubren las categorías más buscadas en Chile
CATALOG_QUERIES = [
    # Lácteos
    "leche entera", "leche descremada", "leche en polvo", "yogurt", "quesillo", "queso",
    "crema", "mantequilla", "margarina",
    # Carnes
    "pollo", "carne molida", "vacuno", "filete", "cerdo", "pavo", "salchicha", "vienesa",
    # Verduras y frutas (más probables de encontrar online)
    "tomate", "lechuga", "zanahoria", "cebolla", "papa",
    # Panadería
    "pan molde", "pan tostado", "hallulla", "marraqueta",
    # Despensa
    "arroz", "fideos", "pasta", "espagueti", "jurel", "atun", "aceite", "maravilla",
    "azucar", "harina", "sal", "fideos", "lentejas", "porotos",
    # Bebidas
    "agua mineral", "jugo", "coca cola", "pepsi", "cerveza",
    # Limpieza
    "papel higienico", "servilletas", "detergente", "cloro", "suavizante",
    # Higiene
    "shampoo", "jabon", "pasta dental", "desodorante",
    # Bebés / Infantil
    "panal", "formula", "chiquitin", "nestum",
    # Snacks
    "galleta", "chocolate", "papas fritas", "cereal",
    # Congelados
    "pizza", "hamburguesa", "nuggets",
]

# Stores to scan. Key = slug used in DB & scrapers.
STORES_TO_SCAN = ["jumbo", "unimarc", "santa_isabel", "lider"]

# Max pages per query per store (cada página ≈ 40 productos)
PAGES_PER_QUERY = 1

# How stale does a StoreProduct need to be before CatalogBot re-audits it?
STALE_HOURS = 24


# ─────────────────────────────────────────────
# Coverage Reporter
# ─────────────────────────────────────────────

class CoverageReport:
    def __init__(self):
        self.scanned_queries: int = 0
        self.new_products: int = 0
        self.updated_products: int = 0
        self.gaps_found: int = 0
        self.stores_ok: list[str] = []
        self.stores_failed: list[str] = []
        self.started_at: datetime = datetime.now(UTC)

    def summary(self) -> str:
        elapsed = (datetime.now(UTC) - self.started_at).seconds // 60
        return (
            f"Scan completo en {elapsed}m | "
            f"Queries: {self.scanned_queries} | "
            f"Nuevos: {self.new_products} | "
            f"Actualizados: {self.updated_products} | "
            f"Gaps cubiertos: {self.gaps_found} | "
            f"Tiendas OK: {','.join(self.stores_ok)} | "
            f"Fallos: {','.join(self.stores_failed) or 'ninguno'}"
        )


# ─────────────────────────────────────────────
# Helper: scrape one store + query
# ─────────────────────────────────────────────

def _scrape_store_query(store_slug: str, query: str, pages: int) -> list[dict]:
    """
    Usa el scraper correspondiente para buscar `query` en `store_slug`.
    Retorna lista de productos normalizados.
    """
    try:
        if store_slug == "jumbo":
            from data.sources.jumbo_scraper import create_session, search_products
            sess = create_session()
            return search_products(sess, query, max_pages=pages)

        elif store_slug == "unimarc":
            from data.sources.unimarc_scraper import create_session, search_products
            sess = create_session()
            return search_products(sess, query, max_pages=pages)

        elif store_slug == "santa_isabel":
            from data.sources.santa_isabel_scraper import create_session, search_products
            sess = create_session()
            return search_products(sess, query, max_pages=pages)

        elif store_slug == "lider":
            from data.sources.lider_scraper import create_session, search_products
            sess = create_session()
            return search_products(sess, query, max_pages=pages)

    except ImportError as e:
        logger.warning(f"Scraper no disponible para {store_slug}: {e}")
    except Exception as e:
        logger.error(f"Error scrapeando {store_slug}/{query}: {e}")

    return []


# ─────────────────────────────────────────────
# Gap Detection: compare scraped vs DB
# ─────────────────────────────────────────────

def _get_existing_external_ids(session, store_id: int) -> set[str]:
    """Retorna el set de external_ids ya en la BD para un store."""
    from core.models import StoreProduct
    rows = (
        session.query(StoreProduct.external_id)
        .filter(StoreProduct.store_id == store_id)
        .all()
    )
    return {r[0] for r in rows}


def _ingest_new_products(session, store, scraped: list[dict], existing_ids: set[str]) -> tuple[int, int]:
    """
    Filtra productos nuevos (no en DB) y los ingesta.
    Retorna (nuevos_insertados, ya_existentes_actualizados).
    """
    from domain.ingest import upsert_store_products

    # Divide en nuevos vs ya conocidos
    new_ones = [p for p in scraped
                if str(p.get("product_id") or p.get("sku_id", "")) not in existing_ids]
    existing_ones = [p for p in scraped
                     if str(p.get("product_id") or p.get("sku_id", "")) in existing_ids]

    inserted = 0
    updated = 0

    if new_ones:
        logger.info(f"  [{store.name}] 🆕 {len(new_ones)} productos nuevos encontrados")
        upsert_store_products(session, store, new_ones, branch=None)
        inserted = len(new_ones)

    if existing_ones:
        # Still upsert to refresh prices / stock
        upsert_store_products(session, store, existing_ones, branch=None)
        updated = len(existing_ones)

    return inserted, updated


# ─────────────────────────────────────────────
# Main scan cycle
# ─────────────────────────────────────────────

def run_catalog_scan() -> CoverageReport:
    """
    Ejecuta un ciclo completo de escaneo de catálogo:
    1. Para cada store y cada query, scrapear
    2. Comparar contra DB
    3. Insertar gaps
    4. Re-ejecutar matcher para crear productos canónicos
    """
    from core.db import get_session
    from core.models import Store, BotState
    from domain.ingest import run_matching

    report = CoverageReport()
    logger.info("=" * 60)
    logger.info("🤖 CatalogBot: Iniciando escaneo de cobertura de catálogo")
    logger.info("=" * 60)

    for store_slug in STORES_TO_SCAN:
        logger.info(f"\n📦 Escaneando tienda: {store_slug.upper()}")

        with get_session() as session:
            store = session.query(Store).filter_by(slug=store_slug).first()
            if not store:
                logger.warning(f"  Tienda '{store_slug}' no encontrada en BD. Omitiendo.")
                report.stores_failed.append(store_slug)
                continue

            existing_ids = _get_existing_external_ids(session, store.id)
            logger.info(f"  DB actual: {len(existing_ids)} productos en {store.name}")

            store_new = 0
            store_updated = 0
            store_errors = 0

            for query in CATALOG_QUERIES:
                # --- PHASE 4: BOT MEMORY CHECK ---
                task_key = f"crawl:{store_slug}:{query}"
                state = session.query(BotState).filter_by(task_key=task_key).first()
                if state and (datetime.now(UTC) - state.last_run.replace(tzinfo=UTC)) < timedelta(hours=12):
                    logger.info(f"  [{store_slug}] ⏩ Omitiendo '{query}' (memoria: escaneado hace menos de 12h)")
                    continue

                try:
                    scraped = _scrape_store_query(store_slug, query, PAGES_PER_QUERY)
                    if not scraped:
                        continue

                    new_c, upd_c = _ingest_new_products(session, store, scraped, existing_ids)
                    store_new += new_c
                    store_updated += upd_c
                    report.gaps_found += new_c

                    # --- PHASE 4: UPDATE BOT MEMORY ---
                    if not state:
                        state = BotState(task_key=task_key)
                        session.add(state)
                    state.last_run = datetime.now(UTC)
                    session.commit()

                    # Update existing_ids to avoid double-counting
                    for p in scraped:
                        ext_id = str(p.get("product_id") or p.get("sku_id", ""))
                        if ext_id:
                            existing_ids.add(ext_id)

                    report.scanned_queries += 1
                    time.sleep(1.2)  # Rate limiting

                except Exception as e:
                    logger.error(f"  Error en query '{query}': {e}")
                    store_errors += 1
                    continue

            session.commit()
            report.new_products += store_new
            report.updated_products += store_updated

            if store_errors == 0:
                report.stores_ok.append(store_slug)
                logger.info(
                    f"  ✅ {store.name}: +{store_new} nuevos, ~{store_updated} actualizados"
                )
            else:
                report.stores_failed.append(store_slug)
                logger.warning(
                    f"  ⚠️  {store.name}: {store_errors} errores, +{store_new} insertados"
                )

    # Re-run matcher across all stores
    logger.info("\n🔗 Re-ejecutando matcher cruzado...")
    try:
        with get_session() as session:
            run_matching(session, STORES_TO_SCAN)
            session.commit()
        logger.info("  ✅ Matcher completado")
    except Exception as e:
        logger.error(f"  Matcher falló: {e}")

    logger.info(f"\n📊 {report.summary()}")
    return report


# ─────────────────────────────────────────────
# Background daemon loop
# ─────────────────────────────────────────────

# Global state accessible from API
_catalog_bot_state = {
    "status": "idle",               # idle | scanning
    "last_run": None,               # ISO timestamp
    "last_report": None,            # CoverageReport summary string
    "new_products_total": 0,
    "next_run": None,               # ISO timestamp
    "lock": threading.Lock(),
}


def catalog_bot_loop():
    """
    Loop infinito que ejecuta catalog scans periódicamente.
    Diseñado para correr en un thread daemon.
    """
    logger.info("🚀 CatalogBot iniciado. Primera ejecución en 60 segundos...")
    time.sleep(60)  # Grace period so the API boots up fully first

    while True:
        try:
            with _catalog_bot_state["lock"]:
                _catalog_bot_state["status"] = "scanning"
                _catalog_bot_state["last_run"] = datetime.now(UTC).isoformat()
                next_run = datetime.now(UTC) + timedelta(hours=SCAN_INTERVAL_HOURS)
                _catalog_bot_state["next_run"] = next_run.isoformat()

            report = run_catalog_scan()

            with _catalog_bot_state["lock"]:
                _catalog_bot_state["status"] = "idle"
                _catalog_bot_state["last_report"] = report.summary()
                _catalog_bot_state["new_products_total"] += report.new_products

        except Exception as e:
            logger.error(f"CatalogBot ciclo falló: {e}")
            with _catalog_bot_state["lock"]:
                _catalog_bot_state["status"] = "idle"
                _catalog_bot_state["last_report"] = f"ERROR: {e}"

        logger.info(f"😴 CatalogBot: Próximo scan en {SCAN_INTERVAL_HOURS}h")
        time.sleep(SCAN_INTERVAL_HOURS * 3600)


def get_catalog_bot_status() -> dict:
    """Retorna el estado actual del CatalogBot para la API."""
    with _catalog_bot_state["lock"]:
        return {
            "status": _catalog_bot_state["status"],
            "last_run": _catalog_bot_state["last_run"],
            "last_report": _catalog_bot_state["last_report"],
            "new_products_total": _catalog_bot_state["new_products_total"],
            "next_run": _catalog_bot_state["next_run"],
            "scan_interval_hours": SCAN_INTERVAL_HOURS,
            "queries_monitored": len(CATALOG_QUERIES),
            "stores_monitored": STORES_TO_SCAN,
        }


def trigger_manual_scan():
    """Lanza un scan manual en un thread separado (no bloquea)."""
    def _run():
        with _catalog_bot_state["lock"]:
            if _catalog_bot_state["status"] == "scanning":
                logger.info("CatalogBot ya está escaneando. Ignorando trigger manual.")
                return
            _catalog_bot_state["status"] = "scanning"
            _catalog_bot_state["last_run"] = datetime.now(UTC).isoformat()

        try:
            report = run_catalog_scan()
            with _catalog_bot_state["lock"]:
                _catalog_bot_state["status"] = "idle"
                _catalog_bot_state["last_report"] = report.summary()
                _catalog_bot_state["new_products_total"] += report.new_products
        except Exception as e:
            logger.error(f"Manual scan falló: {e}")
            with _catalog_bot_state["lock"]:
                _catalog_bot_state["status"] = "idle"
                _catalog_bot_state["last_report"] = f"ERROR: {e}"

    t = threading.Thread(target=_run, daemon=True)
    t.start()
