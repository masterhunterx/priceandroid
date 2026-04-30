"""
Utilidades Compartidas de la API
================================
Funciones auxiliares para la construcción de respuestas, análisis de promociones
y sincronización Just-In-Time (JIT) de productos.
"""

import re
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
from core.db import get_session
from core.models import StoreProduct, Branch, Price, PriceInsight, UserPreference, Store
from sqlalchemy import func
from .schemas import PricePointOut, PriceInsightOut

# Constante para manejo de zona horaria UTC
UTC = timezone.utc

# Mapa de palabras clave para identificar beneficios de fidelidad (Tarjetas/Clubs)
_CARD_KEYWORDS = {
    "cencosud": "Tarjeta Cencosud",
    "jumbo ciclo": "Tarjeta Cencosud",
    "jumbo lpm": "Tarjeta Cencosud",
    "jumbo exclusivas": "Tarjeta Cencosud",
    "club unimarc": "Club Unimarc",
    "diamante": "Club Unimarc",
    "tarjeta lider": "Tarjeta Lider BCI",
    "club lider": "Tarjeta Lider BCI",
    "lider bci": "Tarjeta Lider BCI",
    "tarjeta santa isabel": "Tarjeta Santa Isabel",
}

def analyze_promo(promo_description: str) -> Dict[str, Any]:
    """
    Analiza la descripción binaria de una promoción para extraer el tipo de oferta,
    si requiere tarjeta y el precio unitario en caso de ofertas por volumen (ej. 2x1).
    """
    res = {
        "is_card": False,
        "label": "",
        "offer_type": "generic",
        "unit_price": None
    }
    
    if not promo_description:
        return res
        
    lower = promo_description.lower()
    
    # Identificación de beneficios por tarjeta de crédito o club
    for keyword, label in _CARD_KEYWORDS.items():
        if keyword in lower:
            res["is_card"] = True
            res["label"] = label
            res["offer_type"] = "card"
            break
            
    # Identificación de canales exclusivos
    if res["offer_type"] == "generic":
        if "internet" in lower or "web" in lower:
            res["label"] = "Exclusivo Web"
            res["offer_type"] = "internet"
        elif "app" in lower:
            res["label"] = "Exclusivo App"
            res["offer_type"] = "app"
        elif "liquidaci" in lower or "exclusiv" in lower:
            res["label"] = "Liquidación Exclusiva"
            res["offer_type"] = "liquidacion"

    # Detección de ofertas multi-unidad (ej. '3 por 2000' o '2 x $1.500')
    multi_match = re.search(r'(\d+)\s*(?:x|por)\s*\$?([\d\.]+)', lower)
    if multi_match:
        try:
            qty = int(multi_match.group(1))
            total = float(multi_match.group(2).replace('.', ''))
            if qty > 0:
                res["unit_price"] = total / qty
        except:
            pass
            
    return res


def _infer_unit_label(measurement_unit: str) -> str | None:
    unit = (measurement_unit or "").lower().strip()
    if unit in ("g", "gr", "grs", "gramos", "kg", "kgs"):
        return "$/100g"
    if unit in ("ml", "cc", "l", "lt", "lts", "litro", "litros"):
        return "$/100ml"
    return None


_LOCAL_LOGOS: Dict[str, str] = {
    "jumbo": "/logos/jumbo.png",
    "lider": "/logos/lider.png",
    "santa_isabel": "/logos/santa_isabel.png",
    "unimarc": "/logos/unimarc.png",
}


def preload_latest_prices(db_session, sp_ids: List[int]) -> Dict[int, Any]:
    """
    Carga el último precio chain-wide (branch_id IS NULL) de cada store_product en UNA sola query.
    Devuelve dict {store_product_id: Price}.
    """
    if not sp_ids:
        return {}
    subq = (
        db_session.query(
            Price.store_product_id,
            func.max(Price.scraped_at).label("max_at"),
        )
        .filter(Price.store_product_id.in_(sp_ids), Price.branch_id == None)
        .group_by(Price.store_product_id)
        .subquery()
    )
    rows = (
        db_session.query(Price)
        .join(subq, (Price.store_product_id == subq.c.store_product_id) &
                    (Price.scraped_at == subq.c.max_at))
        .all()
    )
    return {p.store_product_id: p for p in rows}


