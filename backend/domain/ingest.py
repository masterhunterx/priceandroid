"""
Pipeline de Ingesta de Datos
============================
Encargado de recolectar productos de todas las tiendas, insertarlos en la base de datos,
ejecutar el algoritmo de emparejamiento (matching) y registrar el historial de precios.

Optimizaciones de la Fase 4:
  - Ingesta sensible a sucursales (branch_id almacenado en StoreProduct).
  - Detección de cambios basado en Hash (evita escrituras innecesarias en la DB).
  - Precios diferidos (solo inserta una fila de Price cuando el precio cambia realmente).

Uso vía CLI:
    # Búsqueda nacional (cadena completa)
    python ingest.py --search "leche" --pages 1

    # Búsqueda específica por sucursal
    python ingest.py --search "leche" --pages 1 --store jumbo --store-id jumboclj411
"""

import argparse
import hashlib
import logging
import sys
import time
import threading
from datetime import datetime, timezone
import asyncio

logger = logging.getLogger("AntigravityAPI")
UTC = timezone.utc

# Rate limiter JIT por tienda: evita saturar anti-bots (PerimeterX, Akamai)
_jit_rate_lock = threading.Lock()
_jit_last_request: dict[str, float] = {}
_JIT_MIN_INTERVAL: dict[str, float] = {
    "lider": 15.0,   # PerimeterX detecta >1 req/15s como bot
    "default": 2.0,
}

from core.db import get_session, init_db
from .matcher import (
    AUTO_MATCH_THRESHOLD,
    compute_match_score,
    enrich_with_weight,
    extract_weight,
    find_matches,
    clean_product_name,
)
from .hash_utils import compute_content_hash, price_changed
from core.models import Branch, Price, Product, ProductMatch, Store, StoreProduct


# ---------------------------------------------------------------------------
# Despacho de Scrapers (Scraper Dispatch)
# ---------------------------------------------------------------------------

def scrape_store(store_slug: str, query: str, pages: int, store_id: str | None = None) -> list[dict]:
    """
    Ejecuta el scraper apropiado para la tienda dada y retorna productos normalizados.
    Pasa el store_id para habilitar resultados específicos por sucursal (branch-scoped).

    Args:
        store_slug: Slug de la tienda (ej. "jumbo")
        query:      Término de búsqueda
        pages:      Máximo de páginas a scrapper
        store_id:   ID externo de la sucursal (None = a nivel nacional)

    Returns:
        Lista de diccionarios de productos normalizados
    """
    products = []

    if store_slug == "jumbo":
        from data.sources.jumbo_scraper import create_session, search_products
        session = create_session()
        products = search_products(session, query, max_pages=pages, store_id=store_id)

    elif store_slug == "santa_isabel":
        from data.sources.santa_isabel_scraper import create_session, search_products
        session = create_session()
        products = search_products(session, query, max_pages=pages, store_id=store_id)

    elif store_slug == "lider":
        from data.sources.lider_scraper import create_session, search_products
        session = create_session()
        products = search_products(session, query, max_pages=pages, store_id=store_id)

    elif store_slug == "unimarc":
        from data.sources.unimarc_scraper import create_session, search_products
        session = create_session()
        products = search_products(session, query, max_pages=pages, cluster_id=store_id)

    else:
        print(f"  [AVISO] Tienda desconocida: {store_slug}")

    return products


