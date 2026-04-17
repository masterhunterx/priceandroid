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


def build_price_points(db_session, product_id: int, branch_context: Optional[Dict[str, str]] = None) -> List[PricePointOut]:
    """
    Construye la lista de precios actuales para un producto canónico en todas las tiendas.
    Respeta el contexto de sucursal (X-Branch-Context) si está presente.
    """
    # Buscamos todas las instancias de este producto en distintas cadenas
    store_products = (
        db_session.query(StoreProduct)
        .filter(StoreProduct.product_id == product_id)
        .all()
    )

    price_points = []
    seen_stores = set()
    
    for sp in store_products:
        # Solo mostramos un precio por cada tienda física para no saturar
        if sp.store_id in seen_stores: continue
        seen_stores.add(sp.store_id)
        
        store = sp.store
        target_branch_id = None
        
        # Resolución de sucursal específica según el contexto del usuario (geolocalización)
        if branch_context and store.slug in branch_context:
            ext_id = branch_context[store.slug]
            branch = db_session.query(Branch).filter_by(store_id=store.id, external_store_id=ext_id).first()
            if branch:
                target_branch_id = branch.id

        # Consulta del último precio registrado
        latest_query = (
            db_session.query(Price)
            .filter(Price.store_product_id == sp.id)
        )
        if target_branch_id:
            latest_query = latest_query.filter(Price.branch_id == target_branch_id)
        else:
            latest_query = latest_query.filter(Price.branch_id == None)
            
        latest = latest_query.order_by(Price.scraped_at.desc()).first()

        # Fallback a precio nacional (chain-wide) si no hay precio específico para la branch solicitada
        if not latest and target_branch_id:
            latest = db_session.query(Price).filter_by(store_product_id=sp.id, branch_id=None).order_by(Price.scraped_at.desc()).first()

        # Fallback de logos — primero los almacenados en la DB, luego assets locales.
        # Se evita Clearbit (servicio externo sin SLA) que puede bloquearse o caer.
        _LOCAL_LOGOS: dict = {
            "jumbo": "/logos/jumbo.png",
            "lider": "/logos/lider.png",
            "santa_isabel": "/logos/santa_isabel.png",
            "unimarc": "/logos/unimarc.png",
        }
        logo = store.logo_url or _LOCAL_LOGOS.get(store.slug, "")

        promo_desc = (latest.promo_description or "") if latest else ""
        p_info = analyze_promo(promo_desc)
        
        curr_price = latest.price if latest else None
        is_club = p_info["offer_type"] == "card"

        # If a recent positive price exists, consider the product in stock
        # This overrides stale in_stock=False from 24h crawl cycles
        price_based_in_stock = bool(latest and latest.price and latest.price > 0)
        effective_in_stock = sp.in_stock or price_based_in_stock

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
            in_stock=effective_in_stock,
            product_url=sp.product_url or "",
            last_sync=sp.last_sync.isoformat() if sp.last_sync else "",
            is_card_price=p_info["is_card"],
            card_label=p_info["label"],
            offer_type=p_info["offer_type"],
            club_price=curr_price if is_club else None,
            unit_price=p_info["unit_price"],
        ))

    return price_points


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


def check_favorite(db_session, product_id: int) -> bool:
    """Verifica de forma rápida si un producto está en la lista de favoritos del usuario."""
    return db_session.query(UserPreference).filter_by(product_id=product_id).first() is not None


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
            is_stale = (sp.last_sync is None) or (datetime.now(UTC) - sp.last_sync.replace(tzinfo=UTC) > STALE_THRESHOLD)
            
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

        is_stale = (sp.last_sync is None) or (datetime.now(UTC) - sp.last_sync.replace(tzinfo=UTC) > STALE_THRESHOLD)
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
