import os
import sys
import logging
import random
from datetime import datetime
from typing import List, Dict, Any

# Path setup
sys.path.append(os.getcwd())

from core.db import get_session
from core.models import StoreProduct, Price, Branch
from domain.ingest import fetch_single_product_data

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("centinela_audit.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("Centinela")

class CentinelaAuditor:
    """
    Agente Auditor Autónomo para validación de integridad de datos.
    Compara datos en DB vs Realidad en la web.
    """
    
    def __init__(self, sample_size: int = 10):
        this_dir = os.path.dirname(os.path.abspath(__file__))
        self.sample_size = sample_size

    def run_audit(self):
        logger.info(f"--- Iniciando Auditoría de Integridad (Muestra: {self.sample_size}) ---")
        
        with get_session() as session:
            # Seleccionar productos aleatorios con URL válida
            candidates = session.query(StoreProduct).filter(StoreProduct.product_url.isnot(None)).all()
            if not candidates:
                logger.warning("No hay productos con URL para auditar.")
                return
            
            sample = random.sample(candidates, min(len(candidates), self.sample_size))
            
            bugs_found = 0
            for sp in sample:
                logger.info(f"Auditando: {sp.name} ({sp.store.name})")
                
                # Fetch live data
                try:
                    live_data = fetch_single_product_data(sp.store.slug, sp.product_url)
                    if not live_data:
                        logger.error(f"  [BUG] No se pudo obtener info de la web para {sp.product_url}")
                        bugs_found += 1
                        continue
                    
                    # 1. Check Stock
                    if sp.in_stock != live_data.get('in_stock', True):
                        logger.warning(f"  [DISCREPANCIA] Stock incoherente. App: {sp.in_stock}, Web: {live_data['in_stock']}")
                        bugs_found += 1
                    
                    # 2. Check Price (Latest vs Live)
                    latest_price = sp.latest_price.price if sp.latest_price else None
                    live_price = live_data.get('price')
                    
                    if latest_price != live_price:
                        logger.warning(f"  [DISCREPANCIA] Precio desfasado. App: {latest_price}, Web: {live_price}")
                        bugs_found += 1
                        
                    # 3. Check Basic Info (Name mismatch)
                    # (Allow some difference, but if generic name changed completely, it's a bug)
                    
                except Exception as e:
                    logger.error(f"  [ERROR] Fallo crítico auditando {sp.name}: {e}")
                    bugs_found += 1

            logger.info(f"--- Auditoría Finalizada. Bugs/Discrepancias encontradas: {bugs_found} ---")

if __name__ == "__main__":
    auditor = CentinelaAuditor(sample_size=5)
    auditor.run_audit()
