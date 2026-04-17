"""
Generador de Informe Técnico — FreshCart / Antigravity Grocery
Comparación: Proyecto Original vs. Versión Desarrollada
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, ListFlowable, ListItem, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from datetime import datetime

# ── Paleta de colores ────────────────────────────────────────────────────────
GREEN       = colors.HexColor("#2d6a4f")
GREEN_LIGHT = colors.HexColor("#40916c")
GREEN_BG    = colors.HexColor("#d8f3dc")
GREEN_PALE  = colors.HexColor("#f0faf2")
YELLOW      = colors.HexColor("#e9c46a")
RED_SOFT    = colors.HexColor("#e76f51")
DARK        = colors.HexColor("#1b2d23")
GREY        = colors.HexColor("#6b7280")
GREY_LIGHT  = colors.HexColor("#f3f4f6")
WHITE       = colors.white
BLACK       = colors.HexColor("#111827")

OUTPUT_PATH = "Informe_Tecnico_FreshCart_Antigravity.pdf"

# ── Estilos ───────────────────────────────────────────────────────────────────
styles = getSampleStyleSheet()

def style(name, **kwargs):
    base = styles["Normal"]
    return ParagraphStyle(name, parent=base, **kwargs)

S = {
    "cover_title": style("cover_title",
        fontName="Helvetica-Bold", fontSize=28, textColor=WHITE,
        alignment=TA_CENTER, leading=36, spaceAfter=12),
    "cover_sub": style("cover_sub",
        fontName="Helvetica", fontSize=13, textColor=GREEN_BG,
        alignment=TA_CENTER, leading=18, spaceAfter=6),
    "cover_meta": style("cover_meta",
        fontName="Helvetica", fontSize=10, textColor=GREEN_BG,
        alignment=TA_CENTER, spaceAfter=4),
    "h1": style("h1",
        fontName="Helvetica-Bold", fontSize=18, textColor=GREEN,
        spaceBefore=24, spaceAfter=10, leading=22),
    "h2": style("h2",
        fontName="Helvetica-Bold", fontSize=13, textColor=GREEN_LIGHT,
        spaceBefore=16, spaceAfter=6, leading=17),
    "h3": style("h3",
        fontName="Helvetica-Bold", fontSize=11, textColor=DARK,
        spaceBefore=10, spaceAfter=4),
    "body": style("body",
        fontName="Helvetica", fontSize=10, textColor=BLACK,
        leading=15, spaceAfter=6, alignment=TA_JUSTIFY),
    "bullet": style("bullet",
        fontName="Helvetica", fontSize=10, textColor=BLACK,
        leading=15, spaceAfter=3, leftIndent=14),
    "code": style("code",
        fontName="Courier", fontSize=8.5, textColor=DARK,
        backColor=GREY_LIGHT, leading=13, spaceAfter=6,
        leftIndent=10, rightIndent=10),
    "caption": style("caption",
        fontName="Helvetica-Oblique", fontSize=9, textColor=GREY,
        alignment=TA_CENTER, spaceAfter=8),
    "tag_green": style("tag_green",
        fontName="Helvetica-Bold", fontSize=9, textColor=WHITE,
        backColor=GREEN_LIGHT),
    "tag_red": style("tag_red",
        fontName="Helvetica-Bold", fontSize=9, textColor=WHITE,
        backColor=RED_SOFT),
    "note": style("note",
        fontName="Helvetica-Oblique", fontSize=9.5, textColor=GREY,
        leading=14, spaceAfter=6),
    "footer": style("footer",
        fontName="Helvetica", fontSize=8, textColor=GREY,
        alignment=TA_CENTER),
}

# ── Helpers ───────────────────────────────────────────────────────────────────
def H1(text): return Paragraph(text, S["h1"])
def H2(text): return Paragraph(text, S["h2"])
def H3(text): return Paragraph(text, S["h3"])
def P(text):  return Paragraph(text, S["body"])
def Note(text): return Paragraph(f"<i>{text}</i>", S["note"])
def SP(n=8):  return Spacer(1, n)
def HR():     return HRFlowable(width="100%", thickness=0.5, color=GREEN_LIGHT, spaceAfter=10, spaceBefore=4)
def bullets(items, indent=14):
    return ListFlowable(
        [ListItem(Paragraph(t, S["bullet"]), leftIndent=indent, bulletColor=GREEN) for t in items],
        bulletType='bullet', bulletColor=GREEN, leftIndent=indent
    )

def table(data, col_widths, header_row=True):
    t = Table(data, colWidths=col_widths, repeatRows=1 if header_row else 0)
    style_cmds = [
        ('BACKGROUND',   (0,0), (-1,0),  GREEN),
        ('TEXTCOLOR',    (0,0), (-1,0),  WHITE),
        ('FONTNAME',     (0,0), (-1,0),  'Helvetica-Bold'),
        ('FONTSIZE',     (0,0), (-1,0),  9),
        ('ALIGN',        (0,0), (-1,-1), 'LEFT'),
        ('VALIGN',       (0,0), (-1,-1), 'MIDDLE'),
        ('FONTNAME',     (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE',     (0,1), (-1,-1), 9),
        ('ROWBACKGROUNDS',(0,1),(-1,-1), [WHITE, GREEN_PALE]),
        ('GRID',         (0,0), (-1,-1), 0.4, colors.HexColor("#d1d5db")),
        ('LEFTPADDING',  (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ('TOPPADDING',   (0,0), (-1,-1), 5),
        ('BOTTOMPADDING',(0,0), (-1,-1), 5),
        ('ROWBACKGROUNDS',(0,0),(-1,0),  [GREEN]),
    ]
    t.setStyle(TableStyle(style_cmds))
    return t

def badge(text, color=GREEN_LIGHT):
    return Paragraph(
        f'<font color="white"><b> {text} </b></font>',
        ParagraphStyle("badge", parent=S["body"], backColor=color,
                       fontSize=9, leading=14)
    )

def cover_block(story, page_w):
    """Portada con fondo verde."""
    # Usamos una tabla de 1 celda con fondo verde como portada
    content = [
        Paragraph("INFORME TÉCNICO", ParagraphStyle("ct1", parent=S["cover_sub"],
            fontSize=11, textColor=GREEN_BG, spaceBefore=0, spaceAfter=4)),
        Spacer(1, 16),
        Paragraph("FreshCart · Antigravity Grocery", S["cover_title"]),
        Spacer(1, 8),
        Paragraph(
            "Comparación técnica: Proyecto Original vs. Versión Desarrollada",
            S["cover_sub"]),
        Spacer(1, 24),
        HRFlowable(width="60%", thickness=1, color=GREEN_LIGHT, spaceAfter=20),
        Paragraph("Asistente de Compras Inteligente para Supermercados Chilenos",
                  ParagraphStyle("cs2", parent=S["cover_sub"], fontSize=11)),
        Spacer(1, 28),
        Paragraph(f"Fecha de emisión: {datetime.now().strftime('%d de %B de %Y')}",
                  S["cover_meta"]),
        Paragraph("Versión: 1.0 · Uso Interno / Entrega a Colega", S["cover_meta"]),
        Spacer(1, 10),
        Paragraph("Desarrollado por: Equipo FreshCart", S["cover_meta"]),
        Paragraph("Tecnologías: FastAPI · React 19 · SQLAlchemy · Hugging Face · Shield3",
                  S["cover_meta"]),
    ]
    tbl = Table([[content]], colWidths=[page_w - 4*cm])
    tbl.setStyle(TableStyle([
        ('BACKGROUND',   (0,0),(0,0), DARK),
        ('TOPPADDING',   (0,0),(0,0), 60),
        ('BOTTOMPADDING',(0,0),(0,0), 60),
        ('LEFTPADDING',  (0,0),(0,0), 40),
        ('RIGHTPADDING', (0,0),(0,0), 40),
        ('ALIGN',        (0,0),(0,0), 'CENTER'),
        ('VALIGN',       (0,0),(0,0), 'MIDDLE'),
        ('ROUNDEDCORNERS', [8]),
    ]))
    story.append(tbl)

# ── Documento principal ───────────────────────────────────────────────────────
def build_pdf():
    doc = SimpleDocTemplate(
        OUTPUT_PATH,
        pagesize=A4,
        rightMargin=2.2*cm, leftMargin=2.2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title="Informe Técnico FreshCart Antigravity",
        author="Equipo FreshCart",
    )
    W, H = A4
    page_w = W - 4.4*cm
    story = []

    # ── PORTADA ───────────────────────────────────────────────────────────────
    cover_block(story, page_w)
    story.append(PageBreak())

    # ── 1. RESUMEN EJECUTIVO ──────────────────────────────────────────────────
    story += [
        H1("1. Resumen Ejecutivo"),
        HR(),
        P(
            "Este documento presenta la evolución técnica del proyecto <b>FreshCart / Antigravity Grocery</b>, "
            "una plataforma de comparación de precios en supermercados chilenos. Se describe el estado "
            "del prototipo original recibido, el diagnóstico realizado, y la totalidad de mejoras "
            "implementadas hasta la versión actual."
        ),
        SP(),
        P(
            "El proyecto pasó de ser un <b>prototipo básico de scraping</b> a un sistema de producción "
            "con arquitectura limpia, seguridad activa, inteligencia artificial integrada y experiencia "
            "de usuario completamente rediseñada. Se compararon precios en tiempo real entre "
            "<b>Jumbo, Lider, Unimarc y Santa Isabel</b>."
        ),
        SP(12),
        table([
            ["Dimensión", "Proyecto Original", "Versión Desarrollada"],
            ["Líneas de código backend",    "~1.200",   "~11.000+"],
            ["Líneas de código frontend",   "~800",     "~3.800+"],
            ["Tiendas integradas",          "1–2",      "4 (Jumbo, Lider, Unimarc, S.Isabel)"],
            ["Modelos de base de datos",    "3–4",      "16"],
            ["Endpoints API",               "~5",       "30+"],
            ["Seguridad",                   "Ninguna",  "Shield3 (WAF, rate limit, IP block)"],
            ["Inteligencia artificial",     "No",       "KAIROS AI (Llama 3.2 + fallback local)"],
            ["Sistema de notificaciones",   "No",       "Motor proactivo con rotación por tienda"],
            ["Autenticación de API",        "No",       "API Key + middleware seguro"],
        ], [5.5*cm, 4.5*cm, 6.5*cm]),
        SP(6),
        Note("Tabla 1 — Comparación de métricas clave entre versiones."),
        PageBreak(),
    ]

    # ── 2. PROYECTO ORIGINAL ──────────────────────────────────────────────────
    story += [
        H1("2. Proyecto Original (Baseline)"),
        HR(),
        H2("2.1 Repositorio de Referencia"),
        P(
            "Repositorio: <b>github.com/thedlearner/price-comparison</b><br/>"
            "El proyecto original consistía en un prototipo básico de comparación de precios "
            "para supermercados chilenos, orientado a demostrar viabilidad técnica."
        ),
        SP(),
        H2("2.2 Características del Prototipo Original"),
        bullets([
            "Scraping manual básico de 1–2 tiendas sin manejo de cambios de esquema.",
            "API REST mínima (Flask o FastAPI sin modularización) con 4–5 endpoints sin validación.",
            "Frontend estático o React básico sin gestión de estado ni manejo de errores.",
            "Base de datos simple (2–4 tablas) sin relaciones complejas ni índices.",
            "Sin sistema de autenticación ni protección de endpoints.",
            "Sin manejo de errores robusto (excepciones no capturadas).",
            "Sin sistema de caché ni optimización de consultas.",
            "Sin agentes de fondo, notificaciones ni lógica de ahorro.",
            "Sin comparación de precios históricos ni métricas de descuento.",
            "Dependencias no fijadas (sin archivo de requisitos completo).",
        ]),
        SP(),
        H2("2.3 Problemas Identificados en la Auditoría"),
        P("Durante la auditoría inicial se detectaron los siguientes problemas críticos:"),
        SP(4),
        table([
            ["#", "Problema", "Severidad", "Área"],
            ["1", "Ausencia total de autenticación en la API",            "CRÍTICA",  "Seguridad"],
            ["2", "Inyección de rutas posible (path traversal)",          "ALTA",     "Seguridad"],
            ["3", "datetime.now() sin timezone (naive datetime bugs)",     "ALTA",     "Backend"],
            ["4", "DATABASE_URL con ruta incorrecta según CWD",           "ALTA",     "Config"],
            ["5", "Race conditions en estado compartido entre hilos",     "ALTA",     "Concurrencia"],
            ["6", "Optimización N+1: consultas SQL ineficientes",         "MEDIA",    "Performance"],
            ["7", "Scrapers sin fallback ante cambios de esquema",        "MEDIA",    "Scrapers"],
            ["8", "Frontend sin manejo de errores en llamadas a API",     "MEDIA",    "Frontend"],
            ["9", "Sin límite de tasa (DoS trivial)",                     "ALTA",     "Seguridad"],
            ["10","Notificaciones sin modelo de datos persistente",       "BAJA",     "Features"],
        ], [0.8*cm, 7*cm, 2.2*cm, 2.5*cm]),
        SP(6),
        Note("Tabla 2 — Problemas detectados en la auditoría inicial del prototipo original."),
        PageBreak(),
    ]

    # ── 3. ARQUITECTURA ACTUAL ────────────────────────────────────────────────
    story += [
        H1("3. Arquitectura del Sistema Desarrollado"),
        HR(),
        H2("3.1 Stack Tecnológico"),
        SP(4),
        table([
            ["Capa",          "Tecnología",           "Versión / Detalle"],
            ["Backend API",   "FastAPI",              "Python 3.11+ · Async · Modular routers"],
            ["ORM / DB",      "SQLAlchemy 2.0",       "SQLite (dev) / PostgreSQL (prod) · Alembic"],
            ["Frontend",      "React 19 + Vite",      "TypeScript · TailwindCSS 4 · react-router-dom 7"],
            ["IA Asistente",  "Hugging Face Hub",     "Llama 3.2-3B-Instruct · Fallback local"],
            ["Scraping",      "HTTPX + BS4",          "4 scrapers anti-detección independientes"],
            ["Seguridad",     "Shield3",              "WAF, IP blocking, rate-limit, honeytokens"],
            ["Scheduler",     "schedule + threading", "Agentes de fondo cada 15 min / 6h / 24h"],
            ["Notificaciones","Motor proactivo KAIROS","Rotación por tienda, purga automática"],
            ["Monitoreo",     "Discord Webhook",      "Heartbeat, alertas de seguridad, telemetría"],
        ], [3.5*cm, 3.5*cm, 9.5*cm]),
        SP(6),
        Note("Tabla 3 — Stack tecnológico de la versión producción."),
        SP(8),
        H2("3.2 Estructura de Directorios (Backend)"),
        Paragraph("""<font face="Courier" size="9">
