"""
Log Error Tracker — Monitor de errores recurrentes en el backend
================================================================
Analiza server_backend.log cada 24h, agrupa errores por tipo/origen
y reporta a Discord los más frecuentes con contexto para tomar acción.

No modifica código — detecta y reporta. El humano decide si actuar.
"""

import os
import re
import time
import logging
from collections import defaultdict
from datetime import datetime, timezone

logger = logging.getLogger("AntigravityAPI")
UTC = timezone.utc

DISCORD_WEBHOOK    = os.getenv("DISCORD_WEBHOOK_URL", "")
LOG_FILE           = os.getenv("LOG_FILE_PATH", "server_backend.log")
CHECK_INTERVAL_SEC = int(os.getenv("LOG_TRACKER_INTERVAL_HOURS", "24")) * 3600
TOP_N_ERRORS       = 8   # cuántos errores mostrar en el reporte
MIN_OCCURRENCES    = 3   # mínimo de repeticiones para reportar un error


# Patrones a ignorar (ruido esperado, no son bugs reales)
_IGNORE_PATTERNS = [
    r"Rate limit",
    r"RATE_LIMIT",
    r"WAF_BLOCK",
    r"IP bloqueada",
    r"Token inválido",
    r"Credenciales inválidas",
    r"FluxEngine Shield",
    r"Heartbeat",
    r"QAAgent.*Sin correcciones",
    r"SelfHealer.*Sin correcciones",
]
_IGNORE_RE = [re.compile(p, re.IGNORECASE) for p in _IGNORE_PATTERNS]


def _should_ignore(line: str) -> bool:
    return any(r.search(line) for r in _IGNORE_RE)


def _normalize_error(line: str) -> str:
    """
    Quita valores dinámicos (IDs, IPs, timestamps) para agrupar
    errores del mismo tipo aunque tengan parámetros distintos.
    """
    line = re.sub(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "<IP>", line)
    line = re.sub(r"\bsp_id=\d+\b", "sp_id=<N>", line)
    line = re.sub(r"\bid=\d+\b", "id=<N>", line)
    line = re.sub(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[^\s]*", "<TS>", line)
    line = re.sub(r"'[^']{1,60}'", "'<VAL>'", line)
    line = re.sub(r'"[^"]{1,60}"', '"<VAL>"', line)
    return line.strip()


def analyze_logs() -> list[dict]:
    """Lee el log file y retorna lista de errores ordenados por frecuencia."""
    if not os.path.exists(LOG_FILE):
        logger.warning(f"[LogTracker] Archivo de log no encontrado: {LOG_FILE}")
        return []

    error_counts: dict[str, int]         = defaultdict(int)
    error_examples: dict[str, str]       = {}
    error_levels: dict[str, str]         = {}

    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if not ("[ERROR]" in line or "[CRITICAL]" in line or "[WARNING]" in line):
                    continue
                if _should_ignore(line):
                    continue

                level = "ERROR"
                if "[CRITICAL]" in line:
                    level = "CRITICAL"
                elif "[WARNING]" in line:
                    level = "WARNING"

                # Extraer la parte del mensaje (después del logger name)
                match = re.search(r"\] \S+: (.+)$", line)
                msg = match.group(1) if match else line
                key = _normalize_error(msg)[:200]

                error_counts[key] += 1
                if key not in error_examples:
                    error_examples[key] = msg[:300]
                if level in ("CRITICAL", "ERROR"):
                    error_levels[key] = level
                elif key not in error_levels:
                    error_levels[key] = level

    except Exception as e:
        logger.error(f"[LogTracker] Error leyendo log: {e}")
        return []

    # Filtrar y ordenar
    results = [
        {
            "count":   count,
            "level":   error_levels.get(key, "WARNING"),
            "key":     key,
            "example": error_examples.get(key, key),
        }
        for key, count in error_counts.items()
        if count >= MIN_OCCURRENCES
    ]
    results.sort(key=lambda x: (-{"CRITICAL": 3, "ERROR": 2, "WARNING": 1}.get(x["level"], 0), -x["count"]))
    return results[:TOP_N_ERRORS]


def _discord_report(errors: list[dict]) -> None:
    ts = datetime.now(UTC).strftime("%d/%m/%Y %H:%M")

    if not errors:
        _send_discord(f"**📋 Log Tracker** — Sin errores recurrentes detectados `{ts} UTC`")
        return

    has_critical = any(e["level"] == "CRITICAL" for e in errors)
    icon = "🔴" if has_critical else "🟡"
    lines = [f"**{icon} Log Tracker — {len(errors)} error(es) recurrentes** `{ts} UTC`\n"]

    for e in errors:
        lvl_icon = {"CRITICAL": "🔴", "ERROR": "🟠", "WARNING": "🟡"}.get(e["level"], "⚪")
        lines.append(f"{lvl_icon} **x{e['count']}** — `{e['example'][:120]}`")

    lines.append("\n> Revisa Railway logs para contexto completo.")
    _send_discord("\n".join(lines))


def _send_discord(content: str) -> None:
    if not DISCORD_WEBHOOK:
        return
    try:
        import requests as _req
        _req.post(DISCORD_WEBHOOK, json={"content": content}, timeout=10)
    except Exception as e:
        logger.warning(f"[LogTracker] Discord send failed: {e}")


def log_tracker_loop():
    """Loop daemon del Log Tracker. Analiza logs cada 24h."""
    logger.info("[LogTracker] Iniciando — análisis de errores cada 24h.")
    time.sleep(600)  # Esperar 10 min al arranque

    while True:
        try:
            logger.info("[LogTracker] Analizando logs...")
            errors = analyze_logs()
            _discord_report(errors)
            logger.info(f"[LogTracker] Análisis completado: {len(errors)} errores recurrentes.")
        except Exception as e:
            logger.error(f"[LogTracker] Error inesperado: {e}", exc_info=True)
        time.sleep(CHECK_INTERVAL_SEC)
