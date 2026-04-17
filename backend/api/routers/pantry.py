"""
Gestión de Despensa e Inventario Inteligente
============================================
Router para la gestión de productos marcados como comprados y tracking de consumo.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone, timedelta
from core.db import get_session
from core.models import PantryItem, Product
from ..schemas import UnifiedResponse, PantryItemOut, PantryPurchaseRequest
from ..middleware import get_api_key

router = APIRouter(
    prefix="/api/pantry",
    tags=["Pantry & Restocking"],
    dependencies=[Depends(get_api_key)]
)

UTC = timezone.utc

@router.get("/", response_model=UnifiedResponse)
def get_pantry():
    with get_session() as session:
        items = session.query(PantryItem).filter(PantryItem.is_active == True).all()
        
        result = []
        for item in items:
            product = item.product
            # calculate days remaining
            days_remaining = None
            if item.estimated_depletion_at:
                # Ensure datetime objects are timezone-aware in UTC before subtracting
                now = datetime.now(UTC)
                target = item.estimated_depletion_at
                if target.tzinfo is None:
                    target = target.replace(tzinfo=UTC)
                diff = (target - now).days
                days_remaining = max(0, diff)
                
            result.append(PantryItemOut(
                id=item.id,
                product_id=item.product_id,
                product_name=product.canonical_name if product else "Unknown",
                image_url=product.image_url if product else "",
                last_purchased_at=item.last_purchased_at.isoformat() if item.last_purchased_at else "",
                purchase_count=item.purchase_count,
                current_stock_level=item.current_stock_level,
                estimated_depletion_at=item.estimated_depletion_at.isoformat() if item.estimated_depletion_at else None,
                days_remaining=days_remaining
            ))
            
        return UnifiedResponse(data=result)

@router.post("/purchase", response_model=UnifiedResponse)
def buy_pantry_items(purchases: List[PantryPurchaseRequest]):
    with get_session() as session:
        now = datetime.now(UTC)
        for p in purchases:
            # Validar que el producto exista antes de crear el item de despensa
            if not session.get(Product, p.product_id):
                raise HTTPException(
                    status_code=404,
                    detail=f"Producto {p.product_id} no encontrado"
                )
            item = session.query(PantryItem).filter(PantryItem.product_id == p.product_id).first()
            
            if item:
                item.purchase_count += 1
                if item.last_purchased_at:
                    last_at = item.last_purchased_at
                    if last_at.tzinfo is None:
                        last_at = last_at.replace(tzinfo=UTC)
                    days_since_last = (now - last_at).days
                    if days_since_last > 0:
                        item.average_days_between_purchases = (item.average_days_between_purchases + days_since_last) / 2.0
                
                item.last_purchased_at = now
                item.current_stock_level = p.stock_level
                item.is_active = True
                item.estimated_depletion_at = now + timedelta(days=item.average_days_between_purchases)
            else:
                new_item = PantryItem(
                    product_id=p.product_id,
                    last_purchased_at=now,
                    purchase_count=1,
                    average_days_between_purchases=14.0,
                    current_stock_level=p.stock_level,
                    is_active=True,
                    estimated_depletion_at=now + timedelta(days=14)
                )
                session.add(new_item)

        try:
            session.commit()
        except Exception as e:
            session.rollback()
            raise HTTPException(status_code=500, detail=f"Error al guardar en despensa: {e}")
        return UnifiedResponse(data={"message": "Pantry updated successfully"})

@router.post("/{item_id}/consume", response_model=UnifiedResponse)
def consume_pantry_item(item_id: int):
    with get_session() as session:
        item = session.query(PantryItem).filter(PantryItem.id == item_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
            
        if item.current_stock_level == "full":
            item.current_stock_level = "medium"
        elif item.current_stock_level == "medium":
            item.current_stock_level = "low"
        elif item.current_stock_level == "low":
            item.current_stock_level = "empty"
            # Optional: when empty, trigger an immediate notification or sync if needed
            
        try:
            session.commit()
        except Exception as e:
            session.rollback()
            raise HTTPException(status_code=500, detail=f"Error al actualizar stock: {e}")
        return UnifiedResponse(data={"message": f"Stock level updated to {item.current_stock_level}"})
