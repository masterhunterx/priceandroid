# Code Review — Principal Engineer

*Fecha: 2026-04-27 | Rol: Principal Engineer (revisión sin piedad)*

---

## 1. Acoplamiento

### 1.1 Los routers conocen demasiado de la BD

**Problema:** Los routers importan y manipulan modelos SQLAlchemy directamente. `products.py` hace `joinedload`, construye queries, filtra, pagina y serializa — todo en el mismo archivo. No hay separación entre "cómo se obtienen los datos" y "qué se devuelve al cliente".

```python
# products.py — 400+ líneas mezclando routing, query building y serialización
@router.get("/search")
def search_products(...):
    with get_session() as session:
        q = session.query(StoreProduct)
        q = q.join(Store)
        q = _build_text_filter(q, q_param)
        # ... 50 líneas más de lógica de query
```

**Consecuencia:** si cambia el esquema de la BD, hay que buscar el impacto en 9 routers distintos. Si quieres reutilizar la query de búsqueda en un agente daemon, duplicas código.

**Corrección recomendada:** extraer una capa de repositorios:

```python
# core/repositories/product_repo.py
class ProductRepository:
    def __init__(self, session):
        self.session = session

    def search(self, q: str, store: str | None, ...) -> tuple[list[StoreProduct], int]:
        ...

# products.py — solo routing
@router.get("/search")
def search_products(...):
    with get_session() as session:
        repo = ProductRepository(session)
        items, total = repo.search(q, store, ...)
    return UnifiedResponse(data=SearchResponse(...))
```

No es necesario ir a DDD completo — solo separar la consulta de la request handler.

---

### 1.2 `api/utils.py` — Módulo "dios"

Las funciones `build_price_points`, `preload_latest_prices`, `preload_price_insights`, `get_price_insight`, `check_favorite`, `trigger_jit_sync`, `best_price_info`, `analyze_promo`, `_infer_unit_label` están todas en `api/utils.py`. Esto crea un módulo con ~600+ líneas que es importado por casi todos los routers.

Cualquier cambio en `utils.py` requiere revaluar el impacto en todos los routers. Los tests unitarios de `best_price_info` no deberían necesitar importar código relacionado con JIT sync.

**Corrección:** dividir en módulos por responsabilidad:
- `api/pricing.py`: `build_price_points`, `best_price_info`, `analyze_promo`, `_infer_unit_label`
- `api/insights.py`: `preload_price_insights`, `get_price_insight`
- `api/sync.py`: `trigger_jit_sync`, `trigger_jit_sync_standalone`
- `api/favorites.py`: `check_favorite`

---

### 1.3 Estado global compartido sin aislamiento

El sistema tiene múltiples singletons en memoria que los tests no pueden aislar limpiamente:

```python
# En products.py
_search_cache: dict[str, tuple[float, object]] = {}

# En auth.py
_login_attempts: defaultdict[str, list] = defaultdict(list)
_revoked_tokens: dict = {}

# En deals.py
_search_counter: Counter = Counter()
```

Estos singletons son compartidos entre tests porque Python cachea los módulos. Los tests actuales lo trabajan con queries únicas y `autouse` fixtures que limpian el estado, pero es frágil — si se agrega un nuevo test que usa "leche" sin limpiar la caché, puede contaminar a otro.

**Corrección:** encapsular el estado en clases instanciadas una sola vez en `lifespan()`:

```python
# core/cache.py
class SearchCache:
    def __init__(self, maxsize=500, ttl=300):
        self._store = {}
        self._lock = threading.Lock()
        ...

# En main.py lifespan:
app.state.search_cache = SearchCache()
```

Inyectable como `Depends`, completamente aislable en tests.

---

## 2. Abstracciones Innecesarias

### 2.1 13 agentes daemon — complejidad sin supervisión

El sistema arranca 13 threads daemon en `lifespan()`. El problema no es la cantidad, es que:

1. **No hay supervisión de reinicios internos.** Si `PricePipeline` lanza una excepción no capturada, muere silenciosamente. Railway reinicia el *proceso completo*, no el thread individual. Durante los ~10s de restart, los otros 12 agentes también caen.

2. **No hay health reporting por agente.** El endpoint `/health` verifica la BD pero no si los agentes están vivos. Un `StockScan` muerto puede pasar desapercibido días.

3. **Sin priorización.** `LogTracker` y `FeedbackPipeline` compiten por el mismo GIL que `PricePipeline`, que es la operación más crítica.

