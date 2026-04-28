# Análisis de Optimización Cloud — FreshCart

*Fecha: 2026-04-27 | Rol: Cloud Solutions Architect*

---

## 1. Consultas Pesadas de Base de Datos

### 1.1 `search_products` — El cuello de botella principal

**Problema actual:**
La búsqueda ejecuta hasta 4 queries en secuencia por request:
1. `COUNT(*)` para calcular el total de resultados
2. `SELECT` con paginación para obtener los StoreProducts
3. `preload_latest_prices()` — 1 query bulk (ya optimizado)
4. `preload_price_insights()` — 1 query bulk (ya optimizado)

El `COUNT(*)` con JOIN + LIKE es la query más cara. En una tabla de 500K productos:

```sql
-- Esta query puede tardar 200-800ms sin índice
SELECT COUNT(*) FROM store_products sp
JOIN stores s ON sp.store_id = s.id
WHERE LOWER(sp.name) LIKE '%lech_%'
   OR LOWER(sp.brand) LIKE '%lech_%'
```

**Optimizaciones recomendadas:**

```sql
-- Índice de texto completo (PostgreSQL)
CREATE INDEX idx_store_products_name_gin
  ON store_products USING gin(to_tsvector('spanish', name || ' ' || COALESCE(brand, '')));

-- Reemplazar LIKE con ts_vector para búsquedas de texto
-- Mantener LIKE como fallback para consultas cortas (<3 chars)
```

Adicionalmente, eliminar el `COUNT(*)` exacto en favor de una estimación:

```python
# Usar relcount de pg_stat_user_tables como estimación rápida
# Solo ejecutar COUNT exacto en página 1, cachear el total
```

**Impacto estimado:** reducción de 60-80% en latencia de búsqueda en producción.

---

### 1.2 `list_deals` — N+1 latente

**Problema:** El router de deals hace JOIN de `prices → store_products → stores` sin `joinedload`. Si SQLAlchemy resuelve las relaciones lazy, genera un query por fila.

**Solución:**

```python
# En list_deals(), agregar joinedload explícito:
from sqlalchemy.orm import joinedload

q = session.query(Price).options(
    joinedload(Price.store_product).joinedload(StoreProduct.store)
).filter(...)
```

**Impacto estimado:** eliminación de N queries extra (N = cantidad de deals retornados).

---

### 1.3 `get_nearest_branches` — Haversine en Python

**Problema:** El endpoint carga todas las sucursales dentro de un bounding box de ±5° y calcula la distancia en Python. Con 10.000 sucursales en producción, esto es ~10K objetos en memoria por request.

**Solución a corto plazo (sin PostGIS):**

```sql
-- El bounding box actual usa ±0.05° lat y ±0.06° lng (~5.5km)
-- Agregar índice en coordenadas:
CREATE INDEX idx_branches_coords ON branches(latitude, longitude)
  WHERE latitude IS NOT NULL AND longitude IS NOT NULL;
```

**Solución a largo plazo:** Migrar a PostGIS y ejecutar Haversine en SQL:

```sql
SELECT *, ST_Distance(
  ST_MakePoint(longitude, latitude)::geography,
  ST_MakePoint($lng, $lat)::geography
) / 1000 AS distance_km
FROM branches
WHERE ST_DWithin(
  ST_MakePoint(longitude, latitude)::geography,
  ST_MakePoint($lng, $lat)::geography,
  5000  -- metros
)
ORDER BY distance_km
LIMIT 20;
```

---

### 1.4 `preload_latest_prices` — Índice compuesto crítico

La función ya usa bulk loading, pero necesita este índice para ser eficiente:

```sql
-- Si no existe, crearlo urgente:
CREATE INDEX idx_prices_product_scraped
  ON prices(store_product_id, scraped_at DESC);
```

Sin este índice, el `MAX(scraped_at)` hace full table scan en cada sync.

---

## 2. Docker Multi-Stage Build

El proyecto **no tiene Dockerfile propio** — usa Nixpacks en Railway. Esto funciona pero tiene desventajas:

- Imagen resultante incluye el toolchain de build completo (pip, gcc) en producción.
- Sin control fino sobre capas de caché.

**Dockerfile multi-stage recomendado:**

```dockerfile
# ── Stage 1: Builder ─────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt .

# Compilar wheels sin instalar en el sistema
RUN pip install --upgrade pip \
 && pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# ── Stage 2: Runtime ─────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Dependencias del sistema solo para runtime (sin gcc, sin pip extras)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar desde wheels precompilados — sin compilación en runtime
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/*.whl \
 && rm -rf /wheels

COPY . .

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn api.main:app --host 0.0.0.0 --port $PORT"]
```

