"""
Security Audit Agent
====================
Escanea el sistema cada 6h buscando vulnerabilidades, configuraciones
inseguras y patrones de ataque. Guarda hallazgos en security_reports (BD)
y notifica a Discord con resumen por severidad.

Categorías de checks:
  AUTH     — fuerza bruta, tokens débiles, endpoints sin proteger
  CONFIG   — variables mal configuradas, docs expuestos, CORS permisivo
  EXPOSURE — datos sensibles en logs/respuestas, secretos hardcodeados
  INJECTION — patrones SQL/path en logs de seguridad
  INFRA    — IPs bloqueadas en honeytoken, Shield activo, rate limiting
"""

import os
import re
import time
import logging
import threading
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("AntigravityAPI")
UTC = timezone.utc

DISCORD_WEBHOOK    = os.getenv("DISCORD_WEBHOOK_URL", "")
AUDIT_INTERVAL_SEC = int(os.getenv("SECURITY_AUDIT_INTERVAL_HOURS", "6")) * 3600

SEVERITY_EMOJI = {
    "CRITICAL": "🚨",
    "HIGH":     "🔴",
    "MEDIUM":   "🟡",
    "LOW":      "🔵",
    "INFO":     "ℹ️",
}


def _discord(msg: str) -> None:
    if not DISCORD_WEBHOOK:
        return
    try:
        import requests as _r
        _r.post(DISCORD_WEBHOOK, json={"content": msg[:1900]}, timeout=10)
    except Exception as e:
        logger.warning(f"[SecAudit] Discord send failed: {e}")


def _save_report(db, severity, category, title, description, affected="", auto_fixable=False):
    from core.models import SecurityReport
    # Evitar duplicados del mismo hallazgo en menos de 24h
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    existing = db.query(SecurityReport).filter(
        SecurityReport.title == title,
        SecurityReport.fixed == False,
        SecurityReport.created_at >= cutoff,
    ).first()
    if existing:
        return None
    report = SecurityReport(
        severity=severity, category=category, title=title,
        description=description, affected=affected, auto_fixable=auto_fixable,
    )
    db.add(report)
    db.flush()
    return report


# ---------------------------------------------------------------------------
# Checks individuales
# ---------------------------------------------------------------------------

def check_config(db) -> list:
    """Verifica configuraciones de seguridad del entorno."""
    findings = []
    env = os.getenv

    # Docs expuestos en producción
    environment = env("ENVIRONMENT", "").lower()
    if environment == "development":
        findings.append(_save_report(db, "MEDIUM", "CONFIG",
            "Modo development activo en Railway",
            "La variable ENVIRONMENT='development' expone /docs y /redoc en producción. "
            "Cambiar a 'production' o eliminar la variable.",
            affected="FastAPI docs", auto_fixable=False))

    # API Key débil
    api_key = env("API_KEY", "")
    if api_key and len(api_key) < 20:
        findings.append(_save_report(db, "HIGH", "CONFIG",
            "API_KEY demasiado corta",
            f"La API_KEY tiene solo {len(api_key)} caracteres. Recomendado: mínimo 32.",
            affected="API_KEY", auto_fixable=False))

    # Admin password débil
    admin_pw = env("ADMIN_PASSWORD", "")
    if admin_pw and len(admin_pw) < 12:
        findings.append(_save_report(db, "HIGH", "AUTH",
            "ADMIN_PASSWORD demasiado corta",
            f"La contraseña admin tiene {len(admin_pw)} caracteres. Mínimo recomendado: 16.",
            affected="ADMIN_PASSWORD", auto_fixable=False))

    # JWT secret débil
    jwt_secret = env("JWT_SECRET", env("SECRET_KEY", ""))
    if jwt_secret and len(jwt_secret) < 32:
        findings.append(_save_report(db, "CRITICAL", "AUTH",
            "JWT_SECRET inseguro — demasiado corto",
            f"El JWT_SECRET tiene {len(jwt_secret)} caracteres. Un secreto corto es fácil de bruteforcear. "
            "Generar uno nuevo con: python -c \"import secrets; print(secrets.token_hex(32))\"",
            affected="JWT_SECRET", auto_fixable=False))

    # CORS muy permisivo
    extra_origins = env("ALLOWED_ORIGINS", "")
    if "*" in extra_origins:
        findings.append(_save_report(db, "HIGH", "CONFIG",
            "CORS con wildcard (*) detectado",
            "ALLOWED_ORIGINS contiene '*', permitiendo requests desde cualquier origen.",
            affected="CORS", auto_fixable=False))

    # Netlify token expuesto (ya no necesario)
    if env("NETLIFY_TOKEN", ""):
        findings.append(_save_report(db, "LOW", "EXPOSURE",
            "NETLIFY_TOKEN definido pero ya no se usa",
            "La variable NETLIFY_TOKEN existe en el entorno pero el proyecto migró a Vercel. "
            "Eliminarla reduce la superficie de exposición.",
            affected="NETLIFY_TOKEN", auto_fixable=False))

    return [f for f in findings if f]


