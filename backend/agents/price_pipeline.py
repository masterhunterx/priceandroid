"""
Price Pipeline — Notificaciones automáticas de cambios de precio
================================================================
Corre cada hora. Detecta bajadas/subidas significativas en precios
y notifica a usuarios con ese producto en favoritos.

Flujo:
  prices (últimas 2h)
      → comparar con precio anterior
      → bajada >15%  → Notification en BD + Discord para usuarios con favorito
      → subida  >20% → alerta interna en Discord
      → precio mínimo histórico → badge especial

Tablas usadas:
  prices, store_products, products, product_matches,
  user_preferences, notifications
"""

import os
import time
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("FreshCartAPI")
UTC = timezone.utc

DISCORD_WEBHOOK      = os.getenv("DISCORD_WEBHOOK_URL", "")
CHECK_INTERVAL_SEC   = int(os.getenv("PRICE_PIPELINE_INTERVAL_MIN", "60")) * 60
STARTUP_DELAY_SEC    = 240    # esperar 4 min para que CatalogSync popule precios primero
DROP_THRESHOLD       = 0.15   # bajada ≥15% → notificación al usuario
SPIKE_THRESHOLD      = 0.20   # subida ≥20% → alerta interna
LOOKBACK_HOURS       = 2      # ventana de detección de cambios recientes


# ---------------------------------------------------------------------------
# Detección de cambios
# ---------------------------------------------------------------------------

def _detect_price_changes(db) -> list[dict]:
    """
    Retorna lista de cambios de precio detectados en las últimas LOOKBACK_HOURS.
    Cada elemento: {product_id, store_product_id, store_name, product_name,
                    old_price, new_price, pct_change, direction}
    """
    from sqlalchemy import text

    cutoff = datetime.now(UTC) - timedelta(hours=LOOKBACK_HOURS)

    rows = db.execute(text("""
        SELECT
            sp.id          AS sp_id,
            sp.product_id,
            sp.name        AS product_name,
            s.name         AS store_name,
            p_prev.price   AS old_price,
            p_new.price    AS new_price
        FROM store_products sp
        JOIN stores s ON s.id = sp.store_id
        JOIN prices p_new ON p_new.store_product_id = sp.id
        JOIN prices p_prev ON p_prev.store_product_id = sp.id
            AND p_prev.scraped_at = (
                SELECT MAX(px.scraped_at)
                FROM prices px
                WHERE px.store_product_id = sp.id
                  AND px.scraped_at < p_new.scraped_at
            )
        WHERE p_new.scraped_at >= :cutoff
          AND p_prev.price > 0
          AND p_new.price  > 0
          AND p_new.price <> p_prev.price
          AND sp.product_id IS NOT NULL
        ORDER BY ABS(p_new.price - p_prev.price) / p_prev.price DESC
        LIMIT 200
    """), {"cutoff": cutoff}).fetchall()

    changes = []
    for r in rows:
        old_p, new_p = float(r.old_price), float(r.new_price)
        pct = (new_p - old_p) / old_p
        if abs(pct) < DROP_THRESHOLD and abs(pct) < SPIKE_THRESHOLD:
            continue
        changes.append({
            "sp_id":        r.sp_id,
            "product_id":   r.product_id,
            "product_name": r.product_name,
            "store_name":   r.store_name,
            "old_price":    old_p,
            "new_price":    new_p,
            "pct_change":   pct,
            "direction":    "drop" if pct < 0 else "spike",
        })
    return changes


def _is_historical_minimum(db, sp_id: int, new_price: float) -> bool:
    """True si new_price es el precio mínimo de toda la historia del producto."""
    from sqlalchemy import text
    row = db.execute(text(
        "SELECT MIN(price) FROM prices WHERE store_product_id = :id AND price > 0"
    ), {"id": sp_id}).fetchone()
    historical_min = float(row[0]) if row and row[0] else None
    return historical_min is not None and new_price <= historical_min


# ---------------------------------------------------------------------------
# Notificaciones y alertas
# ---------------------------------------------------------------------------

