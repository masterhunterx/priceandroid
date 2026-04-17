from typing import List, Dict, Any
from sqlalchemy.orm import Session, joinedload
from core.models import StoreProduct, ProductMatch, Product, Price
from sqlalchemy import func

def optimize_cart(db: Session, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    KAIROS Intelligence: Optimizes a shopping list to find the minimum total cost.
    Input: [{'query': 'leche loncoleche', 'qty': 2}, ...]
    Output aligns with ShoppingPlanner.tsx expectations.
    """
    optimized_items = []
    total_cart_cost = 0
    stores_visited = set()

    for item in items:
        query = item.get('query', '').strip()
        qty = item.get('qty', 1)
        
        if not query:
            continue

        # 1. Broad but efficient search
        # Using joinedload to fetch prices in the same query (Fixes N+1 problem)
        candidates = db.query(StoreProduct).options(
            joinedload(StoreProduct.prices)
        ).filter(
            StoreProduct.name.ilike(f"%{query}%"),
            StoreProduct.in_stock == True
        ).all()

        if not candidates:
            optimized_items.append({
                'query': query,
                'status': 'not_found',
                'qty': qty
            })
            continue

        # 2. Pick the absolute cheapest candidate with a valid price
        # candidates already have .prices preloaded
        valid_candidates = [c for c in candidates if c.latest_price and c.latest_price.price is not None]
        
        if not valid_candidates:
            optimized_items.append({
                'query': query,
                'status': 'out_of_stock',
                'qty': qty
            })
            continue

        best_candidate = min(valid_candidates, key=lambda x: x.latest_price.price)
        current_price = best_candidate.latest_price.price

        item_total = current_price * qty
        total_cart_cost += item_total
        stores_visited.add(best_candidate.store.name)

        # Use the synthetic ID convention (1_000_000 + sp.id) so the frontend
        # can navigate to /product/{id} and the API will resolve it correctly.
        synthetic_id = 1_000_000 + best_candidate.id
        optimized_items.append({
            'query': query,
            'status': 'optimized',
            'product_name': best_candidate.name,
            'store': best_candidate.store.name,
            'unit_price': current_price,
            'qty': qty,
            'total': item_total,
            'product_id': synthetic_id,
            'image_url': best_candidate.image_url
        })

    return {
        'total_cart_cost': total_cart_cost,
        'items': optimized_items,
        'stores_visited': list(stores_visited),
        'optimized_count': len([i for i in optimized_items if i['status'] == 'optimized'])
    }
