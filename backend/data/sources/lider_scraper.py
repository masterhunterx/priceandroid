"""
Lider Supermarket Product Scraper
==================================
Extracts product data (name, price, brand, category, images)
from Lider.cl (Walmart Chile) using their GraphQL API.

The API was discovered by intercepting browser network traffic.
PerimeterX anti-bot is bypassed by using a mobile app User-Agent.

Usage:
    python lider_scraper.py --search "leche"
    python lider_scraper.py --search "arroz" --pages 3 --output csv
    python lider_scraper.py --search "aceite" --output json --output-dir ./data
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime

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

BASE_URL = "https://www.lider.cl"
GRAPHQL_ENDPOINT = "https://super.lider.cl/orchestra/graphql/search"

# Headers que imitan Chrome real para bypasear PerimeterX
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Accept-Language": "es-CL,es;q=0.9",
    "Origin": "https://www.lider.cl",
    "Referer": "https://www.lider.cl/supermercado/search",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "x-o-gql-query": "query Search",
    "X-APOLLO-OPERATION-NAME": "Search",
    "x-o-bu": "LIDER-CL",
    "x-o-vertical": "OD",
    "x-o-platform": "rweb",
    "x-o-mart": "B2C",
    "x-o-segment": "oaoh",
}

# Products per page (Walmart/Lider default)
PAGE_SIZE = 40

# Default store ID. None = chain-wide / Lider's default warehouse.
# NOTE: Lider branch discovery is blocked by CAPTCHA; pass IDs manually.
DEFAULT_STORE_ID = None

# Rate limiting (seconds between requests)
REQUEST_DELAY = 1.0

# GraphQL query - minimal version requesting only the fields we need
SEARCH_QUERY = """query Search(
  $query: String
  $limit: Int
  $page: Int
  $prg: Prg!
  $sort: Sort = best_match
  $ps: Int
  $pageType: String! = "SearchPage"
  $ffAwareSearchOptOut: Boolean = true
  $enableSlaBadgeV2: Boolean = false
  $additionalQueryParams: JSON = {}
) {
  search(
    query: $query limit: $limit page: $page prg: $prg sort: $sort
    ps: $ps pageType: $pageType ffAwareSearchOptOut: $ffAwareSearchOptOut
    enableSlaBadgeV2: $enableSlaBadgeV2 additionalQueryParams: $additionalQueryParams
  ) {
    searchResult {
      aggregatedCount
      itemStacks {
        meta { totalItemCount title }
        itemsV2 {
          ... on Product {
            id usItemId name brand type shortDescription
            averageRating numberOfReviews
            imageInfo { thumbnailUrl }
            canonicalUrl
            availabilityStatusV2 { display value }
            priceInfo {
              currentPrice { price priceString }
              wasPrice { price priceString }
              listPrice { price priceString }
              unitPrice { price priceString }
              savingsAmount { amount priceString percent }
            }
            badges {
              flags { ... on BaseBadge { key text type } }
            }
            category { path { name url } }
            sellerId sellerName
          }
        }
      }
    }
  }
}"""

# GraphQL query for a single product by ID
SINGLE_PRODUCT_QUERY = """query Product($id: String!, $prg: Prg!) {
  product(id: $id, prg: $prg) {
    id usItemId name brand type shortDescription
    imageInfo { thumbnailUrl }
    canonicalUrl
    availabilityStatusV2 { display value }
    priceInfo {
      currentPrice { price priceString }
      wasPrice { price priceString }
      listPrice { price priceString }
      unitPrice { price priceString }
      savingsAmount { amount priceString percent }
    }
    badges { flags { ... on BaseBadge { key text type } } }
    category { path { name url } }
    sellerId sellerName
  }
}"""


# ---------------------------------------------------------------------------
# Core API functions
# ---------------------------------------------------------------------------

import random as _random

# Fingerprints rotativos — PerimeterX detecta versiones fijas con el tiempo
_FINGERPRINTS = ["chrome131", "chrome130", "chrome129", "chrome124", "chrome116", "chrome110"]

def create_session():
    """Crea sesión curl_cffi con fingerprint Chrome aleatorio para evadir PerimeterX."""
    fp = _random.choice(_FINGERPRINTS)
    session = cffi_requests.Session(impersonate=fp)
    # Variar ligeramente el User-Agent según el fingerprint elegido
    version = fp.replace("chrome", "")
    headers = dict(HEADERS)
    headers["User-Agent"] = (
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{version}.0.0.0 Safari/537.36"
    )
    headers["sec-ch-ua"] = (
        f'"Chromium";v="{version}", "Google Chrome";v="{version}", "Not-A.Brand";v="99"'
    )
    session.headers.update(headers)
    return session


def fetch_single_product(session, product_id, store_id=None):
    """
    Fetch a specific product by its ID from the Lider GraphQL API.
    Used for JIT (Just-In-Time) synchronization.
    Returns None if product genuinely not found; raises on scraping errors.
    """
    variables = {
        "id": str(product_id),
        "prg": "mWeb",
    }
    payload = {"query": SINGLE_PRODUCT_QUERY, "variables": variables}

    request_headers = {}
    if store_id:
        request_headers["x-o-store"] = str(store_id)

    for attempt in range(3):
        try:
            response = session.post(GRAPHQL_ENDPOINT, json=payload, headers=request_headers, timeout=15)

            if response.status_code in (400, 403, 412, 429):
                print(f"  [ERROR] Lider HTTP {response.status_code} para producto {product_id} (intento {attempt+1})")
                if attempt < 2:
                    # Nueva sesión con fingerprint diferente + backoff exponencial
                    session = create_session()
                    time.sleep(2 ** attempt + _random.uniform(0.5, 1.5))
                    continue
                raise ConnectionError(f"Lider HTTP {response.status_code}: scraping bloqueado")

            response.raise_for_status()
            data = response.json()

            if "errors" in data:
                gql_errors = data["errors"]
                print(f"  [ERROR] Lider GraphQL errors: {gql_errors}")
                raise ValueError(f"GraphQL error: {gql_errors[0].get('message', 'unknown')}")

            product_data = data.get("data", {}).get("product")
            if not product_data:
                return None  # Producto legítimamente no existe

            return normalize_product(product_data)

        except ConnectionError:
            raise
        except ValueError:
            raise
        except Exception as e:
            print(f"  [ERROR] Lider fetch_single_product (intento {attempt+1}): {e}")
            if attempt == 0:
                session = create_session()
                time.sleep(1)
                continue
            raise ConnectionError(f"Lider fetch fallido tras 2 intentos: {e}")


def fetch_products_page(session, query, page, store_id=None):
    """
    Fetch a page of products from the Lider GraphQL API.

    Args:
        store_id: Lider branch store ID injected via x-o-store header.
                  None = Lider default / chain-wide.

    Returns: (list of product dicts, total_results int)
    """
    variables = {
        "query": query,
        "page": page,
        "prg": "mWeb",
        "sort": "best_match",
        "ps": PAGE_SIZE,
        "limit": PAGE_SIZE,
        "pageType": "SearchPage",
        "ffAwareSearchOptOut": False,
        "enableSlaBadgeV2": False,
        "additionalQueryParams": {},
    }

    payload = {"query": SEARCH_QUERY, "variables": variables}

    # Lider uses x-o-store header to scope results to a specific branch
    request_headers = {}
    if store_id:
        request_headers["x-o-store"] = str(store_id)

    try:
        response = session.post(
            GRAPHQL_ENDPOINT, json=payload, headers=request_headers, timeout=15
        )
        response.raise_for_status()

        data = response.json()

        if "errors" in data:
            print(f"  [ERROR] GraphQL errors: {data['errors'][0]['message']}")
            return [], None

        search_result = data.get("data", {}).get("search", {}).get("searchResult", {})
        total_results = search_result.get("aggregatedCount", 0)

        # Extract products from all item stacks
        products = []
        for stack in search_result.get("itemStacks", []):
            for item in stack.get("itemsV2", []):
                if item.get("name"):  # Filter out non-product entries
                    products.append(item)

        return products, total_results

    except requests.exceptions.RequestException as e:
        print(f"  [ERROR] API request failed: {e}")
        return [], None


# ---------------------------------------------------------------------------
# Product normalization
# ---------------------------------------------------------------------------

def normalize_product(raw_product):
    """
    Transform a raw Lider GraphQL product into a clean, flat dictionary
    suitable for CSV export and mobile app consumption.
    """
    # Pricing
    price_info = raw_product.get("priceInfo") or {}
    current_price = (price_info.get("currentPrice") or {}).get("price")
    was_price = (price_info.get("wasPrice") or {}).get("price")
    list_price = (price_info.get("listPrice") or {}).get("price")
    unit_price_str = (price_info.get("unitPrice") or {}).get("priceString", "")
    savings = price_info.get("savingsAmount") or {}
    savings_amount = savings.get("amount")
    savings_percent = savings.get("percent")

    # Discount detection
    has_discount = False
    if was_price and current_price and current_price < was_price:
        has_discount = True
    if savings_amount:
        has_discount = True

    # Category path
    category_info = raw_product.get("category") or {}
    category_path_list = category_info.get("path") or []
    category_parts = [p["name"] for p in category_path_list if p.get("name")]
    category_path = " > ".join(category_parts)
    top_category = category_parts[0] if category_parts else ""

    # Image
    image_info = raw_product.get("imageInfo") or {}
    image_url = image_info.get("thumbnailUrl", "")

    # Availability
    availability = raw_product.get("availabilityStatusV2") or {}
    in_stock = availability.get("value") == "IN_STOCK"

    # Badges/flags
    badges_info = raw_product.get("badges") or {}
    flags = badges_info.get("flags") or []
    # Consolidate all meaningful badges
    badge_texts = []
    for f in flags:
        txt = f.get("text", "")
        if txt and txt not in badge_texts:
            badge_texts.append(txt)
            
    promo_description = " | ".join(badge_texts)

    # Slug / canonical URL
    canonical = raw_product.get("canonicalUrl", "")

    # Unit price parsing (e.g., "$2.890 x lt")
    measurement_unit = ""
    if unit_price_str:
        match = re.search(r'x\s+(\w+)', unit_price_str)
        if match:
            measurement_unit = match.group(1)

    name = raw_product.get("name", "")
    brand = raw_product.get("brand", "")

    # AI Fallback trigger
    global _ai_fallback_count
    if (not current_price or not name) and _ai_service and _ai_fallback_count < MAX_FALLBACKS:
        print("  [WARN] Schema mismatch in Lider! Triggering Smart Autoscraper (AI Fallback)...")
        _ai_fallback_count += 1
        ai_data = _ai_service.extract_product_fallback(raw_product)
        if ai_data:
            name = ai_data.get("name") or name
            current_price = ai_data.get("price") or current_price
            image_url = ai_data.get("image_url") or image_url
            brand = ai_data.get("brand") or brand
            print(f"  [SUCCESS] AI recovered product: {name} (${current_price})")

    if not name and not current_price:
        return None # Unrecoverable

    return normalize_scraped_product({
        "product_id": raw_product.get("id", ""),
        "sku_id": raw_product.get("usItemId", ""),
        "reference": raw_product.get("usItemId", ""),
        "name": name,
        "brand": brand,
        "slug": canonical,
        "supermarket": "Lider",
        "price": current_price,
        "list_price": was_price or list_price,
        "promo_price": None,
        "promo_description": promo_description,
        "has_discount": has_discount,
        "measurement_unit": measurement_unit,
        "unit_multiplier": 1,
        "in_stock": in_stock if availability else (current_price is not None and current_price > 0),
        "available_quantity": None,
        "cart_limit": None,
        "top_category": top_category,
        "category_path": category_path,
        "image_url": image_url,
        "product_url": f"{BASE_URL}{canonical}" if canonical else "",
        "average_rating": raw_product.get("averageRating"),
        "num_reviews": raw_product.get("numberOfReviews", 0),
        "seller_name": raw_product.get("sellerName", ""),
        "scraped_at": datetime.now().isoformat(),
    })


# ---------------------------------------------------------------------------
# Search & pagination
# ---------------------------------------------------------------------------

def check_health(session=None):
    """
    Scraper health check: search for 'leche' and verify we get at least 1 result.
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
    Search for products on Lider and return normalized results.
    Uses page-based pagination (40 products per page).

    Args:
        store_id: Lider branch store ID (injected as x-o-store header).
    """
    all_products = []
    seen_ids = set()

    for page in range(1, max_pages + 1):
        print(f"  Fetching page {page}...")

        raw_products, total_results = fetch_products_page(
            session, query, page, store_id=store_id
        )

        if page == 1 and total_results is not None:
            total_pages = (total_results + PAGE_SIZE - 1) // PAGE_SIZE
            print(f"  Total results available: {total_results} ({total_pages} pages)")

        if not raw_products:
            print(f"  No more products found, stopping.")
            break

        new_count = 0
        for raw in raw_products:
            pid = raw.get("id") or raw.get("usItemId")
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
        if total_results and page * PAGE_SIZE >= total_results:
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
        disc = " *" if p.get("has_discount") else ""
        print(f"    - {p['name'][:50]:50s} {price_str:>10s}{disc}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Scrape product data from Lider (Chilean supermarket, Walmart Chile)"
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
        help="Number of pages to scrape (default: 1, 40 products per page)"
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
            "Lider branch store ID (injected as x-o-store header). "
            "Omit for chain-wide results. Branch discovery requires manual capture "
            "due to CAPTCHA protection."
        ),
    )

    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  LIDER PRODUCT SCRAPER")
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
        base_name = f"lider_{safe_query}_{timestamp}"

        if args.output in ("csv", "both"):
            csv_path = os.path.join(args.output_dir, f"{base_name}.csv")
            export_csv(products, csv_path)

        if args.output in ("json", "both"):
            json_path = os.path.join(args.output_dir, f"{base_name}.json")
            export_json(products, json_path)

    print(f"\nDone!")


if __name__ == "__main__":
    main()