**Corrección a corto plazo:** añadir latidos por agente:

```python
_agent_heartbeats: dict[str, float] = {}

class BaseAgent(threading.Thread):
    def run(self):
        while True:
            try:
                self._tick()
                _agent_heartbeats[self.name] = time.time()
            except Exception as e:
                logger.error(f"[{self.name}] crash: {e}")
                time.sleep(5)  # backoff antes de reintentar
```

**Corrección a largo plazo:** mover los pipelines pesados (PricePipeline, MatchPipeline, CatalogSync) a workers Celery separados. Los agentes ligeros (LogTracker, SecAudit) pueden quedarse como threads.

---

### 2.2 `_CATEGORY_MAP` — hardcoded en deals.py

La lista de 13 categorías con keywords, emojis y colores está hardcodeada en `deals.py` como una lista de dicts (154 líneas). La misma información existe implícitamente en `StoreProduct.top_category`.

Cualquier nueva categoría requiere editar `deals.py` Y posiblemente el scraper. No hay garantía de que los keywords del mapa coincidan con los valores reales de la BD.

**Corrección:** persistir las categorías en la BD con una tabla `categories`:
```sql
CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    emoji VARCHAR(10),
    color VARCHAR(7),
    keywords TEXT[]
);
```

Editable en runtime sin deploy. El `GET /api/categories` es entonces una simple query.

---

### 2.3 Schema duplicado: `CartItem` en Pydantic Y TypeScript

`backend/api/schemas.py` define:
```python
class CartItem(BaseModel):
    product_id: conint(gt=0)
    name: str
    quantity: conint(ge=1, le=100) = 1
```

Y el frontend define su propio `CartItem` en `CartContext.tsx`:
```typescript
interface CartItem {
  product_id: number | string;
  name: string;
  brand: string;
  image_url: string;
  price: number;
  store_slug: string;
  store_name: string;
  qty: number;
}
```

Son dos modelos distintos con el mismo nombre representando conceptos distintos (carrito local vs request al backend). Este desacoplamiento es intencional en apariencia, pero en la práctica genera confusión cuando un desarrollador busca "CartItem" — encuentra dos definiciones contradictorias.

**Corrección:** renombrar el tipo del frontend a `LocalCartItem` y el del backend a `CartItemRequest`. Documentar que son tipos distintos por diseño.

---

## 3. Escalabilidad — Qué falla primero a 10K usuarios concurrentes

### 3.1 El lock del search cache se convierte en un semáforo global

```python
_search_cache_lock = threading.Lock()

def _get_cached(key: str):
    with _search_cache_lock:  # bloquea TODOS los requests durante la lectura
        ...
```

Con `threading.Lock()`, solo un thread puede leer o escribir al mismo tiempo. A 10K requests/s con un pool de 4 workers uvicorn, la contención sobre este lock puede añadir latencias de cola de 100-500ms.

**Corrección:** `threading.RLock()` no ayuda aquí. La solución real es:
1. Corto plazo: usar `dict` con reads sin lock (GIL de Python protege las operaciones atómicas en dict), solo lockear en writes.
2. Largo plazo: Redis (ver CLOUD_OPTIMIZATION.md §3.1).

---

### 3.2 `_revoked_tokens` crece indefinidamente en producción

```python
_revoked_tokens: dict[tuple, float] = {}
```

La limpieza oportunística solo ocurre en cada llamada a `_is_token_revoked()`. Si el endpoint `/api/auth/me` no se llama frecuentemente (p.ej. app mobile que usa tokens de larga duración), el dict puede crecer sin límite.

Con `ACCESS_EXP = 8h` y `REFRESH_EXP = 7d`, un atacante que llame a `/logout` repetidamente puede inflar `_revoked_tokens` hasta agotar la RAM.

**Corrección:** limpiar en un background task periódico, no oportunísticamente:

```python
# En SecHealer o en un task aparte:
def _cleanup_revoked_tokens():
    while True:
        time.sleep(3600)  # cada hora
        now = time.time()
        with _revoked_lock:
            expired = [k for k, exp in _revoked_tokens.items() if exp < now]
            for k in expired:
                del _revoked_tokens[k]
```

---

### 3.3 `get_session()` es síncrono en un servidor ASGI

FastAPI con Uvicorn es ASGI (async). Los endpoints usan `def` síncrono en lugar de `async def`, lo que significa que FastAPI los ejecuta en un threadpool. Con muchos requests concurrentes, el threadpool se agota esperando conexiones de BD.