def sync_single_store_product(db_session, sp_id: int, branch_id: int | None = None) -> bool:
    """
    Realiza una sincronización Just-In-Time (JIT) para un único StoreProduct.
    Consulta datos en tiempo real desde la API de la tienda (PDP/SKU).
    
    Args:
        db_session: Sesión de base de datos
        sp_id: ID interno de StoreProduct
        branch_id: ID interno de sucursal opcional (sobrescribe sp.branch_id)
        
    Returns: True si se actualizó con éxito, False en caso de error o no encontrado.
    """
    sp = db_session.get(StoreProduct, sp_id)
    if not sp:
        return False
        
    store = sp.store
    
    # Prioridad: branch_id pasado por parámetro > branch_id propio del producto
    if branch_id:
        branch = db_session.get(Branch, branch_id)
    else:
        branch = sp.branch
        
    ext_branch_id = branch.external_store_id if branch else None
    
    print(f"  [JIT] Sincronizando {store.name}: {sp.name[:40]} (Sucursal: {ext_branch_id or 'Fija'})...")
    
    # Circuit breaker: no intentar si la tienda está bloqueada por errores repetidos
    try:
        from core.circuit_breaker import is_open
        if is_open(store.slug):
            logger.debug(f"[JIT] Circuito abierto para {store.slug} — omitiendo sync de {sp.id}")
            return False
    except Exception:
        pass

    # Rate limiter: espaciar requests por tienda para no activar anti-bots
    min_interval = _JIT_MIN_INTERVAL.get(store.slug, _JIT_MIN_INTERVAL["default"])
    with _jit_rate_lock:
        last = _jit_last_request.get(store.slug, 0.0)
        elapsed = time.time() - last
        if elapsed < min_interval:
            logger.debug(f"[JIT] Rate limit {store.slug} — esperando {min_interval - elapsed:.1f}s")
            return False
        _jit_last_request[store.slug] = time.time()

    result = None
    try:
        if store.slug == "jumbo":
            from data.sources.jumbo_scraper import create_session, fetch_single_product
            session = create_session()
            result = fetch_single_product(session, sp.sku_id, store_id=ext_branch_id)

        elif store.slug == "lider":
            from data.sources.lider_scraper import create_session, fetch_single_product
            session = create_session()
            result = fetch_single_product(session, sp.external_id, store_id=ext_branch_id)

        elif store.slug == "santa_isabel":
            from data.sources.santa_isabel_scraper import create_session, fetch_single_product
            session = create_session()
            result = fetch_single_product(session, sp.sku_id, store_id=ext_branch_id, product_name=sp.name)

        elif store.slug == "unimarc":
            from data.sources.unimarc_scraper import create_session, fetch_single_product
            session = create_session()
            result = fetch_single_product(session, sp.sku_id, cluster_id=ext_branch_id, product_name=sp.name)
            
        try:
            from core.metrics import sync_operations_total, price_updates_total
            _has_metrics = True
        except Exception:
            _has_metrics = False

        if result:
            from .ingest import upsert_store_products
            upsert_store_products(db_session, store, [result], branch=branch)
            sp.last_sync = datetime.now(UTC)
            db_session.commit()
            if _has_metrics:
                sync_operations_total.labels(store=store.slug, result="success").inc()
                price_updates_total.labels(store=store.slug).inc()
            try:
                from core.circuit_breaker import record_success
                record_success(store.slug)
            except Exception:
                pass
            return True
        else:
            print(f"    [JIT] Producto no encontrado en {store.name}. Marcando como Agotado.")
            sp.in_stock = False
            sp.last_sync = datetime.now(UTC)
            db_session.commit()
            if _has_metrics:
                sync_operations_total.labels(store=store.slug, result="not_found").inc()
            return True
    except (ConnectionError, ValueError) as e:
        print(f"    [JIT SCRAPER ERROR] {store.name} bloqueó la request para ID {sp.id}: {e}")
        db_session.rollback()
        try:
            from core.circuit_breaker import record_failure
            tripped = record_failure(store.slug)
            if tripped:
                import os, requests as _rq
                wh = os.getenv("DISCORD_WEBHOOK_URL", "")
                if wh:
                    _rq.post(wh, json={"content": (
                        f"⚡ **[CircuitBreaker] {store.slug.upper()} bloqueado**\n"
                        f"Demasiados errores consecutivos. Sync pausado 2h.\n"
                        f"Último error: `{str(e)[:120]}`"
                    )}, timeout=8)
        except Exception:
            pass
        try:
            from core.metrics import sync_operations_total
            sync_operations_total.labels(store=store.slug, result="error").inc()
        except Exception:
            pass
        return False
    except Exception as e:
        print(f"    [JIT ERROR] Falló la sincronización para ID {sp.id}: {e}")
        db_session.rollback()
        try:
            from core.metrics import sync_operations_total
            sync_operations_total.labels(store=store.slug, result="error").inc()
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
# Inserción en Base de Datos (Optimizado con Hash y Lazy Pricing)
# ---------------------------------------------------------------------------

