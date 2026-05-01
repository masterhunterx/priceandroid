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
import uuid
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
from pydantic import BaseModel, EmailStr
from ..schemas import UnifiedResponse

# H1 — Pre-computar hash dummy para normalizar timing en usuarios inexistentes.
# bcrypt checkpw tarda ~80-150ms; sin esto, usuarios inexistentes responden en <1ms
# lo que permite enumeración de usernames por timing side-channel.
try:
    import bcrypt as _bcrypt
    _DUMMY_HASH: bytes = _bcrypt.hashpw(b"freshcart_dummy_timing_normalizer", _bcrypt.gensalt(rounds=12))
    _BCRYPT_AVAILABLE = True
except ImportError:
    _DUMMY_HASH = b""
    _BCRYPT_AVAILABLE = False

def _check_password(plain: str, stored: str) -> bool:
    """Compara contraseña. Si stored empieza con $2b/$2a/$2y usa bcrypt, si no texto plano."""
    if stored.startswith(("$2b$", "$2a$", "$2y$")):
        try:
            import bcrypt
            return bcrypt.checkpw(plain.encode(), stored.encode())
        except Exception:
            return False
    import hmac
    return hmac.compare_digest(plain, stored)

logger = logging.getLogger("FreshCartAPI")
router = APIRouter(prefix="/api/auth", tags=["Auth"])

# ── Rate limiter ───────────────────────────────────────────────────────────────
_RL_WINDOW = 60
_RL_MAX_ATTEMPTS = 5
_RL_MAX_IPS = 10_000
_RL_CLEANUP_THRESHOLD = int(_RL_MAX_IPS * 0.90)  # limpiar al 90% de capacidad

_login_attempts: dict = defaultdict(list)
_rl_lock = Lock()

_enum_attempts: dict = defaultdict(list)
_enum_lock = Lock()

def _check_enum_limit(ip: str) -> bool:
    """20 checks/min por IP para /approval-status — previene enumeración masiva."""
    now = time.time()
    with _enum_lock:
        recent = [t for t in _enum_attempts[ip] if now - t < _RL_WINDOW]
        if len(recent) >= 20:
            _enum_attempts[ip] = recent
            return False
        recent.append(now)
        _enum_attempts[ip] = recent
        return True


def _cleanup_stale_ips_unsafe() -> None:
    """Elimina IPs sin actividad reciente. DEBE llamarse con _rl_lock ya adquirido."""
    now = time.time()
    stale = [ip for ip, ts_list in _login_attempts.items()
             if not any(now - t < _RL_WINDOW for t in ts_list)]
    for ip in stale:
        del _login_attempts[ip]


