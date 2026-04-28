"""
Router de Productos KAIROS
==========================
Gestión de búsqueda, sugerencias y sincronización en tiempo real de productos.
Soporta búsqueda resiliente y optimización de consultas SQL (joinedload).
"""

import json
import logging
import re
import time
import threading
import unicodedata

logger = logging.getLogger("FreshCartAPI")
from typing import Optional
from fastapi import APIRouter, Query, HTTPException, Header, BackgroundTasks, Depends
from core.db import get_session
from core.models import Product, StoreProduct, Price, Store, ProductMatch, UserPreference
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload
from ..schemas import UnifiedResponse, SearchResponse, ProductOut, ProductDetailOut, PricePointOut, PriceHistoryOut, OptimizeCartRequest
from ..utils import (
    build_price_points,
    preload_latest_prices,
    preload_price_insights,
    get_price_insight,
    check_favorite,
    trigger_jit_sync,
    trigger_jit_sync_standalone,
    best_price_info,
    analyze_promo,
    _infer_unit_label,
)
from ..middleware import get_api_key

router = APIRouter(
    prefix="/api/products",
    tags=["Products"],
    dependencies=[Depends(get_api_key)]
)

# ── Caché de búsquedas en memoria ─────────────────────────────────────────────
# Evita golpear la BD en búsquedas repetidas dentro de la ventana TTL.
_SEARCH_CACHE_TTL = 300  # segundos
_search_cache: dict[str, tuple[float, object]] = {}  # {cache_key: (timestamp, result)}
_search_cache_lock = threading.Lock()

def _get_cached(key: str):
    with _search_cache_lock:
        entry = _search_cache.get(key)
        if entry and (time.time() - entry[0]) < _SEARCH_CACHE_TTL:
            return entry[1]
    return None

def _set_cached(key: str, value):
    with _search_cache_lock:
        if len(_search_cache) >= 500:
            now = time.time()
            expired = [k for k, (ts, _) in _search_cache.items() if now - ts >= _SEARCH_CACHE_TTL]
            for k in expired:
                del _search_cache[k]
            # Si no había expiradas, echar la entrada más antigua (LRU mínimo)
            if len(_search_cache) >= 500:
                oldest = min(_search_cache, key=lambda k: _search_cache[k][0])
                del _search_cache[oldest]
        _search_cache[key] = (time.time(), value)

def _strip_accents(text: str) -> str:
    return ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )


def _build_text_filter(query_obj, q: str):
    """Aplica filtro de búsqueda resiliente a acentos y errores tipográficos en vocales."""
    tok = _strip_accents(q.strip().lower())
    tok_esc = tok.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    pattern = f"%{re.sub(r'[aeiou]', '_', tok_esc)}%"
    return query_obj.filter(
        (func.lower(StoreProduct.name).like(pattern, escape='\\')) |
        (func.lower(StoreProduct.brand).like(pattern, escape='\\'))
    )


_CATEGORY_STOP = frozenset({'y', 'de', 'del', 'la', 'las', 'el', 'los', 'a', 'e'})

def _build_category_filter(query_obj, category: str):
    """Aplica filtro de categoría usando OR de palabras significativas."""
    cat_lower = category.strip().lower()
    cat_esc = cat_lower.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    sig_words = [
        w.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        for w in cat_lower.split()
        if w not in _CATEGORY_STOP and len(w) >= 3
    ]
    conditions = [
        func.lower(StoreProduct.top_category).like(f"%{cat_esc}%", escape='\\'),
        func.lower(StoreProduct.category_path).like(f"%{cat_esc}%", escape='\\'),
    ] + [
        func.lower(StoreProduct.top_category).like(f"%{w}%", escape='\\')
        for w in sig_words
    ] + [
        func.lower(StoreProduct.category_path).like(f"%{w}%", escape='\\')
        for w in sig_words
    ]
    return query_obj.filter(or_(*conditions))


