"""
Métricas Prometheus — FreshCart Antigravity
============================================
Expone métricas de negocio y salud del sistema para Grafana Cloud.
"""

from prometheus_client import Counter, Gauge, Histogram, Info

# ── Info del sistema ───────────────────────────────────────────────────────────
app_info = Info("freshcart_app", "Información de la aplicación FreshCart")
app_info.info({"version": "1.1.0", "environment": "production"})

# ── Catálogo de productos ──────────────────────────────────────────────────────
products_total = Gauge(
    "freshcart_products_total",
    "Total de productos en el catálogo"
)
products_stale = Gauge(
    "freshcart_products_stale_total",
    "Productos sin sincronizar hace más de 48h"
)
products_out_of_stock = Gauge(
    "freshcart_products_out_of_stock_total",
    "Productos marcados como sin stock"
)
products_never_synced = Gauge(
    "freshcart_products_never_synced_total",
    "Productos que nunca han sido sincronizados"
)
products_unmatched = Gauge(
    "freshcart_products_unmatched_total",
    "Productos sin ficha canónica (product_id=NULL, invisibles en la app)"
)

# ── Actividad de sincronización ────────────────────────────────────────────────
sync_operations_total = Counter(
    "freshcart_sync_operations_total",
    "Total de sincronizaciones JIT realizadas",
    ["store", "result"]   # result: success | not_found | error
)
price_updates_total = Counter(
    "freshcart_price_updates_total",
    "Total de actualizaciones de precio grabadas",
    ["store"]
)
scraper_errors_total = Counter(
    "freshcart_scraper_errors_total",
    "Total de errores de scraper por tienda",
    ["store", "error_type"]
)

# ── Stock scan ─────────────────────────────────────────────────────────────────
stock_scan_duration_seconds = Histogram(
    "freshcart_stock_scan_duration_seconds",
    "Duración de cada ciclo de stock scan",
    buckets=[1, 5, 10, 30, 60, 120, 300, 600]
)
stock_scan_products_updated = Gauge(
    "freshcart_stock_scan_last_updated",
    "Productos actualizados en el último ciclo de stock scan"
)
stock_scan_products_oos = Gauge(
    "freshcart_stock_scan_last_marked_oos",
    "Productos marcados sin stock en el último ciclo"
)

# ── Feedback ───────────────────────────────────────────────────────────────────
feedback_total = Gauge(
    "freshcart_feedback_total",
    "Total de reportes de feedback",
    ["type", "status"]    # type: bug|mejora|sugerencia  status: pending|analyzed|resolved
)

# ── API ────────────────────────────────────────────────────────────────────────
api_blocked_requests_total = Counter(
    "freshcart_api_blocked_requests_total",
    "Requests bloqueadas por el WAF o rate limiter",
    ["reason"]            # reason: waf | rate_limit | blocked_ip | unknown_user
)

# ── Usuarios y sesiones ────────────────────────────────────────────────────────
users_active_total = Gauge(
    "freshcart_users_active_total",
    "Usuarios con sesión activa en este momento"
)
user_logins_total = Counter(
    "freshcart_user_logins_total",
    "Total de logins exitosos por usuario",
    ["username"]
)
user_session_duration_seconds = Histogram(
    "freshcart_user_session_duration_seconds",
    "Duración de cada sesión de usuario en segundos",
    buckets=[60, 300, 600, 1800, 3600, 7200, 14400, 28800]
)

# ── Comportamiento de búsqueda ─────────────────────────────────────────────────
user_searches_total = Counter(
    "freshcart_user_searches_total",
    "Total de búsquedas realizadas por usuario",
    ["username"]
)


def refresh_catalog_gauges():
    """Actualiza los gauges de catálogo consultando la BD. Llamar periódicamente."""
    try:
        from datetime import datetime, timezone, timedelta
        from core.db import get_session
        from core.models import StoreProduct
        from sqlalchemy import func

        UTC = timezone.utc
        cutoff_48h = datetime.now(UTC) - timedelta(hours=48)

        with get_session() as session:
            total = session.query(func.count(StoreProduct.id)).scalar() or 0
            oos = session.query(func.count(StoreProduct.id)).filter(
                StoreProduct.in_stock == False
            ).scalar() or 0
            stale = session.query(func.count(StoreProduct.id)).filter(
                (StoreProduct.last_sync == None) | (StoreProduct.last_sync < cutoff_48h)
            ).scalar() or 0
            never = session.query(func.count(StoreProduct.id)).filter(
                StoreProduct.last_sync == None
            ).scalar() or 0
            unmatched = session.query(func.count(StoreProduct.id)).filter(
                StoreProduct.product_id == None
            ).scalar() or 0

        products_total.set(total)
        products_out_of_stock.set(oos)
        products_stale.set(stale)
        products_never_synced.set(never)
        products_unmatched.set(unmatched)

    except Exception:
        pass  # No interrumpir el servidor si falla la métrica


def refresh_feedback_gauges():
    """Actualiza gauges de feedback desde la BD."""
    try:
        from core.db import get_session
        from core.models import Feedback
        from sqlalchemy import func

        with get_session() as session:
            rows = session.query(
                Feedback.type, Feedback.status, func.count(Feedback.id)
            ).group_by(Feedback.type, Feedback.status).all()

        for fb_type, fb_status, count in rows:
            feedback_total.labels(type=fb_type, status=fb_status).set(count)

    except Exception:
        pass
