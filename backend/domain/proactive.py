"""
Proactive Engine: KAIROS
=========================
Monitors all 4 supermarkets and rotates deal notifications daily so the
user always sees fresh opportunities. Each cycle:
  1. Purge stale/read notifications.
  2. If the tray needs more items, pull the next batch from every store
     (rotating through each store's full deal catalogue via stored offsets).
  3. Reset offsets each new day so the cycle restarts daily.
"""

import json
from datetime import datetime, timezone, timedelta

from sqlalchemy import text as _text

from core.db import get_session
from core.models import (
    BotState, Notification, Store, StoreProduct, Price, UserPreference
)

UTC = timezone.utc

# ── Tuneable constants ────────────────────────────────────────────────────────
DEALS_PER_STORE_PER_CYCLE = 5   # How many deals to push per store each refill
MIN_UNREAD_THRESHOLD      = 8   # Don't refill if tray already has ≥ this many unread
MAX_NOTIFICATIONS         = 60  # Hard cap in the tray at any moment
MIN_DISCOUNT_PCT          = 5   # Skip deals with < 5 % off
DEDUP_WINDOW_HOURS        = 12  # Don't re-notify the same product within N hours
# ─────────────────────────────────────────────────────────────────────────────


def _get_or_create_bot_state(session, task_key: str) -> BotState:
    state = session.query(BotState).filter_by(task_key=task_key).first()
    if not state:
        state = BotState(task_key=task_key, meta_data="{}")
        session.add(state)
        session.flush()
    return state


def _load_offset(session, store_slug: str, today_str: str) -> int:
    """Return today's rotation offset for *store_slug* (resets if day changed)."""
    key = f"rotation_offset_{store_slug}"
    state = _get_or_create_bot_state(session, key)
    try:
        meta = json.loads(state.meta_data or "{}")
    except json.JSONDecodeError:
        meta = {}

    if meta.get("date") != today_str:
        # New day -> reset
        meta = {"date": today_str, "offset": 0}
        state.meta_data = json.dumps(meta)

    return meta.get("offset", 0)


def _save_offset(session, store_slug: str, today_str: str, new_offset: int):
    key = f"rotation_offset_{store_slug}"
    state = _get_or_create_bot_state(session, key)
    state.meta_data = json.dumps({"date": today_str, "offset": new_offset})


def _classify(price_val: float, savings_pct: int, product_name: str,
              is_fav: bool) -> tuple[str, str]:
    """Return (type_tag, title) for a deal."""
    name = product_name[:38]
    if price_val <= 1000:
        tag, title = "price_luca", f"✨ ¡A LUCA! {name}"
    elif price_val <= 2000:
        tag, title = "price_under_2k", f"💸 Bajo $2.000: {name}"
    elif savings_pct >= 40:
        tag, title = "price_drop", f"🔥 -{savings_pct}% HOY: {name}"
    else:
        tag, title = "price_drop", f"📉 Oferta {savings_pct}% OFF — {name}"

    if is_fav:
        title = "⭐ " + title
    return tag, title


