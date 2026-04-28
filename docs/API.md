# API Reference — Antigravity Grocery API v1.1.0

Todos los endpoints (excepto `/`, `/health` y `/metrics`) requieren el header:

```
X-API-Key: <tu_api_key>
```

Todas las respuestas siguen el envelope `UnifiedResponse`:

```typescript
interface UnifiedResponse<T = unknown> {
  success: boolean;
  data: T | null;
  error: string | null;
}
```

En errores: `success: false`, `data: null`, `error: "mensaje legible"`.

---

## TypeScript Interfaces (mapeadas desde Pydantic)

```typescript
// ── Tiendas ──────────────────────────────────────────────────────────────────

interface StoreOut {
  id: number;
  name: string;
  slug: string;
  base_url: string;
  logo_url: string;
}

interface BranchOut {
  id: number;
  store_id: number;
  store_name: string;
  name: string;
  city: string;
  region: string | null;
  address: string | null;
  external_store_id: string;
  latitude: number | null;
  longitude: number | null;
  distance_km: number | null;
}

// ── Precios ───────────────────────────────────────────────────────────────────

interface PricePointOut {
  store_id: number;
  store_name: string;
  store_slug: string;
  store_logo: string;
  price: number | null;
  list_price: number | null;
  promo_price: number | null;
  promo_description: string;
  has_discount: boolean;
  in_stock: boolean;
  product_url: string;
  last_sync: string;                   // ISO 8601
  is_card_price: boolean;
  card_label: string;
  offer_type: string;                  // "generic" | "flash" | "club"
  club_price: number | null;
  unit_price: number | null;
  price_per_unit: number | null;       // $/100g o $/100ml normalizado
  unit_label: string | null;           // "$/100g" | "$/100ml"
  is_stale: boolean;                   // datos > 6h sin refresh
}

interface PriceInsightOut {
  avg_price: number | null;
  min_price_all_time: number | null;
  max_price_all_time: number | null;
  price_trend: string;                 // "up" | "down" | "stable"
  is_deal_now: boolean;
  deal_score: number;                  // 0–100
  last_consolidated: string;           // ISO 8601
}

interface PriceHistoryOut {
  price: number | null;
  scraped_at: string;                  // ISO 8601
}

// ── Productos ─────────────────────────────────────────────────────────────────

interface ProductOut {
  id: number;
  name: string;
  brand: string;
  category: string;
  image_url: string;
  weight_value: number | null;
  weight_unit: string | null;
  prices: PricePointOut[];
  best_price: number | null;
  best_store: string | null;
  best_store_slug: string | null;
  price_insight: PriceInsightOut | null;
  is_favorite: boolean;
}

interface ProductDetailOut extends ProductOut {
  category_path: string;
  price_history: PriceHistoryOut[];
}

interface SearchResponse {
  results: ProductOut[];
  total: number;
  page: number;
  page_size: number;
}

// ── Ofertas ───────────────────────────────────────────────────────────────────

interface DealOut {
  product_id: number;
  product_name: string;
  brand: string;
  category: string;
  image_url: string;
  store_name: string;
  store_slug: string;
  store_logo: string;
  price: number | null;
  list_price: number | null;
  promo_price: number | null;
  promo_description: string;
  discount_percent: number | null;
  deal_score: number;
  product_url: string;
}

// ── Autenticación ─────────────────────────────────────────────────────────────

interface LoginRequest {
  username: string;
  password: string;
}

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
}

// ── Carrito / Optimización ────────────────────────────────────────────────────

interface CartItemRequest {
  product_id: number;     // > 0
  name: string;
  quantity: number;       // 1–100
}

interface OptimizeCartRequest {
  items: CartItemRequest[]; // 1–100 items
}

interface PlanItemOut {
  product_id: number;
  product_name: string;
  store_name: string;
  price: number;
}

interface PlanResponse {
  plan_type: string;
  items_requested: number;
  items_found: number;
  estimated_total: number;
  trip_count: number;
  strategy: Record<string, unknown>[];
}

// ── Despensa ──────────────────────────────────────────────────────────────────

interface PantryItemOut {
  id: number;
  product_id: number;
  product_name: string;
  image_url: string;
  last_purchased_at: string;        // ISO 8601
  purchase_count: number;
  current_stock_level: string;      // "full" | "half" | "low" | "empty"
  estimated_depletion_at: string | null;
  days_remaining: number | null;
}

interface PantryPurchaseRequest {
  product_id: number;
  stock_level: string;              // "full" | "half" | "low"
}

// ── Notificaciones ────────────────────────────────────────────────────────────

interface NotificationOut {
  id: number;
  product_id: number | null;
  title: string;
  message: string;
  type: string;
  is_read: boolean;
  created_at: string;
  link_url: string | null;
}

// ── Feedback ──────────────────────────────────────────────────────────────────

interface FeedbackIn {
  type: "bug" | "mejora" | "sugerencia";
  description: string;              // 10–2000 chars
  page_context?: string;
}

// ── Chat ──────────────────────────────────────────────────────────────────────

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

interface ChatRequest {
  messages: ChatMessage[];
}

// ── Catálogo ──────────────────────────────────────────────────────────────────

interface HistoricLowOut {
  product_id: number;
  product_name: string;
  brand: string;
  image_url: string;
  store_name: string;
  store_slug: string;
  store_logo: string;
  price: number | null;
  min_price_all_time: number | null;
  deal_score: number;
}
```