def upsert_store_products(
    db_session,
    store: Store,
    scraped_products: list[dict],
    branch: Branch | None = None,
) -> list[StoreProduct]:
    """
    Inserta o actualiza productos de la tienda y registra precios condicionalmente.

    Optimizaciones aplicadas:
      - Detección basada en Hash: salta la actualización de metadatos si el hash coincide.
      - Lazy Pricing: solo inserta una fila en Price si el valor real ha cambiado.
      - Política de metadatos estáticos: image_url nunca se sobrescribe tras la creación.

    Args:
        db_session:        Sesión activa de SQLAlchemy
        store:             Objeto ORM Store
        scraped_products:  Lista de productos normalizados del scraper
        branch:            Objeto ORM Branch opcional (para ingesta por sucursal)

    Returns:
        Lista de objetos StoreProduct procesados
    """
    store_products = []
    new_count = 0
    updated_count = 0
    hash_skipped = 0
    price_skipped = 0
    price_inserted = 0

    branch_id = branch.id if branch else None
    branch_label = branch.name if branch else "a nivel nacional"

    for product_data in scraped_products:
        external_id = product_data.get("product_id") or product_data.get("sku_id", "")
        if not external_id:
            continue

        new_hash = compute_content_hash(product_data)
        new_price = product_data.get("price")

        # Buscamos si el StoreProduct ya existe en esta cadena
        sp = db_session.query(StoreProduct).filter_by(
            store_id=store.id,
            external_id=str(external_id),
        ).first()

        if sp:
            # --- Detección de cambios por Hash ---
            if sp.content_hash == new_hash:
                # Metadatos idénticos: solo actualizamos visibilidad y stock
                sp.in_stock = product_data.get("in_stock", sp.in_stock)
                sp.last_seen = datetime.now(UTC)
                hash_skipped += 1
            else:
                # Metadatos han cambiado: actualizamos campos críticos
                sp.name = product_data.get("name", sp.name)
                sp.brand = product_data.get("brand", sp.brand)
                sp.slug = product_data.get("slug", sp.slug)
                sp.product_url = product_data.get("product_url", sp.product_url)
                sp.category_path = product_data.get("category_path", sp.category_path)
                sp.top_category = product_data.get("top_category", sp.top_category)
                sp.measurement_unit = product_data.get("measurement_unit", sp.measurement_unit)
                sp.in_stock = product_data.get("in_stock", sp.in_stock)
                sp.content_hash = new_hash
                sp.last_seen = datetime.now(UTC)
                # Registramos sucursal si es la primera vez que se detecta en una específica
                if branch_id and sp.branch_id is None:
                    sp.branch_id = branch_id
                updated_count += 1
        else:
            # --- Creación de nuevo StoreProduct ---
            sp = StoreProduct(
                store_id=store.id,
                branch_id=branch_id,
                external_id=str(external_id),
                sku_id=str(product_data.get("sku_id", "")),
                name=product_data.get("name", ""),
                brand=product_data.get("brand", ""),
                slug=product_data.get("slug", ""),
                product_url=product_data.get("product_url", ""),
                image_url=product_data.get("image_url", ""),  # Protegido tras creación
                category_path=product_data.get("category_path", ""),
                top_category=product_data.get("top_category", ""),
                measurement_unit=product_data.get("measurement_unit", ""),
                in_stock=product_data.get("in_stock", True),
                content_hash=new_hash,
            )
            db_session.add(sp)
            db_session.flush() # Poblar sp.id para el chequeo de precios
            new_count += 1

        # --- Lógica de Precios Diferidos (Lazy Pricing) ---
        if price_changed(sp, new_price):
            price = Price(
                store_product=sp,
                branch=branch, # Vinculamos historia a la sucursal específica
                price=new_price,
                list_price=product_data.get("list_price"),
                promo_price=product_data.get("promo_price"),
                promo_description=product_data.get("promo_description", ""),
                has_discount=product_data.get("has_discount", False),
                savings_amount=product_data.get("savings_amount"),
                discount_percent=product_data.get("discount_percent"),
                scraped_at=datetime.now(UTC),
            )
            db_session.add(price)
            price_inserted += 1
        else:
            price_skipped += 1

        store_products.append(sp)

    db_session.flush()

    print(
        f"    {store.name} [{branch_label}]: "
        f"{new_count} nuevos | {updated_count} actualizados | {hash_skipped} sin cambios (hash) | "
        f"{price_inserted} precios grabados | {price_skipped} precios omitidos"
    )
    return store_products


# ---------------------------------------------------------------------------
# Algoritmo de Emparejamiento (Product Matching)
# ---------------------------------------------------------------------------