def _notify_users(db, change: dict, is_min: bool) -> int:
    """Crea Notification en BD para cada usuario con este producto como favorito."""
    from sqlalchemy import text
    from core.models import Notification

    user_ids = db.execute(text("""
        SELECT DISTINCT up.user_id
        FROM user_preferences up
        WHERE up.product_id = :pid
          AND up.notify_on_deal = TRUE
    """), {"pid": change["product_id"]}).fetchall()

    if not user_ids:
        return 0

    pct = abs(change["pct_change"]) * 100
    old_fmt = f"${int(change['old_price']):,}"
    new_fmt = f"${int(change['new_price']):,}"
    badge   = " 🏆 Mínimo histórico" if is_min else ""

    title   = f"Bajó el precio de {change['product_name'][:40]}{badge}"
    message = (
        f"{change['store_name']}: {old_fmt} → {new_fmt} "
        f"(-{pct:.0f}%){badge}"
    )

    count = 0
    for (user_id,) in user_ids:
        existing = db.execute(text("""
            SELECT id FROM notifications
            WHERE user_id = :uid AND product_id = :pid AND type = 'price_drop'
              AND created_at >= NOW() - INTERVAL '6 hours'
        """), {"uid": user_id, "pid": change["product_id"]}).fetchone()

        if existing:
            continue

        db.add(Notification(
            user_id=user_id,
            product_id=change["product_id"],
            title=title,
            message=message,
            type="price_drop",
        ))
        count += 1

    return count


def _alert_spike(change: dict) -> None:
    """Alerta interna a Discord para subidas significativas."""
    pct    = change["pct_change"] * 100
    old_f  = f"${int(change['old_price']):,}"
    new_f  = f"${int(change['new_price']):,}"
    _send_discord(
        f"**📈 PricePipeline — Subida de precio detectada**\n"
        f"`{change['product_name'][:60]}` en **{change['store_name']}**\n"
        f"{old_f} → {new_f} (+{pct:.0f}%)"
    )


def _discord_summary(drops: int, spikes: int, notifs: int) -> None:
    if drops == 0 and spikes == 0:
        return
    _send_discord(
        f"**💰 PricePipeline — Resumen**\n"
        f"Bajadas notificadas : {drops} productos ({notifs} notificaciones)\n"
        f"Subidas alertadas   : {spikes} productos"
    )


# ---------------------------------------------------------------------------
# Ciclo principal
# ---------------------------------------------------------------------------

def _run_price_cycle(db) -> None:
    changes = _detect_price_changes(db)
    if not changes:
        return

    drops_count  = 0
    spikes_count = 0
    notifs_total = 0

    for change in changes:
        if change["direction"] == "drop":
            is_min = _is_historical_minimum(db, change["sp_id"], change["new_price"])
            n = _notify_users(db, change, is_min)
            notifs_total += n
            drops_count  += 1
            if n:
                logger.info(
                    f"[PricePipeline] DROP {change['store_name']} "
                    f"{change['product_name'][:30]} "
                    f"${int(change['old_price']):,}→${int(change['new_price']):,} "
                    f"({abs(change['pct_change'])*100:.0f}%) → {n} notif(s)"
                )
        else:
            if change["pct_change"] >= SPIKE_THRESHOLD:
                _alert_spike(change)
                spikes_count += 1

    _discord_summary(drops_count, spikes_count, notifs_total)


def price_pipeline_loop():
    """Loop daemon del Price Pipeline."""
    logger.info(f"[PricePipeline] Iniciando — detección de cambios cada {CHECK_INTERVAL_SEC // 60} min.")
    time.sleep(STARTUP_DELAY_SEC)

    while True:
        try:
            from core.db import get_session
            with get_session() as db:
                _run_price_cycle(db)
        except Exception as e:
            logger.error(f"[PricePipeline] Error inesperado: {e}", exc_info=True)

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
        logger.warning(f"[PricePipeline] Discord send failed: {e}")
