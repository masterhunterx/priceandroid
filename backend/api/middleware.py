import os
import logging
from fastapi import Request, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import JSONResponse
from core.shield import Shield3

logger = logging.getLogger("AntigravityAPI")

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


_JWT_SECRET = os.environ.get("JWT_SECRET_KEY", "insecure-default-change-in-production")
if _JWT_SECRET == "insecure-default-change-in-production":
    logger.warning("[SECURITY] JWT_SECRET_KEY no está configurada. Usando clave insegura por defecto — NO apta para producción.")

def _verify_jwt(token: str) -> str:
    """
    Valida un JWT Bearer token y retorna el 'sub' (username).
    Lanza HTTPException 401 si el token es inválido, expirado o revocado.
    """
    import jwt
    from jwt.exceptions import InvalidTokenError
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=["HS256"])
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido o expirado.")

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Se requiere un access token.")

    # Verificar blacklist de tokens revocados (logout)
    try:
        from api.routers.auth import _is_token_revoked
        if _is_token_revoked(payload):
            raise HTTPException(status_code=401, detail="Token inválido o expirado.")
    except ImportError:
        pass

    return payload.get("sub")


async def get_api_key(request: Request, api_key: str = Security(api_key_header)):
    """
    Valida credenciales en el siguiente orden de prioridad:
    1. JWT Bearer token (Authorization: Bearer <token>)
    2. API Key estática (X-API-Key) — compatibilidad con herramientas/CLI
    """
    # Permitir siempre las pre-flight requests de CORS
    if request.method == "OPTIONS":
        return None

    # 1. Intentar JWT Bearer token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        return _verify_jwt(token)

    # 2. Fallback: API Key estática
    expected_key = os.environ.get("API_KEY")
    if not expected_key:
        logger.error("[SECURITY] API_KEY no está configurada en las variables de entorno.")
        raise HTTPException(status_code=500, detail="Error de configuración del servidor.")

    if api_key != expected_key:
        client_ip = request.client.host if request.client else "unknown"
        logger.warning(f"[SECURITY] API Key incorrecta desde IP: {client_ip}")
        raise HTTPException(status_code=403, detail="Credenciales inválidas.")

    return api_key


def _is_private_ip(ip: str) -> bool:
    """Devuelve True si la IP es privada, loopback o link-local."""
    import ipaddress
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_private or addr.is_loopback or addr.is_link_local
    except ValueError:
        return False


def _get_real_ip(request: Request) -> str:
    """
    Extrae la IP real del cliente.
    Acepta X-Forwarded-For solo si el primer IP es público (no spoofeable con 127.0.0.1).
    """
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        first_ip = xff.split(",")[0].strip().replace("::ffff:", "")
        if first_ip and not _is_private_ip(first_ip):
            return first_ip
    x_real = request.headers.get("X-Real-IP", "")
    if x_real:
        candidate = x_real.strip().replace("::ffff:", "")
        if candidate and not _is_private_ip(candidate):
            return candidate
    ip = request.client.host if request.client else "unknown"
    return ip.replace("::ffff:", "")


async def shield_security_middleware(request: Request, call_next):
    """Middleware de defensa activa: rate limiting, bloqueo de IPs y WAF."""
    # /metrics es consumido exclusivamente por Grafana Cloud — bypass del shield
    if request.url.path.startswith("/metrics"):
        return await call_next(request)

    ip = _get_real_ip(request)

    # 1. Blacklist Check
    if Shield3.is_ip_blocked(ip):
        logger.warning(f"[SHIELD] Request bloqueada para IP en lista negra: {ip}")
        return JSONResponse(
            status_code=403,
            content={"success": False, "error": "SECURITY BLOCK: IP bloqueada por FluxEngine Shield."}
        )

    # 2. WAF — detección de amenazas en User-Agent
    if request.method != "OPTIONS":
        is_threat, threat_reason = Shield3.analyze_waf_threat(dict(request.headers))
        if is_threat:
            logger.warning(f"[WAF] Amenaza detectada desde {ip}: {threat_reason}")
            Shield3.log_event(ip, "WAF_BLOCK", "WARNING", threat_reason)
            return JSONResponse(
                status_code=403,
                content={"success": False, "error": "SECURITY BLOCK: Request bloqueada por FluxEngine WAF."}
            )

    # 3. Rate Limiting dinámico
    is_stress_mode = os.environ.get("STRESS_TEST_MODE", "false").lower() == "true"
    normalized_ip = ip

    if normalized_ip not in ["127.0.0.1", "localhost", "::1"] and not is_stress_mode:
        allowed, count = Shield3.track_request(ip, limit=20, window=10)
        if not allowed:
            logger.warning(f"[RATE_LIMIT] Bloqueando IP {normalized_ip} — {count} requests en 10s")
            return JSONResponse(
                status_code=429,
                content={"success": False, "error": f"RATE LIMIT: {count} requests en 10s. Espera un momento."}
            )

    response = await call_next(request)
    return response