def _enrich_results(
    session, page_items, store, branch_map,
    bulk_prices, canonical_products, bulk_insights, fav_product_ids,
):
    """Construye la lista de ProductOut a partir de los store_products paginados."""
    results = []
    seen_canonical_ids: set = set()

    for sp in page_items:
        if sp.product_id:
            if sp.product_id in seen_canonical_ids:
                continue
            p = canonical_products.get(sp.product_id)
            if p:
                seen_canonical_ids.add(p.id)
                price_points = build_price_points(
                    session, p.id, branch_context=branch_map, preloaded_prices=bulk_prices,
                )
                if store:
                    price_points = [pp for pp in price_points if pp.store_slug == store]
                if price_points:
                    best_price_val, b_store, b_store_slug = best_price_info(price_points)
                    results.append(ProductOut(
                        id=p.id,
                        name=p.canonical_name,
                        brand=p.brand or "",
                        category=p.category or "",
                        image_url=p.image_url or "",
                        weight_value=p.weight_value,
                        weight_unit=p.weight_unit,
                        prices=price_points,
                        best_price=best_price_val,
                        best_store=b_store,
                        best_store_slug=b_store_slug,
                        price_insight=bulk_insights.get(p.id),
                        is_favorite=p.id in fav_product_ids,
                    ))
                    continue

        # Fallback para productos no emparejados (unmatched)
        # ID negativo: convencion interna para store_products sin canonical match.
        # Evita colision con product.id cuando sp.id > 1_000_000.
        latest_price_obj = sp.latest_price
        price_val = latest_price_obj.price if latest_price_obj else 0
        results.append(ProductOut(
            id=-(sp.id),
            name=sp.name,
            brand=sp.brand or "",
            category=sp.top_category or "",
            image_url=sp.image_url or "",
            prices=[PricePointOut(
                store_id=sp.store_id,
                store_name=sp.store.name,
                store_slug=sp.store.slug,
                store_logo=sp.store.logo_url or "",
                price=price_val,
                in_stock=sp.in_stock,
                last_sync=sp.last_sync.isoformat() if sp.last_sync else "",
                price_per_unit=sp.unit_price_norm,
                unit_label=_infer_unit_label(sp.measurement_unit),
            )],
            best_price=price_val,
            best_store=sp.store.name,
            best_store_slug=sp.store.slug,
            is_favorite=False,
        ))

    return results


def _logged_jit_sync(product_id: int, branch_context=None):
    try:
        trigger_jit_sync(product_id, branch_context=branch_context)
    except Exception as exc:
        logger.warning(f"[JIT-bg] sync falló para product_id={product_id}: {exc}")

@router.get("/search", response_model=UnifiedResponse)
def search_products(
    q: str = Query("", description="Término de búsqueda"),
    store: Optional[str] = Query(None, description="Filtrar por slug de tienda"),
    category: Optional[str] = Query(None, description="Filtrar por categoría"),
    in_stock: Optional[bool] = Query(True, description="Solo productos en stock"),
    sort: str = Query("price_asc", description="Ordenar: price_asc, price_desc, name"),
    page: int = Query(1, ge=1, description="Página"),
    page_size: int = Query(20, ge=1, le=100, description="Resultados por página"),
    x_branch_context: Optional[str] = Header(None, alias="X-Branch-Context"),
    current_user: str = Depends(get_api_key),
):
    """Motor de Búsqueda KAIROS: búsqueda resiliente multi-tienda con caché y precarga bulk."""
    q = q.strip()
    if len(q) > 100:
        raise HTTPException(status_code=400, detail="El término de búsqueda es demasiado largo.")
    if category and len(category) > 100:
        raise HTTPException(status_code=400, detail="El filtro de categoría es demasiado largo.")

    # current_user es parte de la key: sin esto, los is_favorite de un usuario
    # se filtrarían a otros usuarios que hagan la misma búsqueda.
    cache_key = f"{current_user}|{q}|{store}|{category}|{sort}|{page}|{page_size}"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    if q and current_user and len(current_user) <= 30:
        try:
            from core.metrics import user_searches_total
            user_searches_total.labels(username=current_user).inc()
        except Exception as _e:
            logger.debug(f"[search] metrics: {_e}")
    if q:
        try:
            from .deals import track_search_term
            track_search_term(q)
        except Exception as _e:
            logger.debug(f"[search] track: {_e}")

    branch_map = None
    if x_branch_context:
        try:
            branch_map = json.loads(x_branch_context)
        except json.JSONDecodeError:
            pass

    with get_session() as session:
        base_q = session.query(StoreProduct).options(
            joinedload(StoreProduct.product),
            joinedload(StoreProduct.store),
        )
        if q:
            base_q = _build_text_filter(base_q, q)
        if in_stock is not None:
            base_q = base_q.filter(StoreProduct.in_stock == in_stock)
        if category:
            base_q = _build_category_filter(base_q, category)
        if store:
            base_q = base_q.filter(StoreProduct.store.has(slug=store))

        total = base_q.count()
        offset = (page - 1) * page_size

        if sort in ("price_asc", "price_desc"):
            price_sq = (
                session.query(
                    Price.store_product_id.label("sp_id"),
                    func.min(Price.price).label("min_price"),
                )
                .filter(Price.branch_id == None)
                .group_by(Price.store_product_id)
                .subquery("lp")
            )
            ordered = base_q.outerjoin(price_sq, StoreProduct.id == price_sq.c.sp_id)
            if sort == "price_asc":
                ordered = ordered.order_by(price_sq.c.min_price.asc().nullslast())
            else:
                ordered = ordered.order_by(price_sq.c.min_price.desc().nullsfirst())
            page_items = ordered.limit(page_size).offset(offset).all()
        elif sort == "name":
            page_items = base_q.order_by(StoreProduct.name.asc()).limit(page_size).offset(offset).all()
        else:
            page_items = base_q.order_by(StoreProduct.id.asc()).limit(page_size).offset(offset).all()

        # Precarga bulk — una query por tipo, sin N+1
        canonical_products = {
            sp.product_id: sp.product for sp in page_items if sp.product_id and sp.product
        }
        all_sp_ids = []
        if canonical_products:
            all_sp_ids = [
                s.id for s in session.query(StoreProduct)
                .filter(StoreProduct.product_id.in_(canonical_products.keys())).all()
            ]

        bulk_prices   = preload_latest_prices(session, all_sp_ids) if all_sp_ids else {}
        bulk_insights = preload_price_insights(session, list(canonical_products.keys())) if canonical_products else {}

        fav_product_ids: set = set()
        if canonical_products:
            fav_rows = (
                session.query(UserPreference.product_id)
                .filter(
                    UserPreference.product_id.in_(canonical_products.keys()),
                    UserPreference.user_id == current_user,
                )
                .all()
            )
            fav_product_ids = {r[0] for r in fav_rows}

        results = _enrich_results(
            session, page_items, store, branch_map,
            bulk_prices, canonical_products, bulk_insights, fav_product_ids,
        )

        response = UnifiedResponse(data=SearchResponse(
            results=results[:page_size], total=total, page=page, page_size=page_size,
        ))
        _set_cached(cache_key, response)
        return response

