# Guía de Contribución

## Requisitos previos

- Leer el README.md y levantar el proyecto localmente antes de contribuir.
- Toda nueva funcionalidad debe incluir tests.
- Los tests existentes no deben romperse (CI falla si alguno falla).

---

## Python (Backend)

### Estilo de código

El proyecto sigue **PEP 8** con las siguientes herramientas:

```bash
# Formatear
black backend/

# Verificar estilo
flake8 backend/ --max-line-length=100

# Verificar tipos
mypy backend/api/ --ignore-missing-imports
```

Configuración recomendada en `.flake8`:

```ini
[flake8]
max-line-length = 100
extend-ignore = E203, W503
exclude = __pycache__, .venv, alembic/versions/
```

### Convenciones

- **Type hints** obligatorios en toda función pública.
- **Docstrings** solo cuando el _porqué_ no es obvio desde el nombre. Ningún docstring de múltiples párrafos.
- **Nombres**: `snake_case` para funciones y variables, `PascalCase` para clases, `UPPER_CASE` para constantes de módulo.
- **Imports**: stdlib → third-party → local, separados por línea en blanco.
- **No silenciar excepciones**: `except Exception: pass` está prohibido. Loguear o re-lanzar.
- **Respuestas**: siempre usar `UnifiedResponse` — nunca devolver dicts crudos desde un router.

### Tests (pytest)

```bash
cd backend
pytest tests/ -v --tb=short
```

- Un test por comportamiento, no por función.
- Fixtures de setup/teardown usando `@pytest.fixture(autouse=True)` con `yield`.
- Mockear al nivel del consumidor: `patch("api.routers.products.get_session")`, no `patch("core.db.get_session")`.
- Tests de errores HTTP: usar el fixture `api_client_no_raise` de `conftest.py`.
- Consultas únicas en tests de caché para evitar hits del singleton `_search_cache`.

---

## TypeScript (Frontend)

### Estilo de código

```bash
cd frontend/freshcart---smart-grocery-assistant

# Verificar
npm run lint

# Formatear (si está configurado Prettier)
npx prettier --write src/
```

Configuración ESLint relevante (`.eslintrc` o `eslint.config.js`):

```json
{
  "extends": ["react-app", "plugin:@typescript-eslint/recommended"],
  "rules": {
    "@typescript-eslint/no-explicit-any": "warn",
    "@typescript-eslint/explicit-function-return-type": "off",
    "no-console": ["warn", { "allow": ["warn", "error"] }]
  }
}
```

### Convenciones

- **No `any`** sin justificación. Usar tipos genéricos o `unknown` + narrowing.
- **Componentes**: functional components con tipos explícitos en props.
- **Hooks**: un hook por responsabilidad. No mezclar lógica de datos con lógica de UI.
- **API calls**: siempre a través de `lib/api.ts` — nunca `fetch` directo en componentes.
- **Estado global**: Redux Toolkit para estado compartido, `useState` para estado local de UI.
- **Errores**: envolver secciones críticas en `<ErrorBoundary section="nombre">`.

### Tests (Vitest)

```bash
npm test           # una pasada
npm run test:watch # modo watch
```

- Testear funciones puras y hooks directamente (sin render de pantalla completa).
- Evitar tests que hagan fetch real — usar solo localStorage y funciones utilitarias.
- Cleanup entre tests con `cleanup()` de `@testing-library/react` cuando se monta más de un árbol.

---

## Commits

Formato: `tipo(alcance): descripción breve en imperativo`

| Tipo | Cuándo usarlo |
|------|---------------|
| `feat` | Nueva funcionalidad |
| `fix` | Corrección de bug |
| `refactor` | Cambio de código sin afectar comportamiento |
| `test` | Agregar o corregir tests |
| `docs` | Solo documentación |
| `chore` | Config, CI, dependencias |
| `perf` | Mejora de rendimiento |

Ejemplos:
```
feat(cart): agregar soporte multi-tienda con persistencia por usuario
fix(auth): normalizar timing bcrypt para usuarios inexistentes
test(products): cubrir escenario de caché llena con LRU eviction
```

- Descripción en español o inglés consistente con el historial del proyecto.
- Sin puntos finales en el subject.
- Body opcional: explica el _porqué_, no el _qué_.

---

## Pull Requests

1. Rama desde `main`: `git checkout -b feat/nombre-descriptivo`
2. Tests pasando localmente antes de abrir el PR.
3. Descripción del PR: qué cambia, por qué, cómo probarlo.
4. Un PR por funcionalidad — no acumular cambios no relacionados.

---

## Seguridad

- Nunca commitear `.env` ni claves reales.
- Inputs del usuario siempre validados con Pydantic en el backend (longitud, tipo, rango).
- Nuevos endpoints deben aplicar `Depends(get_api_key)` a menos que sean públicos intencionalmente.
- Reportar vulnerabilidades por privado antes de abrir un issue público.