def run_matching(db_session, store_slugs: list[str]) -> list[dict]:
    """
    Ejecuta el algoritmo de matching sobre los productos recolectados.
    Crea fichas canónicas (Product) y enlaces de comparación (ProductMatch).
    """
    products_by_store = {}

    for slug in store_slugs:
        store = db_session.query(Store).filter_by(slug=slug).first()
        if not store:
            continue

        sps = db_session.query(StoreProduct).filter_by(store_id=store.id).all()
        product_dicts = []
        for sp in sps:
            d = {
                "id": sp.id,
                "name": sp.name,
                "brand": sp.brand,
                "top_category": sp.top_category,
                "image_url": sp.image_url,
            }
            enrich_with_weight(d) # Extrae gramos/litros para comparabilidad técnica
            product_dicts.append(d)

        products_by_store[slug] = product_dicts

    print(f"\n  Ejecutando Matcher sobre {len(products_by_store)} tiendas...")
    for slug, prods in products_by_store.items():
        print(f"    {slug}: {len(prods)} productos")

    matches = find_matches(products_by_store)

    auto_matches = [m for m in matches if m["auto_match"]]
    candidate_matches = [m for m in matches if not m["auto_match"]]

    print(f"\n  Resultados de Emparejamiento:")
    print(f"    Auto-matches:  {len(auto_matches)} pares (confianza >= {AUTO_MATCH_THRESHOLD})")
    print(f"    Candidatos:    {len(candidate_matches)} pares (requieren revisión manual)")

    new_products = 0
    new_links = 0

    for match in auto_matches:
        store_a, prod_a = match["product_a"]
        store_b, prod_b = match["product_b"]
        score = match["score"]

        sp_a = db_session.get(StoreProduct, prod_a["id"])
        sp_b = db_session.get(StoreProduct, prod_b["id"])

        if not sp_a or not sp_b:
            continue

        # Consolidación de ficha canónica
        canonical = None
        if sp_a.product_id:
            canonical = db_session.get(Product, sp_a.product_id)
        elif sp_b.product_id:
            canonical = db_session.get(Product, sp_b.product_id)

        if not canonical:
            weight_val, weight_unit = extract_weight(sp_a.name)
            canonical = Product(
                canonical_name=clean_product_name(sp_a.name) or sp_a.name,
                brand=sp_a.brand,
                category=sp_a.top_category,
                category_path=sp_a.category_path,
                weight_value=weight_val,
                weight_unit=weight_unit,
                image_url=sp_a.image_url or sp_b.image_url,
            )
            db_session.add(canonical)
            db_session.flush()
            new_products += 1

        # Vinculación cruzada
        for sp in [sp_a, sp_b]:
            if sp.product_id != canonical.id:
                sp.product_id = canonical.id

                existing_match = db_session.query(ProductMatch).filter_by(
                    product_id=canonical.id,
                    store_product_id=sp.id,
                ).first()

                if not existing_match:
                    pm = ProductMatch(
                        product_id=canonical.id,
                        store_product_id=sp.id,
                        match_score=score,
                        match_method="auto",
                        verified=False,
                    )
                    db_session.add(pm)
                    new_links += 1

    db_session.flush()

    print(f"    Nuevos productos canónicos: {new_products}")
    print(f"    Nuevos enlaces de comparación: {new_links}")

    return matches


# ---------------------------------------------------------------------------
# Pipeline Principal (Main Pipeline)
# ---------------------------------------------------------------------------

