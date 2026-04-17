"""
Router de Autenticación JWT — Multi-usuario con aprobación admin vía Discord
============================================================================
- Usuarios permitidos: admin + test1/2/3 (env vars)
- test users requieren aprobación explícita del admin antes de entrar
- Usuarios desconocidos son bloqueados y notificados a Discord
- Sesiones activas trackeadas en Prometheus
"""

import os
import sys
import time
import json
import logging
import threading
from collections import defaultdict
from threading import Lock
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel
from ..schemas import UnifiedResponse

logger = logging.getLogger("AntigravityAPI")
router = APIRouter(prefix="/api/auth", tags=["Auth"])

# ── Rate limiter ───────────────────────────────────────────────────────────────
_RL_WINDOW = 60
_RL_MAX_ATTEMPTS = 5
_RL_MAX_IPS = 10_000

_login_attempts: dict = defaultdict(list)
_rl_lock = Lock()

def _check_rate_limit(ip: str) -> bool:
    now = time.time()
    with _rl_lock:
        if ip not in _login_attempts and len(_login_attempts) >= _RL_MAX_IPS:
            return False
        recent = [t for t in _login_attempts[ip] if now - t < _RL_WINDOW]
        if not recent:
            del _login_attempts[ip]
            _login_attempts[ip].append(now)
            return True
        if len(recent) >= _RL_MAX_ATTEMPTS:
            _login_attempts[ip] = recent
            return False
        recent.append(now)
        _login_attempts[ip] = recent
        return True

# ── Configuración JWT ──────────────────────────────────────────────────────────
SECRET_KEY  = os.getenv("JWT_SECRET_KEY", "insecure-default-change-in-production")
ALGORITHM   = "HS256"
ACCESS_EXP  = int(os.getenv("JWT_ACCESS_EXPIRE_HOURS", "8"))
REFRESH_EXP = int(os.getenv("JWT_REFRESH_EXPIRE_DAYS", "7"))

# ── Usuarios permitidos ────────────────────────────────────────────────────────
ADMIN_USERNAME    = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD    = os.getenv("ADMIN_PASSWORD", "")
ADMIN_APPROVE_KEY = os.getenv("ADMIN_APPROVE_KEY", "")   # token secreto para /approve
DISCORD_WEBHOOK   = os.getenv("DISCORD_WEBHOOK_URL", "")
BACKEND_URL       = os.getenv("BACKEND_URL", "https://backend-production-8c5c4.up.railway.app")

ALLOWED_USERS: dict[str, str] = {
    ADMIN_USERNAME: ADMIN_PASSWORD,
    "test1": os.getenv("TEST1_PASSWORD", ""),
    "test2": os.getenv("TEST2_PASSWORD", ""),
    "test3": os.getenv("TEST3_PASSWORD", ""),
}
# Eliminar entradas sin contraseña configurada
ALLOWED_USERS = {k: v for k, v in ALLOWED_USERS.items() if v}

# ── Validación de arranque ─────────────────────────────────────────────────────
_MIN_JWT_LEN = 32

if len(SECRET_KEY) < _MIN_JWT_LEN:
    if os.getenv("ENVIRONMENT", "").lower() == "production":
        logger.critical("[AUTH] JWT_SECRET_KEY insegura en producción. Deteniendo.")
        sys.exit(1)
    else:
        logger.warning("[AUTH] JWT_SECRET_KEY débil — NO usar en producción.")

if not ADMIN_PASSWORD:
    logger.warning("[AUTH] ADMIN_PASSWORD no configurada.")

if not ADMIN_APPROVE_KEY:
    logger.warning("[AUTH] ADMIN_APPROVE_KEY no configurada — el endpoint /approve estará deshabilitado.")

# ── Estado en memoria ──────────────────────────────────────────────────────────
# {username: {"approved": bool, "requested_at": float, "ip": str}}
_pending_approvals: dict = {}
_approvals_lock = Lock()

# Usuarios aprobados al menos una vez — no requieren re-aprobación hasta restart
_approved_users: set = set()

# {username: {"login_at": float, "last_seen": float}}
_active_sessions: dict = {}
_sessions_lock = Lock()

bearer_scheme = HTTPBearer(auto_error=False)

