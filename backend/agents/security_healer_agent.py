"""
Security Healer Agent
=====================
Lee SecurityReport rows con auto_fixable=True y fixed=False,
aplica correcciones automáticas y marca los reportes como resueltos.

Acciones disponibles por categoría:
  AUTH/INJECTION  — bloquear IPs ofensoras en Shield3
  INFRA (blocked_ips grande) — limpiar entradas antiguas (>30 días)
  INFRA (honeytoken) — ya auto-bloqueadas por Shield; solo marcar como procesado
"""

import logging
import time
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("AntigravityAPI")
UTC = timezone.utc

HEALER_INTERVAL_SEC = 3600  # cada 1h


def _discord(msg: str) -> None:
    import os
    webhook = os.getenv("DISCORD_WEBHOOK_URL", "")
    if not webhook:
        return
    try:
        import requests as _r
        _r.post(webhook, json={"content": msg[:1900]}, timeout=10)
    except Exception as e:
        logger.warning(f"[SecHealer] Discord send failed: {e}")


def _mark_fixed(report, description: str) -> None:
    report.fixed = True
    report.fixed_at = datetime.now(UTC)
    report.fix_description = description


# ---------------------------------------------------------------------------
# Acciones de corrección
# ---------------------------------------------------------------------------

def _fix_brute_force(db, report) -> str:
    """Bloquea la IP identificada en un reporte de fuerza bruta."""
    from core.shield import Shield3
    ip = report.affected.strip()
    if not ip or ip in ("", "unknown"):
        return "IP inválida en el reporte, sin acción."
    try:
        Shield3.block_ip(ip, reason=f"Auto-fix: brute force detectado — {report.title}")
        return f"IP {ip} bloqueada automáticamente por Shield3."
    except Exception as e:
        return f"Error al bloquear {ip}: {e}"


def _fix_injection_ips(db, report) -> str:
    """Bloquea IPs que aparecen en el campo affected del reporte de injection."""
    from core.shield import Shield3
    raw = report.affected.strip()
    ips = [ip.strip() for ip in raw.replace(",", " ").split() if ip.strip()]
    blocked = []
    for ip in ips[:10]:
        try:
            Shield3.block_ip(ip, reason=f"Auto-fix: injection attempt — {report.category}")
            blocked.append(ip)
        except Exception:
            pass
    if blocked:
        return f"IPs bloqueadas: {', '.join(blocked)}"
    return "No se identificaron IPs válidas para bloquear."


def _fix_stale_blocked_ips(db, report) -> str:
    """Elimina entradas de blocked_ips con más de 30 días."""
    from core.models import BlockedIP
    cutoff = datetime.now(UTC) - timedelta(days=30)
    old = db.query(BlockedIP).filter(BlockedIP.blocked_at < cutoff)
    count = old.count()
    if count == 0:
        return "No hay entradas antiguas que limpiar."
    old.delete(synchronize_session=False)
    return f"Eliminadas {count} IPs bloqueadas con más de 30 días."


def _fix_honeytoken(db, report) -> str:
    """El Shield ya bloqueó las IPs automáticamente; solo confirma el estado."""
    return "Honeytoken procesado — IPs ofensoras ya bloqueadas por Shield3 al momento del acceso."


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_FIX_DISPATCH = {
    ("AUTH", "Posible fuerza bruta"): _fix_brute_force,
    ("INJECTION", "SQL injection"):    _fix_injection_ips,
    ("INJECTION", "path traversal"):   _fix_injection_ips,
    ("INFRA", "blocked_ips"):          _fix_stale_blocked_ips,
    ("INFRA", "Honeytoken"):           _fix_honeytoken,
}


def _get_fixer(report):
    for (cat, title_fragment), fn in _FIX_DISPATCH.items():
        if report.category == cat and title_fragment.lower() in report.title.lower():
            return fn
    return None


# ---------------------------------------------------------------------------
# Runner principal
# ---------------------------------------------------------------------------

def run_security_healer() -> list:
    """Lee reportes pendientes y aplica correcciones automáticas."""
    from core.db import get_session
    from core.models import SecurityReport

    logger.info("[SecHealer] Iniciando ciclo de auto-corrección...")
    fixed_reports = []

    with get_session() as db:
        try:
            pending = db.query(SecurityReport).filter(
                SecurityReport.auto_fixable == True,
                SecurityReport.fixed == False,
            ).order_by(SecurityReport.created_at.asc()).limit(50).all()

            for report in pending:
                fixer = _get_fixer(report)
                if fixer is None:
                    logger.debug(f"[SecHealer] Sin fixer para: {report.title}")
                    continue
                try:
                    result = fixer(db, report)
                    _mark_fixed(report, result)
                    fixed_reports.append((report, result))
                    logger.info(f"[SecHealer] Fixed [{report.severity}] {report.title}: {result}")
                except Exception as e:
                    logger.error(f"[SecHealer] Error al corregir '{report.title}': {e}")

            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"[SecHealer] Error en ciclo: {e}")

    logger.info(f"[SecHealer] Ciclo completado: {len(fixed_reports)} reportes corregidos.")
    return fixed_reports


def _build_healer_discord(fixed: list) -> str:
    if not fixed:
        return ""
    lines = ["🔧 **[SecHealer] Correcciones automáticas aplicadas**"]
    for report, result in fixed[:10]:
        lines.append(f"  • [{report.severity}] **{report.title}**")
        lines.append(f"    ↳ {result}")
    if len(fixed) > 10:
        lines.append(f"  _(+{len(fixed)-10} más)_")
    return "\n".join(lines)


def security_healer_loop():
    logger.info("[SecHealer] Loop de auto-corrección iniciado (cada 1h).")
    time.sleep(240)  # pequeño delay post-arranque
    while True:
        try:
            fixed = run_security_healer()
            if fixed:
                msg = _build_healer_discord(fixed)
                if msg:
                    _discord(msg)
        except Exception as e:
            logger.error(f"[SecHealer] Error en loop: {e}")
        time.sleep(HEALER_INTERVAL_SEC)
