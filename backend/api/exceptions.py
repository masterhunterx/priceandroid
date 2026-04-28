"""
Manejadores de Excepciones Globales
=====================================
Captura y normaliza todos los errores no controlados de la API.

Jerarquía de respuestas:
  SQLAlchemy OperationalError / DatabaseError  → 503 Service Unavailable
  SQLAlchemy IntegrityError                    → 409 Conflict
  SQLAlchemy SQLAlchemyError (genérico)        → 503 Service Unavailable
  Cualquier otra excepción no capturada        → 500 Internal Server Error
  HTTPException (FastAPI)                      → status_code del exc

En ningún caso se expone el traceback al cliente — solo se logea internamente.
"""
import logging
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from .schemas import UnifiedResponse
from core.telemetry import TelemetryService

# Importar sqlalchemy de forma lazy para no fallar si el driver no está instalado
try:
    from sqlalchemy.exc import (
        OperationalError as _SAOperationalError,
        DatabaseError as _SADatabaseError,
        IntegrityError as _SAIntegrityError,
        SQLAlchemyError as _SQLAlchemyError,
    )
    _SA_AVAILABLE = True
except ImportError:
    _SA_AVAILABLE = False

logger = logging.getLogger("FreshCartAPI")


def _sa_status_and_msg(exc: Exception) -> tuple[int, str]:
    """Mapea errores SQLAlchemy a (http_status, mensaje_cliente)."""
    if not _SA_AVAILABLE:
        return 503, "Servicio temporalmente no disponible."
    if isinstance(exc, _SAIntegrityError):
        return 409, "Conflicto de datos: la operación viola una restricción de integridad."
    if isinstance(exc, (_SAOperationalError, _SADatabaseError)):
        return 503, "Base de datos no disponible. Intenta en unos momentos."
    if isinstance(exc, _SQLAlchemyError):
        return 503, "Servicio temporalmente no disponible."
    return 500, "Error interno del servidor."


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Captura todas las excepciones no controladas.
    - Errores de BD → 503 con mensaje genérico
    - Cualquier otro → 500 con mensaje genérico
    El traceback completo queda en los logs internos, nunca llega al cliente.
    """
    endpoint = f"{request.method} {request.url.path}"

    is_db_error = _SA_AVAILABLE and isinstance(exc, _SQLAlchemyError)

    if is_db_error:
        status_code, client_msg = _sa_status_and_msg(exc)
        logger.error("[DB ERROR %s] %s — %s", status_code, endpoint, exc, exc_info=True)
    else:
        status_code, client_msg = 500, "Error interno del servidor."
        logger.error("[CRITICAL %s] %s — %s", status_code, endpoint, exc, exc_info=True)

    TelemetryService.capture_exception(exc, endpoint_context=endpoint)

    return JSONResponse(
        status_code=status_code,
        content=UnifiedResponse(success=False, error=client_msg).model_dump(),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Normaliza HTTPException al formato UnifiedResponse estándar."""
    return JSONResponse(
        status_code=exc.status_code,
        content=UnifiedResponse(success=False, error=exc.detail).model_dump(),
    )