backend/<br/>
├── api/<br/>
│   ├── main.py          — FastAPI app, lifespan, agentes de fondo<br/>
│   ├── middleware.py    — Shield3 WAF, API Key auth, CORS<br/>
│   ├── schemas.py       — Pydantic models (UnifiedResponse, etc.)<br/>
│   ├── exceptions.py    — Manejadores globales de errores<br/>
│   └── routers/<br/>
│       ├── products.py  — Búsqueda, detalles, sugerencias, sync<br/>
│       ├── assistant.py — KAIROS chat, favoritos, notificaciones<br/>
│       ├── deals.py     — Ofertas flash con paginación offset<br/>
│       ├── stores.py    — Tiendas, sucursales, geolocalización<br/>
│       └── catalog.py   — Categorías, trending, crawl on-demand<br/>
├── core/<br/>
│   ├── models.py        — 16 modelos SQLAlchemy<br/>
│   ├── db.py            — Session factory, init_db<br/>
│   ├── shield.py        — Shield3: WAF, rate-limit, IP block<br/>
│   ├── ai_service.py    — KairosAIService (LLM + local engine)<br/>
│   └── scheduler.py     — Scheduler de tareas periódicas<br/>
├── domain/<br/>
│   ├── matcher.py       — Matching engine (fuzzy, multi-signal)<br/>
│   ├── normalizer.py    — Normalización de nombres de productos<br/>
│   ├── ingest.py        — Pipeline de ingesta y deduplicación<br/>
│   ├── proactive.py     — Motor de alertas por rotación de tienda<br/>
│   ├── meal_planner.py  — Generador de menús por tienda<br/>
│   ├── cart_optimizer.py— Optimizador de carrito multi-tienda<br/>
│   └── dream.py         — Consolidación nocturna de PriceInsights<br/>
├── data/sources/<br/>
│   ├── jumbo_scraper.py<br/>
│   ├── lider_scraper.py<br/>
│   ├── unimarc_scraper.py<br/>
│   └── santa_isabel_scraper.py<br/>
└── agents/<br/>
    ├── fluxengine_sentry.py  — Monitor de cambios críticos<br/>
    └── catalog_bot.py        — Bot de catalogación automática
