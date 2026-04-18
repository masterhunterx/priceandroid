"""
Agente de Escaneo Periódico de Stock
======================================
Revisa productos desactualizados cada 2 horas.
Extraído de api/main.py para mejor estructura y testabilidad.
"""

import logging
import threading
import time

logger = logging.getLogger("AntigravityAPI")


def stock_scan_loop():
    logger.info("[StockAgent] Agente de escaneo periódico de stock: Activo.")
    from api.routers import catalog as _catalog_mod
    # Primera ejecución retrasada 5 minutos para dar tiempo al arranque del servidor
    time.sleep(300)
    while True:
        try:
            with _catalog_mod._stock_scan_lock:
                if not _catalog_mod._stock_scan_state["running"]:
                    _catalog_mod._stock_scan_state["running"] = True
                    run_ok = True
                else:
                    run_ok = False
            if run_ok:
                _catalog_mod.run_stock_scan(batch_size=200)
        except Exception as e:
            logger.error(f"[StockAgent] Error en ciclo periódico: {e}", exc_info=True)
        time.sleep(2 * 3600)


def start_stock_scan_agent():
    thread = threading.Thread(target=stock_scan_loop, name="StockScanAgent", daemon=True)
    thread.start()
    logger.info("[StockAgent] Agente periódico de stock inicializado (cada 2h).")