def check_brute_force(db) -> list:
    """Detecta patrones de fuerza bruta en SecurityLog."""
    from core.models import SecurityLog
    from sqlalchemy import text
    findings = []
    cutoff = datetime.now(UTC) - timedelta(hours=6)

    # IPs con >20 fallos de auth en las últimas 6h
    rows = db.execute(text("""
        SELECT ip, COUNT(*) as cnt
        FROM security_logs
        WHERE event_type IN ('AUTH_FAILURE', 'RATE_LIMIT')
          AND created_at >= :cutoff
          AND ip IS NOT NULL
        GROUP BY ip
        HAVING COUNT(*) > 20
        ORDER BY cnt DESC
        LIMIT 10
    """), {"cutoff": cutoff}).fetchall()

    for row in rows:
        findings.append(_save_report(db, "HIGH", "AUTH",
            f"Posible fuerza bruta desde {row.ip}",
            f"La IP {row.ip} generó {row.cnt} eventos de auth/rate-limit en las últimas 6h.",
            affected=row.ip, auto_fixable=True))

    return [f for f in findings if f]


def check_injection_patterns(db) -> list:
    """Busca intentos de inyección en los logs de seguridad."""
    from core.models import SecurityLog
    findings = []
    cutoff = datetime.now(UTC) - timedelta(hours=24)

    sql_patterns = [r"union.*select", r"drop\s+table", r"insert\s+into",
                    r"exec\s*\(", r"xp_cmdshell", r"--\s*$"]
    path_patterns = [r"\.\./", r"etc/passwd", r"\.env", r"wp-admin"]

    logs = db.query(SecurityLog).filter(
        SecurityLog.created_at >= cutoff,
        SecurityLog.event_type == "THREAT"
    ).limit(500).all()

    sql_hits = path_hits = 0
    offending_ips = set()

    for log in logs:
        detail = (log.details or "").lower()
        for p in sql_patterns:
            if re.search(p, detail):
                sql_hits += 1
                offending_ips.add(log.ip)
        for p in path_patterns:
            if re.search(p, detail):
                path_hits += 1
                offending_ips.add(log.ip)

    if sql_hits > 0:
        findings.append(_save_report(db, "HIGH", "INJECTION",
            f"Intentos de SQL injection detectados ({sql_hits} en 24h)",
            f"IPs involucradas: {', '.join(list(offending_ips)[:5])}. "
            "Revisar logs de seguridad para detalle.",
            affected="security_logs", auto_fixable=True))

    if path_hits > 0:
        findings.append(_save_report(db, "MEDIUM", "INJECTION",
            f"Intentos de path traversal detectados ({path_hits} en 24h)",
            f"Se detectaron intentos de acceder a rutas sensibles (.env, etc/passwd, wp-admin). "
            f"IPs: {', '.join(list(offending_ips)[:5])}",
            affected="security_logs", auto_fixable=True))

    return [f for f in findings if f]