**Beneficios:**
- Imagen final ~60% más pequeña (elimina gcc, pip cache, build artifacts).
- Caché de Docker reutiliza la capa de wheels si `requirements.txt` no cambia.
- Superficie de ataque reducida (sin compiladores en producción).

---

## 3. Oportunidades de Caché Adicionales

### 3.1 Search cache — Ya implementado, mejorar eviction

El caché actual (`_search_cache`) usa TTL de 300s con LRU mínimo (500 entries). Problema: en picos de tráfico, el lock de threading puede ser un cuello de botella.

**Mejora:** Migrar a `cachetools.TTLCache` con `RLock`:

```python
from cachetools import TTLCache
import threading

_search_cache = TTLCache(maxsize=500, ttl=300)
_search_cache_lock = threading.RLock()
```

`TTLCache` maneja eviction automáticamente, sin necesidad del loop de limpieza manual.

**Siguiente nivel:** Redis compartido entre múltiples workers:

```python
import redis, json, hashlib

_redis = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
_CACHE_PREFIX = "sc:v1:"

def _get_cached(key: str):
    raw = _redis.get(_CACHE_PREFIX + hashlib.sha256(key.encode()).hexdigest())
    return json.loads(raw) if raw else None

def _set_cached(key: str, value):
    _redis.setex(
        _CACHE_PREFIX + hashlib.sha256(key.encode()).hexdigest(),
        300,
        json.dumps(value)
    )
```

**Beneficio clave:** el caché actual es por-proceso. Con múltiples workers (Gunicorn + Uvicorn), cada worker tiene su propio caché — en Railway con 2+ réplicas, el cache miss rate es el doble del esperado.

---

### 3.2 Caché de categorías y tiendas — Sin implementar

Las listas de tiendas y categorías son casi estáticas (se actualizan con nuevos scrapers, no en cada request). Actualmente hacen query a BD en cada llamada.

```python
from functools import lru_cache
from datetime import timedelta

# Cachear por 1 hora en memoria
@lru_cache(maxsize=1)
def _get_stores_cached():
    ...

# Invalidar manualmente cuando se agrega una tienda
_get_stores_cached.cache_clear()
```

O con TTL explícito si el LRU no es suficiente:

```python
_stores_cache: tuple[float, list] | None = None
_STORES_TTL = 3600  # 1 hora

def get_stores():
    global _stores_cache
    if _stores_cache and time.time() - _stores_cache[0] < _STORES_TTL:
        return _stores_cache[1]
    result = _fetch_stores_from_db()
    _stores_cache = (time.time(), result)
    return result
```

**Impacto estimado:** eliminar ~50 queries/minuto en producción sin costo.

---

### 3.3 Rate limiter — Migrar a Redis en producción

El `_login_attempts: defaultdict(list)` es en memoria por proceso. Con múltiples instancias del backend:

- Un atacante con 5 workers puede hacer 5×5 = 25 intentos por ventana en vez de 5.
- La limpieza oportunística al 90% puede no activarse en procesos con poca carga.

**Solución:** Redis con atomic increment:

```python
def _check_rate_limit_redis(ip: str) -> bool:
    key = f"rl:login:{ip}"
    pipe = _redis.pipeline()
    pipe.incr(key)
    pipe.expire(key, 60)
    results = pipe.execute()
    return results[0] <= 5
```

Atómico, sin locks, funciona con múltiples instancias.

---

## 4. Estimación de Costos (Railway)

| Componente | Costo actual | Optimizado |
|------------|-------------|-----------|
| Backend (1 replica) | ~$5/mes (512MB RAM) | Sin cambio |
| PostgreSQL 16 | ~$5/mes (Railway Postgres) | Sin cambio |
| Redis (caché compartido) | No existe | +$0 (Railway Redis gratis hasta 25MB) |
| Build time | ~4 min (Nixpacks) | ~2 min (Docker multi-stage con caché) |

La migración a Redis del search cache y rate limiter tiene costo $0 en Railway y elimina la necesidad de aumentar RAM para manejar más tráfico.

---

## 5. Resumen de Prioridades

| Prioridad | Acción | Impacto | Esfuerzo |
|-----------|--------|---------|---------|
| 🔴 Alta | Índice GIN para búsqueda de texto | -70% latencia búsqueda | 30 min |
| 🔴 Alta | Índice compuesto en `prices(store_product_id, scraped_at)` | -60% en preload | 10 min |
| 🟡 Media | Migrar search cache a Redis | Cache compartido multi-worker | 2h |
| 🟡 Media | Caché de `list_stores` y `list_categories` | -50 queries/min | 30 min |
| 🟡 Media | Dockerfile multi-stage | -60% tamaño imagen | 1h |
| 🟢 Baja | Rate limiter en Redis | Protección real multi-instancia | 2h |
| 🟢 Baja | PostGIS para Haversine en SQL | -90% RAM en get_nearest | 4h |