def build_price_points(
    db_session,
    product_id: int,
    branch_context: Optional[Dict[str, str]] = None,
    preloaded_prices: Optional[Dict[int, Any]] = None,
) -> List[PricePointOut]:
    """
    Construye la lista de precios actuales para un producto canónico en todas las tiendas.
    Si se pasa preloaded_prices (dict sp_id→Price) evita queries adicionales por precio.
    """
    store_products = (
        db_session.query(StoreProduct)
        .filter(StoreProduct.product_id == product_id)
        .all()
    )

    price_points = []
    seen_stores = set()

    for sp in store_products:
        if sp.store_id in seen_stores:
            continue
        seen_stores.add(sp.store_id)

        store = sp.store
        target_branch_id = None

        if branch_context and store.slug in branch_context:
            ext_id = branch_context[store.slug]
            branch = db_session.query(Branch).filter_by(store_id=store.id, external_store_id=ext_id).first()
            if branch:
                target_branch_id = branch.id

        if preloaded_prices is not None and not target_branch_id:
            # Usar precio precargado — evita query por producto
            latest = preloaded_prices.get(sp.id)
        else:
            latest_q = db_session.query(Price).filter(Price.store_product_id == sp.id)
            if target_branch_id:
                latest_q = latest_q.filter(Price.branch_id == target_branch_id)
            else:
                latest_q = latest_q.filter(Price.branch_id == None)
            latest = latest_q.order_by(Price.scraped_at.desc()).first()
            if not latest and target_branch_id:
                latest = (
                    db_session.query(Price)
                    .filter_by(store_product_id=sp.id, branch_id=None)
                    .order_by(Price.scraped_at.desc())
                    .first()
                )

        logo = store.logo_url or _LOCAL_LOGOS.get(store.slug, "")
        promo_desc = (latest.promo_description or "") if latest else ""
        p_info = analyze_promo(promo_desc)
        curr_price = latest.price if latest else None
        is_club = p_info["offer_type"] == "card"
        # Staleness: datos sin refrescar más de 6 horas
        _STALE_HOURS = 6
        is_stale = False
        if sp.last_sync:
            sync_dt = sp.last_sync if sp.last_sync.tzinfo else sp.last_sync.replace(tzinfo=UTC)
            is_stale = (datetime.now(UTC) - sync_dt) > timedelta(hours=_STALE_HOURS)
        else:
            is_stale = True

        price_points.append(PricePointOut(
            store_id=store.id,
            store_name=store.name,
            store_slug=store.slug,
            store_logo=logo,
            price=curr_price,
            list_price=latest.list_price if latest else None,
            promo_price=latest.promo_price if latest else None,
            promo_description=promo_desc,
            has_discount=latest.has_discount if latest else False,
            in_stock=sp.in_stock,
            product_url=sp.product_url or "",
            last_sync=sp.last_sync.isoformat() if sp.last_sync else "",
            is_card_price=p_info["is_card"],
            card_label=p_info["label"],
            offer_type=p_info["offer_type"],
            club_price=curr_price if is_club else None,
            unit_price=p_info["unit_price"],
            price_per_unit=sp.unit_price_norm,
            unit_label=_infer_unit_label(sp.measurement_unit),
            is_stale=is_stale,
        ))

    return price_points


def preload_price_insights(db_session, product_ids: List[int]) -> Dict[int, "PriceInsightOut"]:
    """Carga todos los PriceInsights de una lista de product_ids en UNA sola query."""
    if not product_ids:
        return {}
    rows = db_session.query(PriceInsight).filter(PriceInsight.product_id.in_(product_ids)).all()
    result = {}
    for insight in rows:
        result[insight.product_id] = PriceInsightOut(
            avg_price=insight.avg_price,
            min_price_all_time=insight.min_price_all_time,
            max_price_all_time=insight.max_price_all_time,
            price_trend=insight.price_trend,
            is_deal_now=insight.is_deal_now,
            deal_score=insight.deal_score,
            last_consolidated=insight.last_consolidated.isoformat() if insight.last_consolidated else ""
        )
    return result