def run_pipeline(
    query: str,
    pages: int = 1,
    store_slugs: list[str] | None = None,
    store_id: str | None = None,
    all_branches: bool = False,
    use_async: bool = False,
) -> None:
    """
    Pipeline de Ingesta Completo:
    1. Scrapea productos de cada tienda.
    2. Upsert optimizado en DB con Hash + Lazy Pricing.
    3. Ejecuta el Matching Algorithm internacional.
    4. Reporte final de estadísticas.
    """
    if store_slugs is None:
        store_slugs = ["jumbo", "unimarc"]

    print(f"\n{'='*60}")
    print(f"  PIPELINE DE INGESTA ANTIGRAVITY")
    print(f"  Consulta: '{query}' | Páginas: {pages}")
    print(f"  Tiendas: {', '.join(store_slugs)}")
    if store_id:
        print(f"  Sucursal Específica: {store_id}")
    elif all_branches:
        print(f"  Modo: TODAS LAS SUCURSALES (Iterativo)")
    else:
        print(f"  Modo: CADENA COMPLETA (Por defecto)")
    print(f"{'='*60}")

    init_db()

    with get_session() as db_session:
        print(f"\nFase 1: Recolección e Ingesta...")
        
        # Selección entre modo Serial y Paralelo (asíncrono)
        if use_async:
            from .coordinator import ScrapingCoordinator
            coordinator = ScrapingCoordinator(concurrency=5)
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            loop.run_until_complete(
                coordinator.run_parallel_scrape(query, pages, store_slugs, all_branches=all_branches)
            )
        else:
            # Lógica Serial Original
            for slug in store_slugs:
                store = db_session.query(Store).filter_by(slug=slug).first()
                if not store:
                    print(f"  [AVISO] Tienda '{slug}' no en la DB, saltando.")
                    continue

                # Resolución de sucursales a procesar
                branches_to_scrape = []
                if store_id:
                    branch = db_session.query(Branch).filter_by(
                        store_id=store.id,
                        external_store_id=store_id,
                    ).first()
                    if branch:
                        branches_to_scrape = [branch]
                    else:
                        print(f"  [AVISO] Sucursal '{store_id}' no hallada para {store.name}.")
                        branches_to_scrape = [None]
                elif all_branches:
                    branches_to_scrape = db_session.query(Branch).filter_by(
                        store_id=store.id,
                        is_active=True
                    ).all()
                    print(f"  Halladas {len(branches_to_scrape)} sucursales para {store.name}")
                else:
                    branches_to_scrape = [None] # Nacional

                for branch in branches_to_scrape:
                    branch_label = branch.name if branch else "nacional"
                    branch_ext_id = branch.external_store_id if branch else None
                    
                    print(f"\n  --- Scrapeando {store.name} [{branch_label}] ---")
                    scraped = scrape_store(slug, query, pages, store_id=branch_ext_id)
                    print(f"    Recibidos {len(scraped)} productos del scraper")

                    if scraped:
                        upsert_store_products(db_session, store, scraped, branch=branch)
                    
                    # Pausa de cortesía para no saturar APIs de terceros
                    if len(branches_to_scrape) > 1:
                        time.sleep(0.5)

                db_session.commit()
                time.sleep(1)

    with get_session() as db_session:
        print(f"\n  Fase 2: Cruce de productos entre tiendas...")
        run_matching(db_session, store_slugs)

        print(f"\n{'-'*60}")
        print(f"  RESUMEN DEL PIPELINE")
        print(f"{'-'*60}")

        total_store_products = db_session.query(StoreProduct).count()
        total_canonical = db_session.query(Product).count()
        total_prices = db_session.query(Price).count()
        total_matches = db_session.query(ProductMatch).count()

        print(f"  Items en Catálogo:        {total_store_products}")
        print(f"  Productos Canónicos:      {total_canonical}")
        print(f"  Registros de Precio:      {total_prices}")
        print(f"  Enlaces de comparación:   {total_matches}")

        matched_products = db_session.query(Product).limit(5).all()
        if matched_products:
            print(f"\n  Muestra de Emparejamientos:")
            for p in matched_products:
                stores_with = db_session.query(StoreProduct).filter_by(product_id=p.id).all()
                store_names = [sp.store.name for sp in stores_with]
                prices_str = ""
                for sp in stores_with:
                    latest = sp.latest_price
                    if latest and latest.price:
                        prices_str += f"  {sp.store.name}: ${latest.price:,.0f}"
                print(f"    [{p.brand}] {p.canonical_name}")
                print(f"      Disponible en: {', '.join(store_names)} |{prices_str}")

    print(f"\nFinalizado con éxito.")


# ---------------------------------------------------------------------------
# Interfaz de Línea de Comandos (CLI)
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Ingesta de datos de supermercados chilenos (KAIROS Core)"
    )
    parser.add_argument(
        "--search", "-s", required=True,
        help="Consulta de búsqueda (ej., 'leche', 'arroz')"
    )
    parser.add_argument(
        "--pages", "-p", type=int, default=1,
        help="Páginas a scrapper por tienda"
    )
    parser.add_argument(
        "--stores", nargs="+", default=None,
        choices=["jumbo", "unimarc"],
        help="Tiendas a incluir"
    )
    parser.add_argument(
        "--store-id",
        default=None,
        help="ID externo de sucursal específica"
    )
    parser.add_argument(
        "--all-branches", action="store_true",
        help="Procesar todas las sucursales de la cadena (lento)"
    )
    parser.add_argument(
        "--async-mode", action="store_true",
        help="Ejecución asíncrona mediante ScrapingCoordinator"
    )

    args = parser.parse_args()
    run_pipeline(
        args.search, 
        args.pages, 
        args.stores, 
        store_id=args.store_id,
        all_branches=args.all_branches,
        use_async=args.async_mode
    )


if __name__ == "__main__":
    main()
