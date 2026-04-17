"""
Scraper Health Check Tests
============================
Integration tests that hit the LIVE store APIs with a single lightweight
query to verify each scraper is still returning valid data.

These are NOT unit tests - they require a working internet connection.
Run them periodically (e.g., before a full crawl) to catch API changes early.

Usage:
    cd backend
    python -m pytest tests/test_scrapers_health.py -v

    # Run only one store:
    python -m pytest tests/test_scrapers_health.py -v -k "jumbo"

Exit codes:
    0 = all scrapers healthy
    1 = one or more scrapers failed (API changed or blocked)
"""

import sys
import os

import pytest

# Ensure the backend directory is on the path so scrapers can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# A common, stable search term that should return results on any supermarket
TEST_QUERY = "leche"

# Minimum number of products we expect for a healthy query.
# A single page from any store should return at least this many.
MIN_EXPECTED_PRODUCTS = 5

# Required fields that every normalized product dict MUST contain
REQUIRED_PRODUCT_FIELDS = ["name", "price", "brand", "supermarket", "scraped_at"]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def assert_product_shape(products: list, store_name: str):
    """Run standard shape assertions on a list of normalized products."""
    assert len(products) >= MIN_EXPECTED_PRODUCTS, (
        f"{store_name}: Expected at least {MIN_EXPECTED_PRODUCTS} products, "
        f"got {len(products)}. The API may have changed or is blocking requests."
    )

    sample = products[0]
    missing = [f for f in REQUIRED_PRODUCT_FIELDS if f not in sample]
    assert not missing, (
        f"{store_name}: First product is missing required fields: {missing}. "
        f"The response schema may have changed."
    )

    # At least some products should have a non-zero price
    priced = [p for p in products if p.get("price") and p["price"] > 0]
    assert len(priced) > 0, (
        f"{store_name}: All {len(products)} products returned price=0 or None. "
        f"Pricing payload may have changed."
    )

    # Names should be non-empty strings
    named = [p for p in products if p.get("name") and len(str(p["name"])) > 0]
    assert len(named) == len(products), (
        f"{store_name}: Some products have empty names — "
        f"the name field key may have changed."
    )


# ---------------------------------------------------------------------------
# Jumbo
# ---------------------------------------------------------------------------

class TestJumboHealth:
    """Health checks for Jumbo.cl (HTML dehydratedState parsing)."""

    def test_returns_products(self):
        """Verify Jumbo returns products for the test query."""
        from data.sources.jumbo_scraper import create_session, search_products

        session = create_session()
        products = search_products(session, TEST_QUERY, max_pages=1)

        assert_product_shape(products, "Jumbo")

    def test_product_has_category(self):
        """Verify Jumbo products include category information."""
        from data.sources.jumbo_scraper import create_session, search_products

        session = create_session()
        products = search_products(session, TEST_QUERY, max_pages=1)

        with_category = [p for p in products if p.get("top_category")]
        assert len(with_category) > 0, (
            "Jumbo: No products have a top_category. "
            "Category parsing may be broken."
        )

    def test_product_url_format(self):
        """Verify Jumbo product URLs point to jumbo.cl."""
        from data.sources.jumbo_scraper import create_session, search_products

        session = create_session()
        products = search_products(session, TEST_QUERY, max_pages=1)

        with_url = [p for p in products if p.get("product_url")]
        assert len(with_url) > 0, "Jumbo: No products have a product_url."
        assert all("jumbo.cl" in p["product_url"] for p in with_url), (
            "Jumbo: Some product URLs do not contain 'jumbo.cl'. "
            "The URL format may have changed."
        )


# ---------------------------------------------------------------------------
# Lider
# ---------------------------------------------------------------------------

