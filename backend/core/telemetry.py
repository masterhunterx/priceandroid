import os
import json
import time
import traceback
import logging
from collections import deque
from threading import Lock
from datetime import datetime, timezone
import requests
from dotenv import load_dotenv

# Asegurar que se lea el .env del directorio padre si es ejecutado desde /backend
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv() # Fallback

logger = logging.getLogger("AntigravityAPI")

class TelemetryService:
    """
    Antigravity Predictive Monitoring & Telemetry via Discord.
    Sends automated crash reports and system heartbeats without needing third-party SDRs.
    """

    WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", None)

    # Rate limiter: máximo 1 envío cada 5 segundos para no saturar el webhook de Discord
    _RATE_LIMIT_SECS = 5
    _last_send: float = 0.0
    _buffer: deque = deque(maxlen=20)   # Cola de eventos pendientes (máx 20)
    _lock: Lock = Lock()

    @classmethod
    def _send_payload(cls, embed_payload: dict):
        if not cls.WEBHOOK_URL:
            logger.warning("[TELEMETRÍA] Evento omitido — DISCORD_WEBHOOK_URL no configurado.")
            return

        with cls._lock:
            now = time.time()
            if now - cls._last_send < cls._RATE_LIMIT_SECS:
                cls._buffer.append(embed_payload)
                return
            cls._last_send = now

        data = {
            "username": "KAIROS System Monitor",
            "avatar_url": "https://img.icons8.com/color/512/artificial-intelligence.png",
            "embeds": [embed_payload],
        }

        try:
            response = requests.post(
                cls.WEBHOOK_URL,
                json=data,
                headers={"Content-Type": "application/json"},
                timeout=5,
            )
            response.raise_for_status()
        except Exception as e:
            logger.error("[TELEMETRÍA ERROR] Falló el envío del Webhook a Discord: %s", e)

    @classmethod
    def capture_exception(cls, exception: Exception, endpoint_context: str = "Backend"):
        """Captura un error fatal (500) y lo envía inmediatamente al triage de Discord."""
        if not cls.WEBHOOK_URL: return
        
        tb = traceback.format_exc()
        # Extract the last few lines for quick reading
        short_tb = "\n".join(tb.split("\n")[-6:])
        
        embed = {
            "title": "🚨 SYSTEM CRASH: Alerta Crítica 🚨",
            "description": f"Un error no controlado acaba de derribar un proceso en **{endpoint_context}**.",
            "color": 16711680, # Red
            "fields": [
                {"name": "Tipo de Error", "value": f"`{type(exception).__name__}`", "inline": True},
                {"name": "Mensaje Corto", "value": f"{str(exception)[:200]}", "inline": False},
                {"name": "Stack Trace (Final)", "value": f"```python\n{short_tb}\n```", "inline": False}
            ],
            "footer": {"text": "Antigravity Telemetry / Action Required"},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        cls._send_payload(embed)
        
    @classmethod
    def send_heartbeat(cls, stores_count: int, products_count: int, uptime_minutes: int):
        """Envía un reporte periódico indicando que el servidor goza de buena salud y métricas de scraping."""
        if not cls.WEBHOOK_URL: return
        
        embed = {
            "title": "💚 KAIROS Heartbeat: Todo en Orden",
            "description": "Reporte de estado de la aplicación. Los sistemas siguen en pie y estables.",
            "color": 65280, # Green
            "fields": [
                {"name": "App Uptime", "value": f"{uptime_minutes} min", "inline": True},
                {"name": "Catálogo de Productos", "value": f"{products_count} registros", "inline": True},
                {"name": "Tiendas Activas", "value": f"{stores_count} escaneadas", "inline": True}
            ],
            "footer": {"text": "Antigravity Telemetry / Auto-Report"},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        cls._send_payload(embed)
        
    @classmethod
    def notify_ai_fallback(cls, store_name: str, query: str):
        """Notificación específica cuando el scraper nativo se quiebra y la Inteligencia Artificial toma el mando."""
        if not cls.WEBHOOK_URL: return
        
        embed = {
            "title": "🤖 AI FALLBACK DETECTADO",
            "description": f"El Autoscraper de **{store_name}** colapsó extrayendo `{query}`. Llama-3.2 intervino exitosamente para parchar el error.",
            "color": 16753920, # Orange
            "footer": {"text": "KAIROS AI Service"},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        cls._send_payload(embed)
