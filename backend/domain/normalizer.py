"""
Scraper Output Normalizer
==========================
Provides a single function `normalize_scraped_product` that enforces
the unified product schema shared by every supermarket scraper.

Responsibility:
  - Calculate savings_amount and discount_percent from price/list_price.
  - Ensure unit_multiplier exists with a safe default.
  - Strip frontend-display-only string fields.
  - Fill in any missing common fields with safe defaults.

Usage (inside any scraper's normalize_product function):
    from normalizer import normalize_scraped_product
    ...
    raw_dict = { ... }  # built from the API response
    return normalize_scraped_product(raw_dict)
"""

# Fields that are pure UI formatting strings.
# These are stripped out during normalization so the frontend
# controls its own display logic.
_DISPLAY_FIELDS_TO_STRIP = {
    "unit_price_display",
    "measurement_unit_display",
    "unit_multiplier_display",
    "price_per_unit_measurement",
}

# Scraper-specific discount fields that are superseded by our
# centralized calculation. Removed to avoid duplicate/inconsistent data.
_DEPRECATED_DISCOUNT_FIELDS = {
    "savings_percent",   # was Lider-specific (superseded by discount_percent)
}


def normalize_scraped_product(product: dict) -> dict:
    """
    Accept a raw scraper output dictionary and return a clean, unified
    version that conforms to the shared schema.

    This function is idempotent: running it more than once on the same
    dict is safe and produces the same result.

    Args:
        product: dict built by a scraper's normalize_product() function.

    Returns:
        The same dict, mutated in place AND returned, with:
          - savings_amount  calculated (or None if not applicable).
          - discount_percent calculated (or None if not applicable).
          - unit_multiplier defaulted to 1 if missing.
          - Display/deprecated fields removed.
    """
    # ------------------------------------------------------------------
    # 1. Calculate savings_amount and discount_percent
    # ------------------------------------------------------------------
    price = product.get("price")
    list_price = product.get("list_price")

    savings_amount = None
    discount_percent = None

    if price is not None and list_price is not None and list_price > price:
        savings_amount = round(list_price - price, 2)
        discount_percent = round((savings_amount / list_price) * 100)

    product["savings_amount"] = savings_amount
    product["discount_percent"] = discount_percent

    # ------------------------------------------------------------------
    # 2. Ensure unit_multiplier has a safe default
    # ------------------------------------------------------------------
    if "unit_multiplier" not in product or product["unit_multiplier"] is None:
        product["unit_multiplier"] = 1

    # ------------------------------------------------------------------
    # 3. Strip UI-only display string fields
    # ------------------------------------------------------------------
    for field in _DISPLAY_FIELDS_TO_STRIP:
        product.pop(field, None)

    # Also remove the old Jumbo-specific field if present
    product.pop("price_per_unit", None)

    # ------------------------------------------------------------------
    # 4. Remove deprecated per-scraper discount fields
    # ------------------------------------------------------------------
    for field in _DEPRECATED_DISCOUNT_FIELDS:
        product.pop(field, None)

    return product