def _check_rate_limit(ip: str) -> bool:
    now = time.time()
    with _rl_lock:
        # H3 — Cleanup oportunístico al acercarse al límite de capacidad.
        # Sin esto, 10K IPs únicas bloquean indefinidamente a nuevas IPs legítimas.
        if len(_login_attempts) >= _RL_CLEANUP_THRESHOLD:
            _cleanup_stale_ips_unsafe()

        if ip not in _login_attempts and len(_login_attempts) >= _RL_MAX_IPS:
            return False

        recent = [t for t in _login_attempts[ip] if now - t < _RL_WINDOW]
        if not recent:
            _login_attempts.pop(ip, None)
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
BACKEND_URL       = os.getenv("BACKEND_URL", "")
FRONTEND_URL      = os.getenv("FRONTEND_URL", "http://localhost:5001")
GOOGLE_CLIENT_ID  = os.getenv("GOOGLE_CLIENT_ID", "")
GMAIL_USER        = os.getenv("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

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
# {username: {"approved": bool, "requested_at": float, "ip": str, "token": str}}
_pending_approvals: dict = {}
# {token: {"username": str, "expires_at": float}}
_reset_tokens: dict[str, dict] = {}
_reset_lock = Lock()
_approvals_lock = Lock()
# M5 — TTL para solicitudes de aprobación: 1 hora.
# Sin TTL las entradas se acumulan indefinidamente en memoria.
_APPROVAL_TTL_SECONDS = 3600


def _get_approval_if_valid(username: str) -> dict | None:
    """Retorna la aprobación pendiente solo si no expiró. Elimina si venció."""
    now = time.time()
    approval = _pending_approvals.get(username)
    if approval and (now - approval["requested_at"]) > _APPROVAL_TTL_SECONDS:
        del _pending_approvals[username]
        return None
    return approval

# H2 — JWT revocation usando dict {(sub, iat): exp_unix_float} en lugar de set.
# El set original crecía sin límite: nunca se limpiaba aunque los tokens expiraran.
# Con el dict, cada entrada lleva su propio timestamp de expiración y se limpia
# oportunísticamente en cada consulta de _is_token_revoked.
_revoked_tokens: dict[tuple, float] = {}
_revoked_lock = Lock()
# Cap duro: un atacante que llame /logout repetidamente no puede agotar la RAM.
# ACCESS_EXP=8h → máximo 10_000 tokens revocados simultáneamente en ventana de 8h.
_RL_MAX_REVOKED = 10_000


def _revoke_token(payload: dict) -> None:
    sub = payload.get("sub", "")
    iat = payload.get("iat", 0)
    exp = payload.get("exp", time.time() + ACCESS_EXP * 3600)
    # PyJWT puede decodificar 'exp' como int o datetime según versión
    if hasattr(exp, "timestamp"):
        exp = exp.timestamp()
    with _revoked_lock:
        if len(_revoked_tokens) >= _RL_MAX_REVOKED:
            now = time.time()
            # Primero limpiar expirados (sin costo de escritura en BD)
            expired = [k for k, e in _revoked_tokens.items() if e < now]
            for k in expired:
                del _revoked_tokens[k]
            # Si sigue lleno, eliminar los que expiran antes (menos valiosos)
            if len(_revoked_tokens) >= _RL_MAX_REVOKED:
                soonest = sorted(_revoked_tokens.items(), key=lambda x: x[1])
                for k, _ in soonest[: len(_revoked_tokens) - _RL_MAX_REVOKED + 1]:
                    del _revoked_tokens[k]
        _revoked_tokens[(sub, iat)] = float(exp)


def _is_token_revoked(payload: dict) -> bool:
    sub = payload.get("sub", "")
    iat = payload.get("iat", 0)
    now = time.time()
    with _revoked_lock:
        # Cleanup oportunístico: eliminar entradas cuyo token ya expiró por tiempo
        expired = [k for k, exp in _revoked_tokens.items() if exp < now]
        for k in expired:
            del _revoked_tokens[k]
        return (sub, iat) in _revoked_tokens

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

# ── DB helpers ─────────────────────────────────────────────────────────────────
def _get_user_from_db(username: str):
    """Busca usuario en BD. Retorna el objeto User o None."""
    try:
        from core.db import get_session
        from core.models import User
        with get_session() as db:
            user = db.query(User).filter(User.username == username.lower()).first()
            if user:
                db.expunge(user)
            return user
    except Exception as e:
        logger.warning(f"[AUTH] Error consultando BD: {e}")
        return None

def _hash_password(plain: str) -> str:
    if _BCRYPT_AVAILABLE:
        import bcrypt
        return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=12)).decode()
    import hashlib, secrets
    salt = secrets.token_hex(16)
    return f"sha256:{salt}:{hashlib.sha256((salt + plain).encode()).hexdigest()}"

def _update_last_login(username: str) -> None:
    try:
        from core.db import get_session
        from core.models import User
        with get_session() as db:
            user = db.query(User).filter(User.username == username.lower()).first()
            if user:
                user.last_login_at = datetime.now(UTC)
    except Exception as e:
        logger.warning(f"[AUTH] No se pudo actualizar last_login: {e}")

# ── Schemas ────────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str | None = None

