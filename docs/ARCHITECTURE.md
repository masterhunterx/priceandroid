# Arquitectura del Sistema — FreshCart

## Diagrama de Flujo

```
┌─────────────────────────────────────────────────────────────────┐
│                      CLIENTE (Browser/App)                      │
│   React 19 + TypeScript + Vite                                  │
│   Redux Toolkit · React Router · CartContext (localStorage)     │
└───────────────────────┬─────────────────────────────────────────┘
                        │ HTTPS (Vercel CDN)
                        │ Headers: X-API-Key, Authorization: Bearer JWT
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                    BACKEND — Railway                            │
│                                                                 │
│  ┌────────────────────────────────────────────────────────┐    │
│  │  Shield3 WAF (Middleware)                              │    │
│  │  • Rate limiting por IP                                │    │
│  │  • Blacklist dinámica                                  │    │
│  │  • Bloquea: SQLi, XSS, path traversal → 403            │    │
│  │  • Honeytokens (/wp-admin, /.env, /api/admin/...) →    │    │
│  │    ban inmediato + alerta Discord                       │    │
│  └────────────────────┬───────────────────────────────────┘    │
│                       │                                         │
│  ┌────────────────────▼───────────────────────────────────┐    │
│  │  FastAPI — api/main.py                                 │    │
│  │  • Security headers (CSP, HSTS, X-Frame-Options)       │    │
│  │  • Request size limit: 512 KB                          │    │
│  │  • DB lock middleware                                   │    │
│  │  • Prometheus metrics → /metrics                       │    │
│  │                                                         │    │
│  │  Routers (todos con Depends(get_api_key)):             │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │    │
│  │  │ products │ │  auth    │ │  deals   │ │  stores  │ │    │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │    │
│  │  │ catalog  │ │ pantry   │ │assistant │ │feedback  │ │    │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ │    │
│  └────────────────────┬───────────────────────────────────┘    │
│                       │                                         │
│  ┌────────────────────▼───────────────────────────────────┐    │
│  │  Capa de Servicios / Dominio                           │    │
│  │  • KairosAIService: Groq LLM → HuggingFace fallback    │    │
│  │  • cart_optimizer: minimize costo total por tienda      │    │
│  │  • meal_planner: generación de planes nutricionales     │    │
│  │  • Search cache: dict[str, (ts, result)], TTL 300s,    │    │
│  │    LRU cap 500 entries, thread-safe via Lock           │    │
│  └────────────────────┬───────────────────────────────────┘    │
│                       │                                         │
│  ┌────────────────────▼───────────────────────────────────┐    │
│  │  SQLAlchemy 2 ORM (core/db.py)                         │    │
│  │  Session factory con context manager                   │    │
│  └────────────────────┬───────────────────────────────────┘    │
│                       │                                         │
│  ┌────────────────────▼───────────────────────────────────┐    │
│  │  13 Agentes Daemon (background threads, daemon=True)   │    │
│  │  FluxEngineSentry · KairosProactive · StockScan · QA   │    │
│  │  SelfHealer · LogTracker · CatalogSync · ScraperHealth  │    │
│  │  SecAudit · SecHealer · FeedbackPipeline               │    │
│  │  PricePipeline · MatchPipeline                         │    │
│  └────────────────────────────────────────────────────────┘    │
└───────────────────────┬─────────────────────────────────────────┘
                        │
          ┌─────────────┴──────────────┐
          │                            │
          ▼                            ▼
┌─────────────────┐          ┌──────────────────┐
│  PostgreSQL 16  │          │  Servicios Ext.  │
│  (Railway)      │          │                  │
│                 │          │  Discord Bot     │
│  stores         │          │  (alertas,       │
│  branches       │          │  aprobaciones)   │
│  products       │          │                  │
│  store_products │          │  Groq API        │
│  prices         │          │  HuggingFace API │
│  pantry_items   │          │                  │
│  notifications  │          │  Scraper APIs:   │
│  feedback       │          │  Cencosud, etc.  │
│  user_prefs     │          └──────────────────┘
└─────────────────┘
          │
          ▼
┌─────────────────┐
│  Observabilidad │
│                 │
│  Prometheus     │
│  (métricas)     │
│       ↓         │
│  Grafana        │
│  (dashboards)   │
│       ↓         │
│  Grafana Loki   │
│  (JSON logs)    │
└─────────────────┘
```

---

## Flujo de una Request Típica (Búsqueda)

