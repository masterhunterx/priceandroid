"""
Self-Healer Agent — Auto-corrección de datos en Railway PostgreSQL
==================================================================
Corre cada 4 horas. Detecta y CORRIGE problemas de datos sin intervención humana.
Reporta cada acción a Discord con detalle de qué se corrigió y por qué.

Correcciones automáticas:
  1. Productos in_stock=True con precio 0 o nulo → marcar sin stock
  2. Matches duplicados por tienda → conservar el de mayor score, eliminar el resto
  3. Precios huérfanos (sin store_product) → eliminar
  4. StoreProducts sin last_sync → inicializar con created_at
  5. Precios negativos o absurdos → eliminar solo ese registro de precio
"""

import os
import time
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("AntigravityAPI")
UTC = timezone.utc

DISCORD_WEBHOOK   = os.getenv("DISCORD_WEBHOOK_URL", "")
HEAL_INTERVAL_SEC = int(os.getenv("SELF_HEALER_INTERVAL_HOURS", "4")) * 3600

MIN_VALID_PRICE = 100
MAX_VALID_PRICE = 10_000_000


def _send_discord(content: str) -> None:
    if not DISCORD_WEBHOOK:
        return
    try:
        import requests as _req
        _req.post(DISCORD_WEBHOOK, json={"content": content}, timeout=10)
    except Exception as e:
        logger.warning(f"[SelfHealer] Discord send failed: {e}")


# ---------------------------------------------------------------------------
# Correcciones individuales
# ---------------------------------------------------------------------------

def heal_zero_price_in_stock(db) -> int:
    """Marca sin stock los productos con in_stock=True pero sin precio válido."""
    from sqlalchemy import text
    result = db.execute(text("""
        UPDATE store_products sp
        SET in_stock = FALSE, last_sync = NOW()
        WHERE sp.in_stock = TRUE
          AND NOT EXISTS (
              SELECT 1 FROM prices p
              WHERE p.store_product_id = sp.id
                AND p.price IS NOT NULL AND p.price > 0
          )
        RETURNING sp.id
    """))
    count = result.rowcount
    db.commit()
    return count


def heal_duplicate_matches(db) -> int:
    """Elimina matches duplicados por tienda, conservando el de mayor score."""
    from sqlalchemy import text
    result = db.execute(text("""
        DELETE FROM product_matches
        WHERE id IN (
            SELECT pm.id
            FROM product_matches pm
            JOIN store_products sp ON pm.store_product_id = sp.id
            WHERE (pm.product_id, sp.store_id) IN (
                SELECT pm2.product_id, sp2.store_id
                FROM product_matches pm2
                JOIN store_products sp2 ON pm2.store_product_id = sp2.id
                GROUP BY pm2.product_id, sp2.store_id
                HAVING COUNT(*) > 1
            )
            AND pm.match_score < (
                SELECT MAX(pm3.match_score)
                FROM product_matches pm3
                JOIN store_products sp3 ON pm3.store_product_id = sp3.id
                WHERE pm3.product_id = pm.product_id
                  AND sp3.store_id = sp.store_id
            )
        )
        RETURNING id
    """))
    count = result.rowcount
    db.commit()
    return count


def heal_orphan_prices(db) -> int:
    """Elimina registros de precios cuyo store_product ya no existe."""
    from sqlalchemy import text
    result = db.execute(text("""
        DELETE FROM prices
        WHERE store_product_id NOT IN (SELECT id FROM store_products)
        RETURNING id
    """))
    count = result.rowcount
    db.commit()
    return count


def heal_missing_last_sync(db) -> int:
    """Inicializa last_sync con created_at donde sea NULL."""
    from sqlalchemy import text
    result = db.execute(text("""
        UPDATE store_products
        SET last_sync = COALESCE(created_at, NOW())
        WHERE last_sync IS NULL
        RETURNING id
    """))
    count = result.rowcount
    db.commit()
    return count


def heal_absurd_prices(db) -> int:
    """Elimina registros de precio con valores imposibles (<100 o >10M CLP)."""
    from sqlalchemy import text
    result = db.execute(text("""
        DELETE FROM prices
        WHERE price IS NOT NULL
          AND price > 0
          AND (price < :min_p OR price > :max_p)
        RETURNING id
    """), {"min_p": MIN_VALID_PRICE, "max_p": MAX_VALID_PRICE})
    count = result.rowcount
    db.commit()
    return count


def heal_stale_price_history(db) -> int:
    """Elimina registros de precios con más de 90 días para controlar el tamaño de la tabla."""
    from sqlalchemy import text
    cutoff = datetime.now(UTC) - timedelta(days=90)
    result = db.execute(text("""
        DELETE FROM prices
        WHERE scraped_at < :cutoff
    """), {"cutoff": cutoff})
    count = result.rowcount
    db.commit()
    return count


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------

def run_self_healer() -> dict:
    """Ejecuta todas las correcciones y retorna un resumen."""
    from core.db import get_session

    results = {}
    healers = [
        ("zero_price_in_stock",  heal_zero_price_in_stock),
        ("duplicate_matches",    heal_duplicate_matches),
        ("orphan_prices",        heal_orphan_prices),
        ("missing_last_sync",    heal_missing_last_sync),
        ("absurd_prices",        heal_absurd_prices),
        ("stale_price_history",  heal_stale_price_history),
    ]

    try:
        with get_session() as db:
            for name, fn in healers:
                try:
                    fixed = fn(db)
                    results[name] = fixed
                    if fixed > 0:
                        logger.info(f"[SelfHealer] {name}: {fixed} correcciones aplicadas.")
                except Exception as e:
                    logger.error(f"[SelfHealer] Error en {name}: {e}", exc_info=True)
                    results[name] = -1
    except Exception as e:
        logger.error(f"[SelfHealer] Error de sesión: {e}", exc_info=True)

    return results


def _discord_summary(results: dict) -> None:
    total_fixed = sum(v for v in results.values() if v > 0)
    ts = datetime.now(UTC).strftime("%d/%m/%Y %H:%M")

    if total_fixed == 0:
        _send_discord(f"**🩺 Self-Healer** — Sin correcciones necesarias `{ts} UTC`")
        return

    labels = {
        "zero_price_in_stock": "Sin stock (precio=0)",
        "duplicate_matches":   "Matches duplicados",
        "orphan_prices":       "Precios huérfanos",
        "missing_last_sync":   "last_sync inicializado",
        "absurd_prices":       "Precios absurdos",
    }
    lines = [f"**🩺 Self-Healer — {total_fixed} correcciones** `{ts} UTC`"]
    for key, count in results.items():
        if count > 0:
            lines.append(f"• {labels.get(key, key)}: **{count}** registros corregidos")
    _send_discord("\n".join(lines))


def self_healer_loop():
    """Loop daemon del Self-Healer."""
    logger.info("[SelfHealer] Iniciando — auto-corrección cada 4h.")
    time.sleep(240)  # Esperar 4 min al arranque

    while True:
        try:
            logger.info("[SelfHealer] Iniciando ciclo de corrección...")
            results = run_self_healer()
            _discord_summary(results)
        except Exception as e:
            logger.error(f"[SelfHealer] Error inesperado: {e}", exc_info=True)
        time.sleep(HEAL_INTERVAL_SEC)