def get_price_insight(db_session, product_id: int) -> Optional[PriceInsightOut]:
    """
    Recupera los 'Insights' (estadisticas y tendencias) calculados por el sistema inteligente
    para un producto específico.
    """
    insight = db_session.query(PriceInsight).filter_by(product_id=product_id).first()
    if not insight:
        return None
    
    return PriceInsightOut(
        avg_price=insight.avg_price,
        min_price_all_time=insight.min_price_all_time,
        max_price_all_time=insight.max_price_all_time,
        price_trend=insight.price_trend,
        is_deal_now=insight.is_deal_now,
        deal_score=insight.deal_score,
        last_consolidated=insight.last_consolidated.isoformat() if insight.last_consolidated else ""
    )


def check_favorite(db_session, product_id: int, user_id: Optional[str] = None) -> bool:
    """Verifica si un producto está en favoritos del usuario. Filtra por user_id si se provee."""
    q = db_session.query(UserPreference).filter_by(product_id=product_id)
    if user_id:
        q = q.filter_by(user_id=user_id)
    return q.first() is not None


def trigger_jit_sync(product_id: int, branch_context: Optional[Dict[str, str]] = None, block: bool = False):
    """
    Disparador para Sincronización Just-In-Time (JIT).
    Si un producto es consultado y sus datos son antiguos (>10 min), lanza un scraper instantáneo
    para asegurar que el precio mostrado en pantalla sea 100% real.
    """
    from domain.ingest import sync_single_store_product
    STALE_THRESHOLD = timedelta(minutes=10)
    
    with get_session() as session:
        store_products = session.query(StoreProduct).filter_by(product_id=product_id).all()
        updated = False
        for sp in store_products:
            target_branch = None
            if branch_context and sp.store.slug in branch_context:
                ext_id = branch_context[sp.store.slug]
                branch = session.query(Branch).filter_by(store_id=sp.store_id, external_store_id=ext_id).first()
                if branch:
                    target_branch = branch.id

            # Verificación de obsolescencia
            last_sync_aware = sp.last_sync if (sp.last_sync and sp.last_sync.tzinfo) else (sp.last_sync.replace(tzinfo=UTC) if sp.last_sync else None)
            is_stale = (last_sync_aware is None) or (datetime.now(UTC) - last_sync_aware > STALE_THRESHOLD)
            
            # Si el usuario cambió de branch, forzamos sync aunque no sea stale
            if target_branch and sp.branch_id != target_branch:
                is_stale = True

            if is_stale:
                if sync_single_store_product(session, sp.id, branch_id=target_branch):
                    updated = True
        return updated


def trigger_jit_sync_standalone(sp, branch_context: Optional[Dict[str, str]] = None):
    """Sincronización JIT para una instancia única de StoreProduct (usada en vistas de detalle)."""
    from domain.ingest import sync_single_store_product
    STALE_THRESHOLD = timedelta(minutes=10)
    
    target_branch = None
    if branch_context and sp.store.slug in branch_context:
        with get_session() as session:
            ext_id = branch_context[sp.store.slug]
            branch = session.query(Branch).filter_by(store_id=sp.store_id, external_store_id=ext_id).first()
            if branch: target_branch = branch.id

        last_sync_aware = sp.last_sync if (sp.last_sync and sp.last_sync.tzinfo) else (sp.last_sync.replace(tzinfo=UTC) if sp.last_sync else None)
        is_stale = (last_sync_aware is None) or (datetime.now(UTC) - last_sync_aware > STALE_THRESHOLD)
        if is_stale or (target_branch and sp.branch_id != target_branch):
            with get_session() as session:
                sync_single_store_product(session, sp.id, branch_id=target_branch)


def best_price_info(price_points: List[PricePointOut]):
    """Encuentra la mejor oferta (precio más bajo en stock) dentro de un set de opciones."""
    available = [pp for pp in price_points if pp.in_stock and pp.price is not None]
    if not available:
        return None, None, None

    best = min(available, key=lambda pp: pp.price)
    return best.price, best.store_name, best.store_slug