class TestLiderHealth:
    """Health checks for Lider.cl (GraphQL API)."""

    def test_returns_products(self):
        """Verify Lider GraphQL endpoint returns products."""
        from data.sources.lider_scraper import create_session, search_products

        session = create_session()
        products = search_products(session, TEST_QUERY, max_pages=1)

        assert_product_shape(products, "Lider")

    def test_graphql_pricing_fields(self):
        """Verify Lider pricing fields are populated correctly."""
        from data.sources.lider_scraper import create_session, search_products

        session = create_session()
        products = search_products(session, TEST_QUERY, max_pages=1)

        # Lider-specific: check savings_percent field exists in schema
        assert "savings_percent" in products[0], (
            "Lider: 'savings_percent' field missing. "
            "GraphQL schema may have changed."
        )

    def test_stock_status_present(self):
        """Verify Lider products include a stock status."""
        from data.sources.lider_scraper import create_session, search_products

        session = create_session()
        products = search_products(session, TEST_QUERY, max_pages=1)

        assert all("in_stock" in p for p in products), (
            "Lider: Some products are missing 'in_stock'. "
            "The availabilityStatusV2 field may have moved."
        )


# ---------------------------------------------------------------------------
# Santa Isabel
# ---------------------------------------------------------------------------

class TestSantaIsabelHealth:
    """Health checks for Santa Isabel (VTEX Catalog API)."""

    def test_returns_products(self):
        """Verify Santa Isabel VTEX API returns products."""
        from data.sources.santa_isabel_scraper import create_session, search_products

        session = create_session()
        products = search_products(session, TEST_QUERY, max_pages=1)

        assert_product_shape(products, "Santa Isabel")

    def test_vtex_resources_header_parsed(self):
        """
        Verify the VTEX 'resources' header is being read.
        This header tells us total results. If it breaks, pagination will stop too early.
        """
        from data.sources.santa_isabel_scraper import create_session, fetch_products_page

        session = create_session()
        # First page: items 0-49
        products, total_results = fetch_products_page(session, TEST_QUERY, 0, 49)

        assert products, "Santa Isabel: fetch_products_page returned no products."
        assert total_results is not None and total_results > 0, (
            "Santa Isabel: total_results is None or 0. "
            "The 'resources' response header may no longer be present."
        )

    def test_sku_data_parsed(self):
        """Verify SKU-level data (promotions, cart limits) is accessible."""
        from data.sources.santa_isabel_scraper import create_session, search_products

        session = create_session()
        products = search_products(session, TEST_QUERY, max_pages=1)

        # sku_id should appear in every product
        with_sku = [p for p in products if p.get("sku_id")]
        assert len(with_sku) > 0, (
            "Santa Isabel: No products have a sku_id. "
            "The VTEX item structure may have changed."
        )


# ---------------------------------------------------------------------------
# Unimarc
# ---------------------------------------------------------------------------

class TestUnimarcHealth:
    """Health checks for Unimarc.cl (BFF API via curl_cffi Akamai bypass)."""

    def test_returns_products(self):
        """Verify Unimarc BFF API returns products (Akamai bypass is working)."""
        from data.sources.unimarc_scraper import create_session, search_products

        session = create_session()
        products = search_products(session, TEST_QUERY, max_pages=1)

        assert_product_shape(products, "Unimarc")

    def test_no_403_akamai_block(self):
        """
        Explicitly verify we are NOT being blocked by Akamai.
        A 403 means the curl_cffi TLS fingerprint is no longer working.
        """
        from data.sources.unimarc_scraper import create_session, fetch_products_page

        session = create_session()
        products, total_results = fetch_products_page(session, TEST_QUERY, 1)

        assert products is not None, (
            "Unimarc: fetch_products_page returned None. "
            "This is likely an Akamai 403 block — update curl_cffi impersonation target."
        )
        assert len(products) > 0, (
            "Unimarc: Got an empty response. "
            "Possible Akamai block or BFF endpoint URL has changed."
        )

    def test_club_unimarc_pricing_field(self):
        """Verify the Club Unimarc promotional pricing fields are present."""
        from data.sources.unimarc_scraper import create_session, search_products

        session = create_session()
        products = search_products(session, TEST_QUERY, max_pages=1)

        # promo_description and discount_percent are Club-Unimarc-specific fields
        assert all("discount_percent" in p for p in products), (
            "Unimarc: 'discount_percent' field missing from products. "
            "The priceDetail schema may have changed."
        )
