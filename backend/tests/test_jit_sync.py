import sys
import os
import time
from datetime import datetime, timedelta, timezone

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from core.db import get_session
from core.models import StoreProduct, Product
import requests

API_URL = "http://localhost:8000/api"
HEADERS = {"X-API-Key": "antigravity_dev_key"}
UTC = timezone.utc

def test_jit_sync():
    print("\n--- INICIANDO AUDITORÍA DE SINCRONIZACIÓN JIT ---")
    
    with get_session() as session:
        # 1. Buscar un producto que tenga SKU y Store para probar
        sp = session.query(StoreProduct).filter(StoreProduct.sku_id != None).first()
        if not sp:
            print("ERROR: No se encontró producto con SKU para probar")
            return
            
        product_id = sp.product_id
        original_sync = sp.last_sync
        
        # 2. Forzar que sea 'Antiguo' (ayer)
        sp.last_sync = datetime.now(UTC) - timedelta(days=1)
        session.commit()
        print(f"[*] Producto {sp.id} ({sp.name[:30]}...) preparado.")
        print(f"[*] last_sync original (simulado): {sp.last_sync}")
        
        # 3. Disparar JIT a través del Detail View de la API
        print(f"[*] Consultando detalle del producto {product_id} para disparar JIT...")
        resp = requests.get(f"{API_URL}/products/{product_id}", headers=HEADERS)
        if resp.status_code != 200:
            print(f"ERROR: API falló con status {resp.status_code}")
            return
            
        print("[+] API respondió con éxito. Esperando 5 segundos para que la tarea de fondo (JIT) termine...")
        time.sleep(5)
        
        # 4. Verificar en DB si se actualizó
        session.refresh(sp)
        new_sync = sp.last_sync
        
        if new_sync and new_sync > (datetime.now(UTC) - timedelta(minutes=1)).replace(tzinfo=None):
            print(f"\n[SUCCESS] ¡JIT FUNCIONA! El last_sync se actualizó a: {new_sync}")
            print(f"  Diferencia: {new_sync - original_sync if original_sync else 'N/A'}")
        else:
            print(f"\n[FAILURE] El last_sync no se actualizó. Valor actual: {new_sync}")

if __name__ == "__main__":
    test_jit_sync()
