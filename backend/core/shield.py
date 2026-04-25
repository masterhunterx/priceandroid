import logging
import re
import threading
from datetime import datetime, timezone
import statistics
import time

# Patrones WAF — detectan ataques comunes en URLs y query params
_RE_PATH_TRAVERSAL = re.compile(r"\.\./|%2e%2e[/%]|%252e|/etc/passwd|/proc/self", re.IGNORECASE)
_RE_SQLI = re.compile(
    r"(\bunion\b.{0,20}\bselect\b|\bdrop\b.{0,10}\btable\b|"
    r"1\s*=\s*1|'\s*--|\bxp_cmdshell\b|\bexec\s*\(|\bwaitfor\s+delay\b)",
    re.IGNORECASE,
)
_RE_XSS = re.compile(r"<script|javascript:|on\w+\s*=|<iframe|<svg.{0,30}on", re.IGNORECASE)
_RE_SSTI = re.compile(r"\{\{.{0,30}\}\}|\$\{.{0,30}\}|<%=.{0,30}%>", re.IGNORECASE)

# Configuración de Logs del sistema de seguridad Shield
logger = logging.getLogger("FluxShield")
if not logger.handlers:
    # Handler para consola
    c_handler = logging.StreamHandler()
    c_handler.setFormatter(logging.Formatter("%(asctime)s [SHIELD] %(message)s"))
    logger.addHandler(c_handler)

    # Handler para archivo dedicado de auditoría (con rotación para evitar llenado de disco)
    from logging.handlers import RotatingFileHandler
    f_handler = RotatingFileHandler(
        "security.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    f_handler.setFormatter(logging.Formatter("%(asctime)s [AUDIT_SECURITY] %(message)s"))
    logger.addHandler(f_handler)

logger.setLevel(logging.INFO)

class Shield3:
    """
    Shield 3.1: Motor de Defensa Activa para el ecosistema Antigravity.
    Implementa bloqueo de IPs persistente, limitación de tasa dinámica y detección de anomalías.
    """
    # Caché en memoria para evitar consultas recurrentes a la base de datos en cada petición
    BLOCKED_IPS_CACHE = set()
    LAST_CACHE_SYNC = 0        # Marca de tiempo de la última sincronización con la BD
    REQUEST_HISTORY = {}       # Historial por IP: {ip -> {"count": int, "reset_at": timestamp}}
    _LAST_CLEANUP = 0          # Marca de tiempo de la última limpieza de memoria
    _lock = threading.Lock()   # Protege el acceso concurrente desde múltiples hilos


    @classmethod
    def track_request(cls, ip: str, limit: int = 20, window: int = 10):
        """
        Realiza el seguimiento de peticiones por IP y aplica limitación de tasa (Rate Limiting).
        Retorna (allowed, current_count).
        """
        # Bypass instantáneo para tráfico interno o de desarrollo
        if ip in ("127.0.0.1", "::1", "localhost"):
            return True, 0

        now = time.time()
        with cls._lock:
            if ip not in cls.REQUEST_HISTORY:
                cls.REQUEST_HISTORY[ip] = {"count": 1, "reset_at": now + window}
                return True, 1

            data = cls.REQUEST_HISTORY[ip]
            if now > data["reset_at"]:
                # La ventana ha expirado, reiniciamos el contador
                data["count"] = 1
                data["reset_at"] = now + window
                return True, 1

            data["count"] += 1

            # Cada cierto tiempo, realizamos una limpieza de registros antiguos para liberar memoria
            if now - cls._LAST_CLEANUP > 300:  # Cada 5 minutos
                cls._cleanup_old_requests_unsafe()

            if data["count"] > limit:
                logger.warning(f"⚠️ [RATE_LIMIT] IP {ip} superó el límite: {data['count']}/{limit} en {window}s")
                return False, data["count"]

            return True, data["count"]

    @classmethod
    def _cleanup_old_requests_unsafe(cls):
        """
        Elimina registros expirados. Debe llamarse con _lock ya adquirido.
        """
        now = time.time()
        expired_ips = [ip for ip, data in cls.REQUEST_HISTORY.items() if now > data["reset_at"]]
        for ip in expired_ips:
            del cls.REQUEST_HISTORY[ip]
        cls._LAST_CLEANUP = now
        if expired_ips:
            logger.debug(f"[SHIELD] Limpieza completada: {len(expired_ips)} registros expirados eliminados.")

    @classmethod
    def cleanup_old_requests(cls):
        """
        Elimina registros de historial que ya han expirado para evitar fugas de memoria.
        """
        with cls._lock:
            cls._cleanup_old_requests_unsafe()

    
    @classmethod
    def _sync_cache(cls):
        """
        Sincroniza la caché de IPs bloqueadas con la base de datos de forma periódica (cada 60 segundos).
        Esto optimiza el rendimiento al evitar el "DB Hit" en cada request de la API.
        """
        now = time.time()
        # Solo sincronizamos si ha pasado más de un minuto
        if now - cls.LAST_CACHE_SYNC > 60:
            from .db import get_session
            from .models import BlockedIP

            with get_session() as session:
                blocked = session.query(BlockedIP).all()
                with cls._lock:
                    cls.BLOCKED_IPS_CACHE = {b.ip for b in blocked}
                    cls.LAST_CACHE_SYNC = now
            logger.info(f"Sincronización de Shield: {len(cls.BLOCKED_IPS_CACHE)} IPs en caché.")

    @staticmethod
    def is_ip_blocked(ip: str) -> bool:
        """
        Verifica instantáneamente si una IP está en el registro de bloqueos activos.
        Primero consulta la caché en memoria; solo va a la DB si la IP no está en caché.
        """
        Shield3._sync_cache()
        with Shield3._lock:
            if ip in Shield3.BLOCKED_IPS_CACHE:
                return True
        return False

    @staticmethod
    def block_ip(ip, reason="Bot Deception Triggered"):
        """
        Bloquea permanentemente una IP en la base de datos y actualiza la caché inmediata.
        """
        # --- SEGURIDAD EN DESARROLLO: Nunca bloquear localhost para evitar quedar fuera del sistema ---
        if ip in ("127.0.0.1", "::1", "localhost", "testclient"):
            logger.warning(f"⚠️ Supresión: Se intentó bloquear {ip} por {reason}, pero se omitió (Lista Blanca).")
            return False
            
        from .db import get_session
        from .models import BlockedIP, SecurityLog
        
        with get_session() as session:
            # Evitamos duplicados en el registro de bloqueo
            existing = session.query(BlockedIP).filter_by(ip=ip).first()
            if not existing:
                blocked_entry = BlockedIP(
                    ip=ip,
                    reason=reason
                )
                session.add(blocked_entry)
                
                # También registramos el evento en el log general
                log_entry = SecurityLog(
                    ip=ip,
                    event_type="IPS_BLOCK",
                    severity="CRITICAL",
                    details=reason
                )
                session.add(log_entry)
                session.commit()
                
                # Actualizamos la caché de hilos para bloquear el siguiente request en milisegundos
                with Shield3._lock:
                    Shield3.BLOCKED_IPS_CACHE.add(ip)
                
                logger.critical(f"[BRECHA DE SEGURIDAD] IP {ip} BLOQUEADA permanentemente. Razón: {reason}")
                return True
        return False

    @staticmethod
    def log_event(ip, event_type, severity, description):
        """ Registra un evento de seguridad administrativo sin bloquear la IP necesariamente. """
        from .db import get_session
        from .models import SecurityLog
        with get_session() as session:
            event = SecurityLog(
                ip=ip,
                event_type=event_type,
                severity=severity,
                details=description
            )
            session.add(event)
            session.commit()

    @staticmethod
    def detect_anomalous_price(history, current_price):
        """
        Analiza si un nuevo precio scrapeado es coherente con su historial.
        Previene 'Data Poisoning' (envenenamiento de datos).
        """
        if not history or len(history) < 3:
            return False, "Historial insuficiente para auditoría técnica"
        
        avg = statistics.mean(history)
        if len(history) > 3:
            stdev = statistics.stdev(history)
            
            # Refinamos el umbral: 2.5 desviaciones estándar o 40% del promedio
            # Un Z-score > 2.5 captura el 99% de los casos normales.
            threshold = max(stdev * 2.5, avg * 0.4)
            
            if abs(current_price - avg) > threshold:
                return True, f"Anomalía Detectada: Precio {current_price} fuera de rango (Promedio: {avg:.2f}, Desv: {stdev:.2f})"
        
        # Validación crítica por multiplicadores (Salvaguarda para varianza 0)
        if current_price > (avg * 3) or current_price < (avg * 0.2):
            return True, f"Anomalía Crítica: Variación superior al 300% o inferior al 20% detectada."
        
        return False, "Integridad de Datos Verificada exitosamente"

    @staticmethod
    def analyze_waf_threat(headers, url_path: str = "", query_string: str = ""):
        """
        Analiza cabeceras HTTP, path y query params en busca de ataques conocidos.
        Retorna (is_threat, reason).
        """
        ua = headers.get("user-agent", "").lower()

        # Firmas de herramientas de ataque — excluye curl/wget/postman/python-requests (legítimos)
        bot_signatures = [
            "selenium", "puppeteer", "headless", "sqlmap", "nikto",
            "scrapy", "masscan", "zgrab", "nuclei", "dirbuster",
        ]
        for sig in bot_signatures:
            if sig in ua:
                return True, f"Firma de herramienta detectada: {sig}"

        if not ua or len(ua) < 10:
            return True, "User-Agent vacío o sospechosamente corto"

        # Inspección de URL path + query string
        target = f"{url_path}?{query_string}" if query_string else url_path
        if target:
            if _RE_PATH_TRAVERSAL.search(target):
                return True, "Path traversal detectado en URL"
            if _RE_SQLI.search(target):
                return True, "Patrón SQL injection detectado en URL"
            if _RE_XSS.search(target):
                return True, "Patrón XSS detectado en URL"
            if _RE_SSTI.search(target):
                return True, "Patrón SSTI detectado en URL"

        return False, "Tráfico limpio verificado"

    @staticmethod
    def get_security_posture_report():
        """
        Genera un informe rápido del estado de protección de Shield.
        """
        return {
            "version": "Shield 3.1 (Producción)",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "protection_active": True,
            "ips_blocked_in_cache": len(Shield3.BLOCKED_IPS_CACHE),
            "threat_level": "NOMINAL"
        }
