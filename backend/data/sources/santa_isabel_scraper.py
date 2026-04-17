"""
Santa Isabel Supermarket Product Scraper
=========================================
Extracts product data (name, price, brand, category, images, promotions)
from Santa Isabel (santaisabel.cl) using their VTEX catalog API.

The API was reverse-engineered from the Santa Isabel SPA webpack bundles.
Authentication uses an apiKey header against the Cencosud catalog gateway.

Usage:
    python santa_isabel_scraper.py --search "leche"
    python santa_isabel_scraper.py --search "arroz" --pages 3 --output csv
    python santa_isabel_scraper.py --search "aceite" --output json --output-dir ./data
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime
from urllib.parse import urlencode

try:
    from domain.normalizer import normalize_scraped_product
except ImportError:
    def normalize_scraped_product(p): return p  # fallback for standalone use

try:
    from core.ai_service import KairosAIService
    _ai_service = KairosAIService()
except Exception:
    _ai_service = None

_ai_fallback_count = 0
MAX_FALLBACKS = 5

try:
    from curl_cffi import requests as cffi_requests
except ImportError:
    print("[ERROR] 'curl_cffi' library required. Install with: pip install curl_cffi")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = "https://www.santaisabel.cl"
BFF_API = "https://be-reg-groceries-bff-sisa.ecomm.cencosud.com/catalog"
BFF_SEARCH_ENDPOINT = f"{BFF_API}/plp"

# API key for Cencosud BFF (Captured from network traffic)
BFF_API_KEY = "REDACTED_SISA_CATALOG_KEY"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-CL,es;q=0.9",
    "Content-Type": "application/json",
    "apikey": BFF_API_KEY,
    "x-client-platform": "web",
    "x-client-version": "2.3.6",
    "Origin": "https://www.santaisabel.cl",
    "Referer": "https://www.santaisabel.cl/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "cross-site",
}

# VTEX pagination: max 50 products per request
PAGE_SIZE = 50

# Default store/sales-channel ID. None = chain-wide results.
DEFAULT_STORE_ID = None

# Rate limiting (seconds between requests)
REQUEST_DELAY = 1.0


# ---------------------------------------------------------------------------
# Core API functions
# ---------------------------------------------------------------------------

def create_session():
    """Create a curl_cffi session con Chrome TLS impersonation para bypasear Akamai/Cencosud CDN."""
    session = cffi_requests.Session(impersonate="chrome124")
    session.headers.update(HEADERS)
    return session


def fetch_products_page(session, query, from_idx, to_idx, store_id="pedrofontova"):
    """Fetch Santa Isabel products via BFF POST API."""
    payload = {
        "store": store_id or "pedrofontova",
        "collections": [],
        "fullText": query,
        "brands": [],
        "hideUnavailableItems": False,
        "from": from_idx,
        "to": to_idx,
        "orderBy": "OrderByScoreDESC",
        "selectedFacets": [],
        "promotionalCards": False,
        "sponsoredProducts": True
    }

    try:
        response = session.post(BFF_SEARCH_ENDPOINT, json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()
        products = data.get("products", [])
        total_results = data.get("results", 0)
        return products, total_results
    except Exception as e:
        print(f"  [ERROR] BFF API failed: {e}")
        return [], 0


def _si_search(session, full_text: str, store_id: str, to: int = 5):
    """Ejecuta una búsqueda en el BFF de Santa Isabel y devuelve la lista de productos."""
    payload = {
        "store": store_id,
        "collections": [],
        "fullText": full_text,
        "brands": [],
        "hideUnavailableItems": False,
        "from": 0,
        "to": to,
        "orderBy": "OrderByScoreDESC",
        "selectedFacets": [],
        "promotionalCards": False,
        "sponsoredProducts": False,
    }
    resp = session.post(BFF_SEARCH_ENDPOINT, json=payload, timeout=15)
    return resp


def fetch_single_product(session, sku_id, store_id=None, product_name=None):
    """
    Fetch a specific product by its SKU from the Santa Isabel BFF API.
    Used for JIT (Just-In-Time) synchronization.
    Returns None if product genuinely not found; raises on scraping errors.

    Estrategia de búsqueda:
    1. Buscar por SKU exacto y verificar itemId
    2. Si no hay match por SKU, buscar por nombre del producto (más confiable)
    """
    store = store_id or "pedrofontova"

    def _try_search(query: str) -> list:
        resp = _si_search(session, query, store, to=8)
        if resp.status_code in (403, 412, 429):
            raise ConnectionError(f"Santa Isabel HTTP {resp.status_code}: scraping bloqueado")
        if resp.status_code >= 500:
            raise ConnectionError(f"Santa Isabel server error HTTP {resp.status_code}")
        if resp.status_code != 200:
            raise ConnectionError(f"Santa Isabel HTTP inesperado {resp.status_code}")
        return resp.json().get("products", [])

    for attempt in range(2):
        try:
            # Intento 1: buscar por SKU y verificar itemId exacto
            products = _try_search(str(sku_id))
            for p in products:
                for item in p.get("items", []):
                    if str(item.get("itemId", "")) == str(sku_id):
                        return normalize_product(p)

            # Intento 2: si hay nombre disponible, buscar por nombre y verificar SKU
            if product_name:
                # Usar las primeras 4 palabras para evitar búsquedas demasiado específicas
                short_name = " ".join(product_name.split()[:4])
                products_by_name = _try_search(short_name)
                for p in products_by_name:
                    for item in p.get("items", []):
                        if str(item.get("itemId", "")) == str(sku_id):
                            return normalize_product(p)
                # Si encontró resultados por nombre pero ningún match exacto de SKU,
                # no retornamos el primero para evitar datos incorrectos — es not_found real
            return None

        except ConnectionError:
            if attempt == 0:
                session = create_session()
                time.sleep(1)
                continue
            raise
        except Exception as e:
            print(f"  [ERROR] Santa Isabel fetch_single_product (intento {attempt+1}): {e}")
            if attempt == 0:
                session = create_session()
                time.sleep(1)
                continue
            raise ConnectionError(f"Santa Isabel fetch fallido tras 2 intentos: {e}")


# ---------------------------------------------------------------------------
# Product normalization
# ---------------------------------------------------------------------------

def parse_sku_data(raw_sku_data):
    """
    Parse the embedded SkuData JSON string.
    SkuData contains per-SKU details: promotions, measurement units, cart limits.
    Returns: dict keyed by SKU ID
    """
    if not raw_sku_data or not isinstance(raw_sku_data, list):
        return {}
    try:
        return json.loads(raw_sku_data[0])
    except (json.JSONDecodeError, IndexError):
        return {}


def normalize_product(raw_product):
    """
    Transform a raw Cencosud BFF product into a clean, flat dictionary.
    """
    items = raw_product.get("items", [])
    if not items:
        return None

    item = items[0]  # Primary SKU
    sku_id = item.get("itemId", "")

    # Pricing from modern item structure (BFF)
    price = item.get("price")
    list_price = item.get("listPrice")
    available_qty = item.get("availableQuantity")  # None = field not present

    # NEW: Handle raw VTEX IO structure if BFF fields are missing (Playwright extraction)
    sellers = item.get("sellers", [])
    if (price is None or price == 0) and sellers:
        seller = sellers[0]
        # VTEX IO standard path
        offer = seller.get("commertialOffer", {})
        if offer:
            price = offer.get("Price")
            list_price = offer.get("ListPrice")
            if available_qty is None:
                available_qty = offer.get("AvailableQuantity")

        # Alternative context path
        if price is None or price == 0:
            context = seller.get("commertialContext", {})
            if context:
                price = context.get("Price")
                list_price = context.get("ListPrice")
                if available_qty is None:
                    available_qty = context.get("availableQuantity")
                
        # Final fallback
        if price is None or price == 0:
            price = seller.get("price")
            list_price = seller.get("listPrice")

    # If price is still missing, try to find it in the raw product if it's there
    if price is None:
        price = raw_product.get("price")
        list_price = raw_product.get("listPrice")

    # Promotions / Club info
    promo_description = raw_product.get("promotionTag", "")
    best_promo_price = None

    # Build clean category path
    categories = raw_product.get("categories", [])
    category_path = " > ".join(categories) if categories else ""
    top_category = categories[0] if categories else ""

    # Image URL
    images = item.get("images", [])
    image_url = ""
    if images:
        img = images[0]
        if isinstance(img, dict):
            image_url = img.get("imageUrl", "")
        elif isinstance(img, str):
            image_url = img
        # Ensure high-res (500x500)
        if image_url:
            image_url = re.sub(r"-\d+-\d+/", "-500-500/", image_url)

    # SEO Slug (Crucial for fixing the 404 error)
    slug = raw_product.get("slug", "")
    if not slug:
        # Fallback to name-based slug if missing
        slug = item.get("name", "").lower().replace(" ", "-")

    # Measurement units
    measurement_unit = item.get("measurementUnit", "")
    unit_multiplier = item.get("unitMultiplier", 1)

    has_discount = False
    if price and list_price and price < list_price:
        has_discount = True

    name = item.get("name", raw_product.get("productName", ""))
    brand = raw_product.get("brand", "")

    # AI Fallback trigger
    global _ai_fallback_count
    if (not price or not name) and _ai_service and _ai_fallback_count < MAX_FALLBACKS:
        print("  [WARN] Schema mismatch in Santa Isabel! Triggering Smart Autoscraper (AI Fallback)...")
        _ai_fallback_count += 1
        ai_data = _ai_service.extract_product_fallback(raw_product)
        if ai_data:
            name = ai_data.get("name") or name
            price = ai_data.get("price") or price
            image_url = ai_data.get("image_url") or image_url
            brand = ai_data.get("brand") or brand
            print(f"  [SUCCESS] AI recovered product: {name} (${price})")

    if not name and not price:
        return None  # Unrecoverable

    return normalize_scraped_product({
        "product_id": raw_product.get("productId", ""),
        "sku_id": sku_id,
        "reference": raw_product.get("productReference", ""),
        "name": name,
        "brand": brand,
        "slug": slug,
        "supermarket": "Santa Isabel",
        "price": price,
        "list_price": list_price,
        "promo_price": best_promo_price,
        "promo_description": promo_description,
        "has_discount": has_discount,
        "measurement_unit": measurement_unit,
        "unit_multiplier": unit_multiplier,
        "in_stock": available_qty > 0 if available_qty is not None else (price is not None and price > 0),
        "available_quantity": available_qty or 0,
        "cart_limit": raw_product.get("cartLimit"),
        "top_category": top_category,
        "category_path": category_path,
        "category_ids": ",".join(raw_product.get("categoriesIds", [])),
        "image_url": image_url,
        "product_url": f"{BASE_URL}/{slug}/p",
        "scraped_at": datetime.now().isoformat(),
    })


# ---------------------------------------------------------------------------
# Search & pagination
# ---------------------------------------------------------------------------


def check_health(session=None):
    """
    Scraper health check: search for 'leche' and verify we get results.
    Returns: (bool success, str message)
    """
    try:
        from curl_cffi import requests as cffi_requests
        s = session or cffi_requests.Session(impersonate="chrome")
        results, total = search_products(s, "leche", max_pages=1)
        if results and total > 0:
            return True, f"OK: Found {total} products for 'leche'"
        return False, "Failed: API returned 0 products or invalid structure."
    except Exception as e:
        return False, f"Error: {e}"

def search_products(session, query, max_pages=1, store_id=None):
    """
    Search for products on Santa Isabel and return normalized results.
    Uses VTEX _from/_to pagination (50 products per page).

    Args:
        store_id: Santa Isabel branch external ID. None = chain-wide.
    """
    all_products = []
    seen_ids = set()

    for page in range(1, max_pages + 1):
        from_idx = (page - 1) * PAGE_SIZE
        to_idx = from_idx + PAGE_SIZE - 1

        print(f"  Fetching page {page} (items {from_idx}-{to_idx})...")

        raw_products, total_results = fetch_products_page(
            session, query, from_idx, to_idx, store_id=store_id
        )

        if page == 1 and total_results is not None:
            total_pages = (total_results + PAGE_SIZE - 1) // PAGE_SIZE
            print(f"  Total results available: {total_results} ({total_pages} pages)")

        if not raw_products:
            print(f"  No more products found, stopping.")
            break

        new_count = 0
        for raw in raw_products:
            pid = raw.get("productId")
            if pid in seen_ids:
                continue
            seen_ids.add(pid)

            product = normalize_product(raw)
            if product:
                all_products.append(product)
                new_count += 1

        print(f"  Page {page}: {new_count} new products (total: {len(all_products)})")

        if new_count == 0:
            print(f"  No new products, stopping.")
            break

        # Stop if we've fetched all available results
        if total_results and to_idx >= total_results - 1:
            print(f"  All results fetched.")
            break

        if page < max_pages:
            time.sleep(REQUEST_DELAY)

    return all_products


# ---------------------------------------------------------------------------
# Export functions
# ---------------------------------------------------------------------------

def export_csv(products, filename):
    """Export products to a CSV file."""
    if not products:
        return

    fieldnames = list(products[0].keys())

    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(products)

    print(f"  CSV exported: {filename} ({len(products)} products)")


def export_json(products, filename):
    """Export products to a JSON file."""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

    print(f"  JSON exported: {filename} ({len(products)} products)")


def print_summary(products):
    """Print a summary of the scraped products."""
    if not products:
        print("\n  No products found.")
        return

    print(f"\n{'-'*60}")
    print(f"  RESULTS SUMMARY")
    print(f"{'-'*60}")
    print(f"  Total products:  {len(products)}")

    # Price stats
    prices = [p["price"] for p in products if p.get("price")]
    if prices:
        print(f"  Price range:     ${min(prices):,.0f} - ${max(prices):,.0f}")
        avg_price = sum(prices) / len(prices)
        print(f"  Average price:   ${avg_price:,.0f}")

    # Discount stats
    with_discount = sum(1 for p in products if p.get("has_discount"))
    print(f"  With discounts:  {with_discount} ({with_discount*100//len(products)}%)")

    # In stock
    in_stock = sum(1 for p in products if p.get("in_stock"))
    print(f"  In stock:        {in_stock} ({in_stock*100//len(products)}%)")

    # Brands
    brands = set(p["brand"] for p in products if p.get("brand"))
    print(f"  Unique brands:   {len(brands)}")

    # Categories
    categories = set(p["top_category"] for p in products if p.get("top_category"))
    print(f"  Top categories:  {', '.join(sorted(categories)[:5])}")

    # Sample products
    print(f"\n  Sample products:")
    for p in products[:5]:
        price_str = f"${p['price']:,.0f}" if p.get("price") else "N/A"
        disc = " 🏷️" if p.get("has_discount") else ""
        print(f"    • {p['name'][:50]:50s} {price_str:>10s}{disc}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Scrape product data from Santa Isabel (Chilean supermarket)"
    )
    parser.add_argument(
        "--search", "-s",
        required=True,
        help="Search query (e.g., 'leche', 'arroz', 'aceite')"
    )
    parser.add_argument(
        "--pages", "-p",
        type=int,
        default=1,
        help="Number of pages to scrape (default: 1, 50 products per page)"
    )
    parser.add_argument(
        "--output", "-o",
        choices=["csv", "json", "both", "none"],
        default="both",
        help="Output format (default: both)"
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory for output files (default: current directory)"
    )

    parser.add_argument(
        "--store-id",
        default=None,
        help=(
            "Santa Isabel branch external ID (e.g., 'aguasanta'). "
            "Omit for chain-wide results. Use seed_branches.py to list IDs."
        ),
    )

    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  SANTA ISABEL PRODUCT SCRAPER")
    store_label = args.store_id or "chain-wide (default)"
    print(f"  Search: '{args.search}' | Pages: {args.pages} | Store: {store_label}")
    print(f"{'='*60}\n")

    session = create_session()
    products = search_products(
        session, args.search, max_pages=args.pages, store_id=args.store_id
    )

    print_summary(products)

    if products and args.output != "none":
        os.makedirs(args.output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_query = re.sub(r"[^\w]", "_", args.search)
        base_name = f"santa_isabel_{safe_query}_{timestamp}"

        if args.output in ("csv", "both"):
            csv_path = os.path.join(args.output_dir, f"{base_name}.csv")
            export_csv(products, csv_path)

        if args.output in ("json", "both"):
            json_path = os.path.join(args.output_dir, f"{base_name}.json")
            export_json(products, json_path)

    print(f"\nDone!")


if __name__ == "__main__":
    main()
