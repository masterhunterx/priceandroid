"""
Descubrimiento de Ofertas y Tendencias
======================================
Router para la visualización de descuentos activos, productos tendencia y planificación
extrema de ahorro (Ultraplan).
"""

import threading
from collections import Counter
from typing import Optional
from fastapi import APIRouter, Query, Depends, Body, HTTPException
from core.db import get_session
from core.models import Product, StoreProduct, Price, Store
from sqlalchemy import func
from ..schemas import UnifiedResponse, DealOut
from ..middleware import get_api_key

# Contador en memoria de búsquedas — thread-safe via lock
_search_counter: Counter = Counter()
_search_counter_lock = threading.Lock()

_TERM_EMOJI: dict = {
    "leche": "🥛", "cerveza": "🍺", "arroz": "🍚", "pan": "🍞",
    "aceite": "🍳", "yogurt": "🥛", "detergente": "🧼", "atún": "🐟",
    "huevos": "🥚", "pollo": "🍗", "carne": "🥩", "queso": "🧀",
    "vino": "🍷", "agua": "💧", "jugo": "🥤", "cereal": "🌾",
    "café": "☕", "pasta": "🍝", "azúcar": "🍬", "sal": "🧂",
}

def track_search_term(term: str) -> None:
    """Registra una búsqueda en el contador en memoria (thread-safe)."""
    t = term.strip().lower()
    if len(t) >= 2:
        with _search_counter_lock:
            _search_counter[t] += 1

_STATIC_FALLBACK = [
    {"term": "Leche", "icon": "🥛"},   {"term": "Arroz", "icon": "🍚"},
    {"term": "Aceite", "icon": "🍳"},  {"term": "Huevos", "icon": "🥚"},
    {"term": "Yogurt", "icon": "🥛"},  {"term": "Cerveza", "icon": "🍺"},
    {"term": "Atún", "icon": "🐟"},    {"term": "Detergente", "icon": "🧼"},
    {"term": "Pan", "icon": "🍞"},
]

router = APIRouter(
    prefix="/api",
    tags=["Deals & Discover"],
    dependencies=[Depends(get_api_key)]
)

@router.get("/trending", response_model=UnifiedResponse)
async def get_trending_searches():
    """Búsquedas más frecuentes desde el último deploy (contador en memoria)."""
    with _search_counter_lock:
        has_enough = len(_search_counter) >= 5
        top = _search_counter.most_common(9) if has_enough else []
    if has_enough:
        result = []
        for term, _ in top:
            emoji = next((v for k, v in _TERM_EMOJI.items() if k in term), "🔍")
            result.append({"term": term.capitalize(), "icon": emoji})
        return UnifiedResponse(data=result)
    return UnifiedResponse(data=_STATIC_FALLBACK)