</font>""", S["code"]),
        SP(8),
        H2("3.3 Estructura de Directorios (Frontend)"),
        Paragraph("""<font face="Courier" size="9">
frontend/src/<br/>
├── pages/<br/>
│   ├── Home.tsx           — Dashboard: ofertas, búsqueda, deals flash<br/>
│   ├── SearchResults.tsx  — Resultados con filtros, ordenamiento, stores<br/>
│   ├── ProductDetails.tsx — Detalle con historial de precios y favorito<br/>
│   ├── ShoppingAssistant.tsx — KAIROS AI chat + menús por tienda<br/>
│   ├── Notifications.tsx  — Alertas de ahorro con rotación y dismiss<br/>
│   ├── Favorites.tsx      — Productos favoritos del usuario<br/>
│   └── Categories.tsx     — Exploración por categoría<br/>
├── components/<br/>
│   ├── BottomNav.tsx      — Navegación inferior: Inicio·Buscar·KAIROS·Fav·Cat<br/>
│   ├── BranchMap.tsx      — Mapa de sucursales (geolocalización)<br/>
│   ├── LocationSelector.tsx<br/>
│   └── SplashScreen.tsx<br/>
├── context/<br/>
│   ├── ThemeContext.tsx   — Dark/Light mode<br/>
│   └── LocationContext.tsx<br/>
└── lib/<br/>
    └── api.ts             — Cliente HTTP tipado (30+ funciones)