---

## Endpoints

### Salud

#### `GET /`
Ping público. No requiere autenticación.

**Response** `200`
```json
{ "status": "alive" }
```

#### `GET /health`
Health check activo — ejecuta `SELECT 1` contra la BD.

**Response** `200` (BD disponible) | `503` (BD caída)
```json
{ "status": "healthy", "db": "ok", "uptime_s": 3600 }
```

---

### Auth — `/api/auth`

#### `POST /api/auth/login`

**Body**
```json
{ "username": "admin", "password": "secret" }
```

**Response** `200`
```typescript
UnifiedResponse<TokenResponse>
```

**Errores**
| Status | Causa |
|--------|-------|
| 401 | Credenciales incorrectas |
| 429 | Rate limit: 5 intentos / 60s por IP |
| 403 | Usuario pendiente de aprobación Discord |

---

#### `POST /api/auth/logout`

Requiere `Authorization: Bearer <access_token>`.

**Response** `200`
```typescript
UnifiedResponse<{ message: string }>
```

---

#### `GET /api/auth/me`

Requiere `Authorization: Bearer <access_token>`.

**Response** `200`
```typescript
UnifiedResponse<{ username: string; role: string }>
```

**Errores**: `401` token inválido/expirado/tipo incorrecto.

---

#### `POST /api/auth/refresh`

Requiere `Authorization: Bearer <refresh_token>` (tipo `refresh`, no `access`).

**Response** `200`
```typescript
UnifiedResponse<{ access_token: string; token_type: "bearer" }>
```

---

### Productos — `/api/products`

#### `GET /api/products/search`

Motor de búsqueda KAIROS. Resiliente a acentos y errores tipográficos en vocales.
Respuestas cacheadas 300 segundos por clave `user|q|store|category|sort|page|page_size`.

**Query params**

| Param | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `q` | string | `""` | Término de búsqueda (max 100 chars) |
| `store` | string | null | Slug de tienda (`jumbo`, `lider`, etc.) |
| `category` | string | null | Categoría (max 100 chars) |
| `in_stock` | boolean | `true` | Solo productos con stock |
| `sort` | string | `price_asc` | `price_asc` \| `price_desc` \| `name` |
| `page` | integer | 1 | Página (≥ 1) |
| `page_size` | integer | 20 | Resultados por página (1–100) |

**Header opcional**
```
X-Branch-Context: <branch_id>   # filtra precios por sucursal específica
```

**Response** `200`
```typescript
UnifiedResponse<SearchResponse>
```

**Errores**: `400` query o category > 100 chars · `422` page < 1 o page_size > 100.

---

#### `GET /api/products/{product_id}`

Detalle completo de un producto con historial de precios y JIT sync.

**Response** `200`
```typescript
UnifiedResponse<ProductDetailOut>
```

**Errores**: `404` producto no encontrado · `422` ID no numérico.

---

#### `POST /api/optimize/ultraplan`

Planificación extrema de ahorro: dada una lista de IDs, devuelve la distribución óptima de compras por tienda.

**Body**
```json
{ "product_ids": [1, 2, 3] }
```

**Response** `200`
```typescript
UnifiedResponse<PlanResponse>
```

**Errores**: `422` body inválido (array en lugar de objeto, lista vacía).

---

### Ofertas y Descubrimiento — `/api`

#### `GET /api/deals`

Ofertas flash activas ordenadas por `deal_score` descendente.

**Query params**

| Param | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `store` | string | null | Filtrar por slug de tienda |
| `category` | string | null | Filtrar por categoría |
| `limit` | integer | 20 | Máximo de resultados (1–100) |
| `offset` | integer | 0 | Offset para paginación |

