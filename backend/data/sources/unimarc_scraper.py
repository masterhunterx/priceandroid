"""
Unimarc Supermarket Product Scraper
=====================================
Extracts product data from Unimarc.cl using their BFF catalog API.

Requires curl_cffi for Chrome TLS fingerprint impersonation (Akamai CDN blocks
standard Python requests).

Usage:
    python unimarc_scraper.py --search "leche"
    python unimarc_scraper.py --search "arroz" --pages 3 --output csv
    python unimarc_scraper.py --search "aceite" --output json --output-dir ./data
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

BASE_URL = "https://www.unimarc.cl"
BFF_ENDPOINT = "https://bff-unimarc-ecommerce.unimarc.cl/catalog/product/search"

BFF_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "version": "1.0.0",
    "source": "web",
    "Origin": "https://www.unimarc.cl",
    "Referer": "https://www.unimarc.cl/",
}

# Products per page (Unimarc BFF default)
PAGE_SIZE = 50

# Default cluster ID (no specific branch — chain-wide results)
DEFAULT_CLUSTER_ID = None

# Rate limiting (seconds between requests)
REQUEST_DELAY = 1.0


# ---------------------------------------------------------------------------
# Core API functions
# ---------------------------------------------------------------------------

def create_session():
    """Create a curl_cffi session with Chrome TLS impersonation."""
    return cffi_requests.Session(impersonate="chrome")


def fetch_products_page(session, query, page, cluster_id=None):
    """
    Fetch a page of products from the Unimarc BFF API.

    Args:
        cluster_id: Unimarc branch store ID (e.g., "953"). None = chain-wide.

    Returns: (list of raw product dicts, total_results int)
    """
    # Unimarc uses 0-based indexing with from/to for pagination
    page_size = 50
    start = (page - 1) * page_size
    end = start + page_size - 1

    payload = {
        "from": str(start),
        "to": str(end),
        "searching": str(query),
        "orderBy": "",
        "promotionsOnly": False,
        "userTriggered": True
    }
    if cluster_id:
        payload["clusterId"] = str(cluster_id)

    # Enhanced headers with channel and User-Agent
    headers = BFF_HEADERS.copy()
    headers.update({
        "channel": "UNIMARC",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })

    try:
        response = session.post(
            BFF_ENDPOINT,
            json=payload,
            headers=headers,
            timeout=15,
        )

        if response.status_code == 403:
            print(f"  [ERROR] Access denied (Akamai CDN block). Try again in a few minutes.")
            return [], None

        response.raise_for_status()
        data = response.json()

        total_results_str = str(data.get("resource", "0"))
        try:
            total_results = int(re.sub(r'[^\d]', '', total_results_str))
        except (ValueError, TypeError):
            total_results = 0

        products = data.get("availableProducts", [])
        
        # QUALITY LOG: If we got 0 products but total_results > 0, it's a pagination or branch error
        if not products and total_results > 0:
            print(f"  [WARN] API reports {total_results} total results but 0 availableProducts for branch {cluster_id}. Possible regional stock out.")
            
        return products, total_results


    except Exception as e:
        print(f"  [ERROR] API request failed: {e}")
        return [], None


def fetch_single_product(session, sku_id, cluster_id=None, product_name=None):
    """
    Fetch real-time data for a single product by SKU ID from Unimarc.
    Falls back to name search if SKU lookup returns no match.
    """
    print(f"  [Unimarc] Syncing single SKU: {sku_id}...")
    products, _ = fetch_products_page(session, sku_id, 1, cluster_id=cluster_id)

    for p in products:
        item = p.get("item", {})
        if str(item.get("sku")) == str(sku_id):
            return normalize_product(p)

    if product_name:
        short_name = " ".join(product_name.split()[:4])
        name_products, _ = fetch_products_page(session, short_name, 1, cluster_id=cluster_id)
        for p in name_products:
            item = p.get("item", {})
            if str(item.get("sku")) == str(sku_id):
                return normalize_product(p)
        if name_products:
            print(f"  [Unimarc] SKU {sku_id} drifted — usando mejor match por nombre '{short_name}'")
            return normalize_product(name_products[0])

    return None


# ---------------------------------------------------------------------------
# Price parsing
# ---------------------------------------------------------------------------

def parse_chilean_price(price_str):
    """Parse a Chilean price string like '$2.232' into an integer 2232."""
    if not price_str:
        return None
    cleaned = re.sub(r'[^\d]', '', str(price_str))
    try:
        return int(cleaned) if cleaned else None
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Product normalization
# ---------------------------------------------------------------------------

def normalize_product(raw_product):
    """
    Transform a raw Unimarc BFF product into a clean, flat dictionary
    suitable for CSV export and mobile app consumption.
    """
    item = raw_product.get("item") or {}
    price_data = raw_product.get("price") or {}
    promotion = raw_product.get("promotion") or {}
    price_detail = raw_product.get("priceDetail") or {}
    coupon = raw_product.get("coupon")

    # Pricing
    current_price = parse_chilean_price(price_data.get("price"))
    list_price = parse_chilean_price(price_data.get("listPrice"))
    
    # Multipack logic (New: 3.0 Transparency)
    # Check if there's a specialized promotion price (e.g. 4000 for 4 x $16.000)
    promo_obj = raw_product.get("promotion") or {}
    multipack_unit_price = promo_obj.get("price") # Usually an int like 4000
    multipack_msg = promo_obj.get("descriptionMessage") # "4 x $16.000"
    
    # discountPrice from priceDetail is often the same string
    raw_discount_price = price_detail.get("discountPrice")
    multi_buy_text = str(raw_discount_price) if isinstance(raw_discount_price, str) and "x" in raw_discount_price.lower() else multipack_msg or ""
    
    # Priority: If multipack unit price exists and is lower than current_price, use it
    if multipack_unit_price and (not current_price or multipack_unit_price < current_price):
        current_price = float(multipack_unit_price)

    promo_price = parse_chilean_price(raw_discount_price)
    available_qty = price_data.get("availableQuantity")  # None = field not present

    # Determine effective price and discount
    in_offer = price_data.get("inOffer", False) or bool(multipack_unit_price)
    has_discount = in_offer or (current_price and list_price and current_price < list_price)

    # Promotion info
    promo_description = ""
    promo_tag = price_detail.get("promotionalTag") or {}
    promo_tag_text = promo_tag.get("text", "")  # e.g., "Club Unimarc"
    discount_pct = price_detail.get("discountPercentage", 0)
    saving_text = price_data.get("saving", "")  # e.g., "Ahorras $960"

    # Combine all info for transparency
    parts = []
    if promo_tag_text:
        parts.append(promo_tag_text)
    if multi_buy_text:
        parts.append(f"({multi_buy_text})")
    elif discount_pct:
        parts.append(f"-{discount_pct}%")
    elif saving_text:
        parts.append(saving_text)
        
    promo_description = " ".join(parts).strip()
    
    # Final cleanup: if it's "Exclusivo Internet" and we have saving text, combine?
    # Actually, prioritize the tag as it triggers the UI icon.

    # Category path
    categories = item.get("categories", [])
    category_path = ""
    top_category = ""
    if categories:
        # Take the most specific path (longest)
        best = max(categories, key=len)
        parts = [p for p in best.strip("/").split("/") if p]
        category_path = " > ".join(parts)
        top_category = parts[0] if parts else ""

    # Image
    images = item.get("images", [])
    image_url = images[0] if images else ""

    # Measurement units
    measurement_unit = item.get("measurementUnit", "")
    unit_multiplier = item.get("unitMultiplier", 1)
    ppum = price_data.get("ppum", "")  # e.g., "$2.790 x Kg"

    # Slug / URL
    slug = item.get("slug", "")

    name = item.get("nameComplete") or item.get("name", "")
    brand = item.get("brand", "")

    # AI Fallback trigger
    global _ai_fallback_count
    if (not current_price or not name) and _ai_service and _ai_fallback_count < MAX_FALLBACKS:
        print("  [WARN] Schema mismatch in Unimarc! Triggering Smart Autoscraper (AI Fallback)...")
        _ai_fallback_count += 1
        ai_data = _ai_service.extract_product_fallback(raw_product)
        if ai_data:
            name = ai_data.get("name") or name
            current_price = ai_data.get("price") or current_price
            image_url = ai_data.get("image_url") or image_url
            brand = ai_data.get("brand") or brand
            print(f"  [SUCCESS] AI recovered product: {name} (${current_price})")

    if not name and not current_price:
        return None  # Unrecoverable

    return normalize_scraped_product({
        "product_id": item.get("productId", ""),
        "sku_id": item.get("sku", ""),
        "reference": item.get("refId", ""),
        "ean": item.get("ean", ""),
        "name": name,
        "brand": brand,
        "slug": slug,
        "supermarket": "Unimarc",
        "price": current_price,
        "list_price": list_price,
        "promo_price": promo_price if promo_price and promo_price != current_price else None,
        "promo_description": promo_description,
        "has_discount": has_discount,
        "measurement_unit": measurement_unit,
        "unit_multiplier": unit_multiplier,
        "in_stock": available_qty > 0 if available_qty is not None else (current_price is not None and current_price > 0),
        "available_quantity": available_qty or 0,
        "cart_limit": item.get("cartLimit"),
        "top_category": top_category,
        "category_path": category_path,
        "image_url": image_url,
        "product_url": f"{BASE_URL}{slug}" if slug else "",
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
        s = session or create_session()
        products, total = fetch_products_page(s, "leche", 1)
        if products and total > 0:
            return True, f"OK: Found {total} products for 'leche'"
        return False, "Failed: API returned 0 products or invalid structure."
    except Exception as e:
        return False, f"Error: {e}"


def search_products(session, query, max_pages=1, cluster_id=None):
    """
    Search for products on Unimarc and return normalized results.
    Uses page-based pagination (50 products per page).

    Args:
        cluster_id: Unimarc branch store ID. None = chain-wide.
    """
    all_products = []
    seen_ids = set()

    for page in range(1, max_pages + 1):
        print(f"  Fetching page {page}...")

        raw_products, total_results = fetch_products_page(
            session, query, page, cluster_id=cluster_id
        )

        if page == 1 and total_results is not None:
            total_pages = (total_results + PAGE_SIZE - 1) // PAGE_SIZE
            print(f"  Total results available: {total_results} ({total_pages} pages)")

        if not raw_products:
            print(f"  No more products found, stopping.")
            break

        new_count = 0
        for raw in raw_products:
            item = raw.get("item", {})
            pid = item.get("productId") or item.get("sku", "")
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

    prices = [p["price"] for p in products if p.get("price")]
    if prices:
        print(f"  Price range:     ${min(prices):,.0f} - ${max(prices):,.0f}")
        avg_price = sum(prices) / len(prices)
        print(f"  Average price:   ${avg_price:,.0f}")

    with_discount = sum(1 for p in products if p.get("has_discount"))
    print(f"  With discounts:  {with_discount} ({with_discount*100//len(products)}%)")

    in_stock = sum(1 for p in products if p.get("in_stock"))
    print(f"  In stock:        {in_stock} ({in_stock*100//len(products)}%)")

    brands = set(p["brand"] for p in products if p.get("brand"))
    print(f"  Unique brands:   {len(brands)}")

    categories = set(p["top_category"] for p in products if p.get("top_category"))
    print(f"  Top categories:  {', '.join(sorted(categories)[:5])}")

    print(f"\n  Sample products:")
    for p in products[:5]:
        price_str = f"${p['price']:,.0f}" if p.get("price") else "N/A"
        disc = f" ({p['promo_description']})" if p.get("promo_description") else ""
        print(f"    - {p['name'][:50]:50s} {price_str:>10s}{disc}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Scrape product data from Unimarc (Chilean supermarket)"
    )
    parser.add_argument(
        "--search", "-s", required=True,
        help="Search query (e.g., 'leche', 'arroz', 'aceite')"
    )
    parser.add_argument(
        "--pages", "-p", type=int, default=1,
        help="Number of pages to scrape (default: 1, 50 products per page)"
    )
    parser.add_argument(
        "--output", "-o",
        choices=["csv", "json", "both", "none"],
        default="both",
        help="Output format (default: both)"
    )
    parser.add_argument(
        "--output-dir", default=".",
        help="Directory for output files (default: current directory)"
    )

    parser.add_argument(
        "--store-id",
        default=None,
        help=(
            "Unimarc branch cluster ID (e.g., '953'). "
            "Omit for chain-wide results. Use seed_branches.py to list IDs."
        ),
    )

    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  UNIMARC PRODUCT SCRAPER")
    store_label = args.store_id or "chain-wide (default)"
    print(f"  Search: '{args.search}' | Pages: {args.pages} | Store: {store_label}")
    print(f"{'='*60}\n")

    session = create_session()
    products = search_products(
        session, args.search, max_pages=args.pages, cluster_id=args.store_id
    )

    print_summary(products)

    if products and args.output != "none":
        os.makedirs(args.output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_query = re.sub(r"[^\w]", "_", args.search)
        base_name = f"unimarc_{safe_query}_{timestamp}"

        if args.output in ("csv", "both"):
            csv_path = os.path.join(args.output_dir, f"{base_name}.csv")
            export_csv(products, csv_path)

        if args.output in ("json", "both"):
            json_path = os.path.join(args.output_dir, f"{base_name}.json")
            export_json(products, json_path)

    print(f"\nDone!")


if __name__ == "__main__":
    main()
