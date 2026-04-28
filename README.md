# FreshCart — Smart Grocery Assistant

Comparador de precios de supermercados en tiempo real para Chile. Analiza productos de Jumbo, Lider, Santa Isabel y más, y calcula la ruta de compras más económica mediante el motor de optimización KAIROS.

---

## Stack Tecnológico

| Capa | Tecnología |
|------|-----------|
| Backend | Python 3.11 · FastAPI · SQLAlchemy 2 · Alembic |
| Base de datos | PostgreSQL 16 (prod) · SQLite (dev/test) |
| AI / LLM | Groq (primario, <1s) · HuggingFace Llama 3.2 (fallback) |
| Frontend | React 19 · TypeScript · Vite · Redux Toolkit |
| Seguridad | Shield3 WAF · JWT HS256 · bcrypt · rate limiting |
| Observabilidad | Prometheus · Grafana Loki (JSON structured logs) |
| Deploy | Railway (backend) · Vercel (frontend) · Docker Compose (local) |

---

## Prerrequisitos

- **Python** 3.10 o superior
- **Node.js** 18 o superior
- **Docker** y **Docker Compose** (para levantar PostgreSQL local)
- **pip** y **npm**

---

## Instalación y Arranque Local

### 1. Clonar el repositorio

```bash
git clone <url-del-repo>
cd freshcart
```

### 2. Levantar la base de datos con Docker

```bash
docker compose up -d db
```

Levanta PostgreSQL 16 en `localhost:5432`. Espera el healthcheck antes de continuar:

```bash
docker compose ps   # STATUS debe ser "healthy"
```

### 3. Configurar el backend

```bash
cd backend
cp .env.example .env
# Editar .env con tus valores reales (ver sección Variables de Entorno)
```

Instalar dependencias y migrar la base de datos:

```bash
pip install -r requirements.txt
alembic upgrade head
```

Iniciar el servidor de desarrollo:

```bash
uvicorn api.main:app --reload --port 8000
```

La API quedará disponible en `http://localhost:8000`.  
Documentación interactiva: `http://localhost:8000/docs` (deshabilitada en producción).

### 4. Configurar el frontend

```bash
cd frontend/freshcart---smart-grocery-assistant
npm install
npm run dev
```

El frontend quedará disponible en `http://localhost:5173`.

---

## Variables de Entorno

Copia `backend/.env.example` como `backend/.env` y completa los valores:

| Variable | Requerida | Descripción |
|----------|-----------|-------------|
| `DATABASE_URL` | Sí | PostgreSQL en prod; SQLite por defecto en dev |
| `API_KEY` | Sí | Clave requerida en header `X-API-Key` de cada request |
| `JWT_SECRET_KEY` | Sí | Clave de firma JWT (mínimo 32 chars en producción) |
| `JWT_ACCESS_EXPIRE_HOURS` | No | Expiración del access token (default: 8h) |
| `JWT_REFRESH_EXPIRE_DAYS` | No | Expiración del refresh token (default: 7d) |
| `GROQ_API_KEY` | Recomendada | LLM primario para el asistente KAIROS |
| `HUGGINGFACE_TOKEN` | No | LLM de fallback |
| `DISCORD_BOT_TOKEN` | No | Bot interactivo para alertas y aprobación de usuarios |
| `DISCORD_WEBHOOK_URL` | No | Webhook para telemetría y heartbeats |
| `AUTHORIZED_USER_IDS` | No | IDs Discord con permisos admin (separados por coma) |
| `CENCOSUD_API_KEY` | No | API key para scrapers de Cencosud |
| `PORT` | No | Puerto del servidor (default: 8000) |
| `STRESS_TEST_MODE` | No | Desactiva rate limiting; nunca en producción |

> **Seguridad**: En `ENVIRONMENT=production`, el servidor rechaza arrancar si `JWT_SECRET_KEY` tiene menos de 32 caracteres.

---

## Ejecutar Tests

### Backend (pytest)

```bash
cd backend
pip install -r requirements.txt
pytest tests/ -v
```

Módulos de test disponibles:

| Archivo | Descripción |
|---------|-------------|
| `tests/test_unit_critical.py` | Lógica de negocio crítica (48 tests) |
| `tests/test_security_and_validation.py` | Validación de inputs y caché |
| `tests/test_security_owasp.py` | OWASP Top 10: SQLi, XSS, JWT, Access Control (33 tests) |
| `tests/test_error_handling.py` | Respuestas de error HTTP 4xx/5xx (24 tests) |

### Frontend (Vitest)

```bash
cd frontend/freshcart---smart-grocery-assistant
npm test
```

---

## Deploy con Docker Compose (solo DB)

El `docker-compose.yml` levanta únicamente PostgreSQL. El backend se despliega en Railway y el frontend en Vercel.

Para un entorno completamente local:

```bash
# 1. Levantar DB
docker compose up -d db

# 2. Backend
cd backend && uvicorn api.main:app --host 0.0.0.0 --port 8000

# 3. Frontend (otra terminal)
cd frontend/freshcart---smart-grocery-assistant && npm run dev
```

---

## Deploy en Railway (producción)

El backend usa Nixpacks como builder. El `railway.toml` ejecuta automáticamente:

```
alembic upgrade head && uvicorn api.main:app --host 0.0.0.0 --port $PORT
```

Variables de entorno requeridas en Railway: `DATABASE_URL`, `API_KEY`, `JWT_SECRET_KEY`.

---

## Estructura del Proyecto

```
├── backend/
│   ├── api/
│   │   ├── main.py          # FastAPI app, middleware, lifespan, honeytokens
│   │   ├── schemas.py       # Pydantic models (request/response)
│   │   ├── middleware.py    # API key auth, Shield WAF
│   │   └── routers/         # products, auth, deals, stores, catalog, pantry,
│   │                        # assistant, feedback
│   ├── core/
│   │   ├── db.py            # SQLAlchemy session factory
│   │   ├── models.py        # ORM models (Store, Product, Price, …)
│   │   └── ai_service.py    # KairosAIService (Groq + HuggingFace)
│   ├── agents/              # 13 agentes daemon en background
│   ├── domain/              # cart_optimizer, meal_planner
│   ├── tests/               # pytest suite
│   └── alembic/             # migraciones de esquema
├── frontend/
│   └── freshcart---smart-grocery-assistant/
│       ├── src/
│       │   ├── context/     # CartContext, AuthContext
│       │   ├── components/  # ErrorBoundary, UI components
│       │   ├── pages/       # rutas React Router
│       │   └── lib/api.ts   # cliente HTTP con retry/refresh
│       └── src/__tests__/   # Vitest suite
├── docker-compose.yml
└── docs/                    # Documentación técnica extendida
```
