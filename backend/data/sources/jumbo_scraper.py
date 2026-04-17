"""
Jumbo.cl Supermarket Product Scraper
=====================================
Extracts product data (name, price, brand, category, images, promotions)
from Jumbo.cl via the BFF (Backend For Frontend) catalog API.

Supports:
  - Search queries (e.g., "leche", "arroz", "aceite")
  - Pagination
  - CSV and JSON export

Usage:
  python jumbo_scraper.py --search "leche"
  python jumbo_scraper.py --search "arroz" --pages 3
  python jumbo_scraper.py --search "aceite" --output json
  python jumbo_scraper.py --search "leche" --output both
"""

import sys
import os
import csv
import json
import re
import time
import argparse
from datetime import datetime
from urllib.parse import urlencode

try:
    import requests
except ImportError:
    print("ERROR: 'requests' library is required. Install with: pip install requests")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = "https://www.jumbo.cl"

# BFF (Backend For Frontend) API endpoint — replaces the old dehydratedState
# HTML parsing approach. This endpoint is used by the Jumbo website itself
# to fetch product listings client-side.
API_URL = "https://bff.jumbo.cl/catalog/plp"

# Items per page (Jumbo BFF default is 40)
PAGE_SIZE = 40

# Store identifier required by the BFF.
# Override via --store-id CLI argument; this is the default (Santiago Costanera).
DEFAULT_STORE_ID = "jumboclj512"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Content-Type": "application/json",
    "Referer": "https://www.jumbo.cl/",
    # API key observed from Jumbo's BFF requests
    "apikey": "REDACTED_JUMBO_CATALOG_KEY",
    "x-client-platform": "web",
    "x-client-version": "3.3.44",
}

# Rate limiting (seconds between requests)
REQUEST_DELAY = 1.5


# ---------------------------------------------------------------------------
# Normalizer import (shared across scrapers)
# ---------------------------------------------------------------------------

try:
    from domain.normalizer import normalize_scraped_product
except ImportError:
    def normalize_scraped_product(product):
        return product

try:
    from core.ai_service import KairosAIService
    _ai_service = KairosAIService()
except Exception:
    _ai_service = None

_ai_fallback_count = 0
MAX_FALLBACKS = 5


# ---------------------------------------------------------------------------
# Core scraping functions
# ---------------------------------------------------------------------------

def create_session():
    """Create a requests session with appropriate headers."""
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def fetch_api_page(session, query, from_index=0, to_index=None, store_id=DEFAULT_STORE_ID):
    """
    Fetch one page of products from the Jumbo BFF API.

    Args:
        session:     requests.Session
        query:       The search term (e.g., "leche")
        from_index:  First item index (0-based, inclusive)
        to_index:    Last item index (0-based, inclusive)
        store_id:    Branch external ID (e.g., "jumboclj411")

    Returns:
        (list of raw product dicts, total_results int or None)
    """
    if to_index is None:
        to_index = from_index + PAGE_SIZE - 1

    payload = {
        "store": store_id,
        "collections": [],
        "fullText": query,
        "brands": [],
        "hideUnavailableItems": False,
        "from": from_index,
        "to": to_index,
        "orderBy": "",
        "selectedFacets": [],
        "promotionalCards": False,
        "sponsoredProducts": True,
    }

    try:
        resp = session.post(API_URL, json=payload, timeout=20)
        if resp.status_code != 200:
            print(f"  [WARN] HTTP {resp.status_code} from BFF API")
            return [], None

        data = resp.json()
        products = data.get("products", [])
        total_results = data.get("total", None)
        return products, total_results

    except requests.RequestException as e:
        print(f"  [ERROR] Request failed: {e}")
        return [], None
    except (ValueError, KeyError) as e:
        print(f"  [ERROR] Unexpected response format: {e}")
        return [], None


def fetch_single_product(session, sku_id, store_id=DEFAULT_STORE_ID):
    """
    Fetch a specific product by its SKU from the Jumbo BFF API.
    Used for JIT (Just-In-Time) synchronization.
    """
    payload = {
        "store": store_id,
        "skus": [str(sku_id)],
    }
    try:
        resp = session.post(API_URL, json=payload, timeout=10)
        if resp.status_code != 200:
            return None
            
        data = resp.json()
        products = data.get("products", [])
        if not products:
            return None
            
        return normalize_product(products[0])
    except Exception as e:
        print(f"  [ERROR] Single product fetch failed: {e}")
        return None


def normalize_product(raw_product):
    """
    Transform a raw BFF product into a clean, flat dictionary
    suitable for CSV export and mobile app consumption.
    """
    items = raw_product.get("items", [])
    if not items:
        return None

    item = items[0]  # Primary SKU
    promotions = item.get("promotions", [])

    # Determine the best promotional price
    best_promo_price = None
    promo_description = None
    for promo in promotions:
        up = promo.get("unitPrice")
        if up and (best_promo_price is None or up < best_promo_price):
            best_promo_price = up
            promo_description = promo.get("description", "")

    # Build clean category path
    category_names = raw_product.get("categoryNames", [])
    category_path = " > ".join(category_names) if category_names else ""
    top_category = category_names[0] if category_names else ""

    # Image URL — BFF places images inside the item, not at root level
    # Try to upgrade resolution from 250x250 to 500x500
    images = item.get("images", [])
    image_url = ""
    if images:
        image_url = images[0]
        image_url = re.sub(r"-\d+-\d+/", "-500-500/", image_url)

    price = item.get("price")
    list_price = item.get("listPrice")
    name = item.get("name", "")
    brand = raw_product.get("brand", "")

    # AI Fallback trigger
    global _ai_fallback_count
    if (not price or not name) and _ai_service and _ai_fallback_count < MAX_FALLBACKS:
        print("  [WARN] Schema mismatch in Jumbo! Triggering Smart Autoscraper (AI Fallback)...")
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
        "sku_id": item.get("skuId", ""),
        "reference": raw_product.get("reference", ""),
        "name": name,
        "brand": brand,
        "slug": raw_product.get("slug", ""),
        "supermarket": "Jumbo",
        "price": price,
        "list_price": list_price,
        "promo_price": best_promo_price,
        "promo_description": promo_description or "",
        "has_discount": (
            (price is not None and list_price is not None and price < list_price)
            or best_promo_price is not None
        ),
        "measurement_unit": item.get("measurementUnit", ""),
        "unit_multiplier": item.get("unitMultiplier", 1),
        "in_stock": item.get("stock", False) or (price is not None and price > 0),
        "cart_limit": item.get("cartLimit"),
        "top_category": top_category,
        "category_path": category_path,
        "category_ids": ",".join(raw_product.get("categories", [])),
        "image_url": image_url,
        "product_url": f"{BASE_URL}/{raw_product.get('slug', '')}/p",
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

