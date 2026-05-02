import hashlib
from datetime import datetime, timezone
UTC = timezone.utc
from core.models import StoreProduct

def compute_content_hash(product_data: dict) -> str:
    """
    Compute an MD5 fingerprint of the product's semi-static metadata.
    """
    fields = (
        str(product_data.get("name", "")),
        str(product_data.get("brand", "")),
        str(product_data.get("slug", "")),
        str(product_data.get("category_path", "")),
        str(product_data.get("top_category", "")),
        str(product_data.get("measurement_unit", "")),
    )
    return hashlib.md5("|".join(fields).encode(), usedforsecurity=False).hexdigest()  # nosec B324


def price_changed(sp: StoreProduct, new_price: float | None) -> bool:
    """
    Return True if the new price differs from the last recorded price.
    """
    latest = sp.latest_price
    if latest is None:
        return True
    if latest.price is None and new_price is None:
        return False
    if latest.price is None or new_price is None:
        return True
    return abs(latest.price - new_price) > 0.01
