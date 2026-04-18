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
def _is_running(name: str) -> bool:
    return any(t.name == name for t in threading.enumerate())


def start_background_agents():
    """Arranca todos los agentes de fondo. Cada agente vive en su propio módulo."""
    from agents.fluxengine_sentry import fluxengine_sentry_loop
    from agents.proactive_alert_agent import start_proactive_alert_agent
    from agents.stock_scan_agent import start_stock_scan_agent
    from agents.qa_agent import qa_agent_loop
    from agents.self_healer import self_healer_loop
    from agents.log_tracker import log_tracker_loop
    from agents.catalog_sync_scheduler import start_catalog_sync_scheduler
    from agents.scraper_health_agent import start_scraper_health_agent
    from agents.security_audit_agent import security_audit_loop
    from agents.security_healer_agent import security_healer_loop

    if not _is_running("FluxEngineSentry"):
        threading.Thread(target=fluxengine_sentry_loop, name="FluxEngineSentry", daemon=True).start()
        logger.info("[Sentry] Monitoreo activo inicializado.")

    if not _is_running("KairosProactive"):
        start_proactive_alert_agent()

    if not _is_running("StockScanAgent"):
        start_stock_scan_agent()

    if not _is_running("QAAgent"):
        threading.Thread(target=qa_agent_loop, name="QAAgent", daemon=True).start()
        logger.info("[QAAgent] Monitor de integridad inicializado.")

    if not _is_running("SelfHealer"):
        threading.Thread(target=self_healer_loop, name="SelfHealer", daemon=True).start()
        logger.info("[SelfHealer] Auto-corrección de BD inicializada.")

    if not _is_running("LogTracker"):
        threading.Thread(target=log_tracker_loop, name="LogTracker", daemon=True).start()
        logger.info("[LogTracker] Tracker de errores de log inicializado.")

    if not any(t.name.startswith("CatalogSync_") for t in threading.enumerate()):
        start_catalog_sync_scheduler()
        logger.info("[CatalogSync] Scheduler de resincronización por tienda inicializado.")

    health_threads = [t.name for t in threading.enumerate() if t.name in ("ScraperHealthCheck", "ScraperRetry")]
    if len(health_threads) < 2:
        start_scraper_health_agent()
        logger.info("[HealthAgent] Agente de salud de scrapers inicializado.")

    if not _is_running("SecAudit"):
        threading.Thread(target=security_audit_loop, name="SecAudit", daemon=True).start()
        logger.info("[SecAudit] Agente de auditoría de seguridad inicializado.")

    if not _is_running("SecHealer"):
        threading.Thread(target=security_healer_loop, name="SecHealer", daemon=True).start()
        logger.info("[SecHealer] Agente de auto-corrección de seguridad inicializado.")


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
    "https://freshcart-app-beryl.vercel.app",      # Vercel production frontend
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
@app.middleware("http")
async def security_headers_middleware(request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    if _is_production:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    return response

# --- LÍMITE DE TAMAÑO DE REQUEST ---
_MAX_REQUEST_BODY = 512 * 1024  # 512 KB

@app.middleware("http")
async def request_size_middleware(request, call_next):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > _MAX_REQUEST_BODY:
        return JSONResponse(
            status_code=413,
            content={"success": False, "error": "Request demasiado grande."}
        )
    return await call_next(request)

# --- MANEJADORES DE EXCEPCIONES GLOBALES ---
app.add_exception_handler(Exception, global_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)

# --- BLOQUEO DE BD (control en tiempo real desde Discord) ---
from core.db_lock import is_locked, set_locked

@app.middleware("http")
async def db_lock_middleware(request, call_next):
    safe_paths = {"/", "/metrics", "/internal/db/lock", "/internal/db/unlock",
                  "/internal/db/status", "/api/auth/login", "/api/auth/refresh"}
    if is_locked() and request.url.path not in safe_paths:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"detail": "Servicio en mantenimiento. Intenta más tarde."})
    return await call_next(request)

_INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "")

@app.post("/internal/db/lock")
async def db_lock(request):
    token = request.headers.get("X-Internal-Token", "")
    if not _INTERNAL_SECRET or token != _INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    set_locked(True)
    logger.warning("[DB-LOCK] Base de datos bloqueada via endpoint interno.")
    return {"status": "locked"}

@app.post("/internal/db/unlock")
async def db_unlock(request):
    token = request.headers.get("X-Internal-Token", "")
    if not _INTERNAL_SECRET or token != _INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    set_locked(False)
    logger.info("[DB-LOCK] Base de datos desbloqueada via endpoint interno.")
    return {"status": "unlocked"}

@app.get("/internal/db/status")
async def db_status(request):
    token = request.headers.get("X-Internal-Token", "")
    if not _INTERNAL_SECRET or token != _INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    return {"locked": is_locked()}

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
def _honeytoken_block(request, label: str):
    from core.shield import Shield3
    from api.middleware import _get_real_ip
    ip = _get_real_ip(request)
    Shield3.block_ip(ip, reason=f"Honeytoken: {label}")
    raise HTTPException(status_code=403, detail="SECURITY BREACH: IP BLOCKED BY FLUXENGINE SHIELD.")

@app.get("/api/admin/config/v1/internal_metrics")
async def honeytoken_internal_metrics(request):
    _honeytoken_block(request, "internal_metrics")

@app.get("/wp-admin")
@app.get("/wp-login.php")
@app.get("/admin")
@app.get("/.env")
@app.get("/phpinfo.php")
@app.get("/config.php")
@app.get("/.git/config")
@app.get("/api/v1/admin")
async def honeytoken_common_scans(request):
    _honeytoken_block(request, request.url.path)

@app.get("/")
async def root():
    """Estado base de la API (Público)."""
    return {"status": "online"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    debug_mode = os.getenv("DEBUG", "false").lower() == "true"
    uvicorn.run("api.main:app", host="0.0.0.0", port=port, reload=debug_mode)
