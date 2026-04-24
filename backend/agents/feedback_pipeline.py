"""
Feedback Pipeline — Resolución automática de reportes de usuarios
=================================================================
Corre cada 15 minutos. Clasifica cada feedback pendiente y actúa:

  • producto_faltante → scrape automático + ingest + marca resuelto
  • bug              → alerta Discord con contexto enriquecido
  • sugerencia       → acumula; reporte semanal al admin

Flujo:
  BD (feedback pendiente)
      → clasificar por palabras clave
      → si producto faltante: scrape_store() → upsert_store_products() → resolved
      → si bug: Discord alert con pantalla/descripción
      → si sugerencia: dismissed (se reportan en batch semanal)
"""

import os
import re
import time
import logging
import threading
from datetime import datetime, timezone

logger = logging.getLogger("AntigravityAPI")
UTC = timezone.utc

DISCORD_WEBHOOK    = os.getenv("DISCORD_WEBHOOK_URL", "")
CHECK_INTERVAL_SEC = int(os.getenv("FEEDBACK_PIPELINE_INTERVAL_MIN", "15")) * 60
STARTUP_DELAY_SEC  = 120   # esperar 2 min tras arranque
MAX_PAGES_SCRAPE   = 2     # páginas de scrape por producto faltante
STORES_TO_SEARCH   = ["jumbo", "santa_isabel", "unimarc"]


# ---------------------------------------------------------------------------
# Clasificación de feedback
# ---------------------------------------------------------------------------

_MISSING_PRODUCT_KEYWORDS = [
    r"\bno (encuentro|aparece|tengo|hay)\b",
    r"\bfalta\b",
    r"\bno est[aá]\b",
    r"\bno (lo |la )?encuentro\b",
    r"\bbuscando\b",
    r"\bno (sale|aparece|existe)\b",
    r"\bagrega[r]?\b",
    r"\binclui[r]?\b",
]
_MISSING_RE = [re.compile(p, re.IGNORECASE) for p in _MISSING_PRODUCT_KEYWORDS]


def _classify(feedback) -> str:
    """Retorna: 'missing_product', 'bug', o 'suggestion'."""
    if feedback.type in ("mejora", "sugerencia"):
        return "suggestion"

    desc = (feedback.description or "").lower()
    if any(r.search(desc) for r in _MISSING_RE):
        return "missing_product"

    return "bug"


def _extract_query(description: str) -> str:
    """Extrae el término de búsqueda más probable del texto del feedback."""
    text = re.sub(r"(no encuentro|no aparece|busco|busca|falta|agregar|incluir)", "", description, flags=re.IGNORECASE)
    text = re.sub(r"[^\w\s]", " ", text)
    words = [w for w in text.split() if len(w) > 3]
    return " ".join(words[:4]).strip() or description[:40]


# ---------------------------------------------------------------------------
# Handlers por clasificación
# ---------------------------------------------------------------------------

def _handle_missing_product(db, feedback) -> bool:
    """Scrape multi-tienda y upsert. Retorna True si encontró algo."""
    from domain.ingest import scrape_store, upsert_store_products
    from core.models import Store

    query = _extract_query(feedback.description)
    logger.info(f"[FeedbackPipeline] Buscando producto faltante: '{query}' (feedback #{feedback.id})")

    total_saved = 0
    for slug in STORES_TO_SEARCH:
        try:
            products = scrape_store(slug, query, pages=MAX_PAGES_SCRAPE)
            if products:
                store = db.query(Store).filter_by(slug=slug).first()
                if store:
                    saved = upsert_store_products(db, store, products)
                    total_saved += len(saved)
                    logger.info(f"[FeedbackPipeline] {slug}: {len(saved)} productos guardados para '{query}'")
            time.sleep(2)
        except Exception as e:
            logger.error(f"[FeedbackPipeline] Error scrapeando {slug} para '{query}': {e}")

    if total_saved > 0:
        _send_discord(
            f"**✅ FeedbackPipeline — Producto encontrado**\n"
            f"Feedback #{feedback.id}: `{feedback.description[:100]}`\n"
            f"Búsqueda: `{query}` → **{total_saved} productos** agregados al catálogo."
        )
        return True

    _send_discord(
        f"**⚠️ FeedbackPipeline — Producto no encontrado**\n"
        f"Feedback #{feedback.id}: `{feedback.description[:100]}`\n"
        f"Búsqueda: `{query}` → Sin resultados en {', '.join(STORES_TO_SEARCH)}."
    )
    return False


def _handle_bug(feedback) -> None:
    """Reporta bug a Discord con contexto enriquecido."""
    page = feedback.page_context or "desconocida"
    ts = feedback.created_at.strftime("%d/%m %H:%M") if feedback.created_at else "?"
    _send_discord(
        f"**🐛 FeedbackPipeline — Bug reportado**\n"
        f"Feedback #{feedback.id} | Pantalla: `{page}` | `{ts}`\n"
        f"```\n{feedback.description[:400]}\n```"
    )


# ---------------------------------------------------------------------------
# Ciclo principal
# ---------------------------------------------------------------------------

def _process_pending(db) -> int:
    """Procesa todos los feedback pendientes. Retorna cantidad procesada."""
    from core.models import Feedback
    from datetime import datetime

    pending = db.query(Feedback).filter_by(status="pending").order_by(Feedback.created_at).all()
    if not pending:
        return 0

    logger.info(f"[FeedbackPipeline] Procesando {len(pending)} feedback(s) pendiente(s)...")
    processed = 0

    for fb in pending:
        try:
            kind = _classify(fb)

            if kind == "missing_product":
                found = _handle_missing_product(db, fb)
                fb.status = "resolved" if found else "analyzed"
                fb.ai_plan = f'{{"action":"scrape","query":"{_extract_query(fb.description)}","found":{str(found).lower()}}}'

            elif kind == "bug":
                _handle_bug(fb)
                fb.status = "analyzed"
                fb.ai_plan = '{"action":"bug_reported","sent_to_discord":true}'

            else:  # suggestion
                fb.status = "analyzed"
                fb.ai_plan = '{"action":"suggestion_queued"}'

            fb.updated_at = datetime.now(UTC)
            db.flush()
            processed += 1

        except Exception as e:
            logger.error(f"[FeedbackPipeline] Error procesando feedback #{fb.id}: {e}", exc_info=True)

    return processed


def feedback_pipeline_loop():
    """Loop daemon del Feedback Pipeline."""
    logger.info(f"[FeedbackPipeline] Iniciando — revisión cada {CHECK_INTERVAL_SEC // 60} min.")
    time.sleep(STARTUP_DELAY_SEC)

    while True:
        try:
            from core.db import get_session
            with get_session() as db:
                count = _process_pending(db)
                if count:
                    logger.info(f"[FeedbackPipeline] Ciclo completado: {count} feedback(s) procesados.")
        except Exception as e:
            logger.error(f"[FeedbackPipeline] Error inesperado: {e}", exc_info=True)

        time.sleep(CHECK_INTERVAL_SEC)


# ---------------------------------------------------------------------------
# Utils
# ---------------------------------------------------------------------------

def _send_discord(content: str) -> None:
    if not DISCORD_WEBHOOK:
        return
    try:
        import requests as _req
        _req.post(DISCORD_WEBHOOK, json={"content": content}, timeout=10)
    except Exception as e:
        logger.warning(f"[FeedbackPipeline] Discord send failed: {e}")