_CATEGORY_MAP = [
    {
        "name": "Despensa",
        "emoji": "🛒",
        "color": "#f59e0b",
        "keywords": ["despensa", "arroz", "pasta", "fideos", "legumbre", "aceite", "vinagre", "sal", "azucar", "harina", "conserva", "enlatado", "salsa", "condimento", "cereal", "avena"],
    },
    {
        "name": "Lácteos y Huevos",
        "emoji": "🥛",
        "color": "#3b82f6",
        "keywords": ["lacteo", "lácteo", "leche", "yogur", "queso", "mantequilla", "crema", "huevo", "frescos", "refrigerad"],
    },
    {
        "name": "Frutas y Verduras",
        "emoji": "🥦",
        "color": "#22c55e",
        "keywords": ["fruta", "verdura", "vegetal", "hortaliza", "ensalada"],
    },
    {
        "name": "Carnes y Pescados",
        "emoji": "🥩",
        "color": "#ef4444",
        "keywords": ["carne", "pollo", "cerdo", "vacuno", "pescado", "marisco", "filete", "carnicer", "pescader"],
    },
    {
        "name": "Panadería y Dulces",
        "emoji": "🍞",
        "color": "#f97316",
        "keywords": ["pan", "pasteler", "pastel", "torta", "dulce", "chocolate", "galleta", "snack", "colacion", "desayuno", "mermelada", "miel", "manjar"],
    },
    {
        "name": "Bebidas y Licores",
        "emoji": "🍷",
        "color": "#8b5cf6",
        "keywords": ["bebida", "jugo", "agua", "licor", "vino", "cerveza", "whisky", "ron", "pisco", "refresco", "energetica"],
    },
    {
        "name": "Congelados",
        "emoji": "🧊",
        "color": "#06b6d4",
        "keywords": ["congelado", "helado", "pizza congelada"],
    },
    {
        "name": "Quesos y Fiambres",
        "emoji": "🧀",
        "color": "#eab308",
        "keywords": ["queso", "fiambre", "embutido", "jamon", "salame", "mortadela", "salchicha"],
    },
    {
        "name": "Limpieza del Hogar",
        "emoji": "🧹",
        "color": "#14b8a6",
        "keywords": ["limpieza", "detergente", "cloro", "suavizante", "limpiapisos", "esponja", "basura", "aseo"],
    },
    {
        "name": "Cuidado Personal",
        "emoji": "🧴",
        "color": "#ec4899",
        "keywords": ["personal", "belleza", "perfumer", "higiene", "shampoo", "jabon", "desodorante", "crema", "maquillaje", "boti", "farmacia", "salud"],
    },
    {
        "name": "Bebés y Niños",
        "emoji": "👶",
        "color": "#a78bfa",
        "keywords": ["bebe", "bebé", "niño", "panal", "pañal", "infantil", "juguete", "mundo beb"],
    },
    {
        "name": "Mascotas",
        "emoji": "🐾",
        "color": "#84cc16",
        "keywords": ["mascota", "perro", "gato", "animal"],
    },
    {
        "name": "Comidas Preparadas",
        "emoji": "🍱",
        "color": "#f43f5e",
        "keywords": ["preparad", "plato", "comida lista", "listo para comer"],
    },
    {
        "name": "Hogar y Tecnología",
        "emoji": "🏠",
        "color": "#64748b",
        "keywords": ["hogar", "tecnolog", "electro", "ferreteri", "jardin", "automo"],
    },
]

def _normalize_category(raw: str) -> str:
    """Mapea una categoría raw de tienda a la categoría canónica."""
    if not raw:
        return "Otros"
    lower = raw.lower()
    for cat in _CATEGORY_MAP:
        if any(kw in lower for kw in cat["keywords"]):
            return cat["name"]
    return "Otros"


@router.get("/categories", response_model=UnifiedResponse)
def list_categories(
    store: Optional[str] = Query(None, description="Filtrar por slug de tienda"),
):
    """
    Lista categorías normalizadas agrupando las variantes de cada tienda.
    Devuelve nombre canónico, emoji, color y conteo de productos en stock.
    Acepta ?store=jumbo para mostrar solo los conteos de esa tienda.
    """
    with get_session() as session:
        q = (
            session.query(StoreProduct.top_category, func.count(StoreProduct.id))
            .filter(StoreProduct.top_category.isnot(None), StoreProduct.top_category != "")
            .filter(StoreProduct.in_stock == True)
        )
        if store:
            q = q.join(Store, Store.id == StoreProduct.store_id).filter(Store.slug == store)
        rows = q.group_by(StoreProduct.top_category).all()

    # Agrupar por categoría normalizada
    counts: dict[str, int] = {}
    for raw_cat, count in rows:
        canonical = _normalize_category(raw_cat)
        counts[canonical] = counts.get(canonical, 0) + count

    # Construir respuesta ordenada por conteo desc, con metadata visual
    meta = {c["name"]: c for c in _CATEGORY_MAP}
    meta["Otros"] = {"name": "Otros", "emoji": "📦", "color": "#94a3b8"}

    result = []
    for name, count in sorted(counts.items(), key=lambda x: -x[1]):
        m = meta.get(name, meta["Otros"])
        result.append({
            "name": name,
            "emoji": m["emoji"],
            "color": m["color"],
            "product_count": count,
        })

    return UnifiedResponse(data=result)