class ProfileUpdateRequest(BaseModel):
    selected_store: str | None = None
    selected_branch: str | None = None
    email: str | None = None

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class GoogleLoginRequest(BaseModel):
    credential: str  # Google ID token

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

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

    # 1. Buscar usuario: primero en BD, luego fallback a whitelist en memoria.
    # H1 — Timing normalization: siempre ejecutamos _check_password (o dummy bcrypt)
    # para evitar enumeración por timing side-channel.
    db_user = _get_user_from_db(username)
    stored_pw = ""
    user_exists = False
    is_db_user = False

    if db_user:
        stored_pw = db_user.password_hash
        user_exists = True
        is_db_user = True
    elif username in ALLOWED_USERS:
        stored_pw = ALLOWED_USERS[username]
        user_exists = True

    if not user_exists and _BCRYPT_AVAILABLE:
        _bcrypt.checkpw(body.password.encode(), _DUMMY_HASH)  # normaliza latencia
    credentials_ok = user_exists and _check_password(body.password, stored_pw)

    if not user_exists:
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

    if not credentials_ok:
        logger.warning(f"[AUTH] Credenciales inválidas para: '{username}' desde {client_ip}")
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")

    # 2. Usuario en BD: verificar activo y aprobado
    if is_db_user:
        if not db_user.is_active:
            raise HTTPException(status_code=403, detail="Cuenta desactivada.")
        if not db_user.is_approved and db_user.role != "admin":
            raise HTTPException(status_code=202, detail="Cuenta pendiente de aprobación.")
        _update_last_login(username)
        _start_session(username)
        logger.info(f"[AUTH] Login BD: {username} (role={db_user.role})")
        tokens = _issue_tokens(username)
        tokens["role"] = db_user.role
        tokens["selected_store"] = db_user.selected_store
        tokens["selected_branch"] = db_user.selected_branch
        return JSONResponse(content={"success": True, "data": tokens})

    # 3. Admin desde env → token directo
    if username == ADMIN_USERNAME.lower():
        _start_session(username)
        logger.info(f"[AUTH] Login admin (env): {username}")
        return JSONResponse(content={"success": True, "data": _issue_tokens(username)})

    # 4. Test user → flujo de aprobación
    if username in _approved_users:
        _start_session(username)
        logger.info(f"[AUTH] Login directo (ya aprobado): {username}")
        return JSONResponse(content={"success": True, "data": _issue_tokens(username)})

    with _approvals_lock:
        approval = _get_approval_if_valid(username)

        if approval is None:
            # Token único por solicitud — no expone el ADMIN_APPROVE_KEY permanente
            one_time_token = str(uuid.uuid4())
            approve_url = f"{BACKEND_URL}/api/auth/approve/{username}?token={one_time_token}"
            _pending_approvals[username] = {
                "approved": False,
                "requested_at": time.time(),
                "ip": client_ip,
                "token": one_time_token,
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
    """Admin aprueba un usuario pendiente. Usa token único por solicitud (enviado a Discord)."""
    username = username.strip().lower()
    with _approvals_lock:
        pending = _get_approval_if_valid(username)
        if not pending:
            raise HTTPException(status_code=404, detail=f"No hay solicitud pendiente para '{username}'.")
        # Acepta el token único de la solicitud O el ADMIN_APPROVE_KEY como fallback de emergencia
        one_time = pending.get("token", "")
        is_valid = (one_time and token == one_time) or (ADMIN_APPROVE_KEY and token == ADMIN_APPROVE_KEY)
        if not is_valid:
            raise HTTPException(status_code=403, detail="Token de aprobación inválido.")
        _pending_approvals[username]["approved"] = True
        # Invalidar el token único tras usarlo
        _pending_approvals[username]["token"] = ""

    logger.info(f"[AUTH] Admin aprobó a: {username}")
    _send_discord(f"✅ Acceso **aprobado** para `{username}`. Ya puede iniciar sesión.")
    return {"message": f"Acceso aprobado para {username}. El usuario puede ingresar ahora."}


@router.get("/approval-status/{username}")
def approval_status(username: str, request: Request):
    """Frontend polling: ¿fue aprobado ya el usuario?"""
    from api.middleware import _get_real_ip
    client_ip = _get_real_ip(request)
    if not _check_enum_limit(client_ip):
        raise HTTPException(status_code=429, detail="Demasiadas solicitudes. Intenta más tarde.")
    username = username.strip().lower()
    with _approvals_lock:
        approval = _get_approval_if_valid(username)
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
            _revoke_token(payload)  # invalida el token en servidor
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
    if _is_token_revoked(payload):
        raise HTTPException(status_code=401, detail="Token revocado.")
    username = payload.get("sub")
    _revoke_token(payload)  # rotación: cada refresh token solo se usa una vez
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
    if _is_token_revoked(payload):
        raise HTTPException(status_code=401, detail="Token revocado.")
    username = payload.get("sub")
    _touch_session(username)

    profile: dict = {"username": username, "authenticated": True, "role": "user"}
    db_user = _get_user_from_db(username)
    if db_user:
        profile.update({
            "role":            db_user.role,
            "email":           db_user.email,
            "selected_store":  db_user.selected_store,
            "selected_branch": db_user.selected_branch,
            "created_at":      db_user.created_at.isoformat() if db_user.created_at else None,
            "last_login_at":   db_user.last_login_at.isoformat() if db_user.last_login_at else None,
        })
    elif username == ADMIN_USERNAME.lower():
        profile["role"] = "admin"

    return UnifiedResponse(data=profile)


@router.patch("/profile", response_model=UnifiedResponse)
def update_profile(body: ProfileUpdateRequest,
                   credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    """Actualiza preferencias del usuario (tienda, sucursal, email)."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Token requerido.")
    payload = _decode_token(credentials.credentials)
    if _is_token_revoked(payload):
        raise HTTPException(status_code=401, detail="Token revocado.")
    username = payload.get("sub")

    try:
        from core.db import get_session
        from core.models import User
        with get_session() as db:
            user = db.query(User).filter(User.username == username).first()
            if not user:
                raise HTTPException(status_code=404, detail="Usuario no encontrado en BD.")
            if body.selected_store is not None:
                user.selected_store = body.selected_store
            if body.selected_branch is not None:
                user.selected_branch = body.selected_branch
            if body.email is not None:
                user.email = body.email
        _touch_session(username)
        return UnifiedResponse(data={"message": "Perfil actualizado."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[AUTH] Error actualizando perfil de {username}: {e}")
        raise HTTPException(status_code=500, detail="Error al actualizar perfil.")


@router.post("/register", response_model=UnifiedResponse)
def register(body: RegisterRequest, request: Request):
    """Registra un nuevo usuario. Requiere aprobación de admin antes de poder ingresar."""
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Demasiados intentos.")

    username = body.username.strip().lower()
    if len(username) < 3 or len(username) > 30:
        raise HTTPException(status_code=400, detail="Username debe tener entre 3 y 30 caracteres.")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 8 caracteres.")

    try:
        from core.db import get_session
        from core.models import User
        from sqlalchemy.exc import IntegrityError
        with get_session() as db:
            if db.query(User).filter(User.username == username).first():
                raise HTTPException(status_code=409, detail="El usuario ya existe.")
            new_user = User(
                username=username,
                email=body.email,
                password_hash=_hash_password(body.password),
                role="user",
                is_active=True,
                is_approved=False,
            )
            db.add(new_user)

        one_time_token = str(uuid.uuid4())
        approve_url = f"{BACKEND_URL}/api/auth/approve/{username}?token={one_time_token}"
        with _approvals_lock:
            _pending_approvals[username] = {
                "approved": False,
                "requested_at": time.time(),
                "ip": client_ip,
                "token": one_time_token,
            }
        _send_discord(
            f"🆕 **Nuevo registro — FreshCart**\n"
            f"👤 Usuario: `{username}` · 📧 `{body.email or 'sin email'}` · 🌐 `{client_ip}`\n"
            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"✅ **Aprobar acceso:**\n{approve_url}"
        )
        logger.info(f"[AUTH] Nuevo registro: {username} desde {client_ip}")
        return UnifiedResponse(data={"message": "Registro exitoso. Esperando aprobación del administrador."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[AUTH] Error en registro: {e}")
        raise HTTPException(status_code=500, detail="Error al registrar usuario.")


@router.post("/change-password", response_model=UnifiedResponse)
def change_password(body: ChangePasswordRequest,
                    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    """Cambia la contraseña del usuario autenticado."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Token requerido.")
    payload = _decode_token(credentials.credentials)
    if _is_token_revoked(payload):
        raise HTTPException(status_code=401, detail="Token revocado.")
    username = payload.get("sub")

    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="La nueva contraseña debe tener al menos 8 caracteres.")

    try:
        from core.db import get_session
        from core.models import User
        with get_session() as db:
            user = db.query(User).filter(User.username == username).first()
            if not user:
                raise HTTPException(status_code=404, detail="Usuario no encontrado.")
            if not _check_password(body.current_password, user.password_hash):
                raise HTTPException(status_code=401, detail="Contraseña actual incorrecta.")
            user.password_hash = _hash_password(body.new_password)
        logger.info(f"[AUTH] Cambio de contraseña: {username}")
        return UnifiedResponse(data={"message": "Contraseña actualizada correctamente."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[AUTH] Error cambiando contraseña: {e}")
        raise HTTPException(status_code=500, detail="Error al cambiar contraseña.")


@router.get("/users", response_model=UnifiedResponse)
def list_users(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    """Lista todos los usuarios registrados (solo admin)."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Token requerido.")
    payload = _decode_token(credentials.credentials)
    if payload.get("sub", "").lower() != ADMIN_USERNAME.lower():
        raise HTTPException(status_code=403, detail="Solo el admin puede listar usuarios.")

    try:
        from core.db import get_session
        from core.models import User
        with get_session() as db:
            users = db.query(User).order_by(User.created_at.desc()).all()
            return UnifiedResponse(data={
                "users": [
                    {
                        "id":             u.id,
                        "username":       u.username,
                        "email":          u.email,
                        "role":           u.role,
                        "is_active":      u.is_active,
                        "is_approved":    u.is_approved,
                        "selected_store": u.selected_store,
                        "created_at":     u.created_at.isoformat() if u.created_at else None,
                        "last_login_at":  u.last_login_at.isoformat() if u.last_login_at else None,
                    }
                    for u in users
                ],
                "total": len(users),
            })
    except Exception as e:
        logger.error(f"[AUTH] Error listando usuarios: {e}")
        raise HTTPException(status_code=500, detail="Error al listar usuarios.")


@router.patch("/users/{username}/approve", response_model=UnifiedResponse)
def approve_user_db(username: str,
                    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    """Aprueba o desactiva un usuario en la BD (solo admin)."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Token requerido.")
    payload = _decode_token(credentials.credentials)
    if payload.get("sub", "").lower() != ADMIN_USERNAME.lower():
        raise HTTPException(status_code=403, detail="Solo el admin puede aprobar usuarios.")

    try:
        from core.db import get_session
        from core.models import User
        with get_session() as db:
            user = db.query(User).filter(User.username == username.lower()).first()
            if not user:
                raise HTTPException(status_code=404, detail="Usuario no encontrado.")
            user.is_approved = True
            _approved_users.add(username.lower())
        return UnifiedResponse(data={"message": f"Usuario '{username}' aprobado."})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error al aprobar usuario.")


def _send_reset_email(to_email: str, username: str, token: str) -> None:
    """Envía email de recuperación via Gmail SMTP en hilo separado."""
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        logger.warning("[AUTH] GMAIL_USER/GMAIL_APP_PASSWORD no configurados — email omitido")
        return
    reset_url = f"{FRONTEND_URL}/login?reset_token={token}"
    body = (
        f"Hola {username},\n\n"
        f"Recibimos una solicitud para restablecer la contraseña de tu cuenta FreshCart.\n\n"
        f"Haz clic en el siguiente enlace (válido por 15 minutos):\n{reset_url}\n\n"
        f"Si no solicitaste esto, ignora este mensaje.\n\n— Equipo FreshCart"
    )
    def _send():
        import smtplib
        from email.mime.text import MIMEText
        try:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = "FreshCart — Recuperación de contraseña"
            msg["From"] = GMAIL_USER
            msg["To"] = to_email
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
                smtp.sendmail(GMAIL_USER, to_email, msg.as_string())
            logger.info(f"[AUTH] Email de recuperación enviado a {to_email}")
        except Exception as e:
            logger.warning(f"[AUTH] Error enviando email: {e}")
    threading.Thread(target=_send, daemon=True).start()


@router.post("/forgot-password", response_model=UnifiedResponse)
def forgot_password(body: ForgotPasswordRequest, request: Request):
    """Genera token de recuperación y lo envía al email. Siempre responde 200 (anti-enumeración)."""
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Demasiados intentos.")
    email = body.email.strip().lower()
    try:
        from core.db import get_session
        from core.models import User
        with get_session() as db:
            user = db.query(User).filter(User.email == email).first()
            if user and user.is_active:
                token = str(uuid.uuid4())
                expires = time.time() + 900  # 15 min
                with _reset_lock:
                    _reset_tokens[token] = {"username": user.username, "expires_at": expires}
                _send_reset_email(email, user.username, token)
    except Exception as e:
        logger.error(f"[AUTH] Error en forgot-password: {e}")
    return UnifiedResponse(data={"message": "Si el correo existe, recibirás un enlace de recuperación en los próximos minutos."})


@router.post("/reset-password", response_model=UnifiedResponse)
def reset_password(body: ResetPasswordRequest):
    """Valida token de recuperación y actualiza la contraseña."""
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 8 caracteres.")
    with _reset_lock:
        entry = _reset_tokens.get(body.token)
        if not entry or time.time() > entry["expires_at"]:
            _reset_tokens.pop(body.token, None)
            raise HTTPException(status_code=400, detail="Enlace inválido o expirado. Solicita uno nuevo.")
        username = entry["username"]
        del _reset_tokens[body.token]
    try:
        from core.db import get_session
        from core.models import User
        with get_session() as db:
            user = db.query(User).filter(User.username == username).first()
            if not user:
                raise HTTPException(status_code=404, detail="Usuario no encontrado.")
            user.password_hash = _hash_password(body.new_password)
        logger.info(f"[AUTH] Contraseña reseteada: {username}")
        return UnifiedResponse(data={"message": "Contraseña actualizada. Ya puedes iniciar sesión."})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[AUTH] Error en reset-password: {e}")
        raise HTTPException(status_code=500, detail="Error al actualizar contraseña.")


@router.post("/google", response_model=UnifiedResponse)
def google_login(body: GoogleLoginRequest, request: Request):
    """Login con Google OAuth. Verifica ID token y emite JWT propio."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google OAuth no configurado en el servidor.")
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Demasiados intentos.")
    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests
        # Acepta tokens del cliente web original y del cliente Firebase (móvil nativo)
        _firebase_web_client = os.getenv("FIREBASE_WEB_CLIENT_ID", "")
        _client_ids = [cid for cid in [GOOGLE_CLIENT_ID, _firebase_web_client] if cid]
        idinfo = None
        last_exc = None
        for cid in _client_ids:
            try:
                idinfo = id_token.verify_oauth2_token(body.credential, google_requests.Request(), cid)
                break
            except Exception as e:
                last_exc = e
        if idinfo is None:
            raise last_exc
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Token de Google inválido.")
    email = (idinfo.get("email") or "").lower()
    google_sub = idinfo.get("sub", "")
    if not email or not idinfo.get("email_verified"):
        raise HTTPException(status_code=401, detail="Email de Google no verificado.")
    try:
        from core.db import get_session
        from core.models import User
        UTC_tz = timezone.utc
        with get_session() as db:
            user = db.query(User).filter(User.email == email).first()
            if user:
                if not user.is_active:
                    raise HTTPException(status_code=403, detail="Cuenta desactivada.")
                if not user.is_approved:
                    user.is_approved = True  # Google users auto-approved
                user.last_login_at = datetime.now(UTC_tz)
                username = user.username
                selected_store = user.selected_store
                selected_branch = user.selected_branch
                role = user.role
            else:
                # Crear usuario nuevo desde cuenta Google
                base = email.split("@")[0][:20].replace(".", "_").replace("-", "_")
                username = base
                suffix = 1
                while db.query(User).filter(User.username == username).first():
                    username = f"{base}{suffix}"
                    suffix += 1
                new_user = User(
                    username=username,
                    email=email,
                    password_hash=f"google:{google_sub}",
                    role="user",
                    is_active=True,
                    is_approved=True,
                )
                db.add(new_user)
                selected_store = None
                selected_branch = None
                role = "user"
        _start_session(username)
        tokens = _issue_tokens(username)
        tokens.update({"role": role, "selected_store": selected_store, "selected_branch": selected_branch, "username": username})
        logger.info(f"[AUTH] Google login: {username} ({email})")
        return UnifiedResponse(data=tokens)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[AUTH] Error en google-login: {e}")
        raise HTTPException(status_code=500, detail="Error procesando login de Google.")


class FirebaseLoginRequest(BaseModel):
    id_token: str

_FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "")
_FIREBASE_JWK_URL = "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"
_firebase_jwk_cache: dict = {"keys": {}, "fetched_at": 0}
_firebase_jwk_lock = Lock()

def _get_firebase_public_keys() -> dict:
    """Retorna {kid: jwk_dict}. Cache de 30 min."""
    now = time.time()
    with _firebase_jwk_lock:
        if now - _firebase_jwk_cache["fetched_at"] < 1800 and _firebase_jwk_cache["keys"]:
            return _firebase_jwk_cache["keys"]
    import requests as _req
    resp = _req.get(_FIREBASE_JWK_URL, timeout=10)
    resp.raise_for_status()
    keys = {k["kid"]: k for k in resp.json().get("keys", [])}
    with _firebase_jwk_lock:
        _firebase_jwk_cache["keys"] = keys
        _firebase_jwk_cache["fetched_at"] = now
    return keys

def _verify_firebase_token(id_token: str) -> dict:
    """Verifica Firebase ID token sin service account usando las claves JWK públicas de Google."""
    if not _FIREBASE_PROJECT_ID:
        raise HTTPException(status_code=503, detail="Firebase no configurado en el servidor.")
    import jwt as _jwt
    from jwt.algorithms import RSAAlgorithm
    try:
        keys = _get_firebase_public_keys()
        header = _jwt.get_unverified_header(id_token)
        kid = header.get("kid", "")
        if kid not in keys:
            raise HTTPException(status_code=401, detail="Token Firebase inválido.")
        public_key = RSAAlgorithm.from_jwk(keys[kid])
        payload = _jwt.decode(
            id_token,
            public_key,
            algorithms=["RS256"],
            audience=_FIREBASE_PROJECT_ID,
            issuer=f"https://securetoken.google.com/{_FIREBASE_PROJECT_ID}",
        )
        return payload
    except HTTPException:
        raise
    except _jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token Firebase expirado.")
    except Exception as e:
        logger.warning(f"[AUTH] Firebase token inválido: {e}")
        raise HTTPException(status_code=401, detail="Token Firebase inválido.")


@router.post("/firebase", response_model=UnifiedResponse)
def firebase_login(body: FirebaseLoginRequest, request: Request):
    """Login con Firebase (Google Sign-In nativo en Android). Verifica Firebase ID token."""
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Demasiados intentos.")

    payload = _verify_firebase_token(body.id_token)
    email = (payload.get("email") or "").lower()
    if not email or not payload.get("email_verified"):
        raise HTTPException(status_code=401, detail="Email de Firebase no verificado.")

    firebase_uid = payload.get("uid") or payload.get("sub", "")

    try:
        from core.db import get_session
        from core.models import User
        UTC_tz = timezone.utc
        with get_session() as db:
            user = db.query(User).filter(User.email == email).first()
            if user:
                if not user.is_active:
                    raise HTTPException(status_code=403, detail="Cuenta desactivada.")
                if not user.is_approved:
                    user.is_approved = True
                user.last_login_at = datetime.now(UTC_tz)
                username = user.username
                selected_store = user.selected_store
                selected_branch = user.selected_branch
                role = user.role
            else:
                base = email.split("@")[0][:20].replace(".", "_").replace("-", "_")
                username = base
                suffix = 1
                while db.query(User).filter(User.username == username).first():
                    username = f"{base}{suffix}"
                    suffix += 1
                new_user = User(
                    username=username,
                    email=email,
                    password_hash=f"firebase:{firebase_uid}",
                    role="user",
                    is_active=True,
                    is_approved=True,
                )
                db.add(new_user)
                selected_store = None
                selected_branch = None
                role = "user"
        _start_session(username)
        tokens = _issue_tokens(username)
        tokens.update({"role": role, "selected_store": selected_store, "selected_branch": selected_branch, "username": username})
        logger.info(f"[AUTH] Firebase login: {username} ({email})")
        return UnifiedResponse(data=tokens)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[AUTH] Error en firebase-login: {e}")
        raise HTTPException(status_code=500, detail="Error procesando login de Firebase.")


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