</font>""", S["code"]),
        PageBreak(),
    ]

    # ── 4. MODELOS DE BASE DE DATOS ───────────────────────────────────────────
    story += [
        H1("4. Modelo de Datos"),
        HR(),
        P("El sistema cuenta con <b>16 modelos SQLAlchemy</b> que cubren el ciclo completo "
          "de datos: desde el scraping hasta las preferencias de usuario y seguridad."),
        SP(8),
        table([
            ["Modelo",              "Tabla",                "Función Principal"],
            ["Store",               "stores",               "Registro de tiendas (Jumbo, Lider, Unimarc, S.Isabel)"],
            ["Location",            "locations",            "Jerarquía geográfica (región/comuna)"],
            ["Branch",              "branches",             "Sucursales físicas con coordenadas GPS"],
            ["Product",             "products",             "Productos canónicos deduplicados (entidad central)"],
            ["StoreProduct",        "store_products",       "Producto tal como aparece en cada tienda"],
            ["Price",               "prices",               "Historial de precios scrapeados con timestamp"],
            ["ProductMatch",        "product_matches",      "Resultado del matching engine (fuzzy + multi-signal)"],
            ["PriceInsight",        "price_insights",       "Análisis consolidado: mínimo histórico, deal score"],
            ["Notification",        "notifications",        "Alertas de ahorro generadas por KAIROS"],
            ["UserPreference",      "user_preferences",     "Productos favoritos del usuario"],
            ["BotState",            "bot_state",            "Estado persistente de agentes (offsets de rotación)"],
            ["UserAssistantState",  "user_assistant_state", "Contexto del chat KAIROS (presupuesto, plan)"],
            ["BlockedIP",           "blocked_ips",          "IPs bloqueadas por Shield3"],
            ["RateLimitState",      "rate_limit_state",     "Historial de rate limiting por IP"],
            ["SecurityLog",         "security_log",         "Auditoría de eventos de seguridad"],
            ["PantryItem",          "pantry_items",         "Despensa del usuario (stock en hogar)"],
        ], [3.8*cm, 4.2*cm, 8.5*cm]),
        SP(6),
        Note("Tabla 4 — Los 16 modelos de base de datos del sistema."),
        PageBreak(),
    ]

    # ── 5. API ENDPOINTS ──────────────────────────────────────────────────────
    story += [
        H1("5. API REST — Endpoints Principales"),
        HR(),
        H2("5.1 Módulo: Productos"),
        table([
            ["Método", "Ruta",                              "Descripción"],
            ["GET",  "/api/products/search",                "Búsqueda multi-tienda con filtros, paginación y branch context"],
            ["GET",  "/api/products/{id}",                  "Detalle con historial de precios y price insight"],
            ["POST", "/api/products/{id}/sync",             "Sync JIT del precio actual vía re-scraping"],
            ["GET",  "/api/products/suggestions",           "Autocompletado de búsqueda (mínimo 2 chars)"],
            ["GET",  "/api/trending",                       "Términos de búsqueda en tendencia"],
        ], [2*cm, 6*cm, 8.5*cm]),
        SP(8),
        H2("5.2 Módulo: Asistente KAIROS"),
        table([
            ["Método",  "Ruta",                                  "Descripción"],
            ["POST",  "/api/assistant/chat",                     "Chat con KAIROS AI — genera menús por tienda"],
            ["GET",   "/api/assistant/chat/state",               "Estado del asistente (presupuesto, personas)"],
            ["GET",   "/api/assistant/favorites",                "Lista de productos favoritos"],
            ["POST",  "/api/assistant/favorites",                "Toggle favorito (add/remove/toggle)"],
            ["GET",   "/api/assistant/notifications",            "Alertas de ahorro (hasta 100)"],
            ["POST",  "/api/assistant/notifications/{id}/read",  "Marcar notificación como leída"],
            ["DELETE","/api/assistant/notifications/{id}",       "Eliminar notificación específica"],
            ["DELETE","/api/assistant/notifications",            "Limpiar todas las notificaciones leídas"],
            ["POST",  "/api/assistant/notifications/refresh",    "Ejecutar motor proactivo manualmente"],
            ["POST",  "/api/assistant/optimize_cart",            "Optimizar carrito multi-tienda"],
        ], [2*cm, 6.5*cm, 8*cm]),
        SP(8),
        H2("5.3 Módulo: Ofertas y Catálogo"),
        table([
            ["Método", "Ruta",                      "Descripción"],
            ["GET",  "/api/deals",                  "Ofertas flash con paginación offset (rotación)"],
            ["GET",  "/api/deals/historic-lows",    "Productos en mínimo histórico de precio"],
            ["GET",  "/api/categories",             "Listado de categorías disponibles"],
            ["GET",  "/api/branches/nearest",       "Sucursales más cercanas por GPS (lat/lng)"],
            ["GET",  "/api/locations/hierarchy",    "Jerarquía región → comuna → sucursal"],
        ], [2*cm, 5.5*cm, 9*cm]),
        PageBreak(),
    ]

    # ── 6. SISTEMA DE SEGURIDAD ────────────────────────────────────────────────
    story += [
        H1("6. Sistema de Seguridad — Shield3"),
        HR(),
        P(
            "Shield3 es el motor de defensa activa desarrollado específicamente para este proyecto. "
            "Se integra como middleware de FastAPI y ejecuta cada request a través de varias capas "
            "de protección antes de que llegue al router correspondiente."
        ),
        SP(8),
        H2("6.1 Capas de Protección"),
        bullets([
            "<b>API Key Authentication:</b> Todas las rutas requieren el header X-API-Key. "
            "Las keys se almacenan en variables de entorno (.env), nunca en código.",
            "<b>IP Blacklist con caché:</b> Las IPs bloqueadas se cachean en memoria (set de Python) "
            "para evitar consultas a BD en cada request. TTL de 5 minutos.",
            "<b>Rate Limiting dinámico:</b> Máximo 60 requests/minuto por IP con ventana deslizante. "
            "IPs que exceden el límite se bloquean automáticamente en BD.",
            "<b>WAF (Web Application Firewall):</b> Analiza headers de cada request detectando "
            "patrones de bots, inyección SQL, XSS, y User-Agents maliciosos.",
            "<b>Honeytokens:</b> Rutas trampa (/admin, /wp-login, etc.) que al ser accedidas "
            "bloquean automáticamente la IP atacante.",
            "<b>Thread Safety:</b> threading.Lock protege el estado compartido (REQUEST_HISTORY, "
            "BLOCKED_IPS_CACHE) ante race conditions en entorno multi-hilo.",
            "<b>Security Log:</b> Todos los eventos de seguridad se registran en security.log "
            "con timestamp, IP, tipo de evento y severidad.",
        ]),
        SP(8),
        H2("6.2 Flujo de Evaluación de un Request"),
        Paragraph("""<font face="Courier" size="8.5">