def generate_proactive_alerts():
    """
    Main entry point called every 15 minutes by the scheduler.
    """
    print(f"\n  [KAIROS] Proactive engine starting…")
    start_time = datetime.now()

    with get_session() as session:
        now = datetime.now(UTC)
        today_str = now.strftime("%Y-%m-%d")

        # ── 1. Purge: DELETE directo — sin cargar objetos en memoria ────────
        cutoff_24h = now - timedelta(hours=24)
        purged = session.execute(_text("""
            DELETE FROM notifications
            WHERE is_read = TRUE OR created_at < :cutoff
        """), {"cutoff": cutoff_24h}).rowcount
        session.flush()
        print(f"  [KAIROS] Purgadas {purged} notificaciones antiguas/revisadas.")

        # ── 2. Check current unread count ────────────────────────────────────
        unread_count = (
            session.query(Notification)
            .filter(Notification.is_read == False)
            .count()
        )
        total_count = session.query(Notification).count()

        if unread_count >= MIN_UNREAD_THRESHOLD or total_count >= MAX_NOTIFICATIONS:
            print(f"  [KAIROS] Tray OK ({unread_count} unread). Skipping refill.")
            session.commit()
            elapsed = datetime.now() - start_time
            print(f"  [KAIROS] Done in {elapsed.total_seconds():.2f}s.")
            return

        # ── 3. Gather context ─────────────────────────────────────────────────
        stores = session.query(Store).all()
        fav_ids = {f.product_id for f in session.query(UserPreference).all()}

        # Product IDs already notified in the last DEDUP_WINDOW_HOURS
        recent_notif_pids = {
            n.product_id
            for n in session.query(Notification)
            .filter(Notification.created_at >= now - timedelta(hours=DEDUP_WINDOW_HOURS))
            .all()
            if n.product_id is not None
        }

        notifications_added = 0

        # ── 4. Per-store rotation ─────────────────────────────────────────────
        for store in stores:
            offset = _load_offset(session, store.slug, today_str)

            # Fetch a larger pool from this store, ordered by best deal first
            # Priority: has_discount desc → savings % desc → price asc
            pool = (
                session.query(StoreProduct, Price)
                .join(Price, Price.store_product_id == StoreProduct.id)
                .filter(
                    StoreProduct.store_id == store.id,
                    StoreProduct.in_stock == True,
                    Price.price.isnot(None),
                    Price.price > 0,
                    Price.scraped_at >= now - timedelta(hours=48),
                )
                .order_by(
                    Price.has_discount.desc(),
                    Price.scraped_at.desc(),
                )
                .all()
            )

            if not pool:
                print(f"  [KAIROS] {store.name}: no hay precios recientes.")
                continue

            # De-duplicate: keep best price per canonical product (or sp.id)
            seen_keys: dict[int, tuple] = {}
            for sp, price in pool:
                key = sp.product_id if sp.product_id else sp.id
                if key not in seen_keys:
                    seen_keys[key] = (sp, price)

            deduped = list(seen_keys.values())

            # Filter: minimum discount
            eligible = []
            for sp, price in deduped:
                if price.list_price and price.list_price > price.price:
                    savings_pct = round((1 - price.price / price.list_price) * 100)
                else:
                    savings_pct = 0

                if savings_pct < MIN_DISCOUNT_PCT and not price.has_discount:
                    continue

                if not sp.product_id:
                    continue  # sin producto canónico → FK violation en Postgres
                product_id_for_link = sp.product_id
                if product_id_for_link in recent_notif_pids:
                    continue

                eligible.append((sp, price, savings_pct, product_id_for_link))

            total_eligible = len(eligible)
            if total_eligible == 0:
                print(f"  [KAIROS] {store.name}: sin elegibles.")
                continue

            # Rotate: slice from current offset
            start = offset % total_eligible
            # Take a window, wrapping around if needed
            slice_items = []
            needed = DEALS_PER_STORE_PER_CYCLE
            idx = start
            while len(slice_items) < needed and len(slice_items) < total_eligible:
                slice_items.append(eligible[idx % total_eligible])
                idx += 1

            new_offset = (start + len(slice_items)) % total_eligible
            _save_offset(session, store.slug, today_str, new_offset)

            added_this_store = 0
            for sp, price, savings_pct, product_id_for_link in slice_items:
                product_name = sp.name
                price_val = price.price
                list_price = price.list_price or price_val

                savings_abs = round(list_price - price_val)
                is_fav = (sp.product_id in fav_ids) if sp.product_id else False

                type_tag, title = _classify(price_val, savings_pct, product_name, is_fav)

                message = (
                    f"{store.name} · Ahorra ${savings_abs:,.0f} hoy. "
                    f"Precio normal ${list_price:,.0f} → Precio oferta ${price_val:,.0f}."
                )
                if price.promo_description:
                    message += f" ({price.promo_description})"

                session.add(Notification(
                    product_id=product_id_for_link,
                    title=title,
                    message=message,
                    type=type_tag,
                    link_url=f"/product/{product_id_for_link}"
                ))
                recent_notif_pids.add(product_id_for_link)
                added_this_store += 1
                notifications_added += 1

            print(f"  [KAIROS] {store.name}: +{added_this_store} alertas (offset {start}->{new_offset} / {total_eligible})")

        session.commit()

    elapsed = datetime.now() - start_time
    print(f"  [KAIROS] {notifications_added} nuevas alertas generadas en {elapsed.total_seconds():.2f}s.")


if __name__ == "__main__":
    generate_proactive_alerts()
