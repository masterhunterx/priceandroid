"""
Match Pipeline — Emparejamiento automático de productos sin ficha canónica
=========================================================================
Corre cada 6 horas. Toma StoreProducts con product_id=NULL y ejecuta
el algoritmo de matching para crear fichas canónicas (Product) y enlaces
(ProductMatch), haciéndolos visibles en la app.

Flujo:
  store_products WHERE product_id IS NULL
      → agrupar por tienda
      → run_matching() por lote
      → flush + commit
      → reportar a Discord cuántos se emparejaron

Límite de lote: configurable via MATCH_PIPELINE_BATCH (default 500/ciclo)
para no saturar la BD en ciclos con backlog grande.
"""

import os
import time
import logging
from datetime import datetime, timezone

logger = logging.getLogger("AntigravityAPI")
UTC = timezone.utc

DISCORD_WEBHOOK    = os.getenv("DISCORD_WEBHOOK_URL", "")
CHECK_INTERVAL_SEC = int(os.getenv("MATCH_PIPELINE_INTERVAL_HOURS", "6")) * 3600
STARTUP_DELAY_SEC  = 360     # 6 min — arrancar tras CatalogSync y FeedbackPipeline
BATCH_SIZE         = int(os.getenv("MATCH_PIPELINE_BATCH", "500"))


# ---------------------------------------------------------------------------
# Conteo de sin emparejar
# ---------------------------------------------------------------------------

def _count_unmatched(db) -> int:
    from sqlalchemy import text
    row = db.execute(text(
        "SELECT COUNT(*) FROM store_products WHERE product_id IS NULL"
    )).fetchone()
    return int(row[0]) if row else 0


# ---------------------------------------------------------------------------
# Matching por lote
# ---------------------------------------------------------------------------

def _run_match_batch(db) -> dict:
    """
    Carga hasta BATCH_SIZE StoreProducts sin product_id por tienda,
    corre run_matching() y retorna estadísticas.
    """
    from sqlalchemy import text
    from core.models import Store, StoreProduct
    from domain.ingest import run_matching

    stats: dict = {"before": 0, "after": 0, "new_products": 0, "new_links": 0}
    stats["before"] = _count_unmatched(db)

    if stats["before"] == 0:
        return stats

    # Obtener slugs de tiendas que tienen productos sin emparejar
    rows = db.execute(text("""
        SELECT DISTINCT s.slug
        FROM store_products sp
        JOIN stores s ON s.id = sp.store_id
        WHERE sp.product_id IS NULL
    """)).fetchall()
    store_slugs = [r[0] for r in rows]

    if not store_slugs:
        return stats

    logger.info(
        f"[MatchPipeline] {stats['before']:,} productos sin emparejar en: {', '.join(store_slugs)}"
    )

    # run_matching trabaja con los datos en BD — flush previo garantiza consistencia
    db.flush()
    result = run_matching(db, store_slugs)

    # run_matching retorna lista de match dicts; contamos los nuevos
    stats["new_links"]    = sum(1 for m in result if m.get("new_link"))
    stats["new_products"] = sum(1 for m in result if m.get("new_product"))

    # Promover huérfanos restantes a fichas canónicas propias (mono-tienda)
    promoted = _promote_solo_products(db)
    stats["promoted_solo"] = promoted
    if promoted:
        logger.info(f"[MatchPipeline] {promoted} productos promovidos a ficha propia (sin par cruzado)")

    stats["after"] = _count_unmatched(db)
    return stats


# ---------------------------------------------------------------------------
# Promoción de productos sin emparejar a fichas canónicas propias
# ---------------------------------------------------------------------------

def _promote_solo_products(db) -> int:
    """
    Crea fichas canónicas (Product) para StoreProducts que siguen sin product_id
    después del matcher. Así son visibles en la app aunque no tengan comparación
    cruzada entre tiendas. Retorna el número de productos promovidos.
    """
    from core.models import StoreProduct, Product, ProductMatch
    from domain.matcher import extract_weight, clean_product_name

    orphans = (
        db.query(StoreProduct)
        .filter(StoreProduct.product_id == None)
        .limit(BATCH_SIZE)
        .all()
    )
    promoted = 0
    for sp in orphans:
        weight_val, weight_unit = extract_weight(sp.name)
        canonical = Product(
            canonical_name=clean_product_name(sp.name) or sp.name,
            brand=sp.brand or "",
            category=sp.top_category or "",
            category_path=sp.category_path or "",
            weight_value=weight_val,
            weight_unit=weight_unit,
            image_url=sp.image_url or "",
        )
        db.add(canonical)
        db.flush()
        sp.product_id = canonical.id
        db.add(ProductMatch(
            product_id=canonical.id,
            store_product_id=sp.id,
            match_score=1.0,
            match_method="solo",
            verified=False,
        ))
        promoted += 1

    if promoted:
        db.flush()
    return promoted


# ---------------------------------------------------------------------------
# Reporte
# ---------------------------------------------------------------------------

def _discord_report(stats: dict) -> None:
    if stats["before"] == 0:
        return

    resolved = stats["before"] - stats["after"]
    icon = "✅" if stats["after"] == 0 else ("🟡" if resolved > 0 else "⚠️")
    ts   = datetime.now(UTC).strftime("%d/%m %H:%M")

    _send_discord(
        f"**{icon} MatchPipeline** `{ts} UTC`\n"
        f"```\n"
        f"Sin emparejar antes : {stats['before']:,}\n"
        f"Sin emparejar ahora : {stats['after']:,}\n"
        f"Emparejados (cruce) : {resolved - stats.get('promoted_solo', 0):,}\n"
        f"Promovidos (solo)   : {stats.get('promoted_solo', 0):,}\n"
        f"Fichas canónicas    : {stats['new_products']:,} nuevas\n"
        f"Links creados       : {stats['new_links']:,}\n"
        f"```"
    )


# ---------------------------------------------------------------------------
# Ciclo principal
# ---------------------------------------------------------------------------

def match_pipeline_loop():
    """Loop daemon del Match Pipeline."""
    logger.info(f"[MatchPipeline] Iniciando — matching cada {CHECK_INTERVAL_SEC // 3600}h.")
    time.sleep(STARTUP_DELAY_SEC)

    while True:
        try:
            from core.db import get_session
            with get_session() as db:
                stats = _run_match_batch(db)
                _discord_report(stats)
                if stats["before"] > 0:
                    resolved = stats["before"] - stats["after"]
                    logger.info(
                        f"[MatchPipeline] Ciclo completado — "
                        f"{resolved:,} emparejados, {stats['after']:,} pendientes."
                    )
        except Exception as e:
            logger.error(f"[MatchPipeline] Error inesperado: {e}", exc_info=True)

        time.sleep(CHECK_INTERVAL_SEC)


# ---------------------------------------------------------------------------
# Utils
# ---------------------------------------------------------------------------

def _send_discord(content: str) -> None:
    if not DISCORD_WEBHOOK:
        return
    try:
        import requests as _req
        _req.post(DISCORD_WEBHOOK, json={"content": content}, timeout=10)
    except Exception as e:
        logger.warning(f"[MatchPipeline] Discord send failed: {e}")