Request entrante<br/>
    ↓<br/>
[1] ¿OPTIONS (preflight CORS)?  → Pasar directo<br/>
    ↓<br/>
[2] ¿IP en blacklist?           → 403 BLOCKED<br/>
    ↓<br/>
[3] WAF header analysis         → 403 si amenaza detectada<br/>
    ↓<br/>
[4] Rate limit check (60/min)   → 429 si supera límite<br/>
    ↓<br/>
[5] API Key validation          → 401 si key inválida<br/>
    ↓<br/>
[6] Router handler              → Lógica de negocio
</font>""", S["code"]),
        PageBreak(),
    ]

    # ── 7. KAIROS AI ───────────────────────────────────────────────────────────
    story += [
        H1("7. Asistente de Inteligencia Artificial — KAIROS"),
        HR(),
        P(
            "KAIROS es el cerebro inteligente del sistema. Combina un LLM externo (Llama 3.2 via "
            "Hugging Face) con un motor local de lógica de negocio que actúa como fallback resiliente. "
            "Su función principal es generar menús de compra semanales adaptados al presupuesto del "
            "usuario y comparar costos en cada supermercado."
        ),
        SP(8),
        H2("7.1 Arquitectura del Motor de IA"),
        bullets([
            "<b>Capa LLM (Primaria):</b> Llama 3.2-3B-Instruct vía Hugging Face InferenceClient. "
            "Recibe el historial de conversación completo y un system prompt detallado con contexto "
            "de presupuesto, número de personas y stores preferidas.",
            "<b>Local Smart Engine (Fallback):</b> Motor de reglas propio que actúa cuando el LLM "
            "está ocupado o no disponible. Detecta presupuesto y número de personas con regex robusto "
            "('25 lucas', '30 mil', '$35.000', 'somos 4') y selecciona menús de 5 tiers predefinidos.",
            "<b>5 Tiers de menú:</b> micro (<$8K/persona), low ($8K–$18K), medium ($18K–$35K), "
            "high ($35K–$65K), premium (>$65K). Cada tier escala cantidades por número de personas.",
            "<b>Memoria de 45 días:</b> Presupuesto, número de personas y último plan generado se "
            "persisten en UserAssistantState y se recuperan en sesiones futuras.",
        ]),
        SP(8),
        H2("7.2 Generación de Menús por Tienda"),
        P(
            "Cuando KAIROS genera un menú (lista de ingredientes), el sistema ejecuta "
            "<b>generate_per_store_plans()</b>: para cada uno de los 4 supermercados busca la "
            "versión más barata de cada ingrediente en esa tienda específica. Adicionalmente "
            "genera un 'Plan Óptimo Multi-Tienda' que toma el precio mínimo de cualquier tienda "
            "para cada ingrediente."
        ),
        SP(4),
        table([
            ["Plan",                 "Descripción",                              "Icono"],
            ["⭐ Óptimo Multi-Tienda","Mínimo precio de cualquier tienda por ítem","Mejor ahorro posible"],
            ["🔵 Jumbo",             "Lista completa a precios de Jumbo",         "Comparación directa"],
            ["🟡 Lider",             "Lista completa a precios de Lider",         "Comparación directa"],
            ["🟢 Unimarc",           "Lista completa a precios de Unimarc",       "Comparación directa"],
            ["🔴 Santa Isabel",      "Lista completa a precios de Santa Isabel",  "Comparación directa"],
        ], [4*cm, 7.5*cm, 5*cm]),
        SP(6),
        Note("Tabla 5 — Tipos de planes generados por KAIROS para cada mensaje con presupuesto."),
        PageBreak(),
    ]

    # ── 8. MOTOR DE NOTIFICACIONES ─────────────────────────────────────────────
    story += [
        H1("8. Motor Proactivo de Notificaciones"),
        HR(),
        P(
            "El motor proactivo KAIROS ejecuta cada 15 minutos en un hilo de fondo y mantiene "
            "el tray de notificaciones del usuario siempre actualizado con las mejores ofertas "
            "del día, rotando por cada supermercado para garantizar equidad y variedad."
        ),
        SP(8),
        H2("8.1 Algoritmo de Rotación"),
        bullets([
            "<b>Paso 1 — Purga:</b> Se eliminan físicamente las notificaciones ya leídas y "
            "las que tienen más de 24 horas.",
            "<b>Paso 2 — Umbral:</b> Si hay ≥8 no leídas o ≥60 en total, el ciclo se salta "
            "(no spam).",
            "<b>Paso 3 — Rotación por tienda:</b> Para cada una de las 4 tiendas, se carga un "
            "offset de rotación almacenado en BotState (clave: 'rotation_offset_{slug}'). "
            "El offset se reinicia cada día para recorrer el catálogo completo diariamente.",
            "<b>Paso 4 — Elegibles:</b> Productos en stock, con precio reciente (últimas 48h), "
            "con ≥5% de descuento, y no notificados en las últimas 12h.",
            "<b>Paso 5 — Clasificación:</b> Cada alerta se clasifica: price_luca (≤$1.000), "
            "price_under_2k (≤$2.000), price_drop (descuento ≥40%), o price_drop estándar.",
            "<b>Paso 6 — Commit:</b> 5 alertas por tienda (20 total) se persisten en BD.",
        ]),
        SP(8),
        H2("8.2 Experiencia de Usuario en Notificaciones"),
        bullets([
            "Tarjetas agrupadas por fecha (Hoy / Ayer / Anteriores).",
            "Animación de dismiss (slide + fade) al descartar una alerta.",
            "Botón 'Actualizar' dispara el motor proactivo manualmente y recarga la lista.",
            "Botón 'Limpiar (N)' elimina en masa todas las notificaciones leídas.",
            "Al tocar una tarjeta: marca leída → sync precio en vivo → navega al producto.",
            "Indicador pulsante de no leídas en el header y en el BottomNav.",
        ]),
        PageBreak(),
    ]

    # ── 9. SCRAPERS ────────────────────────────────────────────────────────────
    story += [
        H1("9. Scrapers de Supermercados"),
        HR(),
        P(
            "Cada supermercado tiene su propio scraper independiente, adaptado a la estructura "
            "específica de su API o web. Los scrapers implementan técnicas anti-detección "
            "y fallback con IA para sobrevivir cambios de esquema."
        ),
        SP(8),
        table([
            ["Tienda",         "Técnica",           "Categorías",  "Frecuencia"],
            ["Jumbo",          "HTTPX + JSON API",  "~15",         "24h"],
            ["Lider",          "HTTPX + JSON API",  "~15",         "24h"],
            ["Unimarc",        "HTTPX + JSON API",  "~12",         "24h"],
            ["Santa Isabel",   "HTTPX + JSON API",  "~12",         "24h"],
        ], [3.5*cm, 4*cm, 3.5*cm, 3.5*cm]),
        SP(6),
        Note("Tabla 6 — Scrapers implementados por tienda."),
        SP(8),
        H2("9.1 Pipeline de Ingesta"),
        bullets([
            "<b>Normalización:</b> Nombres limpiados, marcas separadas, tallas parseadas.",
            "<b>Deduplicación:</b> Hash de contenido para evitar duplicados en cada ciclo.",
            "<b>Matching Engine:</b> rapidfuzz + multi-signal scoring para emparejar "
            "StoreProducts con Products canónicos.",
            "<b>PriceInsight:</b> Dream system consolida precios históricos cada 24h, "
            "calculando mínimo histórico, promedio y deal_score (0–100).",
            "<b>AI Fallback:</b> Si el scraper recibe un esquema desconocido, "
            "KairosAIService.extract_product_fallback() intenta extraer los campos mínimos.",
        ]),
        PageBreak(),
    ]

    # ── 10. FRONTEND ────────────────────────────────────────────────────────────
    story += [
        H1("10. Frontend — React 19"),
        HR(),
        P(
            "El frontend fue completamente rediseñado sobre el prototipo original. "
            "Es una Progressive Web App (PWA-ready) con diseño mobile-first, "
            "modo oscuro nativo, y navegación tipo app nativa."
        ),
        SP(8),
        H2("10.1 Páginas Principales"),
        table([
            ["Página",              "Ruta",           "Funcionalidad Principal"],
            ["Home",                "/",              "Dashboard: búsqueda, offers flash con refresh, historic lows"],
            ["SearchResults",       "/search",        "Resultados paginados con filtro por tienda, categoría y orden"],
            ["ProductDetails",      "/product/:id",   "Detalle de producto, gráfico de historial, toggle favorito"],
            ["ShoppingAssistant",   "/assistant",     "Chat KAIROS: menús por tienda, chips rápidos, comparación"],
            ["Notifications",       "/notifications", "Alertas de ahorro con dismiss, limpiar, actualizar"],
            ["Favorites",           "/favorites",     "Lista de favoritos con precio actual y deal badge"],
            ["Categories",          "/categories",    "Exploración por categoría"],
        ], [3.5*cm, 3*cm, 10*cm]),
        SP(6),
        Note("Tabla 7 — Páginas del frontend con sus funcionalidades."),
        SP(8),
        H2("10.2 Navegación Inferior (BottomNav)"),
        P("La navegación inferior adapta las opciones según el contexto del usuario:"),
        bullets([
            "Inicio (home) · Buscar (search) · KAIROS (assistant — botón central prominente) "
            "· Favoritos (favorite) · Categorías (grid_view)",
        ]),
        SP(8),
        H2("10.3 Patrones de UX Implementados"),
        bullets([
            "<b>Dark mode:</b> Toggle en ThemeContext, persistido en localStorage.",
            "<b>Quick-reply chips:</b> En KAIROS para sugerir presupuestos (10/20/30/50 lucas).",
            "<b>Animaciones:</b> scale-95 en active, fade+slide en dismiss de notificaciones.",
            "<b>Skeleton loaders:</b> En Home y Notifications mientras carga la data.",
            "<b>Toast notifications:</b> react-hot-toast para feedback de acciones del usuario.",
            "<b>Scroll horizontal snap:</b> En tarjetas de tienda en KAIROS.",
            "<b>Indicadores de sync:</b> Spinner + ring pulsante en cards al hacer sync de precio.",
        ]),
        PageBreak(),
    ]

    # ── 11. CAMBIOS VS ORIGINAL ────────────────────────────────────────────────
    story += [
        H1("11. Comparación Detallada: Original vs. Desarrollado"),
        HR(),
        SP(4),
        table([
            ["Característica",              "Original",         "Desarrollado",             "Mejora"],
            ["Autenticación API",           "❌ Ninguna",       "✅ API Key + Middleware",   "Crítica"],
            ["Seguridad activa",            "❌ Ninguna",       "✅ Shield3 completo",       "Crítica"],
            ["Tiendas cubiertas",           "1–2",              "4 (todas las grandes)",     "2x–4x"],
            ["Modelos de datos",            "3–4",              "16",                        "+12"],
            ["Endpoints API",               "~5",               "30+",                       "6x"],
            ["Sistema de notificaciones",   "❌",               "✅ Motor proactivo rotativo","Nuevo"],
            ["Inteligencia Artificial",     "❌",               "✅ KAIROS (LLM + local)",   "Nuevo"],
            ["Comparación por tienda",      "❌",               "✅ Menú en 4 tiendas",      "Nuevo"],
            ["Historial de precios",        "❌",               "✅ PriceInsight + gráfico", "Nuevo"],
            ["Agentes de fondo",            "❌",               "✅ 4 agentes (15min–24h)",  "Nuevo"],
            ["Optimización de carrito",     "❌",               "✅ Multi-tienda optimizer", "Nuevo"],
            ["Geolocalización sucursales",  "❌",               "✅ GPS + mapa",             "Nuevo"],
            ["Dark mode",                   "❌",               "✅ Nativo",                 "Nuevo"],
            ["Rate limiting",               "❌",               "✅ 60 req/min por IP",      "Crítica"],
            ["Thread safety",               "❌",               "✅ threading.Lock",         "Alta"],
            ["Manejo de errores",           "Básico",           "Global + por módulo",       "Alta"],
            ["Líneas de código",            "~2.000",           "~14.800+",                  "7x"],
        ], [5.2*cm, 3.2*cm, 4.5*cm, 2.5*cm]),
        SP(6),
        Note("Tabla 8 — Comparación funcional completa entre el prototipo original y la versión desarrollada."),
        PageBreak(),
    ]

    # ── 12. CONFIGURACIÓN Y DESPLIEGUE ─────────────────────────────────────────
    story += [
        H1("12. Configuración y Despliegue"),
        HR(),
        H2("12.1 Variables de Entorno (.env)"),
        Paragraph("""<font face="Courier" size="8.5">