@router.get("/deals", response_model=UnifiedResponse)
def list_deals(
    limit: int = Query(20, ge=1, le=100, description="Máximo de ofertas a retornar"),
    offset: int = Query(0, ge=0, description="Desplazamiento para paginación"),
    store: Optional[str] = Query(None, description="Filtrar por slug de tienda (jumbo, santa_isabel, lider, unimarc)"),
):
    """
    Motor de Detección de Ofertas: Encuentra los productos con mayores descuentos activos
    en relación a su precio de lista histórico. Prioriza las ofertas recolectadas recientemente.
    Soporta paginación mediante el parámetro offset y filtrado por tienda.
    """
    _VALID_STORE_SLUGS = frozenset({'jumbo', 'lider', 'santa_isabel', 'unimarc'})
    if store and store not in _VALID_STORE_SLUGS:
        raise HTTPException(status_code=400, detail="Slug de tienda no válido.")

    with get_session() as session:
        q = (
            session.query(StoreProduct, Price, Store)
            .join(Price, Price.store_product_id == StoreProduct.id)
            .join(Store, Store.id == StoreProduct.store_id)
            .filter(Price.has_discount == True)
            .filter(StoreProduct.in_stock == True)
        )
        if store:
            q = q.filter(Store.slug == store)
        # Fijamos un pool grande (500) para que la deduplicación y la paginación
        # funcionen correctamente sin depender del offset del cliente.
        discounted = q.order_by(Price.scraped_at.desc()).limit(500).all()

        seen_products = set()
        all_deals = []

        for sp, price, store_obj in discounted:
            if sp.id in seen_products: continue
            seen_products.add(sp.id)

            discount_pct = None
            if price.list_price and price.price and price.list_price > 0:
                discount_pct = round((1 - price.price / price.list_price) * 100, 1)

            deal_score = 0
            if discount_pct:
                deal_score = min(100, int(discount_pct * 1.5))

            all_deals.append(DealOut(
                product_id=sp.product_id if sp.product_id else (1000000 + sp.id),
                product_name=sp.name,
                brand=sp.brand or "",
                category=sp.top_category or "",
                image_url=sp.image_url or "",
                store_name=store_obj.name,
                store_slug=store_obj.slug,
                store_logo=store_obj.logo_url or "",
                price=price.price,
                current_price=price.price,
                list_price=price.list_price,
                promo_price=price.promo_price,
                promo_description=price.promo_description or "",
                discount_percent=discount_pct,
                deal_score=deal_score,
                product_url=sp.product_url or "",
            ))

        all_deals.sort(key=lambda d: d.discount_percent if d.discount_percent else 0, reverse=True)
        return UnifiedResponse(data=all_deals[offset: offset + limit])


@router.get("/deals/historic-lows", response_model=UnifiedResponse)
def get_historic_lows(limit: int = Query(10, ge=1, le=50)):
    """Deals at their all time lowest price based on KAIROS insights."""
    from core.models import PriceInsight
    with get_session() as session:
        insights = (
            session.query(PriceInsight, Product, Store)
            .join(Product, Product.id == PriceInsight.product_id)
            .outerjoin(Store, Store.id == PriceInsight.cheapest_store_id)
            .filter(PriceInsight.is_deal_now == True)
            .filter(PriceInsight.deal_score >= 80)
            .order_by(PriceInsight.deal_score.desc())
            .limit(limit)
            .all()
        )
        
        results = []
        for insight, product, store in insights:
            if not store: continue
            results.append({
                "product_id": product.id,
                "product_name": product.canonical_name,
                "brand": product.brand,
                "image_url": product.image_url,
                "store_name": store.name,
                "store_slug": store.slug,
                "store_logo": store.logo_url,
                "price": insight.min_price_all_time,
                "min_price_all_time": insight.min_price_all_time,
                "deal_score": insight.deal_score
            })
            
        return UnifiedResponse(data=results)


@router.post("/optimize/ultraplan", response_model=UnifiedResponse)
def run_ultraplan(product_ids: list[int] = Body(..., embed=True)):
    """
    Lógica 'Ultraplan': Algoritmo avanzado que calcula la ruta de compra óptima
    para una canasta de productos específica, cruzando múltiples tiendas y ofertas.
    """
    if not product_ids:
        raise HTTPException(status_code=400, detail="La lista de productos no puede estar vacía.")
    if len(product_ids) > 100:
        raise HTTPException(status_code=400, detail="Máximo 100 productos por Ultraplan.")
    if any(pid <= 0 for pid in product_ids):
        raise HTTPException(status_code=400, detail="IDs de producto inválidos.")
    from domain.planner import ShoppingPlanner
    planner = ShoppingPlanner(product_ids)
    plan = planner.optimize_plan()
    return UnifiedResponse(data=plan)