@router.get("/suggestions", response_model=UnifiedResponse)
def get_search_suggestions(q: str = Query("", min_length=1)):
    """
    KAIROS Suggestion Engine: Autocompletado rápido con product_id para navegación directa.
    """
    if not q or len(q.strip()) < 2:
        return UnifiedResponse(data=[])

    q_clean = q.strip().lower()
    q_esc   = q_clean.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    term    = f"{q_esc}%"

    with get_session() as session:
        rows = (
            session.query(
                StoreProduct.name,
                StoreProduct.brand,
                ProductMatch.product_id,
                Store.name.label("store_name"),
                Store.slug.label("store_slug"),
                Store.logo_url.label("store_logo"),
            )
            .join(Store)
            .outerjoin(ProductMatch, ProductMatch.store_product_id == StoreProduct.id)
            .filter(
                StoreProduct.in_stock == True,
                (func.lower(StoreProduct.name).like(term, escape='\\')) |
                (func.lower(StoreProduct.brand).like(term, escape='\\'))
            )
            .limit(20)
            .all()
        )

        seen_names  = set()
        seen_brands = set()
        results     = []

        for name, brand, product_id, s_name, s_slug, s_logo in rows:
            clean_name = name.strip()
            key = clean_name.lower()
            if key not in seen_names:
                results.append({
                    "term":       clean_name,
                    "type":       "product",
                    "product_id": product_id,
                    "store":      s_name,
                    "store_slug": s_slug,
                    "store_logo": s_logo,
                })
                seen_names.add(key)

            if brand and brand.lower().startswith(q_clean):
                bkey = brand.strip().lower()
                if bkey not in seen_brands:
                    results.append({
                        "term":       brand.strip(),
                        "type":       "brand",
                        "product_id": None,
                        "store":      None,
                        "store_slug": None,
                        "store_logo": None,
                    })
                    seen_brands.add(bkey)

        return UnifiedResponse(data=results[:8])

