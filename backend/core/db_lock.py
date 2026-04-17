"""
Control de acceso a la BD en tiempo real.
El flag _locked se puede activar/desactivar sin reiniciar el servidor.
"""
import threading

_lock = threading.Lock()
_locked = False

def is_locked() -> bool:
    with _lock:
        return _locked

def set_locked(value: bool) -> None:
    global _locked
    with _lock:
        _locked = value