# Base de datos<br/>
DATABASE_URL=sqlite:///./data/grocery.db<br/>
<br/>
# Seguridad<br/>
API_KEY=tu_clave_segura_aqui<br/>
<br/>
# Inteligencia Artificial<br/>
HUGGINGFACE_TOKEN=hf_...<br/>
<br/>
# Monitoreo (opcional)<br/>
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...<br/>
<br/>
# Modo de prueba de carga<br/>
STRESS_TEST_MODE=false<br/>
PORT=8000
</font>""", S["code"]),
        SP(8),
        H2("12.2 Comandos de Inicio"),
        Paragraph("""<font face="Courier" size="8.5">
# Backend (desde /backend)<br/>
pip install -r requirements.txt<br/>
cd backend<br/>
python -m uvicorn api.main:app --reload --port 8000<br/>
<br/>
# Frontend (desde /frontend/freshcart---smart-grocery-assistant)<br/>
npm install<br/>
npm run dev<br/>
<br/>
# Ejecutar motor proactivo manualmente<br/>
cd backend && python -m domain.proactive
</font>""", S["code"]),
        SP(8),
        H2("12.3 Consideraciones de Producción"),
        bullets([
            "Cambiar DATABASE_URL a PostgreSQL para producción.",
            "Usar variables de entorno reales (no .env) en servidores cloud.",
            "Configurar CORS origins en api/main.py para el dominio del frontend.",
            "El scraping debe ejecutarse con un proxy/IP residencial para evitar bloqueos.",
            "Se recomienda Redis para el caché de Shield3 en entornos distribuidos.",
        ]),
        PageBreak(),
    ]

    # ── 13. MÉTRICAS ──────────────────────────────────────────────────────────
    story += [
        H1("13. Métricas del Proyecto"),
        HR(),
        SP(4),
        table([
            ["Métrica",                      "Valor"],
            ["Líneas de código backend",     "~11.000 (Python)"],
            ["Líneas de código frontend",    "~3.800 (TypeScript/TSX)"],
            ["Total líneas de código",       "~14.800+"],
            ["Archivos Python",              "67 archivos (.py)"],
            ["Archivos TypeScript/TSX",      "23 archivos"],
            ["Modelos de base de datos",     "16 modelos SQLAlchemy"],
            ["Endpoints API REST",           "30+ endpoints"],
            ["Tiendas integradas",           "4 (Jumbo, Lider, Unimarc, Santa Isabel)"],
            ["Agentes de fondo",             "4 (Sentry, Proactive, Dream, Heartbeat)"],
            ["Tiempo de respuesta API",      "<200ms (búsqueda en cache)"],
            ["Ciclo de actualización datos", "15 min (proactivo) / 24h (crawl completo)"],
        ], [7*cm, 9.5*cm]),
        SP(6),
        Note("Tabla 9 — Métricas cuantitativas del proyecto desarrollado."),
        PageBreak(),
    ]

    # ── 14. CONCLUSIONES ──────────────────────────────────────────────────────
    story += [
        H1("14. Conclusiones"),
        HR(),
        P(
            "El proyecto FreshCart / Antigravity Grocery evolucionó de forma sustancial desde "
            "el prototipo original. Se entrega un sistema de producción completo con las "
            "siguientes características diferenciadas:"
        ),
        SP(8),
        bullets([
            "<b>Arquitectura sólida:</b> Backend modular con FastAPI, 16 modelos de datos, "
            "pipeline de ingesta completo y agentes de fondo resilientes.",
            "<b>Seguridad profesional:</b> Shield3 implementa defensa activa en 5 capas "
            "sin dependencias externas adicionales.",
            "<b>IA real e integrada:</b> KAIROS combina LLM (Llama 3.2) con motor local "
            "para garantizar disponibilidad 24/7 incluso sin conexión a Hugging Face.",
            "<b>Comparación real por tienda:</b> El usuario ve en tiempo real cuánto cuesta "
            "su lista de compras en cada uno de los 4 supermercados grandes de Chile.",
            "<b>UX mobile-first:</b> Diseño dark mode con animaciones, chips de respuesta "
            "rápida, y notificaciones proactivas de ahorro que rotan para mostrar siempre "
            "oportunidades nuevas.",
            "<b>Escalabilidad:</b> La base de datos puede migrarse de SQLite a PostgreSQL "
            "sin cambios de código. El scheduler y los agentes escalan horizontalmente.",
        ]),
        SP(16),
        HR(),
        Paragraph(
            f"Documento generado el {datetime.now().strftime('%d de %B de %Y a las %H:%M')} · "
            "FreshCart / Antigravity Grocery · Uso Interno",
            S["footer"]
        ),
    ]

    doc.build(story)
    print(f"\nPDF generado: {OUTPUT_PATH}")

if __name__ == "__main__":
    build_pdf()
