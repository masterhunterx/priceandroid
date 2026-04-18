import os
import time
import logging
import threading
from fastapi import Request, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import JSONResponse
from core.shield import Shield3

logger = logging.getLogger("AntigravityAPI")

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# ── API Key brute-force protection ─────────────────────────────────────────────
# Bloquea IPs que envíen demasiadas API keys incorrectas
_APIKEY_FAIL_MAX    = 10    # intentos fallidos máximos
_APIKEY_FAIL_WINDOW = 3600  # ventana de 1 hora
_apikey_failures: dict[str, list] = {}
_apikey_lock = threading.Lock()

def _register_apikey_failure(ip: str) -> bool:
    """Registra un fallo de API key. Retorna True si la IP debe bloquearse."""
    now = time.time()
    with _apikey_lock:
        recent = [t for t in _apikey_failures.get(ip, []) if now - t < _APIKEY_FAIL_WINDOW]
        recent.append(now)
        _apikey_failures[ip] = recent
        return len(recent) >= _APIKEY_FAIL_MAX


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
        client_ip = _get_real_ip(request)
        logger.warning(f"[SECURITY] API Key incorrecta desde IP: {client_ip}")
        if _register_apikey_failure(client_ip):
            Shield3.block_ip(client_ip, reason="Brute force: demasiadas API keys incorrectas")
            logger.critical(f"[SECURITY] IP {client_ip} bloqueada por brute force de API key")
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


_METRICS_TOKEN = os.environ.get("METRICS_TOKEN", "")

# Límites por path — más estrictos en endpoints costosos
_PATH_RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/api/products/search": (30, 60),   # 30 req/min
    "/api/assistant":       (10, 60),   # 10 req/min
}

async def shield_security_middleware(request: Request, call_next):
    """Middleware de defensa activa: rate limiting, bloqueo de IPs y WAF."""
    path = request.url.path

    # /metrics — solo accesible si METRICS_TOKEN no está configurado o el token coincide
    if path.startswith("/metrics"):
        if _METRICS_TOKEN:
            token = request.headers.get("X-Metrics-Token", "")
            if token != _METRICS_TOKEN:
                return JSONResponse(status_code=403, content={"error": "Forbidden"})
        return await call_next(request)

    ip = _get_real_ip(request)

    # 1. Blacklist Check
    if Shield3.is_ip_blocked(ip):
        logger.warning(f"[SHIELD] Request bloqueada para IP en lista negra: {ip}")
        return JSONResponse(
            status_code=403,
            content={"success": False, "error": "SECURITY BLOCK: IP bloqueada por FluxEngine Shield."}
        )

    # 2. WAF — cabeceras + URL path + query string
    if request.method != "OPTIONS":
        qs = str(request.url.query)
        is_threat, threat_reason = Shield3.analyze_waf_threat(
            dict(request.headers), url_path=path, query_string=qs
        )
        if is_threat:
            logger.warning(f"[WAF] Amenaza detectada desde {ip}: {threat_reason}")
            Shield3.log_event(ip, "WAF_BLOCK", "WARNING", threat_reason)
            return JSONResponse(
                status_code=403,
                content={"success": False, "error": "SECURITY BLOCK: Request bloqueada por FluxEngine WAF."}
            )

    # 3. Rate Limiting — global + por path
    is_stress_mode = os.environ.get("STRESS_TEST_MODE", "false").lower() == "true"

    if ip not in ("127.0.0.1", "localhost", "::1") and not is_stress_mode:
        # 3a. Límite global
        allowed, count = Shield3.track_request(ip, limit=20, window=10)
        if not allowed:
            logger.warning(f"[RATE_LIMIT] IP {ip} — {count} req en 10s (global)")
            return JSONResponse(
                status_code=429,
                content={"success": False, "error": f"RATE LIMIT: {count} requests en 10s. Espera un momento."}
            )
        # 3b. Límites por endpoint específico
        for prefix, (limit, window) in _PATH_RATE_LIMITS.items():
            if path.startswith(prefix):
                allowed2, count2 = Shield3.track_request(f"{ip}:{prefix}", limit=limit, window=window)
                if not allowed2:
                    logger.warning(f"[RATE_LIMIT] IP {ip} — {count2} req en {window}s en {prefix}")
                    return JSONResponse(
                        status_code=429,
                        content={"success": False, "error": f"RATE LIMIT: Demasiadas requests a {prefix}. Espera un momento."}
                    )

    response = await call_next(request)
    return response
