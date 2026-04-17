"""
Full Catalog Crawler
=====================
Discovers and crawls all product categories from Chilean supermarkets.
Feeds results through the ingestion pipeline to keep the database fresh.

Usage:
    python category_crawler.py                    # Crawl all stores
    python category_crawler.py --stores jumbo     # Crawl specific store
    python category_crawler.py --dry-run          # Show categories without scraping
"""

import argparse
import time
from datetime import datetime

from core.db import get_session, init_db
from core.models import Store
from domain.ingest import upsert_store_products, run_matching
from .jumbo_scraper import search_products as search_jumbo, create_session as session_jumbo
from .santa_isabel_scraper import search_products as search_santa, create_session as session_santa
from .lider_scraper import search_products as search_lider, create_session as session_lider
from .unimarc_scraper import search_products as search_unimarc, create_session as session_unimarc


# ---------------------------------------------------------------------------
# Category definitions per store
# ---------------------------------------------------------------------------
# Santa Isabel categories come from the VTEX category tree API.
# Other stores use curated keyword lists (their APIs don't expose
# category tree endpoints, so we use broad search terms that cover
# the full catalog).

def fetch_santa_isabel_categories():
    """Fetch the live category tree from Santa Isabel's VTEX API."""
    import requests

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
        "Accept": "application/json",
        "apiKey": os.environ.get("CENCOSUD_API_KEY", ""),
        "x-client-platform": "web",
        "x-client-version": "2.3.3",
        "Origin": "https://www.santaisabel.cl",
        "Referer": "https://www.santaisabel.cl/",
    })

    url = "https://sm-web-api.ecomm.cencosud.com/catalog/api/v1/catalog_system/pub/category/tree/3/"

    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        tree = resp.json()
    except Exception as e:
        print(f"  [ERROR] Failed to fetch Santa Isabel categories: {e}")
        return _FALLBACK_SANTA_ISABEL

    # Extract leaf category names for search
    categories = []
    for dept in tree:
        dept_name = dept.get("name", "")
        children = dept.get("children", [])
        if not children:
            categories.append(dept_name)
        else:
            for sub in children:
                sub_name = sub.get("name", "")
                leaves = sub.get("children", [])
                if not leaves:
                    categories.append(sub_name)
                else:
                    for leaf in leaves:
                        categories.append(leaf.get("name", ""))

    return [c for c in categories if c]


# Fallback if API is down
_FALLBACK_SANTA_ISABEL = [
    "Leches", "Yoghurt", "Postres", "Quesos", "Mantequillas",
    "Frutas", "Verduras", "Ensaladas",
    "Arroz", "Legumbres", "Pastas", "Salsas", "Aceites",
    "Snacks", "Galletas", "Cereales", "Avena",
    "Azucar", "Harina", "Mermeladas", "Miel",
    "Cafe", "Te", "Infusiones", "Jugos", "Aguas", "Bebidas",
    "Cervezas", "Vinos", "Licores",
    "Carnes", "Pollo", "Cerdo", "Pescados", "Mariscos",
    "Pan", "Pasteleria", "Tortillas",
    "Hamburguesas", "Nuggets", "Pizzas",
    "Detergente", "Lavaloza", "Limpiadores",
    "Papel higienico", "Servilletas", "Toallas",
    "Shampoo", "Jabon", "Cremas", "Desodorante",
    "Panales", "Comida bebe",
    "Comida perro", "Comida gato",
]


# Jumbo shares the Cencosud platform with Santa Isabel.
# We use broad search keywords since its SPA doesn't expose category nav.
JUMBO_CATEGORIES = [
    "leche", "yoghurt", "queso", "mantequilla", "huevos", "crema",
    "frutas", "verduras", "ensalada",
    "arroz", "fideos", "pasta", "lentejas", "porotos",
    "aceite", "vinagre", "salsa", "ketchup", "mayonesa",
    "cafe", "te", "infusion", "chocolate", "cacao",
    "cereales", "avena", "granola",
    "azucar", "harina", "levadura", "mermelada", "miel",
    "pan", "tortilla", "galletas", "snacks",
    "jugos", "agua", "bebida", "gaseosa", "energetica",
    "cerveza", "vino", "pisco", "whisky",
    "carne", "pollo", "cerdo", "pavo",
    "pescado", "marisco", "salmon", "atun",
    "hamburguesa", "nuggets", "pizza", "empanada",
    "helado", "postre",
    "detergente", "lavaloza", "cloro", "limpiador",
    "papel higienico", "servilleta", "toalla",
    "shampoo", "jabon", "crema", "desodorante", "pasta dental",
    "panales", "toallitas", "comida bebe",
    "comida perro", "comida gato", "arena gato",
]

LIDER_CATEGORIES = [
    "leche", "yoghurt", "queso", "mantequilla", "huevos", "crema",
    "frutas", "verduras", "ensalada",
    "arroz", "fideos", "legumbres", "lentejas",
    "aceite", "salsa", "condimentos", "especias",
    "cafe", "te", "chocolate",
    "cereales", "avena", "granola",
    "azucar", "harina", "mermelada", "miel",
    "pan", "galletas", "snacks", "papas fritas",
    "jugos", "agua", "bebida", "gaseosa",
    "cerveza", "vino", "pisco",
    "carne", "pollo", "cerdo",
    "pescado", "marisco", "atun",
    "hamburguesa", "nuggets", "pizza",
    "helado", "postre",
    "detergente", "lavaloza", "limpiador",
    "papel higienico", "servilleta",
    "shampoo", "jabon", "desodorante", "pasta dental",
    "panales", "comida bebe",
    "comida perro", "comida gato",
]