```
1. Frontend: GET /api/products/search?q=leche&store=jumbo
   → Header: X-API-Key, X-Branch-Context (opcional)

2. Shield WAF:
   → Valida IP no está en blacklist
   → Valida que "leche" no contiene payloads SQLi/XSS

3. FastAPI middleware:
   → Verifica X-API-Key (get_api_key dependency)
   → Verifica DB lock (no en mantenimiento)

4. Router products.search_products():
   → Valida longitud de q (max 100 chars)
   → Calcula cache_key = f"{user}|leche|jumbo|..."
   → Cache HIT? → retorna resultado inmediato

5. Cache MISS → SQLAlchemy:
   → JOIN store_products ↔ stores (filter by store=jumbo)
   → _build_text_filter(): LIKE con tolerancia a vocales/acentos
   → COUNT total, OFFSET/LIMIT para paginación
   → preload_latest_prices(): 1 query bulk para N productos
   → preload_price_insights(): 1 query bulk para N productos

6. _enrich_results():
   → Deduplica por canonical product_id
   → Construye PricePointOut[] con precios cargados
   → Llama best_price_info() por producto
   → is_favorite lookup

7. JIT sync en background (BackgroundTasks):
   → Si el producto no fue sincronizado en > X tiempo,
     lanza trigger_jit_sync() sin bloquear la response

8. _set_cached(): guarda resultado para próximos 300s

9. Retorna: UnifiedResponse<SearchResponse>
   { success: true, data: { results: [...], total: N, page: 1, page_size: 20 } }
```

---

## Modelo de Datos (Relaciones Clave)

```
Store (1) ──────── (N) Branch
  │
  └── (N) StoreProduct ──── (N) Price
            │
            └── (0..1) Product (canonical)
                          │
                          ├── (N) PriceInsight
                          └── (N) PantryItem ── (N) User
```

- **Store**: cadena (Jumbo, Lider). `slug` es el identificador de negocio.
- **Branch**: sucursal física con coordenadas GPS.
- **StoreProduct**: producto como aparece en el scraper (nombre y precio sin normalizar).
- **Product** (canonical): ficha unificada que agrupa StoreProducts equivalentes.
- **Price**: registro histórico de precio. El scraper inserta una fila por sync.
- **PantryItem**: inventario del usuario con estimación de depleción.

---

## Seguridad en Capas

```
Internet
   │
   ▼ [1] Shield3 WAF: IP blacklist, pattern matching, rate limit global
   ▼ [2] HTTPS/TLS: cifrado en tránsito (Railway + Vercel)
   ▼ [3] X-API-Key: primera barrera de autenticación de servicio
   ▼ [4] JWT HS256: identidad de usuario en endpoints autenticados
            │ type=access para operaciones normales
            │ type=refresh solo en /api/auth/refresh
   ▼ [5] Pydantic: validación de tipos, rangos y longitudes
   ▼ [6] SQLAlchemy ORM: queries parametrizadas (sin SQL raw)
   ▼ [7] bcrypt: almacenamiento seguro de contraseñas
            + timing normalization (_DUMMY_HASH) anti-enumeración
   ▼ [8] global_exception_handler: 500 sin tracebacks al cliente
```

---

## Agentes en Background

Los 13 daemons arrancan en `lifespan()` y corren en `daemon=True` threads. Al caer el proceso, mueren automáticamente. No hay supervisión de reinicio interno — Railway provee restart en fallo.

| Agente | Responsabilidad |
|--------|----------------|
| FluxEngineSentry | Monitorea salud del sistema y detecta anomalías |
| KairosProactive | Genera alertas de precios para usuarios con favoritos |
| StockScan | Detecta cambios de stock en productos vigilados |
| QA | Auto-testing de integridad de datos en BD |
| SelfHealer | Repara inconsistencias detectadas por QA |
| LogTracker | Agrega métricas de logs para Grafana |
| CatalogSync | Sincroniza el catálogo de productos periódicamente |
| ScraperHealth | Monitorea que los scrapers estén retornando datos frescos |
| SecAudit | Revisa intentos de intrusión y actualiza blacklists |
| SecHealer | Limpia tokens revocados y sessions expiradas |
| FeedbackPipeline | Procesa feedbacks y genera tickets de acción |
| PricePipeline | Consolida precios y calcula PriceInsights |
| MatchPipeline | Empareja StoreProducts con Products canónicos |