@router.get("/{product_id}", response_model=UnifiedResponse)
def get_product(
    product_id: int,
    background_tasks: BackgroundTasks,
    x_branch_context: Optional[str] = Header(None, alias="X-Branch-Context"),
    current_user: str = Depends(get_api_key),
):
    """
    Obtener detalle completo de un producto por su ID.
    Controla tanto productos canónicos como productos específicos de tienda.
    """
    branch_map = None
    if x_branch_context:
        try:
            branch_map = json.loads(x_branch_context)
        except json.JSONDecodeError:
            pass  # Header malformado, se ignora

    # Lógica para productos específicos de tienda (unmatched)
    if product_id >= 1000000:
        sp_id = product_id - 1000000
        with get_session() as session:
            sp = session.get(StoreProduct, sp_id)
            if not sp:
                raise HTTPException(status_code=404, detail="Producto no encontrado")
            
            # Sincronización instantánea si los datos están desactualizados
            try:
                trigger_jit_sync_standalone(sp, branch_context=branch_map)
                session.refresh(sp)
            except Exception as exc:
                logger.warning(f"[JIT] sync falló para sp_id={sp_id}: {exc}")
            latest = sp.latest_price
            promo_desc = (latest.promo_description or "") if latest else ""
            p_info = analyze_promo(promo_desc)
            curr_price = latest.price if latest else None
            is_club = p_info["offer_type"] == "card"

            price_points = [PricePointOut(
                store_id=sp.store_id,
                store_name=sp.store.name,
                store_slug=sp.store.slug,
                store_logo=sp.store.logo_url or "",
                price=curr_price,
                list_price=latest.list_price if latest else None,
                promo_price=latest.promo_price if latest else None,
                promo_description=promo_desc,
                has_discount=latest.has_discount if latest else False,
                last_sync=sp.last_sync.isoformat() if sp.last_sync else "",
                in_stock=sp.in_stock,
                product_url=sp.product_url or "",
                is_card_price=p_info["is_card"],
                card_label=p_info["label"],
                offer_type=p_info["offer_type"],
                club_price=curr_price if is_club else None,
                unit_price=p_info["unit_price"],
            )]

            return UnifiedResponse(data=ProductDetailOut(
                id=product_id,
                name=sp.name,
                brand=sp.brand or "",
                category=sp.top_category or "",
                category_path=sp.category_path or "",
                image_url=sp.image_url or "",
                prices=price_points,
                best_price=latest.price if latest else None,
                best_store=sp.store.name,
                best_store_slug=sp.store.slug,
                price_history=[], 
                price_insight=None,
                is_favorite=False,
            ))

    # JIT sync en background — no bloquea el request; el usuario ve datos del último ciclo
    background_tasks.add_task(_logged_jit_sync, product_id, branch_context=branch_map)
    
    with get_session() as session:
        product = session.get(Product, product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
 
        price_points = build_price_points(session, product.id, branch_context=branch_map)
        best_price_val, b_store, b_store_slug = best_price_info(price_points)

        # Historial de precios: query directa con LIMIT — evita cargar todas las filas en memoria
        PRICE_HISTORY_LIMIT = 60
        sp_id_list = [
            r[0] for r in session.query(StoreProduct.id)
            .filter(StoreProduct.product_id == product.id)
            .all()
        ]
        price_history = []
        if sp_id_list:
            history_rows = (
                session.query(Price)
                .filter(Price.store_product_id.in_(sp_id_list))
                .order_by(Price.scraped_at.asc())
                .limit(PRICE_HISTORY_LIMIT)
                .all()
            )
            price_history = [
                PriceHistoryOut(
                    price=pr.price,
                    scraped_at=pr.scraped_at.isoformat() if pr.scraped_at else "",
                )
                for pr in history_rows
            ]

        return UnifiedResponse(data=ProductDetailOut(
            id=product.id,
            name=product.canonical_name,
            brand=product.brand or "",
            category=product.category or "",
            category_path=product.category_path or "",
            image_url=product.image_url or "",
            weight_value=product.weight_value,
            weight_unit=product.weight_unit,
            prices=price_points,
            best_price=best_price_val,
            best_store=b_store,
            best_store_slug=b_store_slug,
            price_history=price_history,
            price_insight=get_price_insight(session, product.id),
            is_favorite=check_favorite(session, product.id, user_id=current_user),
        ))

@router.post("/{product_id}/sync", response_model=UnifiedResponse)
def sync_product_details(product_id: int):
    """Fuerza la sincronización en tiempo real de los precios de un producto."""
    from domain.ingest import sync_single_store_product
    with get_session() as session:
        if product_id >= 1000000:
            sp_target_id = product_id - 1000000
            store_products = [session.get(StoreProduct, sp_target_id)]
        else:
            store_products = session.query(StoreProduct).filter_by(product_id=product_id).all()
            
        if not store_products or not any(store_products):
            raise HTTPException(status_code=404, detail="No se encontraron precios para sincronizar")
            
        updated = 0
        for sp in store_products:
            if not sp: continue
            if sync_single_store_product(session, sp.id):
                updated += 1
                
        return UnifiedResponse(data={"updated_count": updated, "status": "verified"})

@router.post("/verify/{product_id}", response_model=UnifiedResponse)
def verify_price_realtime(product_id: int):
    """Alias para la sincronización de precios (Verificación de integridad)."""
    return sync_product_details(product_id)


@router.post("/optimize-cart", response_model=UnifiedResponse)
def optimize_cart_endpoint(req: OptimizeCartRequest):
    """Optimiza un carrito de compras eligiendo la mejor tienda por producto."""
    from domain.cart_optimizer import optimize_cart
    with get_session() as session:
        result = optimize_cart(session, list(req.items))
    return UnifiedResponse(data=result)
