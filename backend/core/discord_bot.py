import os
import discord
from dotenv import load_dotenv
import logging
from .db import get_session
from .models import StoreProduct, Store, Price
from sqlalchemy import or_

# Load config
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
# IDs de usuarios autorizados (opcional, lista separada por comas en .env)
# Ejemplo: AUTHORIZED_USER_IDS=123456789,987654321
auth_ids_raw = os.getenv("AUTHORIZED_USER_IDS", "")
AUTHORIZED_USER_IDS = [int(i.strip()) for i in auth_ids_raw.split(",") if i.strip()]

logger = logging.getLogger("AntigravityAPI")

# Configuramos Intents para poder leer mensajes de los usuarios
intents = discord.Intents.default()
intents.message_content = True

bot = discord.Client(intents=intents)

@bot.event
async def on_ready():
    logger.info(f"[KAIROS BOT] Conectado exitosamente a Discord como {bot.user}")
    logger.info(f"[KAIROS BOT] Presente en {len(bot.guilds)} servidores.")
    for guild in bot.guilds:
        logger.info(f" - Servidor: {guild.name} (ID: {guild.id})")
    await bot.change_presence(activity=discord.Game(name="Comparando precios... | !buscar"))

def _is_authorized(author) -> bool:
    """Verifica si el autor del mensaje está en la lista de usuarios autorizados."""
    if not AUTHORIZED_USER_IDS:
        logger.warning("[KAIROS BOT] AUTHORIZED_USER_IDS no configurado — todos los comandos bloqueados.")
        return False  # Fail-secure: sin lista configurada, nadie accede
    return author.id in AUTHORIZED_USER_IDS