def check_honeytoken_hits(db) -> list:
    """Detecta accesos recientes al honeytoken."""
    from core.models import SecurityLog, BlockedIP
    findings = []
    cutoff = datetime.now(UTC) - timedelta(hours=24)

    hits = db.query(SecurityLog).filter(
        SecurityLog.event_type == "HONEYTOKEN",
        SecurityLog.created_at >= cutoff,
    ).count()

    if hits > 0:
        findings.append(_save_report(db, "CRITICAL", "INFRA",
            f"Honeytoken activado {hits} veces en 24h",
            "Alguien está escaneando endpoints internos (/api/admin/config/...). "
            "Las IPs ya fueron bloqueadas automáticamente por el Shield.",
            affected="/api/admin/config/v1/internal_metrics", auto_fixable=False))

    # IPs bloqueadas en las últimas 24h
    new_blocks = db.query(BlockedIP).filter(
        BlockedIP.blocked_at >= cutoff
    ).count()

    if new_blocks >= 5:
        findings.append(_save_report(db, "MEDIUM", "INFRA",
            f"{new_blocks} IPs nuevas bloqueadas en las últimas 24h",
            "Actividad inusualmente alta de bloqueos. Podría indicar un scan coordinado.",
            affected="Shield3", auto_fixable=False))

    return [f for f in findings if f]


def check_stale_blocked_ips(db) -> list:
    """Detecta si la tabla blocked_ips está creciendo sin control."""
    from core.models import BlockedIP
    findings = []
    total = db.query(BlockedIP).count()
    if total > 1000:
        findings.append(_save_report(db, "LOW", "INFRA",
            f"Tabla blocked_ips con {total} registros",
            "La lista de IPs bloqueadas es muy grande. Considera limpiar entradas antiguas (>30 días) "
            "para mejorar el rendimiento del Shield.",
            affected="blocked_ips", auto_fixable=True))
    return [f for f in findings if f]


# ---------------------------------------------------------------------------
# Runner principal
# ---------------------------------------------------------------------------

def run_security_audit() -> list:
    """Ejecuta todos los checks y guarda los hallazgos en la BD."""
    from core.db import get_session
    logger.info("[SecAudit] Iniciando auditoría de seguridad...")

    all_findings = []
    with get_session() as db:
        try:
            all_findings += check_config(db)
            all_findings += check_brute_force(db)
            all_findings += check_injection_patterns(db)
            all_findings += check_honeytoken_hits(db)
            all_findings += check_stale_blocked_ips(db)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"[SecAudit] Error durante auditoría: {e}")

    logger.info(f"[SecAudit] Auditoría completada: {len(all_findings)} hallazgos nuevos.")
    return all_findings


def _build_discord_report(findings: list) -> str:
    if not findings:
        return "✅ **[SecAudit] Sin hallazgos nuevos** — sistema limpio."

    by_sev = {"CRITICAL": [], "HIGH": [], "MEDIUM": [], "LOW": [], "INFO": []}
    for f in findings:
        by_sev.get(f.severity, by_sev["INFO"]).append(f)

    lines = ["🔒 **KAIROS Security Audit — Nuevos Hallazgos**"]
    for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]:
        items = by_sev[sev]
        if not items:
            continue
        emoji = SEVERITY_EMOJI[sev]
        lines.append(f"\n{emoji} **{sev}** ({len(items)})")
        for f in items[:3]:
            fix_tag = " `[auto-fix]`" if f.auto_fixable else ""
            lines.append(f"  • {f.title}{fix_tag}")
        if len(items) > 3:
            lines.append(f"  _(+{len(items)-3} más)_")

    lines.append("\nUsa `!security` en Discord para ver el reporte completo.")
    return "\n".join(lines)


def security_audit_loop():
    logger.info("[SecAudit] Loop de auditoría de seguridad iniciado (cada 6h).")
    time.sleep(180)  # esperar arranque
    while True:
        try:
            findings = run_security_audit()
            if findings:
                _discord(_build_discord_report(findings))
        except Exception as e:
            logger.error(f"[SecAudit] Error en loop: {e}")
        time.sleep(AUDIT_INTERVAL_SEC)
