"""
Gestor de Catálogo Antigravity
==============================
Módulo encargado de la salud del inventario y el control del robot de escaneo (CatalogBot).
"""

import threading
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import func
from core.db import get_session
from core.models import StoreProduct, Product, Store, Price
from ..schemas import UnifiedResponse
from ..middleware import get_api_key
from agents.catalog_bot import get_catalog_bot_status, trigger_manual_scan, _catalog_bot_state

logger = logging.getLogger("AntigravityAPI")
UTC = timezone.utc

router = APIRouter(
    prefix="/api/catalog",
    tags=["Catalog Management"],
    dependencies=[Depends(get_api_key)]
)

@router.get("/status", response_model=UnifiedResponse)
def get_catalog_status():
    """
    Estado actual del CatalogBot y estadísticas de cobertura de productos.
    Informa sobre cuántos productos están emparejados (matched) y la salud general de la DB.
    """
    bot_status = get_catalog_bot_status()
    
    with get_session() as session:
        # Estadísticas globales de productos en el sistema
        total_store_products = session.query(StoreProduct).count()
        total_canonical = session.query(Product).count()
        total_matched = session.query(StoreProduct).filter(
            StoreProduct.product_id.isnot(None)
        ).count()
        
        # Cálculo de porcentaje de cobertura (productos enlazados a una ficha canónica)
        coverage_pct = round((total_matched / total_store_products * 100), 1) if total_store_products > 0 else 0
        
        # Desglose de productos recolectados por cada supermercado
        stores = session.query(Store).all()
        store_stats = []
        for st in stores:
            count = session.query(StoreProduct).filter_by(store_id=st.id).count()
            store_stats.append({"store": st.name, "products": count})
    
    return UnifiedResponse(data={
        **bot_status,
        "db_stats": {
            "total_store_products": total_store_products,
            "total_canonical_products": total_canonical,
            "matched_products": total_matched,
            "coverage_percent": coverage_pct,
            "by_store": store_stats,
        }
    })


@router.post("/scan", response_model=UnifiedResponse)
def trigger_catalog_scan():
    """
    Dispara un escaneo manual inmediato del CatalogBot.
    Útil para forzar una actualización tras cambios masivos en los scrapers.
    """
    # Verificamos que el robot no esté ya trabajando para evitar colisiones
    if _catalog_bot_state["status"] == "scanning":
        return UnifiedResponse(success=False, error="El CatalogBot ya está escaneando. Espera que termine para iniciar uno nuevo.")
    
    trigger_manual_scan()
    return UnifiedResponse(success=True, data={
        "message": "🤖 Escaneo de cobertura iniciado con éxito en segundo plano.",
        "tip": "Puedes consultar la evolución en tiempo real mediante GET /api/catalog/status."
    })


# ── Estado del stock scanner ───────────────────────────────────────────────────
_stock_scan_state: dict = {"running": False, "last_run": None, "updated": 0, "marked_oos": 0}
_stock_scan_lock  = threading.Lock()


@router.get("/stock-status", response_model=UnifiedResponse)
def get_stock_status():
    """Estadísticas de stock: productos en stock, sin stock y última sincronización."""
    with get_session() as session:
        total   = session.query(func.count(StoreProduct.id)).scalar()
        in_stk  = session.query(func.count(StoreProduct.id)).filter(StoreProduct.in_stock == True).scalar()
        oos     = total - in_stk

        # Cuántos productos no se han sincronizado en las últimas 48h
        cutoff  = datetime.now(UTC) - timedelta(hours=48)
        stale   = session.query(func.count(StoreProduct.id)).filter(
            (StoreProduct.last_sync == None) | (StoreProduct.last_sync < cutoff)
        ).scalar()

        latest_price = session.query(func.max(Price.scraped_at)).scalar()

    return UnifiedResponse(data={
        "total_products":     total,
        "in_stock":           in_stk,
        "out_of_stock":       oos,
        "stale_over_48h":     stale,
        "last_price_update":  latest_price.isoformat() if latest_price else None,
        "scanner":            _stock_scan_state,
    })


def run_stock_scan(batch_size: int = 50) -> None:
    """
    Ejecuta un ciclo completo de escaneo de stock en el hilo actual.
    Diseñada para ser llamada desde el endpoint HTTP o desde el agente periódico.
    """
    updated = 0
    marked_oos = 0
    try:
        from domain.ingest import sync_single_store_product
        cutoff = datetime.now(UTC) - timedelta(hours=24)

        with get_session() as session:
            targets = (
                session.query(StoreProduct.id)
                .filter(
                    StoreProduct.in_stock == True,
                    (StoreProduct.last_sync == None) | (StoreProduct.last_sync < cutoff)
                )
                .order_by(StoreProduct.last_sync.asc().nullsfirst())
                .limit(batch_size)
                .all()
            )
            sp_ids = [r[0] for r in targets]

        logger.info(f"[StockScan] Iniciando escaneo de {len(sp_ids)} productos.")
        for sp_id in sp_ids:
            try:
                with get_session() as session:
                    ok = sync_single_store_product(session, sp_id)
                    if ok:
                        updated += 1
                        sp = session.get(StoreProduct, sp_id)
                        if sp and not sp.in_stock:
                            marked_oos += 1
            except Exception as e:
                logger.warning(f"[StockScan] Error en sp_id={sp_id}: {e}")

    except Exception as e:
        logger.error(f"[StockScan] Error general: {e}", exc_info=True)
    finally:
        with _stock_scan_lock:
            _stock_scan_state["running"]    = False
            _stock_scan_state["last_run"]   = datetime.now(UTC).isoformat()
            _stock_scan_state["updated"]    = updated
            _stock_scan_state["marked_oos"] = marked_oos
        logger.info(f"[StockScan] Completado. {updated} actualizados, {marked_oos} marcados sin stock.")


@router.post("/stock-scan", response_model=UnifiedResponse)
def trigger_stock_scan(batch_size: int = 50):
    """
    Lanza un escaneo de stock en segundo plano.
    Revisa productos sin sincronizar recientemente, actualiza precios y marca sin-stock.
    batch_size: cuántos productos revisar (máx 200).
    """
    batch_size = min(max(batch_size, 10), 200)

    with _stock_scan_lock:
        if _stock_scan_state["running"]:
            return UnifiedResponse(
                success=False,
                error="Ya hay un escaneo en curso. Espera que termine."
            )
        _stock_scan_state["running"] = True

    threading.Thread(
        target=run_stock_scan,
        args=(batch_size,),
        name="StockScanner",
        daemon=True
    ).start()
    return UnifiedResponse(success=True, data={
        "message": f"Escaneo de stock iniciado para {batch_size} productos en segundo plano.",
        "tip":     "Consulta el progreso en GET /api/catalog/stock-status"
    })
