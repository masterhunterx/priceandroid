"""
Utilidades compartidas para todos los scrapers
================================================
Centraliza imports, inicialización de servicios y constantes comunes
para evitar duplicación en jumbo, lider, santa_isabel y unimarc scrapers.
"""

import logging
import time
from typing import Callable

logger = logging.getLogger("AntigravityAPI")

# ── Constantes comunes ─────────────────────────────────────────────────────────
MAX_FALLBACKS = 5         # máximo de fallbacks AI por sesión de scraping
DEFAULT_TIMEOUT = 15      # segundos por request HTTP
DEFAULT_RETRY_DELAY = 2.0 # segundos entre reintentos

# User-Agent estándar para scrapers que usan requests (no curl_cffi)
STANDARD_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)

STANDARD_ACCEPT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


# ── Normalizer ─────────────────────────────────────────────────────────────────
def get_normalizer() -> Callable:
    """Retorna normalize_scraped_product o un identity fallback si el módulo no está disponible."""
    try:
        from domain.normalizer import normalize_scraped_product
        return normalize_scraped_product
    except ImportError:
        logger.debug("[scraper_utils] domain.normalizer no disponible — usando identity")
        return lambda p: p


# ── AI Service ─────────────────────────────────────────────────────────────────
def get_ai_service():
    """Retorna instancia de KairosAIService o None si no está disponible."""
    try:
        from core.ai_service import KairosAIService
        return KairosAIService()
    except Exception as e:
        logger.debug(f"[scraper_utils] KairosAIService no disponible: {e}")
        return None


# ── Retry helper ───────────────────────────────────────────────────────────────
def retry_request(fn: Callable, retries: int = 3, delay: float = DEFAULT_RETRY_DELAY,
                  retry_on_status: tuple = (429, 503, 502)):
    """
    Ejecuta fn() con reintentos automáticos.
    fn debe retornar un objeto con atributo .status_code, o lanzar excepción.
    Retorna el resultado de fn() o None si todos los intentos fallan.
    """
    for attempt in range(retries):
        try:
            response = fn()
            if hasattr(response, "status_code") and response.status_code in retry_on_status:
                wait = delay * (attempt + 1)
                logger.warning(f"[retry] HTTP {response.status_code} en intento {attempt+1}/{retries} — esperando {wait:.1f}s")
                time.sleep(wait)
                continue
            return response
        except Exception as e:
            if attempt < retries - 1:
                wait = delay * (attempt + 1)
                logger.warning(f"[retry] Error en intento {attempt+1}/{retries}: {e} — esperando {wait:.1f}s")
                time.sleep(wait)
            else:
                logger.error(f"[retry] Todos los intentos fallaron: {e}")
                return None
    return None