def search_products(session, query, max_pages=1, store_id=DEFAULT_STORE_ID):
    """
    Search for products on Jumbo.cl and return normalized results.
    Handles pagination via from/to offsets.

    Args:
        store_id: Branch external ID (e.g., "jumboclj411"). Defaults to Santiago.
    """
    all_products = []
    seen_ids = set()

    for page in range(1, max_pages + 1):
        from_index = (page - 1) * PAGE_SIZE
        to_index = from_index + PAGE_SIZE - 1

        print(f"  Fetching page {page} (items {from_index}–{to_index})...")

        raw_products, total_results = fetch_api_page(
            session, query, from_index, to_index, store_id=store_id
        )

        if page == 1 and total_results is not None:
            print(f"  Total results available: {total_results}")

        if not raw_products:
            print(f"  No products returned for page {page}, stopping.")
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
            print(f"  No more new products found, stopping.")
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
        print("  No products to export.")
        return

    fieldnames = list(products[0].keys())

    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(products)

    print(f"  Exported {len(products)} products to {filename}")


def export_json(products, filename):
    """Export products to a JSON file."""
    if not products:
        print("  No products to export.")
        return

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

    print(f"  Exported {len(products)} products to {filename}")


def print_summary(products):
    """Print a summary of the scraped products."""
    if not products:
        print("\n  No products found.")
        return

    print(f"\n{'='*70}")
    print(f"  SCRAPING RESULTS SUMMARY")
    print(f"{'='*70}")
    print(f"  Total products: {len(products)}")

    # Price stats
    prices = [p["price"] for p in products if p.get("price")]
    if prices:
        print(f"  Price range: ${min(prices):,} - ${max(prices):,}")
        print(f"  Average price: ${sum(prices) // len(prices):,}")

    # Discount stats
    discounted = [p for p in products if p.get("has_discount")]
    print(f"  Products on sale: {len(discounted)} ({len(discounted)*100//len(products)}%)")

    # Brand breakdown
    brands = {}
    for p in products:
        b = p.get("brand") or "Unknown"
        brands[b] = brands.get(b, 0) + 1
    top_brands = sorted(brands.items(), key=lambda x: -x[1])[:10]
    print(f"  Top brands: {', '.join(f'{b} ({c})' for b, c in top_brands)}")

    # Category breakdown
    categories = {}
    for p in products:
        c = p.get("top_category") or "Unknown"
        categories[c] = categories.get(c, 0) + 1
    print(f"  Categories: {', '.join(f'{c} ({n})' for c, n in sorted(categories.items(), key=lambda x: -x[1]))}")

    # Sample products
    print(f"\n  SAMPLE PRODUCTS:")
    print(f"  {'-'*66}")
    for p in products[:10]:
        discount_str = ""
        if p.get("has_discount"):
            if p.get("promo_price"):
                discount_str = f" -> PROMO ${p['promo_price']:,}"
            elif p.get("list_price") and p.get("price") and p["price"] < p["list_price"]:
                discount_str = f" (was ${p['list_price']:,})"

        print(f"  [{p.get('brand', '')}] {p.get('name', '')}")
        price_val = p.get('price') or 0
        stock_str = 'In Stock' if p.get('in_stock') else 'OUT OF STOCK'
        print(f"    ${price_val:,}{discount_str} | {stock_str}")
        print(f"    {p.get('category_path', '')}")
        print()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    # Force UTF-8 output on Windows when run as a script
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Scrape product data from Jumbo.cl (Chilean supermarket)"
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
        help="Number of pages to scrape (default: 1)"
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
        default=DEFAULT_STORE_ID,
        help=(
            f"Jumbo branch external ID (default: {DEFAULT_STORE_ID}). "
            "Use seed_branches.py to list available IDs."
        ),
    )

    args = parser.parse_args()

    print(f"\n{'='*70}")
    print(f"  JUMBO.CL PRODUCT SCRAPER")
    print(f"  Search: '{args.search}' | Pages: {args.pages} | Store: {args.store_id}")
    print(f"{'='*70}\n")

    session = create_session()
    products = search_products(session, args.search, max_pages=args.pages, store_id=args.store_id)

    print_summary(products)

    if products and args.output != "none":
        os.makedirs(args.output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_query = re.sub(r"[^\w]", "_", args.search)
        base_name = f"jumbo_{safe_query}_{timestamp}"

        if args.output in ("csv", "both"):
            csv_path = os.path.join(args.output_dir, f"{base_name}.csv")
            export_csv(products, csv_path)

        if args.output in ("json", "both"):
            json_path = os.path.join(args.output_dir, f"{base_name}.json")
            export_json(products, json_path)

    print(f"\nDone!")


if __name__ == "__main__":
    main()
