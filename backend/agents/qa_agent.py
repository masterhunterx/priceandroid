"""
QA Agent — Monitor Continuo de Integridad
==========================================
Corre en background cada 6 horas y detecta problemas en la BD antes de que
lleguen al usuario. Reporta por Discord y logs con severidad 🟡/🔴.

Checks implementados:
  1. Precio cero/nulo con in_stock=True
  2. Anomalía de precio (cambio brusco >80%)
  3. Sync estancado >48h con in_stock=True
  4. Matches duplicados (misma tienda, mismo producto canónico)
  5. StoreProducts sin product_id (nunca emparejados)
  6. Tienda entera sin productos en stock
  7. Precios absurdos (<100 CLP o >10.000.000 CLP)
"""

import os
import time
import logging
import threading
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("AntigravityAPI")
UTC = timezone.utc

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "")
CHECK_INTERVAL_HOURS = int(os.getenv("QA_AGENT_INTERVAL_HOURS", "6"))

# Umbrales configurables
PRICE_ANOMALY_THRESHOLD = 0.80   # cambio >80% considerado anómalo
STALE_SYNC_HOURS        = 48     # horas sin sync antes de alertar
MIN_VALID_PRICE         = 100    # CLP mínimo razonable
MAX_VALID_PRICE         = 10_000_000  # CLP máximo razonable
MAX_UNMATCHED_REPORT    = 20     # máx productos sin match a listar en Discord


# ---------------------------------------------------------------------------
# Envío a Discord
# ---------------------------------------------------------------------------

def _send_discord(content: str) -> None:
    if not DISCORD_WEBHOOK:
        return
    try:
        import requests as _req
        _req.post(DISCORD_WEBHOOK, json={"content": content}, timeout=10)
    except Exception as e:
        logger.warning(f"[QAAgent] Discord send failed: {e}")


def _discord_report(issues: list[dict]) -> None:
    """Construye y envía el reporte a Discord."""
    critical = [i for i in issues if i["level"] == "critical"]
    warnings  = [i for i in issues if i["level"] == "warning"]

    if not issues:
        _send_discord(
            "**✅ QA Agent — Todo en orden**\n"
            f"Revisión completada sin anomalías. `{datetime.now(UTC).strftime('%d/%m %H:%M')} UTC`"
        )
        return

    lines = [f"**{'🔴' if critical else '🟡'} QA Agent — {len(issues)} problema(s) detectado(s)**"]
    lines.append(f"`{datetime.now(UTC).strftime('%d/%m/%Y %H:%M')} UTC`\n")

    if critical:
        lines.append("**🔴 CRÍTICOS:**")
        for i in critical:
            lines.append(f"• {i['title']}: {i['detail']}")
        lines.append("")

    if warnings:
        lines.append("**🟡 ADVERTENCIAS:**")
        for i in warnings:
            lines.append(f"• {i['title']}: {i['detail']}")

    _send_discord("\n".join(lines))


# ---------------------------------------------------------------------------
# Checks individuales
# ---------------------------------------------------------------------------

def check_zero_price_in_stock(db) -> list[dict]:
    """Productos marcados en stock pero sin precio válido."""
    from sqlalchemy import text
    result = db.execute(text("""
        SELECT sp.id, s.name AS store, sp.name
        FROM store_products sp
        JOIN stores s ON sp.store_id = s.id
        LEFT JOIN (
            SELECT store_product_id, MAX(scraped_at) AS latest
            FROM prices GROUP BY store_product_id
        ) lp ON lp.store_product_id = sp.id
        LEFT JOIN prices p ON p.store_product_id = sp.id AND p.scraped_at = lp.latest
        WHERE sp.in_stock = TRUE
          AND (p.price IS NULL OR p.price = 0)
        LIMIT 30
    """)).fetchall()

    if not result:
        return []

    sample = ", ".join(f"`{r[1]}/{r[0]}`" for r in result[:5])
    return [{
        "level": "warning",
        "title": "Precio cero con in_stock=True",
        "detail": f"{len(result)} productos. Ej: {sample}",
    }]


