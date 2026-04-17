from core.db import get_session
from core.models import StoreProduct, Store

with get_session() as s:
    stores = s.query(Store).all()
    print(f"Stores in DB: {[st.slug for st in stores]}")
    for st in stores:
        count = s.query(StoreProduct).filter_by(store_id=st.id).count()
        print(f"  - {st.name} ({st.slug}): {count} products")
    print(f"Total Products: {s.query(StoreProduct).count()}")
