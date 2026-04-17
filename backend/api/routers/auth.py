"""
Router de Autenticación JWT
============================
Login con usuario/contraseña → access token (8h) + refresh token (30 días).
Usuario único configurado vía variables de entorno (ADMIN_USERNAME / ADMIN_PASSWORD).
"""

import os
import time
import logging
from collections import defaultdict
from threading import Lock
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel
from ..schemas import UnifiedResponse

# ── Rate limiter (in-memory): 3 intentos por minuto por IP ────────────────────
_RL_WINDOW = 60        # segundos
_RL_MAX_ATTEMPTS = 3   # intentos por ventana (reducido de 5 para mayor protección)
_RL_MAX_IPS = 10_000   # tamaño máximo del dict (protección contra DDoS con IPs rotativas)

_login_attempts: dict = defaultdict(list)
_rl_lock = Lock()

def _check_rate_limit(ip: str) -> bool:
    now = time.time()
    with _rl_lock:
        # Evitar que el dict crezca sin límite bajo rotación de IPs (DDoS con IPs únicas)
        if ip not in _login_attempts and len(_login_attempts) >= _RL_MAX_IPS:
            return False
        # Evictar entradas expiradas
        recent = [t for t in _login_attempts[ip] if now - t < _RL_WINDOW]
        if not recent:
            # Liberar la clave para no acumular IPs inactivas en memoria
            del _login_attempts[ip]
            _login_attempts[ip].append(now)
            return True
        if len(recent) >= _RL_MAX_ATTEMPTS:
            _login_attempts[ip] = recent  # guardar la versión purgada
            return False
        recent.append(now)
        _login_attempts[ip] = recent
        return True

logger = logging.getLogger("AntigravityAPI")
router = APIRouter(prefix="/api/auth", tags=["Auth"])

# ── Configuración ──────────────────────────────────────────────────────────────
SECRET_KEY  = os.getenv("JWT_SECRET_KEY", "insecure-default-change-in-production")
ALGORITHM   = "HS256"
ACCESS_EXP  = int(os.getenv("JWT_ACCESS_EXPIRE_HOURS", "8"))   # horas
REFRESH_EXP = int(os.getenv("JWT_REFRESH_EXPIRE_DAYS", "7"))   # días (reducido de 30 a 7)

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

# Validar fortaleza de contraseña al arrancar el servidor
def _validate_password_strength(pwd: str) -> bool:
    return (
        len(pwd) >= 12
        and any(c.isupper() for c in pwd)
        and any(c.isdigit() for c in pwd)
        and any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in pwd)
    )

import sys

_MIN_JWT_SECRET_LEN = 32

if ADMIN_PASSWORD and not _validate_password_strength(ADMIN_PASSWORD):
    logger.warning(
        "[AUTH] ADMIN_PASSWORD no cumple los requisitos mínimos: "
        "12+ caracteres, mayúscula, número y símbolo especial."
    )

if SECRET_KEY == "insecure-default-change-in-production" or len(SECRET_KEY) < _MIN_JWT_SECRET_LEN:
    if os.getenv("ENVIRONMENT", "").lower() == "production":
        logger.critical("[AUTH] JWT_SECRET_KEY insegura en producción. Deteniendo servidor.")
        sys.exit(1)
    else:
        logger.warning("[AUTH] JWT_SECRET_KEY débil o por defecto — NO usar en producción.")

bearer_scheme = HTTPBearer(auto_error=False)

# ── Schemas ────────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str

class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # segundos

# ── Helpers ────────────────────────────────────────────────────────────────────
def _create_token(sub: str, token_type: str, expires: timedelta) -> str:
    payload = {
        "sub": sub,
        "type": token_type,
        "exp": datetime.now(timezone.utc) + expires,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido o expirado.")


def verify_credentials(username: str, password: str) -> bool:
    """Verifica usuario y contraseña contra las env vars."""
    return username == ADMIN_USERNAME and password == ADMIN_PASSWORD


# ── Endpoints ──────────────────────────────────────────────────────────────────
@router.post("/login", response_model=UnifiedResponse)
def login(body: LoginRequest, request: Request):
    """Retorna access_token + refresh_token si las credenciales son correctas."""
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Demasiados intentos. Intenta en un minuto.")

    if not ADMIN_PASSWORD:
        logger.error("[AUTH] ADMIN_PASSWORD no está configurado en las variables de entorno.")
        raise HTTPException(status_code=500, detail="Servidor mal configurado: credenciales no definidas.")

    if not verify_credentials(body.username, body.password):
        logger.warning(f"[AUTH] Intento de login fallido para usuario: {body.username}")
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")

    access_exp = timedelta(hours=ACCESS_EXP)
    refresh_exp = timedelta(days=REFRESH_EXP)

    access_token  = _create_token(body.username, "access",  access_exp)
    refresh_token = _create_token(body.username, "refresh", refresh_exp)

    logger.info(f"[AUTH] Login exitoso: {body.username}")
    return UnifiedResponse(data=TokenOut(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=int(access_exp.total_seconds()),
    ))


@router.post("/refresh", response_model=UnifiedResponse)
def refresh_access_token(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
):
    """Renueva el access_token usando un refresh_token válido."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Refresh token requerido.")

    payload = _decode_token(credentials.credentials)

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Se requiere un refresh token, no un access token.")

    username = payload.get("sub")
    access_exp = timedelta(hours=ACCESS_EXP)
    new_token  = _create_token(username, "access", access_exp)

    return UnifiedResponse(data={
        "access_token": new_token,
        "token_type": "bearer",
        "expires_in": int(access_exp.total_seconds()),
    })


@router.get("/me", response_model=UnifiedResponse)
def get_me(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    """Retorna información del usuario autenticado."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Token requerido.")

    payload = _decode_token(credentials.credentials)

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Se requiere un access token.")

    return UnifiedResponse(data={
        "username": payload.get("sub"),
        "authenticated": True,
    })