def check_price_anomalies(db) -> list[dict]:
    """Detecta cambios de precio >80% entre los últimos 2 registros."""
    from sqlalchemy import text
    cutoff_48h = datetime.now(UTC) - timedelta(hours=48)
    result = db.execute(text("""
        SELECT sp.id, s.name, sp.name, p1.price AS old_price, p2.price AS new_price
        FROM store_products sp
        JOIN stores s ON sp.store_id = s.id
        JOIN prices p2 ON p2.store_product_id = sp.id
        JOIN prices p1 ON p1.store_product_id = sp.id
        WHERE p2.scraped_at > p1.scraped_at
          AND p1.price > 0
          AND p2.price > 0
          AND ABS(p2.price - p1.price) / p1.price > :threshold
          AND p2.scraped_at >= :cutoff
        ORDER BY ABS(p2.price - p1.price) / p1.price DESC
        LIMIT 10
    """), {"threshold": PRICE_ANOMALY_THRESHOLD, "cutoff": cutoff_48h}).fetchall()

    if not result:
        return []

    sample = "; ".join(
        f"`{r[1]}/{r[0]}` ${int(r[3]):,}→${int(r[4]):,}"
        for r in result[:3]
    )
    return [{
        "level": "warning",
        "title": "Anomalía de precio (>80% cambio)",
        "detail": f"{len(result)} casos en 48h. Ej: {sample}",
    }]


def check_stale_sync(db) -> list[dict]:
    """Productos in_stock=True sin sincronizar en más de STALE_SYNC_HOURS."""
    from sqlalchemy import text
    cutoff = datetime.now(UTC) - timedelta(hours=STALE_SYNC_HOURS)
    result = db.execute(text("""
        SELECT COUNT(*) FROM store_products
        WHERE in_stock = TRUE
          AND (last_sync IS NULL OR last_sync < :cutoff)
    """), {"cutoff": cutoff}).fetchone()

    count = result[0] if result else 0
    if count == 0:
        return []

    level = "critical" if count > 500 else "warning"
    return [{
        "level": level,
        "title": f"Sync estancado >{STALE_SYNC_HOURS}h",
        "detail": f"{count:,} productos en stock sin actualizar.",
    }]


def check_duplicate_matches(db) -> list[dict]:
    """Misma tienda emparejada dos veces al mismo producto canónico."""
    from sqlalchemy import text
    result = db.execute(text("""
        SELECT pm.product_id, s.name, COUNT(*) AS cnt
        FROM product_matches pm
        JOIN store_products sp ON pm.store_product_id = sp.id
        JOIN stores s ON sp.store_id = s.id
        GROUP BY pm.product_id, s.name
        HAVING COUNT(*) > 1
        ORDER BY cnt DESC
        LIMIT 20
    """)).fetchall()

    if not result:
        return []

    sample = ", ".join(f"`prod#{r[0]}/{r[1]}`(x{r[2]})" for r in result[:5])
    return [{
        "level": "warning",
        "title": "Matches duplicados",
        "detail": f"{len(result)} productos con >1 match por tienda. Ej: {sample}",
    }]


def check_unmatched_products(db) -> list[dict]:
    """StoreProducts ingresados pero sin product_id (nunca emparejados)."""
    from sqlalchemy import text
    result = db.execute(text("""
        SELECT COUNT(*) FROM store_products WHERE product_id IS NULL
    """)).fetchone()

    count = result[0] if result else 0
    if count == 0:
        return []

    level = "critical" if count > 1000 else "warning"
    return [{
        "level": level,
        "title": "StoreProducts sin emparejar",
        "detail": f"{count:,} registros con product_id=NULL (no visibles en la app).",
    }]


