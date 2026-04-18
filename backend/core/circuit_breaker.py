"""
Circuit Breaker por tienda.
Si una tienda supera el umbral de errores consecutivos, se bloquea
temporalmente para no saturar logs ni desperdiciar requests.

Estados:
  CLOSED    → operación normal
  OPEN      → bloqueado (demasiados errores), esperar recovery_timeout
  HALF_OPEN → probando si la tienda se recuperó (1 request de prueba)
"""
import threading
import time
import logging

logger = logging.getLogger("AntigravityAPI")

FAILURE_THRESHOLD = 3         # errores consecutivos para abrir el circuito
RECOVERY_TIMEOUT  = 21600     # segundos bloqueado antes de probar recuperación (6h)

_CLOSED    = "closed"
_OPEN      = "open"
_HALF_OPEN = "half_open"

_lock  = threading.Lock()
_state: dict[str, dict] = {}


def _get(store: str) -> dict:
    return _state.setdefault(store, {"state": _CLOSED, "failures": 0, "opened_at": 0.0})


def record_failure(store: str) -> bool:
    """Registra un fallo. Retorna True si acabó de abrir el circuito."""
    with _lock:
        s = _get(store)
        s["failures"] += 1
        # HALF_OPEN: cualquier fallo vuelve a abrir inmediatamente
        if s["state"] == _HALF_OPEN:
            s["state"]     = _OPEN
            s["opened_at"] = time.time()
            logger.warning(f"[CircuitBreaker] 🔴 Circuito re-ABIERTO para {store} (falló en HALF_OPEN). Pausa de {RECOVERY_TIMEOUT//3600}h.")
            return True
        if s["state"] == _CLOSED and s["failures"] >= FAILURE_THRESHOLD:
            s["state"]     = _OPEN
            s["opened_at"] = time.time()
            logger.warning(
                f"[CircuitBreaker] 🔴 Circuito ABIERTO para {store} "
                f"({s['failures']} errores consecutivos). "
                f"Pausa de {RECOVERY_TIMEOUT//3600}h."
            )
            return True
        return False


def record_success(store: str) -> None:
    """Registra un éxito. Cierra el circuito y resetea contadores."""
    with _lock:
        s = _get(store)
        if s["state"] != _CLOSED:
            logger.info(f"[CircuitBreaker] 🟢 Circuito CERRADO para {store}. Sync restaurado.")
        s["state"]    = _CLOSED
        s["failures"] = 0


def is_open(store: str) -> bool:
    """Retorna True si el circuito está abierto (no se debe intentar sync)."""
    with _lock:
        s = _get(store)
        if s["state"] == _CLOSED:
            return False
        if s["state"] == _OPEN:
            if time.time() - s["opened_at"] >= RECOVERY_TIMEOUT:
                s["state"]    = _HALF_OPEN
                s["failures"] = 0
                logger.info(f"[CircuitBreaker] 🟡 Circuito HALF-OPEN para {store}. Probando recuperación...")
                return False  # dejar pasar 1 request de prueba
            return True
        return False  # HALF_OPEN → dejar pasar


def get_all_status() -> dict[str, dict]:
    """Retorna el estado de todos los circuitos."""
    with _lock:
        return {
            store: {
                "state":    info["state"],
                "failures": info["failures"],
                "blocked_since": (
                    time.strftime("%H:%M:%S", time.localtime(info["opened_at"]))
                    if info["state"] == _OPEN else None
                ),
                "recovers_in_min": (
                    max(0, int((info["opened_at"] + RECOVERY_TIMEOUT - time.time()) / 60))
                    if info["state"] == _OPEN else None
                ),
            }
            for store, info in _state.items()
        }