**Response** `200`
```typescript
UnifiedResponse<DealOut[]>
```

---

#### `GET /api/trending`

Búsquedas más frecuentes desde el último deploy (contador en memoria).
Devuelve fallback estático si hay menos de 5 términos registrados.

**Response** `200`
```typescript
UnifiedResponse<Array<{ term: string; icon: string }>>
```

---

#### `GET /api/categories`

Categorías normalizadas con conteo de productos en stock.

**Query params**

| Param | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `store` | string | null | Filtrar por slug de tienda |

**Response** `200`
```typescript
UnifiedResponse<Array<{
  name: string;
  emoji: string;
  color: string;
  count: number;
}>>
```

---

#### `GET /api/historic-lows`

Productos en su mínimo histórico de precio.

**Response** `200`
```typescript
UnifiedResponse<HistoricLowOut[]>
```

---

### Tiendas — `/api`

#### `GET /api/stores`

Lista todos los supermercados registrados.

**Response** `200`
```typescript
UnifiedResponse<StoreOut[]>
```

---

#### `GET /api/branches/nearest`

Sucursales físicas más cercanas usando la fórmula de Haversine.

**Query params**

| Param | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `lat` | float | Sí | Latitud GPS |
| `lng` | float | Sí | Longitud GPS |
| `limit` | integer | No (5) | Máximo por cadena (1–20) |

**Response** `200`
```typescript
UnifiedResponse<BranchOut[]>
```

---

### Catálogo — `/api/catalog`

#### `GET /api/catalog/status`

Estado del CatalogBot y estadísticas de cobertura de productos en la BD.

**Response** `200`
```typescript
UnifiedResponse<{
  // Estado del bot
  is_running: boolean;
  last_scan: string | null;
  // Estadísticas de BD
  db_stats: {
    total_store_products: number;
    total_canonical_products: number;
    matched_products: number;
    coverage_pct: number;
    store_breakdown: Array<{ store: string; products: number }>;
  };
}>
```

---

### Despensa — `/api/pantry`

#### `GET /api/pantry/`

Items de despensa activos del usuario autenticado.

**Response** `200`
```typescript
UnifiedResponse<PantryItemOut[]>
```

---

#### `POST /api/pantry/purchase`

Registra una compra y actualiza el stock estimado.

**Body**
```typescript
PantryPurchaseRequest
```

**Response** `200`
```typescript
UnifiedResponse<PantryItemOut>
```

---

### Asistente KAIROS — `/api/assistant`

#### `POST /api/assistant/optimize_cart`

Optimización de carrito con IA: agrupa por tienda para minimizar el gasto total.

**Body**
```typescript
OptimizeCartRequest
```

**Response** `200`
```typescript
UnifiedResponse<PlanResponse>
```

---

#### `POST /api/assistant/chat`

Chat conversacional con el asistente KAIROS (Groq LLM con fallback HuggingFace).

**Body**
```typescript
ChatRequest
```

**Response** `200`
```typescript
UnifiedResponse<{ reply: string }>
```

---

#### `GET /api/assistant/notifications`

Notificaciones del usuario (alertas de precios, confirmaciones de compra).

**Response** `200`
```typescript
UnifiedResponse<NotificationOut[]>
```

---

### Feedback — `/api/feedback`

#### `POST /api/feedback/`

Enviar reporte de bug, mejora o sugerencia.

**Body**
```typescript
FeedbackIn
```

**Response** `200`
```typescript
UnifiedResponse<{ id: number; message: string }>
```

---

#### `GET /api/feedback/`

Lista de feedbacks (admin).

**Response** `200`
```typescript
UnifiedResponse<FeedbackIn[]>
```

---

## Códigos de Error Comunes

| Status | Significado |
|--------|-------------|
| 400 | Input fuera de rango o demasiado largo |
| 401 | Token JWT inválido, expirado o tipo incorrecto |
| 403 | API key ausente o incorrecta · WAF bloqueó el request (SQLi/XSS/path traversal) |
| 404 | Recurso no encontrado |
| 422 | Body Pydantic inválido (campo faltante, tipo incorrecto) |
| 429 | Rate limit de login excedido (5 intentos / 60s) |
| 500 | Error interno del servidor (sin detalles en el body) |
| 503 | Base de datos no disponible |

Todos los errores retornan:
```json
{ "success": false, "data": null, "error": "mensaje legible" }
```
Sin tracebacks, rutas de archivo ni detalles de SQLAlchemy en el body.