UNIMARC_CATEGORIES = [
    "leche", "yoghurt", "queso", "mantequilla", "huevos", "crema",
    "frutas", "verduras",
    "arroz", "fideos", "legumbres",
    "aceite", "salsa", "condimentos",
    "cafe", "te", "chocolate",
    "cereales", "avena",
    "azucar", "harina", "mermelada",
    "pan", "galletas", "snacks",
    "jugos", "agua", "bebida",
    "cerveza", "vino", "pisco",
    "carne", "pollo", "cerdo",
    "pescado", "marisco",
    "hamburguesa", "nuggets", "pizza",
    "helado", "postre",
    "detergente", "lavaloza", "limpiador",
    "papel higienico", "servilleta",
    "shampoo", "jabon", "desodorante",
    "panales", "comida bebe",
    "comida perro", "comida gato",
]


# ---------------------------------------------------------------------------
# Crawling logic
# ---------------------------------------------------------------------------

def get_categories_for_store(store_slug):
    """Return the list of search terms/categories to crawl for a store."""
    if store_slug == "santa_isabel":
        # Use curated keyword list instead of live tree because multi-word
        # categories from the tree cause 500 errors in the search API.
        return JUMBO_CATEGORIES
    elif store_slug == "jumbo":
        return JUMBO_CATEGORIES
    elif store_slug == "lider":
        return LIDER_CATEGORIES
    elif store_slug == "unimarc":
        return UNIMARC_CATEGORIES
    else:
        print(f"  [WARNING] Unknown store: {store_slug}")
        return []


def scrape_store_category(store_slug, category, pages_per_category=3):
    """Scrape a single category from a store. Returns list of product dicts."""
    from domain.ingest import scrape_store
    return scrape_store(store_slug, category, pages_per_category)


def crawl_store(store_slug, pages_per_category=3, dry_run=False):
    """
    Crawl all categories for a store.
    Returns total products scraped.
    """
    categories = get_categories_for_store(store_slug)

    if not categories:
        print(f"  No categories found for {store_slug}")
        return 0

    print(f"\n  Crawling {store_slug}: {len(categories)} categories, {pages_per_category} pages each")

    if dry_run:
        for i, cat in enumerate(categories, 1):
            print(f"    {i:3d}. {cat}")
        return 0

    total_products = 0

    for i, category in enumerate(categories, 1):
        print(f"\n  [{i}/{len(categories)}] {store_slug} > {category}")

        try:
            products = scrape_store_category(store_slug, category, pages_per_category)
            total_products += len(products)
            print(f"    Got {len(products)} products (running total: {total_products})")
        except Exception as e:
            print(f"    [ERROR] Failed: {e}")
            continue

        # Brief pause between categories to be polite
        if i < len(categories):
            time.sleep(2)

    return total_products


# ---------------------------------------------------------------------------
# Full crawl pipeline
# ---------------------------------------------------------------------------

def run_full_crawl(store_slugs=None, pages_per_category=3, dry_run=False):
    """
    Run a full catalog crawl across all stores.

    1. Crawl all categories per store
    2. Upsert products into the database
    3. Run the product matcher
    """
    if store_slugs is None:
        store_slugs = ["jumbo", "unimarc"]

    print(f"\n{'='*60}")
    print(f"  FULL CATALOG CRAWL")
    print(f"  Stores: {', '.join(store_slugs)}")
    print(f"  Pages per category: {pages_per_category}")
    print(f"  Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    if dry_run:
        print("\n  DRY RUN — showing categories only, no scraping\n")
        for slug in store_slugs:
            print(f"\n  --- {slug.upper()} ---")
            crawl_store(slug, dry_run=True)
        return

    # Initialize database
    init_db()

    with get_session() as db_session:
        all_results = {}

        for slug in store_slugs:
            store = db_session.query(Store).filter_by(slug=slug).first()
            if not store:
                print(f"\n  [WARNING] Store '{slug}' not found in database, skipping.")
                continue

            print(f"\n\n{'-'*60}")
            print(f"  CRAWLING: {store.name}")
            print(f"{'-'*60}")

            categories = get_categories_for_store(slug)
            store_total = 0

            for i, category in enumerate(categories, 1):
                print(f"\n  [{i}/{len(categories)}] {category}")

                try:
                    products = scrape_store_category(slug, category, pages_per_category)
                except Exception as e:
                    print(f"    [ERROR] Scrape failed: {e}")
                    continue

                if products:
                    upsert_store_products(db_session, store, products)
                    store_total += len(products)
                    print(f"    Ingested {len(products)} products (store total: {store_total})")

                if i < len(categories):
                    time.sleep(2)

            all_results[slug] = store_total
            db_session.commit()

        # Run product matching across all stores
        print(f"\n\n{'-'*60}")
        print(f"  MATCHING PRODUCTS ACROSS STORES")
        print(f"{'-'*60}")
        run_matching(db_session, store_slugs)

    # Summary
    print(f"\n{'='*60}")
    print(f"  CRAWL COMPLETE")
    print(f"  Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")
    for slug, count in all_results.items():
        print(f"  {slug:20s}: {count:5d} products")
    print(f"  {'TOTAL':20s}: {sum(all_results.values()):5d} products")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Full catalog crawler for Chilean supermarkets"
    )
    parser.add_argument(
        "--stores", nargs="+", default=None,
        choices=["jumbo", "unimarc"],
        help="Which stores to crawl (default: all)"
    )
    parser.add_argument(
        "--pages", "-p", type=int, default=3,
        help="Pages to scrape per category (default: 3)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show categories without scraping"
    )

    args = parser.parse_args()
    run_full_crawl(args.stores, args.pages, args.dry_run)


if __name__ == "__main__":
    main()
