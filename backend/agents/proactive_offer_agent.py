
import os
import sys
import time
from datetime import datetime, timezone

# Ensure backend is in path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from core.db import get_session
from core.models import StoreProduct, Price, Store

def curate_deals():
    """
    KAIROS Agent: Scans all supermarkets for the best active deals.
    Focuses on > 20% discount and verified stock.
    """
    print(f"[{datetime.now().isoformat()}] KAIROS: Iniciando curación de ofertas diarias...")
    
    with get_session() as session:
        # 1. Fetch all store products with recent prices
        # For demo, we rely on existing Price records with has_discount=True
        deals_query = (
            session.query(StoreProduct, Price, Store)
            .join(Price, Price.store_product_id == StoreProduct.id)
            .join(Store, Store.id == StoreProduct.store_id)
            .filter(Price.has_discount == True)
            .filter(StoreProduct.in_stock == True)
            .order_by(Price.scraped_at.desc())
            .all()
        )
        
        print(f"KAIROS: Encontradas {len(deals_query)} ofertas potenciales.")
        
        curated = []
        for sp, price, store in deals_query:
            # Re-calculate and verify discount
            if not price.list_price or not price.price or price.list_price <= price.price:
                continue
                
            discount_pct = (1 - price.price / price.list_price) * 100
            
            # Filter criteria for 'Mejores Ofertas'
            if discount_pct >= 20: 
                curated.append({
                    "id": sp.id,
                    "name": sp.name,
                    "store": store.name,
                    "discount": f"{round(discount_pct)}%",
                    "price": price.price
                })
        
        # Sort by best discount
        curated.sort(key=lambda x: float(x['discount'].replace('%', '')), reverse=True)
        
        print(f"KAIROS: Curación completada. Top 5 ofertas seleccionadas para portada:")
        for i, deal in enumerate(curated[:5]):
            print(f"  {i+1}. {deal['name']} ({deal['store']}): {deal['discount']} OFF -> ${deal['price']}")
            
    print(f"[{datetime.now().isoformat()}] KAIROS: Portada optimizada.")

if __name__ == "__main__":
    curate_deals()