def check_empty_stores(db) -> list[dict]:
    """Tiendas que tienen 0 productos en stock."""
    from sqlalchemy import text
    # Compatible SQLite + PostgreSQL: subquery en lugar de FILTER aggregate
    result = db.execute(text("""
        SELECT s.name
        FROM stores s
        WHERE (
            SELECT COUNT(*) FROM store_products sp
            WHERE sp.store_id = s.id AND sp.in_stock = 1
        ) = 0
    """)).fetchall()

    if not result:
        return []

    names = ", ".join(f"`{r[0]}`" for r in result)
    return [{
        "level": "critical",
        "title": "Tienda sin stock",
        "detail": f"Las tiendas {names} tienen 0 productos disponibles.",
    }]


def check_absurd_prices(db) -> list[dict]:
    """Precios fuera del rango válido (<100 o >10M CLP)."""
    from sqlalchemy import text
    cutoff_24h = datetime.now(UTC) - timedelta(hours=24)
    result = db.execute(text("""
        SELECT sp.id, s.name, sp.name, p.price
        FROM prices p
        JOIN store_products sp ON p.store_product_id = sp.id
        JOIN stores s ON sp.store_id = s.id
        WHERE p.scraped_at >= :cutoff
          AND (p.price < :min_price OR p.price > :max_price)
          AND p.price IS NOT NULL AND p.price > 0
        LIMIT 20
    """), {"cutoff": cutoff_24h, "min_price": MIN_VALID_PRICE, "max_price": MAX_VALID_PRICE}).fetchall()

    if not result:
        return []

    sample = ", ".join(f"`{r[1]}/{r[0]}` ${int(r[3]):,}" for r in result[:4])
    return [{
        "level": "warning",
        "title": "Precios absurdos (últimas 24h)",
        "detail": f"{len(result)} registros fuera del rango válido. Ej: {sample}",
    }]


def check_feedback_overflow(db) -> list[dict]:
    """Alerta si hay demasiados bugs pendientes sin revisar."""
    from sqlalchemy import text
    result = db.execute(text("""
        SELECT COUNT(*) FROM feedback WHERE status = 'pending'
    """)).fetchone()

    count = result[0] if result else 0
    if count < 5:
        return []

    level = "critical" if count >= 20 else "warning"
    return [{
        "level": level,
        "title": "Backlog de feedback",
        "detail": f"{count} reportes de usuarios pendientes de revisión.",
    }]


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------

def run_qa_checks() -> list[dict]:
    """Ejecuta todos los checks y retorna lista de issues encontrados."""
    from core.db import get_session

    issues = []
    checks = [
        check_zero_price_in_stock,
        check_price_anomalies,
        check_stale_sync,
        check_duplicate_matches,
        check_unmatched_products,
        check_empty_stores,
        check_absurd_prices,
        check_feedback_overflow,
    ]

    try:
        with get_session() as db:
            for check_fn in checks:
                try:
                    found = check_fn(db)
                    issues.extend(found)
                    if found:
                        for i in found:
                            lvl = i["level"].upper()
                            logger.warning(f"[QAAgent] [{lvl}] {i['title']}: {i['detail']}")
                except Exception as e:
                    logger.error(f"[QAAgent] Error en {check_fn.__name__}: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"[QAAgent] Error abriendo sesión de BD: {e}", exc_info=True)
        return []

    critical_count = sum(1 for i in issues if i["level"] == "critical")
    warning_count  = sum(1 for i in issues if i["level"] == "warning")
    logger.info(f"[QAAgent] Revisión completada: {critical_count} críticos, {warning_count} advertencias.")
    return issues


def qa_agent_loop():
    """Loop daemon del QA Agent. Se ejecuta en su propio hilo."""
    logger.info(f"[QAAgent] Iniciando — revisión cada {CHECK_INTERVAL_HOURS}h.")

    # Primera ejecución: esperar 3 minutos para que el server arranque
    time.sleep(180)

    while True:
        try:
            logger.info("[QAAgent] Iniciando ciclo de revisión de integridad...")
            issues = run_qa_checks()
            _discord_report(issues)
        except Exception as e:
            logger.error(f"[QAAgent] Error inesperado en ciclo: {e}", exc_info=True)

        time.sleep(CHECK_INTERVAL_HOURS * 3600)