# ── Discord ────────────────────────────────────────────────────────────────────
def _send_discord(message: str) -> None:
    if not DISCORD_WEBHOOK:
        logger.warning("[AUTH] DISCORD_WEBHOOK_URL no configurada — notificación omitida.")
        return
    def _post():
        try:
            import requests as _requests
            r = _requests.post(
                DISCORD_WEBHOOK,
                json={"content": message},
                timeout=10,
            )
            if r.status_code not in (200, 204):
                logger.warning(f"[AUTH] Discord respondió {r.status_code}: {r.text[:200]}")
            else:
                logger.info("[AUTH] Notificación Discord enviada OK.")
        except Exception as e:
            logger.warning(f"[AUTH] Discord notification failed: {e}")
    threading.Thread(target=_post, daemon=True).start()

# ── Session helpers ────────────────────────────────────────────────────────────
def _update_session_metrics():
    try:
        from core.metrics import users_active_total
        with _sessions_lock:
            count = len(_active_sessions)
        users_active_total.set(count)
    except Exception:
        pass

def _start_session(username: str) -> None:
    now = time.time()
    with _sessions_lock:
        _active_sessions[username] = {"login_at": now, "last_seen": now}
    try:
        from core.metrics import user_logins_total
        user_logins_total.labels(username=username).inc()
    except Exception:
        pass
    _update_session_metrics()
    _send_discord(
        f"🟢 **Sesión iniciada — FreshCart**\n"
        f"👤 Usuario: `{username}` · ⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

def _end_session(username: str) -> None:
    duration = 0.0
    with _sessions_lock:
        session = _active_sessions.pop(username, None)
        if session:
            duration = time.time() - session["login_at"]
    if duration > 0:
        try:
            from core.metrics import user_session_duration_seconds
            user_session_duration_seconds.observe(duration)
        except Exception:
            pass
    _update_session_metrics()
    mins = round(duration / 60, 1)
    _send_discord(
        f"🔴 **Sesión cerrada — FreshCart**\n"
        f"👤 Usuario: `{username}` · ⏱ Duración: `{mins} min` · ⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

def _touch_session(username: str) -> None:
    with _sessions_lock:
        if username in _active_sessions:
            _active_sessions[username]["last_seen"] = time.time()

# ── JWT helpers ────────────────────────────────────────────────────────────────
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

def _issue_tokens(username: str) -> dict:
    access_exp  = timedelta(hours=ACCESS_EXP)
    refresh_exp = timedelta(days=REFRESH_EXP)
    return {
        "access_token":  _create_token(username, "access",  access_exp),
        "refresh_token": _create_token(username, "refresh", refresh_exp),
        "token_type":    "bearer",
        "expires_in":    int(access_exp.total_seconds()),
    }

# ── Schemas ────────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str

# ── Endpoints ──────────────────────────────────────────────────────────────────
@router.post("/login")
def login(body: LoginRequest, request: Request):
    """
    Login multi-usuario con aprobación admin:
    - admin → acceso directo
    - test1/2/3 → requieren aprobación explícita del admin vía Discord
    - cualquier otro → bloqueado + alerta Discord
    """
    client_ip = request.client.host if request.client else "unknown"

    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Demasiados intentos. Intenta en un minuto.")

    username = body.username.strip().lower()

    # 1. Whitelist
    if username not in ALLOWED_USERS:
        logger.warning(f"[AUTH] Usuario no autorizado: '{username}' desde {client_ip}")
        _send_discord(
            f"🚨 **ALERTA DE SEGURIDAD — FreshCart**\n"
            f"Intento de acceso de usuario **no autorizado**\n"
            f"👤 `{body.username}` · 🌐 IP: `{client_ip}`\n"
            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        try:
            from core.metrics import api_blocked_requests_total
            api_blocked_requests_total.labels(reason="unknown_user").inc()
        except Exception:
            pass
        raise HTTPException(status_code=403, detail="Acceso denegado. Usuario no autorizado.")

    # 2. Credenciales
    if ALLOWED_USERS.get(username) != body.password:
        logger.warning(f"[AUTH] Contraseña incorrecta para: {username}")
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")

    # 3. Admin → token directo
    if username == ADMIN_USERNAME.lower():
        _start_session(username)
        logger.info(f"[AUTH] Login admin: {username}")
        return JSONResponse(content={"success": True, "data": _issue_tokens(username)})

    # 4. Test user → flujo de aprobación
    # Si ya fue aprobado antes en esta sesión del servidor, acceso directo
    if username in _approved_users:
        _start_session(username)
        logger.info(f"[AUTH] Login directo (ya aprobado): {username}")
        return JSONResponse(content={"success": True, "data": _issue_tokens(username)})

    with _approvals_lock:
        approval = _pending_approvals.get(username)

        if approval is None:
            # Primera solicitud: notificar al admin
            approve_url = f"{BACKEND_URL}/api/auth/approve/{username}?token={ADMIN_APPROVE_KEY}"
            _pending_approvals[username] = {
                "approved": False,
                "requested_at": time.time(),
                "ip": client_ip,
            }
            _send_discord(
                f"🔐 **Solicitud de acceso — FreshCart**\n"
                f"👤 Usuario: `{username}` · 🌐 IP: `{client_ip}`\n"
                f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"✅ **Aprobar acceso:**\n{approve_url}"
            )
            logger.info(f"[AUTH] Aprobación solicitada para: {username}")

        elif approval["approved"]:
            # Ya aprobado: guardar en set permanente y emitir tokens
            _pending_approvals.pop(username, None)
            _approved_users.add(username)
            _start_session(username)
            logger.info(f"[AUTH] Login exitoso (aprobado): {username}")
            return JSONResponse(content={"success": True, "data": _issue_tokens(username)})

    # Esperando aprobación
    return JSONResponse(
        status_code=202,
        content={
            "success": False,
            "status": "pending_approval",
            "detail": "Acceso pendiente de aprobación del administrador. Te avisaremos pronto.",
        },
    )


@router.get("/approve/{username}")
def approve_user(username: str, token: str = ""):
    """Admin aprueba un usuario pendiente. Se accede vía el enlace enviado a Discord."""
    if not ADMIN_APPROVE_KEY or token != ADMIN_APPROVE_KEY:
        raise HTTPException(status_code=403, detail="Token de aprobación inválido.")

    username = username.strip().lower()
    with _approvals_lock:
        if username not in _pending_approvals:
            return {"message": f"No hay solicitud pendiente para '{username}'."}
        _pending_approvals[username]["approved"] = True

    logger.info(f"[AUTH] Admin aprobó a: {username}")
    _send_discord(f"✅ Acceso **aprobado** para `{username}`. Ya puede iniciar sesión.")
    return {"message": f"Acceso aprobado para {username}. El usuario puede ingresar ahora."}


@router.get("/approval-status/{username}")
def approval_status(username: str):
    """Frontend polling: ¿fue aprobado ya el usuario?"""
    username = username.strip().lower()
    with _approvals_lock:
        approval = _pending_approvals.get(username)
    if approval is None:
        return {"approved": False, "pending": False}
    return {"approved": approval["approved"], "pending": not approval["approved"]}


@router.post("/logout", response_model=UnifiedResponse)
def logout_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    if credentials:
        try:
            payload = _decode_token(credentials.credentials)
            username = payload.get("sub")
            _end_session(username)
            logger.info(f"[AUTH] Logout: {username}")
        except Exception:
            pass
    return UnifiedResponse(data={"message": "Sesión cerrada."})


@router.post("/refresh", response_model=UnifiedResponse)
def refresh_access_token(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
):
    if not credentials:
        raise HTTPException(status_code=401, detail="Refresh token requerido.")
    payload = _decode_token(credentials.credentials)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Se requiere un refresh token.")
    username = payload.get("sub")
    _touch_session(username)
    access_exp = timedelta(hours=ACCESS_EXP)
    return UnifiedResponse(data={
        "access_token": _create_token(username, "access", access_exp),
        "token_type":   "bearer",
        "expires_in":   int(access_exp.total_seconds()),
    })


@router.get("/me", response_model=UnifiedResponse)
def get_me(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Token requerido.")
    payload = _decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Se requiere un access token.")
    username = payload.get("sub")
    _touch_session(username)
    return UnifiedResponse(data={"username": username, "authenticated": True})


@router.get("/sessions", response_model=UnifiedResponse)
def get_active_sessions(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    """Lista sesiones activas (solo admin)."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Token requerido.")
    payload = _decode_token(credentials.credentials)
    if payload.get("sub", "").lower() != ADMIN_USERNAME.lower():
        raise HTTPException(status_code=403, detail="Solo el admin puede ver sesiones.")
    now = time.time()
    with _sessions_lock:
        sessions = [
            {
                "username":         u,
                "login_at":         datetime.fromtimestamp(s["login_at"]).isoformat(),
                "last_seen":        datetime.fromtimestamp(s["last_seen"]).isoformat(),
                "duration_minutes": round((now - s["login_at"]) / 60, 1),
            }
            for u, s in _active_sessions.items()
        ]
    return UnifiedResponse(data={"sessions": sessions, "count": len(sessions)})