@bot.event
async def on_message(message):
    # Evitar que el bot se responda a sí mismo
    if message.author == bot.user:
        return

    content = message.content.strip()

    # Log de entrada para diagnóstico
    if content:
        logger.info(f"[KAIROS BOT] Mensaje recibido de {message.author}: '{content}'")
    else:
        if not message.author.bot:
            logger.warning(f"[KAIROS BOT] Mensaje RECIBIDO de {message.author} pero el CONTENIDO ESTÁ VACÍO. Verifique Message Content Intent.")

    cmd = content.lower()

    # ── !idea ──────────────────────────────────────────────────────────────────
    if cmd.startswith("!idea "):
        if not _is_authorized(message.author):
            await message.channel.send("No tienes permisos para usar este comando.")
            logger.warning(f"[KAIROS BOT] Acceso denegado a !idea para {message.author} (ID: {message.author.id})")
            return
        texto = content[6:].strip()
        if not texto:
            await message.channel.send("Escribe la idea despues del comando. Ejemplo: `!idea Agregar filtro por precio`")
            return
        try:
            from .models import IdeaAdmin
            with get_session() as s:
                idea = IdeaAdmin(idea=texto, source="discord")
                s.add(idea)
                s.flush()
                idea_id = idea.id
                s.commit()
            await message.channel.send(f"Idea #{idea_id} guardada en la BD:\n> {texto[:300]}")
            logger.info(f"[KAIROS BOT] Idea #{idea_id} guardada desde Discord.")
        except Exception as e:
            await message.channel.send(f"Error al guardar idea: {e}")
            logger.error(f"[KAIROS BOT] Error guardando idea: {e}")
        return

    # ── !ideas ─────────────────────────────────────────────────────────────────
    if cmd == "!ideas":
        if not _is_authorized(message.author):
            await message.channel.send("No tienes permisos para usar este comando.")
            return
        try:
            from .models import IdeaAdmin
            from sqlalchemy import desc as _desc
            with get_session() as s:
                rows = s.query(IdeaAdmin).order_by(_desc(IdeaAdmin.created_at)).limit(10).all()
                data = [(r.id, r.status, r.created_at, r.idea) for r in rows]
            if not data:
                await message.channel.send("No hay ideas guardadas aun.")
                return
            lines = [f"**Ultimas {len(data)} ideas:**"]
            for rid, status, created_at, idea in data:
                fecha = created_at.strftime("%d/%m %H:%M") if created_at else "?"
                lines.append(f"`#{rid}` [{status}] {fecha} -- {idea[:120]}")
            await message.channel.send("\n".join(lines))
        except Exception as e:
            await message.channel.send(f"Error: {e}")
        return

    # ── !feedback ──────────────────────────────────────────────────────────────
    if cmd == "!feedback":
        if not _is_authorized(message.author):
            await message.channel.send("No tienes permisos para usar este comando.")
            return
        try:
            from .models import Feedback
            from sqlalchemy import desc as _desc
            with get_session() as s:
                rows = s.query(Feedback).order_by(_desc(Feedback.created_at)).limit(10).all()
                data = [(r.id, r.type, r.status, r.created_at, r.description) for r in rows]
            if not data:
                await message.channel.send("No hay feedback aun.")
                return
            lines = [f"**Ultimos {len(data)} reportes:**"]
            for rid, rtype, status, created_at, desc in data:
                fecha = created_at.strftime("%d/%m %H:%M") if created_at else "?"
                tipo = {"bug": "[BUG]", "mejora": "[MEJORA]", "sugerencia": "[SUGERENCIA]"}.get(rtype, "[?]")
                lines.append(f"`#{rid}` {tipo} [{status}] {fecha}\n  {desc[:100]}")
            await message.channel.send("\n".join(lines))
        except Exception as e:
            await message.channel.send(f"Error: {e}")
        return

    # ── !usuarios ──────────────────────────────────────────────────────────────
    if cmd == "!usuarios":
        if not _is_authorized(message.author):
            await message.channel.send("No tienes permisos para usar este comando.")
            return
        try:
            import time as _time
            from api.routers.auth import _active_sessions
            now = _time.time()
            if not _active_sessions:
                await message.channel.send("No hay usuarios conectados ahora.")
                return
            lines = [f"**Usuarios activos ({len(_active_sessions)}):**"]
            for u, s in _active_sessions.items():
                mins = round((now - s["login_at"]) / 60, 1)
                lines.append(f"- `{u}` conectado hace {mins} min")
            await message.channel.send("\n".join(lines))
        except Exception as e:
            await message.channel.send(f"Error: {e}")
        return

    # !passwords eliminado — exponer contraseñas en Discord es un riesgo de seguridad.
    # Usar Railway Variables directamente para consultar credenciales.

    # ── !stats ─────────────────────────────────────────────────────────────────
    if cmd == "!stats":
        if not _is_authorized(message.author):
            await message.channel.send("No tienes permisos para usar este comando.")
            return
        try:
            from .models import StoreProduct, Feedback, IdeaAdmin
            from sqlalchemy import func as _func
            import time as _time
            with get_session() as s:
                total_p = s.query(_func.count(StoreProduct.id)).scalar()
                oos = s.query(_func.count(StoreProduct.id)).filter(StoreProduct.in_stock == False).scalar()
                pending_fb = s.query(_func.count(Feedback.id)).filter(Feedback.status == "pending").scalar()
                total_ideas = s.query(_func.count(IdeaAdmin.id)).scalar()
            from api.routers.auth import _active_sessions
            activos = len(_active_sessions)
            await message.channel.send(
                f"**Estadisticas FreshCart:**\n"
                f"```\n"
                f"Productos totales  : {total_p:,}\n"
                f"Sin stock          : {oos:,}\n"
                f"Feedback pendiente : {pending_fb}\n"
                f"Ideas guardadas    : {total_ideas}\n"
                f"Usuarios activos   : {activos}\n"
                f"```"
            )
        except Exception as e:
            await message.channel.send(f"Error: {e}")
        return

    # ── !frontend ──────────────────────────────────────────────────────────────
    if cmd.startswith("!frontend"):
        if not _is_authorized(message.author):
            await message.channel.send("No tienes permisos para usar este comando.")
            return
        import requests as _req
        VERCEL_TOKEN      = os.getenv("VERCEL_TOKEN", "")
        VERCEL_PROJECT_ID = os.getenv("VERCEL_PROJECT_ID", "")
        VERCEL_TEAM_ID    = os.getenv("VERCEL_TEAM_ID", "")  # opcional, vacío si cuenta personal
        if not VERCEL_TOKEN or not VERCEL_PROJECT_ID:
            await message.channel.send("VERCEL_TOKEN o VERCEL_PROJECT_ID no configurados.")
            return
        v_headers = {"Authorization": f"Bearer {VERCEL_TOKEN}", "Content-Type": "application/json"}
        team_qs   = f"&teamId={VERCEL_TEAM_ID}" if VERCEL_TEAM_ID else ""
        parts  = content.split()
        action = parts[1].lower() if len(parts) > 1 else "status"

        MAINTENANCE_HTML = """\
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FreshCart &mdash; En Mantenimiento</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{background:#0f172a;color:#e2e8f0;font-family:system-ui,-apple-system,sans-serif;
         min-height:100vh;display:flex;align-items:center;justify-content:center}
    .card{text-align:center;padding:3rem 2rem;max-width:480px}
    .icon{margin-bottom:1.5rem}
    .icon svg{width:80px;height:80px;animation:spin 3s linear infinite}
    @keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}
    h1{font-size:1.9rem;font-weight:700;margin-bottom:.75rem;
       background:linear-gradient(135deg,#38bdf8,#818cf8);
       -webkit-background-clip:text;-webkit-text-fill-color:transparent}
    p{color:#94a3b8;font-size:1rem;line-height:1.6;margin-bottom:1.5rem}
    .badge{display:inline-block;background:#1e293b;border:1px solid #334155;
           color:#38bdf8;font-size:.8rem;padding:.4rem 1rem;border-radius:999px;
           letter-spacing:.05em}
    .dots span{display:inline-block;width:8px;height:8px;border-radius:50%;
               background:#38bdf8;margin:0 3px;
               animation:bounce .8s ease-in-out infinite}
    .dots span:nth-child(2){animation-delay:.15s}
    .dots span:nth-child(3){animation-delay:.3s}
    @keyframes bounce{0%,80%,100%{transform:translateY(0)}40%{transform:translateY(-10px)}}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">
      <svg viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="1.5"
           stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 2a10 10 0 1 0 10 10"/>
        <path d="M12 6v6l4 2"/>
        <path d="M16.5 2.5l1 2.5 2.5 1-2.5 1-1 2.5-1-2.5-2.5-1 2.5-1z"/>
      </svg>
    </div>
    <h1>Estamos mejorando FreshCart</h1>
    <p>El sitio se encuentra temporalmente en mantenimiento.<br>
       Volvemos pronto con novedades.</p>
    <div class="dots" style="margin-bottom:1.5rem">
      <span></span><span></span><span></span>
    </div>
    <span class="badge">&#x1F6CD;&#xFE0F; FreshCart &mdash; Volvemos pronto</span>
  </div>
</body>
</html>"""

        def _vercel_list_deployments(limit: int = 10) -> list:
            r = _req.get(
                f"https://api.vercel.com/v6/deployments?projectId={VERCEL_PROJECT_ID}&limit={limit}&target=production{team_qs}",
                headers=v_headers, timeout=15,
            )
            return r.json().get("deployments", []) if r.status_code == 200 else []

        def _vercel_promote(deploy_id: str) -> int:
            r = _req.post(
                f"https://api.vercel.com/v10/projects/{VERCEL_PROJECT_ID}/promote/{deploy_id}?{team_qs.lstrip('&')}",
                headers=v_headers, timeout=15,
            )
            return r.status_code

        def _vercel_deploy_maintenance(html: str) -> tuple[int, str]:
            """Crea un deploy de mantenimiento en Vercel con un solo archivo index.html."""
            payload = {
                "name": "freshcart-app",
                "files": [{"file": "index.html", "data": html, "encoding": "utf-8"}],
                "projectSettings": {"buildCommand": "", "outputDirectory": "", "framework": None},
                "target": "production",
            }
            r = _req.post(
                f"https://api.vercel.com/v13/deployments?{team_qs.lstrip('&')}",
                headers=v_headers,
                json=payload,
                timeout=30,
            )
            data = r.json()
            deploy_id = data.get("id", "")
            return r.status_code, deploy_id

        def _vercel_wait_ready(deploy_id: str, timeout_s: int = 60) -> bool:
            """Espera hasta que el deploy esté en estado READY."""
            import time as _time
            deadline = _time.time() + timeout_s
            while _time.time() < deadline:
                r = _req.get(
                    f"https://api.vercel.com/v13/deployments/{deploy_id}?{team_qs.lstrip('&')}",
                    headers=v_headers, timeout=10,
                )
                state = r.json().get("status") or r.json().get("readyState", "")
                if state in ("READY", "ready"):
                    return True
                if state in ("ERROR", "CANCELED"):
                    return False
                _time.sleep(3)
            return False

        try:
            if action == "off":
                # Guardar el deploy actual antes de reemplazarlo
                deploys = _vercel_list_deployments(5)
                prev_id = deploys[0]["uid"] if deploys else "desconocido"

                await message.channel.send("⏳ Desplegando página de mantenimiento...")
                status, new_id = _vercel_deploy_maintenance(MAINTENANCE_HTML)
                if status in (200, 201) and new_id:
                    ready = _vercel_wait_ready(new_id)
                    if ready:
                        await message.channel.send(
                            f"🔴 Frontend **desactivado**. Página de mantenimiento activa.\n"
                            f"`!frontend on` para restaurar (deploy anterior: `{prev_id[:16]}`)"
                        )
                        logger.info(f"[KAIROS BOT] Frontend desactivado. Deploy mantenimiento: {new_id}")
                    else:
                        await message.channel.send(f"⚠️ Deploy creado (`{new_id[:16]}`) pero tardó demasiado en estar listo. Verifica en Vercel.")
                else:
                    await message.channel.send(f"Error al desactivar: HTTP {status}")

            elif action == "on":
                deploys = _vercel_list_deployments(15)
                # Saltar el deploy actual (index 0) y buscar el primero con meta de git (app real)
                # Los deploys de mantenimiento no tienen gitSource ni commitMessage
                restore_dep = None
                for dep in deploys[1:]:
                    if dep.get("meta", {}).get("githubCommitSha") or dep.get("meta", {}).get("gitlabCommitSha") or dep.get("name") == "freshcart-app" and dep.get("meta"):
                        restore_dep = dep
                        break
                # Fallback: tomar simplemente el segundo deploy disponible
                if not restore_dep and len(deploys) > 1:
                    restore_dep = deploys[1]

                if not restore_dep:
                    await message.channel.send("No se encontró un deploy anterior para restaurar.")
                    return

                restore_id = restore_dep["uid"]
                await message.channel.send("⏳ Restaurando deploy anterior...")
                status = _vercel_promote(restore_id)
                if status in (200, 201, 204):
                    ready = _vercel_wait_ready(restore_id)
                    if ready:
                        await message.channel.send(f"🟢 Frontend **activado**. Deploy `{restore_id[:16]}` activo en producción.")
                    else:
                        await message.channel.send(f"⚠️ Promote enviado pero el deploy tardó. Verifica en Vercel.")
                    logger.info(f"[KAIROS BOT] Frontend restaurado al deploy {restore_id}")
                else:
                    await message.channel.send(f"Error al activar: HTTP {status}")

            else:  # status
                deploys = _vercel_list_deployments(1)
                if deploys:
                    dep   = deploys[0]
                    uid   = dep.get("uid", "N/A")[:16]
                    state = dep.get("state", "N/A")
                    url   = dep.get("url", "N/A")
                else:
                    uid, state, url = "N/A", "N/A", "N/A"
                await message.channel.send(
                    f"**Estado del Frontend (Vercel):**\n"
                    f"```\n"
                    f"URL    : https://{url}\n"
                    f"State  : {state}\n"
                    f"Deploy : {uid}\n"
                    f"```\n"
                    f"Usa `!frontend off` para mantenimiento o `!frontend on` para restaurar."
                )
        except Exception as e:
            await message.channel.send(f"Error al contactar Vercel: {e}")
            logger.error(f"[KAIROS BOT] Error en !frontend: {e}")
        return

    # ── !db ────────────────────────────────────────────────────────────────────
    if cmd.startswith("!db"):
        if not _is_authorized(message.author):
            await message.channel.send("No tienes permisos para usar este comando.")
            return
        from core.db_lock import is_locked, set_locked
        parts  = content.split()
        action = parts[1].lower() if len(parts) > 1 else "status"

        try:
            if action == "off":
                set_locked(True)
                await message.channel.send(
                    "🔴 **Base de datos bloqueada.** La API rechaza todas las peticiones.\n"
                    "Usa `!db on` para reactivar."
                )
                logger.warning("[KAIROS BOT] BD bloqueada por comando Discord.")

            elif action == "on":
                set_locked(False)
                await message.channel.send("🟢 **Base de datos desbloqueada.** La API vuelve a operar con normalidad.")
                logger.info("[KAIROS BOT] BD desbloqueada por comando Discord.")

            else:  # status
                locked = is_locked()
                estado = "🔴 Bloqueada (modo emergencia)" if locked else "🟢 Activa — operando con normalidad"
                await message.channel.send(
                    f"**Estado de la BD:**\n```\n{estado}\n```\n"
                    f"Usa `!db off` para bloquear o `!db on` para desbloquear."
                )
        except Exception as e:
            await message.channel.send(f"Error en !db: {e}")
            logger.error(f"[KAIROS BOT] Error en !db: {e}")
        return

    # ── !qa ────────────────────────────────────────────────────────────────────
    if cmd == "!qa":
        if not _is_authorized(message.author):
            await message.channel.send("No tienes permisos para usar este comando.")
            return
        await message.channel.send("Iniciando revision de integridad... (puede tardar unos segundos)")
        try:
            from agents.qa_agent import run_qa_checks, _discord_report
            import asyncio
            loop = asyncio.get_event_loop()
            issues = await loop.run_in_executor(None, run_qa_checks)
            _discord_report(issues)
        except Exception as e:
            await message.channel.send(f"Error al ejecutar QA: {e}")
            logger.error(f"[KAIROS BOT] Error en !qa: {e}")
        return

    # ── !heal ──────────────────────────────────────────────────────────────────
    if cmd == "!heal":
        if not _is_authorized(message.author):
            await message.channel.send("No tienes permisos para usar este comando.")
            return
        await message.channel.send("Iniciando auto-corrección de BD... (puede tardar unos segundos)")
        try:
            from agents.self_healer import run_self_healer, _discord_summary
            import asyncio
            results = await asyncio.get_event_loop().run_in_executor(None, run_self_healer)
            _discord_summary(results)
        except Exception as e:
            await message.channel.send(f"Error en heal: {e}")
            logger.error(f"[KAIROS BOT] Error en !heal: {e}")
        return

    # ── !sync ──────────────────────────────────────────────────────────────────
    if cmd.startswith("!sync"):
        if not _is_authorized(message.author):
            await message.channel.send("No tienes permisos para usar este comando.")
            return
        VALID_STORES = ["jumbo", "santa_isabel", "lider", "unimarc"]
        parts = content.split()
        store = parts[1].lower() if len(parts) > 1 else ""
        if store not in VALID_STORES:
            await message.channel.send(
                f"Tienda no reconocida. Usa: `!sync jumbo` | `!sync santa_isabel` | `!sync lider` | `!sync unimarc`"
            )
            return
        await message.channel.send(f"Iniciando resync de **{store}**... (tarda varios minutos)")
        try:
            from agents.catalog_sync_scheduler import sync_store, _discord_report
            import asyncio
            stats = await asyncio.get_event_loop().run_in_executor(None, sync_store, store)
            _discord_report(stats)
        except Exception as e:
            await message.channel.send(f"Error en sync: {e}")
            logger.error(f"[KAIROS BOT] Error en !sync: {e}")
        return

    # ── !security ──────────────────────────────────────────────────────────────
    if cmd == "!security":
        if not _is_authorized(message.author):
            await message.channel.send("No tienes permisos para usar este comando.")
            return
        try:
            from core.db import get_session
            from core.models import SecurityReport
            with get_session() as db:
                reports = (
                    db.query(SecurityReport)
                    .filter(SecurityReport.fixed == False)
                    .order_by(SecurityReport.created_at.desc())
                    .limit(20)
                    .all()
                )
                total_fixed = db.query(SecurityReport).filter(SecurityReport.fixed == True).count()

            if not reports:
                await message.channel.send(
                    f"✅ **Sin reportes de seguridad pendientes.** ({total_fixed} corregidos en total)"
                )
                return

            sev_emoji = {"CRITICAL": "🚨", "HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🔵", "INFO": "ℹ️"}
            lines = [f"🔒 **Reportes de seguridad pendientes** ({len(reports)}) — {total_fixed} ya corregidos", ""]
            for r in reports:
                emoji = sev_emoji.get(r.severity, "⚪")
                fix_tag = " `[auto-fix pendiente]`" if r.auto_fixable else ""
                lines.append(f"{emoji} **[{r.severity}] {r.category}** — {r.title}{fix_tag}")
                lines.append(f"  └ {r.description[:120]}{'...' if len(r.description) > 120 else ''}")
            await message.channel.send("\n".join(lines)[:1900])
        except Exception as e:
            await message.channel.send(f"Error al consultar reportes: {e}")
        return

    # ── !cb ────────────────────────────────────────────────────────────────────
    if cmd == "!cb":
        if not _is_authorized(message.author):
            await message.channel.send("No tienes permisos para usar este comando.")
            return
        try:
            from core.circuit_breaker import get_all_status
            status = get_all_status()
            if not status:
                await message.channel.send("No hay datos de circuit breakers aún (ninguna tienda ha sido monitoreada).")
                return
            icons = {"closed": "🟢", "open": "🔴", "half_open": "🟡"}
            lines = ["**Circuit Breakers — Estado de tiendas:**", "```"]
            for store, info in status.items():
                icon  = icons.get(info["state"], "⚪")
                state = info["state"].upper()
                fails = info["failures"]
                extra = f" — recupera en {info['recovers_in_min']}min" if info.get("recovers_in_min") else ""
                lines.append(f"{icon} {store:<15} {state:<10} fallos: {fails}{extra}")
            lines.append("```")
            await message.channel.send("\n".join(lines))
        except Exception as e:
            await message.channel.send(f"Error al consultar circuit breakers: {e}")
        return

    # ── !pin ───────────────────────────────────────────────────────────────────
    if cmd == "!pin":
        if not _is_authorized(message.author):
            await message.channel.send("No tienes permisos para usar este comando.")
            return
        MENU = (
            "**KAIROS Bot — Comandos disponibles**\n"
            "```\n"
            "── Información ──────────────────────────────\n"
            "!stats              → Estadísticas del sistema\n"
            "!usuarios           → Lista de usuarios registrados\n"
            "!feedback           → Últimos reportes de usuarios\n"
            "!ideas              → Ideas registradas\n"
            "!idea <texto>       → Guardar una nueva idea\n"
            "!buscar <producto>  → Buscar producto en el catálogo\n"
            "\n"
            "── Frontend (Vercel) ─────────────────────────\n"
            "!frontend off       → Activar página de mantenimiento\n"
            "!frontend on        → Restaurar app en producción\n"
            "!frontend status    → Ver estado actual del frontend\n"
            "\n"
            "── Base de datos (Railway) ───────────────────\n"
            "!db off             → Apagar BD (emergencia de seguridad)\n"
            "!db on              → Reactivar BD\n"
            "!db status          → Ver estado actual de la BD\n"
            "\n"
            "── Mantenimiento ─────────────────────────────\n"
            "!qa                 → Revisión manual de integridad de datos\n"
            "!heal               → Auto-corregir problemas en la BD\n"
            "!sync <tienda>      → Resync manual (jumbo/lider/unimarc/santa_isabel)\n"
            "!cb                 → Estado de circuit breakers por tienda\n"
            "!security           → Ver reportes de seguridad pendientes\n"
            "\n"
            "── Utilidades ────────────────────────────────\n"
            "!pin                → Fijar este menú en el canal\n"
            "!help               → Mostrar este menú\n"
            "```\n"
            "> Todos los comandos requieren autorización de administrador."
        )
        try:
            sent = await message.channel.send(MENU)
            await sent.pin()
            await message.delete()
        except discord.Forbidden:
            await message.channel.send(
                "No pude fijar el mensaje. Dale al bot el permiso **Gestionar mensajes** en el servidor."
            )
        return

    # ── !help ──────────────────────────────────────────────────────────────────
    if cmd == "!help":
        await message.channel.send(
            "**KAIROS Bot — Comandos disponibles:**\n"
            "```\n"
            "── Información ──────────────────────────────\n"
            "!stats              -> Estadisticas del sistema\n"
            "!usuarios           -> Lista de usuarios registrados\n"
            "!feedback           -> Ultimos reportes de usuarios\n"
            "!ideas              -> Ideas registradas\n"
            "!idea <texto>       -> Guardar una nueva idea\n"
            "!buscar <producto>  -> Buscar producto en el catalogo\n"
            "\n"
            "── Frontend (Vercel) ─────────────────────────\n"
            "!frontend off       -> Activar pagina de mantenimiento\n"
            "!frontend on        -> Restaurar app en produccion\n"
            "!frontend status    -> Ver estado actual del frontend\n"
            "\n"
            "── Base de datos (Railway) ───────────────────\n"
            "!db off             -> Apagar BD (emergencia de seguridad)\n"
            "!db on              -> Reactivar BD\n"
            "!db status          -> Ver estado actual de la BD\n"
            "\n"
            "── Mantenimiento ─────────────────────────────\n"
            "!qa                 -> Revision manual de integridad de datos\n"
            "!heal               -> Auto-corregir problemas en la BD\n"
            "!sync <tienda>      -> Resync manual (jumbo/lider/unimarc/santa_isabel)\n"
            "!cb                 -> Estado de circuit breakers por tienda\n"
            "!security           -> Ver reportes de seguridad pendientes\n"
            "\n"
            "── Utilidades ────────────────────────────────\n"
            "!pin                -> Fijar menu en el canal\n"
            "!help               -> Mostrar este menu\n"
            "```"
        )
        return

    if content.lower().startswith("!buscar "):
        try:
            query = content[8:].strip()
            if not query:
                await message.channel.send("❌ Debes escribir algo. Ejemplo: `!buscar lactuca`")
                return
            
            # Verificación de autorización (si está configurada)
            if AUTHORIZED_USER_IDS and message.author.id not in AUTHORIZED_USER_IDS:
                logger.warning(f"[KAIROS BOT] Intento de uso No Autorizado de {message.author} (ID: {message.author.id})")
                await message.channel.send("🚫 No tienes permisos para usar este comando.")
                return
                
            await message.channel.send(f"🔍 Evaluando el catálogo buscando: **{query}**...")
            logger.info(f"[KAIROS BOT] Ejecutando búsqueda para: {query}")
            
            # Ejecutar busqueda en BD bloqueante en un contexto de sesión
            results = search_products_in_db(query)
            
            if not results:
                await message.channel.send(f"🪙 No encontré productos similares a `{query}` en el Catálogo de FreshCart.")
                return

            embed = discord.Embed(
                title=f"Resultados para '{query}'",
                color=0x00f076,
                description="Aquí tienes las opciones más baratas actualmente:"
            )

            for res in results:
                store_name = res['store']
                prod_name = res['name']
                price = f"${int(res['price']):,}".replace(",", ".")
                
                # Formatear el markdown
                embed.add_field(
                    name=f"{store_name} | {price}",
                    value=f"_{prod_name}_",
                    inline=False
                )
                
            embed.set_footer(text="KAIROS Asistente de Compras • Precios en vivo")
            
            await message.channel.send(embed=embed)
            logger.info(f"[KAIROS BOT] Respuesta enviada con éxito para {query}")
            
        except Exception as e:
            logger.error(f"❌ [KAIROS BOT] Error procesando comando !buscar: {e}")
            await message.channel.send("⚠️ Lo siento, ocurrió un error interno al buscar en el catálogo.")
            import traceback
            logger.error(traceback.format_exc())

def search_products_in_db(query_term: str, limit=5):
    """Busca en SQLite los StoreProducts con los precios más bajos y en stock."""
    from sqlalchemy.orm import joinedload
    
    with get_session() as db:
        # Búsqueda ILIKE (no distingue mayúsculas/minúsculas)
        search_pattern = f"%{query_term}%"
        
        products = db.query(StoreProduct).join(Store).outerjoin(Price).filter(
            StoreProduct.in_stock == True,
            StoreProduct.name.ilike(search_pattern)
        ).order_by(Price.price.asc()).limit(limit).all()
        
        results = []
        for p in products:
            latest_price = p.latest_price.price if p.latest_price else 0
            if latest_price > 0:
                results.append({
                    "store": p.store.name,
                    "name": p.name,
                    "price": latest_price
                })
                
        return results
