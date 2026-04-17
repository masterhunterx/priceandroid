import asyncio
import httpx
import time
import statistics
import os
import sys

# --- CONFIGURACIÓN DEL TEST ---
BASE_URL = "http://127.0.0.1:8000"
API_KEY = "antigravity_dev_key"
STRESS_MODE = "true"

# Endpoints pesados para atacar
TARGETS = [
    {"method": "GET", "url": "/api/products/search?q=leche", "name": "Búsqueda (leche)"},
    {"method": "GET", "url": "/api/assistant/favorites", "name": "Listado Favoritos"},
    {"method": "POST", "url": "/api/assistant/optimize_cart", "name": "Optimización Carrito", "json": {
        "items": [
            {"name": "leche", "id": 1, "qty": 2},
            {"name": "pan soprole", "id": 45, "qty": 1},
            {"name": "arroz tucapel", "id": 12, "qty": 3}
        ]
    }}
]

HEADERS = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

# Límites de falla
LATENCY_THRESHOLD = 2.0  # Segundos
ERROR_THRESHOLD_PERCENT = 5.0

class StressTester:
    def __init__(self):
        self.stats = {
            "total_requests": 0,
            "failed_requests": 0,
            "latencies": []
        }
        self.stop_requested = False

    async def hit_endpoint(self, client, target):
        start = time.perf_counter()
        try:
            if target["method"] == "GET":
                resp = await client.get(target["url"])
            else:
                resp = await client.post(target["url"], json=target.get("json", {}))
            
            latency = time.perf_counter() - start
            self.stats["latencies"].append(latency)
            self.stats["total_requests"] += 1
            
            if resp.status_code >= 400:
                self.stats["failed_requests"] += 1
                print(f"  [!] Error {resp.status_code} en {target['name']}")
                
        except Exception as e:
            self.stats["failed_requests"] += 1
            print(f"  [X] Fallo de conexión: {e}")

    async def run_batch(self, concurrent_users):
        async with httpx.AsyncClient(base_url=BASE_URL, headers=HEADERS, timeout=10.0) as client:
            tasks = []
            for _ in range(concurrent_users):
                # Rotamos entre los objetivos
                target = TARGETS[concurrent_users % len(TARGETS)]
                tasks.append(self.hit_endpoint(client, target))
            
            await asyncio.gather(*tasks)

    def report(self, users):
        if not self.stats["latencies"]:
            return
            
        avg = statistics.mean(self.stats["latencies"])
        p95 = statistics.quantiles(self.stats["latencies"], n=20)[18] if len(self.stats["latencies"]) >= 20 else avg
        error_rate = (self.stats["failed_requests"] / max(1, self.stats["total_requests"])) * 100
        
        print(f"[TEST] Usuarios: {users:<4} | Req: {self.stats['total_requests']:<6} | Avg: {avg:.2f}s | p95: {p95:.2f}s | Errores: {error_rate:.1f}%")
        
        # Breaking Point Detection
        if avg > LATENCY_THRESHOLD:
            print(f"\n[STOP] BREAKING POINT ALCANZADO: Latencia promedio > {LATENCY_THRESHOLD}s")
            self.stop_requested = True
            
        if error_rate > ERROR_THRESHOLD_PERCENT:
            print(f"\n[STOP] BREAKING POINT ALCANZADO: Tasa de errores > {ERROR_THRESHOLD_PERCENT}%")
            self.stop_requested = True

    async def main_loop(self):
        print("[START] Iniciando Stress Test Agresivo...")
        print(f"Objetivo: {BASE_URL}")
        print(f"Ramp-up: +50 usuarios cada 10s\n")
        
        users = 50
        while not self.stop_requested:
            # Ejecutamos ráfagas durante 10 segundos para este nivel de carga
            start_level = time.time()
            self.stats = {"total_requests": 0, "failed_requests": 0, "latencies": []}
            
            while time.time() - start_level < 10:
                await self.run_batch(users)
                if self.stop_requested: break
                
            self.report(users)
            if self.stop_requested: break
            
            users += 50
            if users > 1000:
                print("--- [FIN] Se alcanzó el límite máximo de usuarios (1000).")
                break

if __name__ == "__main__":
    # Aseguramos que el bypass de Shield esté activo mediante env var si se desea
    os.environ["STRESS_TEST_MODE"] = STRESS_MODE
    asyncio.run(StressTester().main_loop())
