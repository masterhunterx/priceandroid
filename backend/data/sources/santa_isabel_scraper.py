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
    import requests
except ImportError:
    print("[ERROR] 'requests' library required. Install with: pip install requests")
    sys.exit(1)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("[WARN] 'playwright' library not found. Search will fall back to legacy/BFF methods.")
    sync_playwright = None


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
    """Create a requests session with appropriate headers and initialized VTEX segment."""
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        # 1. Warm up the base domain
        session.get(BASE_URL, timeout=10)
        
        # 2. Get the VTEX segment cookie for Santa Isabel (sc=1)
        # This provides the necessary context for the BFF to return products.
        segment_url = f"{BASE_URL}/api/segments/getsegment?sc=1"
        resp = session.get(segment_url, timeout=10)
        
        # If the segment is returned in the body, try to set it manually in cookies if missing
        if "vtex_segment" not in session.cookies and resp.status_code == 200:
            try:
                segment_data = resp.json()
                # Some VTEX sites allow setting the context via cookie or header
                pass
            except:
                pass
        
    except Exception as e:
        print(f"  [WARN] Session initialization failed: {e}")
    return session


def fetch_products_page_playwright(query, from_idx, to_idx):
    """
    Fetch products using a headless browser (Playwright).
    This is the most robust method against WAF/bot blocking.
    """
    if not sync_playwright:
        print("  [ERROR] Playwright not installed. Cannot use browser bypass.")
        return [], 0

    url = f"https://www.santaisabel.cl/busqueda?ft={query}"
    products = []
    total = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        try:
            print(f"  [Browser] Navigating to {url}...")
            # Navigate and wait for the renderData to be available
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            
            # Wait a few seconds for hydration
            page.wait_for_timeout(3000)
            
            # Extract data from window.__renderData
            render_data = page.evaluate("window.__renderData")
            
            if render_data:
                # Same extraction logic as before but from a live DOM object
                apps = render_data.get("apps", [])
                for app in apps:
                    if "plp" in app.get("name", "").lower():
                        plp_data = app.get("data", {})
                        products = plp_data.get("plp_products", {}).get("products", [])
                        total = plp_data.get("plp_products", {}).get("results", 0)
                        if products:
                            break
            
            if not products:
                 # Fallback: deep search for products
                 def deep_search(obj, key):
                    if isinstance(obj, dict):
                        if key in obj: return obj[key]
                        for v in obj.values():
                            res = deep_search(v, key)
                            if res: return res
                    return None
                 
                 products = deep_search(render_data, "products")
                 total = deep_search(render_data, "results") or 0

        except Exception as e:
            print(f"  [ERROR] Playwright extraction failed: {e}")
        finally:
            browser.close()

    return products, total


def fetch_products_page(session, query, from_idx, to_idx, store_id="pedrofontova"):
    """
    Main entry point for fetching Santa Isabel products.
    Uses Playwright for the first page to bypass locks, then falls back to session-based if needed.
    """
    # Use Playwright for initial search to get the catalog unlocked
    if from_idx == 0:
        return fetch_products_page_playwright(query, from_idx, to_idx)

    # Legacy/BFF Fallback (Still useful for deep paging if session is warm)
    payload = {
        "store": store_id,
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

        if not isinstance(products, list):
            print(f"  [WARN] Expected list of products, got {type(products).__name__}")
            return [], total_results

        return products, total_results

    except requests.exceptions.RequestException as e:
        print(f"  [ERROR] BFF API request failed: {e}")
        return [], None


def fetch_single_product(session, sku_id, store_id=None):
    """
    Fetch a specific product by its SKU from the Santa Isabel VTEX API.
    Used for JIT (Just-In-Time) synchronization.
    """
    params = {
        "fq": f"skuId:{sku_id}"
    }
    if store_id:
        params["sc"] = store_id
        
    url = f"{BFF_SEARCH_ENDPOINT}?{urlencode(params)}"
    
    try:
        resp = session.get(url, timeout=10)
        if resp.status_code != 200:
            return None
            
        products = resp.json()
        if not products or not isinstance(products, list):
            return None
            
        return normalize_product(products[0])
    except Exception as e:
        print(f"  [ERROR] Single product fetch failed: {e}")
        return None


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
    available_qty = item.get("availableQuantity", 0)

    # NEW: Handle raw VTEX IO structure if BFF fields are missing (Playwright extraction)
    sellers = item.get("sellers", [])
    if (price is None or price == 0) and sellers:
        seller = sellers[0]
        # VTEX IO standard path
        offer = seller.get("commertialOffer", {})
        if offer:
            price = offer.get("Price")
            list_price = offer.get("ListPrice")
            available_qty = offer.get("AvailableQuantity", 0)
        
        # Alternative context path
        if price is None or price == 0:
            context = seller.get("commertialContext", {})
            if context:
                price = context.get("Price")
                list_price = context.get("ListPrice")
                available_qty = context.get("availableQuantity", 0)
                
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
        "in_stock": available_qty > 0 or (price is not None and price > 0),
        "available_quantity": available_qty,
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