```python
@router.get("/search")
def search_products(...):      # síncrono — ejecutado en threadpool
    with get_session() as s:  # bloquea el thread durante la query
        ...
```

**Consecuencia:** con el default de Uvicorn de 40 threads en el pool y queries de ~100ms, el throughput máximo es 40/0.1 = 400 req/s antes de que el pool se sature.

**Corrección a largo plazo:** migrar a SQLAlchemy async con `asyncpg`:

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

@router.get("/search")
async def search_products(...):
    async with get_async_session() as session:
        ...
```

Esto permite manejar miles de requests concurrentes con pocos threads, usando I/O async.

**Corrección a corto plazo:** aumentar el threadpool de Uvicorn:

```bash
uvicorn api.main:app --workers 4 --limit-concurrency 200
```

---

### 3.4 Sin connection pooling explícito

`create_engine()` en SQLAlchemy tiene un pool por defecto de 5 conexiones con overflow de 10. A 10K usuarios:
- Cada request toma 1 conexión del pool.
- Con queries de 100ms y 15 conexiones disponibles → máximo 150 req/s antes de espera.

**Corrección:**

```python
engine = create_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=40,
    pool_timeout=30,
    pool_pre_ping=True,  # detecta conexiones muertas antes de usarlas
)
```

En producción con múltiples workers, considerar **PgBouncer** como proxy de conexiones entre el backend y PostgreSQL.

---

## 4. Bugs Latentes

### 4.1 Race condition en `_check_rate_limit`

```python
if ip not in _login_attempts and len(_login_attempts) >= _RL_MAX_IPS:
    return False
```

Esta verificación ocurre dentro del `with _rl_lock`, pero `ip not in _login_attempts` hace acceso a un `defaultdict` — si dos threads verifican simultáneamente (imposible con Lock, posible si se cambia a RLock), el check y el insert no son atómicos.

Con `threading.Lock()` actual esto es seguro. El riesgo es que alguien cambie a `RLock` en el futuro sin entender la implicación. Agregar un comentario explicativo aquí vale más que una abstracción.

---

### 4.2 Fallback ID `1000000 + sp.id` puede colisionar

```python
# products.py — para StoreProducts sin emparejamiento canónico
results.append(ProductOut(
    id=1000000 + sp.id,  # ID temporal
    ...
))
```

Si `sp.id` > 1.000.000 (probable con meses de scraping de múltiples tiendas), este ID colisiona con IDs de productos canónicos reales. El frontend almacena `product_id` en localStorage — una colisión causaría que el carrito del usuario mezcle productos distintos.

**Corrección:** usar un namespace diferente y negativo, o un UUID, o agregar un prefijo no numérico al ID temporal que el frontend sepa ignorar para persistencia.

---

### 4.3 `_search_cache` incluye `is_favorite` por usuario

La cache key incluye `current_user`, lo que es correcto. Pero si el mismo usuario agrega un favorito, la caché no se invalida — verá `is_favorite: false` hasta que expire el TTL de 300s.

Esto es un trade-off aceptable (UX ligeramente desincronizado), pero debería estar documentado. Si no se documenta, un desarrollador futuro podría intentar "arreglarlo" invalidando la caché en el endpoint de favoritos, causando una cadena de efectos secundarios.

---

## 5. Resumen

| Área | Severidad | Acción |
|------|-----------|--------|
| Routers con lógica de BD directa | Alta | Extraer repositorios o query builders |
| `utils.py` monolítico | Alta | Dividir en módulos por responsabilidad |
| `_revoked_tokens` sin límite | Alta | Cleanup periódico en background |
| Pool de conexiones sin configurar | Alta | `pool_size=20, max_overflow=40` |
| 13 threads sin supervisión de salud | Media | Heartbeats + health endpoint por agente |
| `CartItem` duplicado frontend/backend | Media | Renombrar para eliminar ambigüedad |
| Categorías hardcodeadas | Media | Persistir en BD |
| Lock en search cache | Media | Reads sin lock (GIL), writes con lock |
| ID `1000000 + sp.id` colisionable | Media | Namespace seguro para IDs temporales |
| Sync endpoints en servidor ASGI | Baja (ahora) | Migrar a async/asyncpg a futuro |
| Caché de favoritos no invalidada | Baja | Documentar el trade-off |
