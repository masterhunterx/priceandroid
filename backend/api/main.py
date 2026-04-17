"""
API de Supermercados Antigravity
================================
Aplicación FastAPI que expone datos de productos y lógica de ahorro KAIROS al frontend.
Esta versión modularizada utiliza routers y un sistema de seguridad avanzado (Shield).
"""

import logging
import threading
import time
import os
from logging.handlers import RotatingFileHandler
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import make_asgi_app
from starlette.routing import Mount

from core.db import init_db, get_session
from core.models import Store, StoreProduct
from .middleware import (
    get_api_key, 
    shield_security_middleware, 
)
from .exceptions import global_exception_handler, http_exception_handler
from .routers import products, stores, assistant, catalog, deals, pantry, auth, feedback
from .schemas import UnifiedResponse

# --- CONFIGURACIÓN DE LOGS ---
# Registramos eventos tanto en consola como en un archivo de depuración permanente.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler("server_debug.log", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
    ]
)
logger = logging.getLogger("AntigravityAPI")

# --- AGENTES EN SEGUNDO PLANO ---
def start_background_agents():
    """
    Inicializa los agentes inteligentes que corren de forma asíncrona en hilos separados.
    Esto permite que la API responda rápido mientras los bots procesan datos.
    """
    from agents.fluxengine_sentry import fluxengine_sentry_loop
    from domain.proactive import generate_proactive_alerts

    # 1. FluxEngine Sentry: Monitorea cambios críticos en el mercado.
    if not any(t.name == "FluxEngineSentry" for t in threading.enumerate()):
        sentry_thread = threading.Thread(target=fluxengine_sentry_loop, name="FluxEngineSentry", daemon=True)
        sentry_thread.start()
        logger.info("[Sentry] Monitoreo activo inicializado.")

    # 2. KAIROS Proactive Alert Engine: Genera alertas de ahorro cada 15 minutos.
    _kairos_stop_event = threading.Event()

    def proactive_alert_loop(stop_event: threading.Event):
        logger.info("[KAIROS] Motor de Alertas Proactivas: Activo.")

        from datetime import datetime, timezone
        from core.telemetry import TelemetryService
        from core.db import get_session
        from core.models import Store, StoreProduct

        start_time = datetime.now(timezone.utc)

        while not stop_event.is_set():
            try:
                generate_proactive_alerts()

                # --- Enviar Telemetría (Heartbeat) ---
                uptime_mins = int((datetime.now(timezone.utc) - start_time).total_seconds() / 60)
                with get_session() as db:
                    sc = db.query(Store).count()
                    pc = db.query(StoreProduct).count()
                TelemetryService.send_heartbeat(stores_count=sc, products_count=pc, uptime_minutes=uptime_mins)

                # Refrescar métricas Prometheus tras cada ciclo
                try:
                    from core.metrics import refresh_catalog_gauges, refresh_feedback_gauges
                    refresh_catalog_gauges()
                    refresh_feedback_gauges()
                except Exception:
                    pass

            except Exception as e:
                logger.error(f"❌ [KAIROS] Error en motor de alertas: {e}", exc_info=True)

            # Esperar en intervalos de 1s para poder detener el thread rápidamente
            stop_event.wait(timeout=900)

        logger.info("[KAIROS] Motor proactivo detenido.")

    if not any(t.name == "KairosProactive" for t in threading.enumerate()):
        proactive_thread = threading.Thread(
            target=proactive_alert_loop,
            args=(_kairos_stop_event,),
            name="KairosProactive",
            daemon=True
        )
        proactive_thread.start()
        logger.info("[KAIROS] Motor proactivo inicializado.")

    # 3. StockScanAgent: Revisa productos desactualizados cada 6 horas.
    _catalog_mod = catalog  # capture already-imported module for use inside thread

    def stock_scan_loop():
        logger.info("[StockAgent] Agente de escaneo periódico de stock: Activo.")
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
            # Esperar 2 horas entre ciclos (antes 6h — acelerado para alcanzar productos sin sync)
            time.sleep(2 * 3600)

    if not any(t.name == "StockScanAgent" for t in threading.enumerate()):
        threading.Thread(target=stock_scan_loop, name="StockScanAgent", daemon=True).start()
        logger.info("[StockAgent] Agente periódico de stock inicializado (cada 6h).")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestor de ciclo de vida de la aplicación.
    Ejecuta tareas al arrancar y al apagar el servidor.
    """
    # Inicialización de la base de datos (creación de tablas si no existen)
    init_db()
    
    # Auditoría rápida de arranque para verificar salud de los datos
    try:
        with get_session() as db:
            store_count = db.query(Store).count()
            product_count = db.query(StoreProduct).count()
            logger.info(f"Sistema Inicializado: {store_count} tiendas, {product_count} productos en catálogo.")
            if product_count == 0:
                logger.warning("La base de datos está vacía. Es posible que los scrapers necesiten ejecutarse.")

    except Exception as e:
        logger.error(f"La auditoría de arranque falló: {e}")

    # --- Auto-Recuperación Heurística (Self-Healing) — en hilo background para no bloquear ---
    def _run_audit():
        try:
            from domain.audit import run_startup_audit
            from core.db import get_session
            with get_session() as audit_db:
                run_startup_audit(audit_db)
        except Exception as e:
            logger.error(f"La auditoría de arranque falló: {e}")

    threading.Thread(target=_run_audit, name="StartupAudit", daemon=True).start()

    # Inicializar métricas de catálogo al arrancar
    try:
        from core.metrics import refresh_catalog_gauges, refresh_feedback_gauges
        refresh_catalog_gauges()
        refresh_feedback_gauges()
    except Exception as e:
        logger.warning(f"[Metrics] No se pudieron inicializar gauges: {e}")

    # Lanzamiento de agentes en segundo plano
    start_background_agents()

    # --- INICIALIZAR DISCORD BOT ---
    import asyncio
    from core.discord_bot import bot, DISCORD_BOT_TOKEN
    
    bot_task = None
    if DISCORD_BOT_TOKEN:
        bot_task = asyncio.create_task(bot.start(DISCORD_BOT_TOKEN))
        logger.info("[KAIROS BOT] Hilo de Asistente Discord asíncrono disparado.")

    yield
    
    logger.info("Sistema apagándose...")
    if bot_task:
        await bot.close()
        bot_task.cancel()

# --- INICIALIZACIÓN DE LA APP ---
# Fail-closed: si ENVIRONMENT no está explícitamente en "development", se trata como producción.
# Esto evita exponer /docs en un deploy donde se olvidó configurar la variable.
_env = os.getenv("ENVIRONMENT", "").lower()
_is_production = _env != "development"

app = FastAPI(
    title="Antigravity Grocery API",
    description="API comparativa de productos y ahorro inteligente KAIROS",
    version="1.1.0",
    lifespan=lifespan,
    # Documentación deshabilitada en producción — evita exponer el mapa completo de la API
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
)

# --- MÉTRICAS PROMETHEUS ---
# Expone /metrics para Grafana Cloud Prometheus scraping (público, sin API key)
_instrumentator = Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=True,
    excluded_handlers=["/metrics", "/"],
).instrument(app)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# --- CONFIGURACIÓN DE CORS ---
# Permite que el Frontend (React/Vite) y el APK (Capacitor) se comuniquen con la API.
_base_origins = [
    "http://localhost:5000",
    "http://127.0.0.1:5000",
    "http://localhost:5001",
    "http://127.0.0.1:5001",
    "http://localhost:5173",
    "http://localhost:3000",
    "capacitor://localhost",   # APK Capacitor (Android/iOS)
    "ionic://localhost",        # Ionic Capacitor
    "https://dancing-nougat-071a55.netlify.app",  # Netlify production frontend
]
# Orígenes adicionales de producción configurados vía env var (ej: URL de Railway del frontend)
_extra = os.getenv("ALLOWED_ORIGINS", "")
_allowed_origins = _base_origins + [o.strip() for o in _extra.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "Authorization", "X-Branch-Context"],
)

# --- MIDDLEWARE DE SEGURIDAD (SHIELD) ---
# Todas las peticiones pasan por este escudo antes de llegar a la lógica de negocio.
@app.middleware("http")
async def security_middleware_wrapper(request, call_next):
    return await shield_security_middleware(request, call_next)

# --- SECURITY HEADERS ---
# Añade cabeceras de seguridad a todas las respuestas.
@app.middleware("http")
async def security_headers_middleware(request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    if _is_production:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    return response

# --- MANEJADORES DE EXCEPCIONES GLOBALES ---
app.add_exception_handler(Exception, global_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)

# --- INCLUSIÓN DE ROUTERS MODULARES (Protegidos internamente por API Key) ---
app.include_router(auth.router)        # Público — login/refresh/me
app.include_router(products.router)
app.include_router(stores.router)
app.include_router(assistant.router)
app.include_router(catalog.router)
app.include_router(deals.router)
app.include_router(pantry.router)
app.include_router(feedback.router)

# --- TRAMPAS PARA BOTS (HONEYTOKENS) ---
# Endpoints falsos diseñados para detectar y bloquear scrapers malintencionados inmediatamente.
@app.get("/api/admin/config/v1/internal_metrics")
async def honeytoken_internal_metrics(request):
    """TRAMPA PARA BOTS: Bloqueo de IP instantáneo por acceso sospechoso."""
    from core.shield import Shield3
    ip = request.client.host if request.client else "unknown"
    Shield3.block_ip(ip, reason="Honeytoken Trap Sprung (Internal Metrics Access)")
    raise HTTPException(status_code=403, detail="SECURITY BREACH: IP BLOCKED BY FLUXENGINE SHIELD.")

@app.get("/")
async def root():
    """Estado base de la API (Público)."""
    return {"status": "online"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    debug_mode = os.getenv("DEBUG", "false").lower() == "true"
    uvicorn.run("api.main:app", host="0.0.0.0", port=port, reload=debug_mode)
