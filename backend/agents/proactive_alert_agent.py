"""
Agente de Alertas Proactivas KAIROS
====================================
Loop que genera alertas de ahorro cada 15 minutos y envía telemetría de heartbeat.
Extraído de api/main.py para mejor estructura y testabilidad.
"""

import logging
import threading
import time
from datetime import datetime, timezone

logger = logging.getLogger("AntigravityAPI")
UTC = timezone.utc

_ALERT_INTERVAL_SECONDS = 900   # 15 min entre ciclos de alertas proactivas
_STARTUP_DELAY_SECONDS  = 0     # sin retraso inicial para este agente


def proactive_alert_loop(stop_event: threading.Event):
    logger.info("[KAIROS] Motor de Alertas Proactivas: Activo.")

    from domain.proactive import generate_proactive_alerts
    from core.telemetry import TelemetryService
    from core.db import get_session
    from core.models import Store, StoreProduct

    start_time = datetime.now(UTC)

    while not stop_event.is_set():
        try:
            generate_proactive_alerts()

            uptime_mins = int((datetime.now(UTC) - start_time).total_seconds() / 60)
            with get_session() as db:
                sc = db.query(Store).count()
                pc = db.query(StoreProduct).count()
            TelemetryService.send_heartbeat(stores_count=sc, products_count=pc, uptime_minutes=uptime_mins)

            try:
                from core.metrics import refresh_catalog_gauges, refresh_feedback_gauges
                refresh_catalog_gauges()
                refresh_feedback_gauges()
            except Exception as me:
                logger.debug(f"[Metrics] refresh falló: {me}")

        except Exception as e:
            logger.error(f"❌ [KAIROS] Error en motor de alertas: {e}", exc_info=True)

        stop_event.wait(timeout=_ALERT_INTERVAL_SECONDS)

    logger.info("[KAIROS] Motor proactivo detenido.")


def start_proactive_alert_agent() -> threading.Event:
    """Arranca el agente y retorna el stop_event para poder detenerlo."""
    stop_event = threading.Event()
    thread = threading.Thread(
        target=proactive_alert_loop,
        args=(stop_event,),
        name="KairosProactive",
        daemon=True,
    )
    thread.start()
    logger.info("[KAIROS] Motor proactivo inicializado.")
    return stop_event
