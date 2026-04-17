import logging
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from .schemas import UnifiedResponse
from core.telemetry import TelemetryService

logger = logging.getLogger("AntigravityAPI")

async def global_exception_handler(request: Request, exc: Exception):
    """Global catch-all for errors to prevent trace leakage in production."""
    endpoint = f"{request.method} {request.url.path}"
    # exc_info=True incluye el traceback completo en el log estructurado
    logger.error("[CRITICAL ERROR] %s — %s", endpoint, exc, exc_info=True)

    # Enviar reporte urgente a Discord
    TelemetryService.capture_exception(exc, endpoint_context=endpoint)
    
    # Return a generic message without internal details
    return JSONResponse(
        status_code=500,
        content=UnifiedResponse(
            success=False,
            error="An internal server error occurred. Please contact the administrator (Ref: FluxShield logs)."
        ).model_dump()
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle FastAPI exceptions with a structured format."""
    return JSONResponse(
        status_code=exc.status_code,
        content=UnifiedResponse(
            success=False,
            error=exc.detail
        ).model_dump()
    )
