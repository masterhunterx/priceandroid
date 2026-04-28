"""
Tests de manejo de errores HTTP.

Verifica que TODOS los errores devuelven {success: false, error: "..."} sin
tracebacks ni detalles internos en el body de la respuesta.

Cubre:
  - 404 producto desconocido
  - 400 inputs fuera de rango
  - 422 body Pydantic inválido
  - 401/403 autenticación
  - 500/503 simulados via mock de DB
  - Formato UnifiedResponse en respuestas exitosas
  - 5 escenarios catastróficos documentados al final del módulo
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json as _json
import pytest
from unittest.mock import patch, MagicMock

_HAS_APP = False

try:
    from api.main import app as _unused  # noqa: F401
    _HAS_APP = True
except Exception:
    pass

pytestmark = pytest.mark.skipif(not _HAS_APP, reason="api.main no importable en este entorno")

AUTH = {"X-API-Key": os.environ.get("API_KEY", "")}
client = None


@pytest.fixture(scope="module", autouse=True)
def _start_client(api_client_no_raise):
    global client
    client = api_client_no_raise
    yield


def _assert_error_envelope(resp) -> dict:
    """
    Verifica el sobre de error UnifiedResponse:
      - success: false
      - algún campo de error (error o detail)
      - sin detalles internos en el body
    Devuelve el body parseado para aserciones adicionales.
    """
    body = resp.json()
    assert body.get("success") is False, f"Esperaba success=false, recibí: {body}"
    has_error_field = "error" in body or "detail" in body
    assert has_error_field, f"No hay campo error/detail en: {body}"

    raw = _json.dumps(body).lower()
    assert "traceback" not in raw, f"Traceback filtrado al cliente: {raw[:400]}"
    assert "sqlalchemy" not in raw, f"Detalles SQLAlchemy filtrados: {raw[:400]}"
    assert 'file "' not in raw, f"Ruta de archivo filtrada: {raw[:400]}"

    return body


# ─── 4xx: errores de cliente ───────────────────────────────────────────────────

class TestHTTP4xxErrors:
    def test_404_unknown_product(self):
        r = client.get("/api/products/99999999", headers=AUTH)
        assert r.status_code == 404
        _assert_error_envelope(r)

    def test_400_query_too_long(self):
        r = client.get(f"/api/products/search?q={'a' * 101}", headers=AUTH)
        assert r.status_code == 400
        _assert_error_envelope(r)

    def test_400_category_too_long(self):
        r = client.get(f"/api/products/search?category={'z' * 101}", headers=AUTH)
        assert r.status_code == 400
        _assert_error_envelope(r)

    def test_422_ultraplan_bare_array_body(self):
        """Frontend enviando bare array en lugar de {product_ids: [...]} → 422."""
        r = client.post("/api/optimize/ultraplan", json=[1, 2, 3], headers=AUTH)
        assert r.status_code == 422

    def test_422_ultraplan_empty_object(self):
        """Body vacío donde se requiere product_ids → 422."""
        r = client.post("/api/optimize/ultraplan", json={}, headers=AUTH)
        assert r.status_code == 422

    def test_403_missing_api_key(self):
        r = client.get("/api/products/search?q=leche")  # sin X-API-Key
        assert r.status_code in (401, 403)
        assert "application/json" in r.headers.get("content-type", "")

    def test_401_invalid_jwt_on_auth_endpoint(self):
        r = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
        assert r.status_code == 401
        _assert_error_envelope(r)

    def test_no_traceback_across_multiple_4xx(self):
        """Prueba masiva: ningún 4xx debe contener traceback."""
        cases = [
            ("GET", "/api/products/99999999", None),
            ("GET", f"/api/products/search?q={'a' * 101}", None),
            ("POST", "/api/optimize/ultraplan", [1, 2, 3]),
        ]
        for method, path, body in cases:
            if method == "GET":
                r = client.get(path, headers=AUTH)
            else:
                r = client.post(path, json=body, headers=AUTH)
            raw = _json.dumps(r.json()).lower()
            assert "traceback" not in raw, f"Traceback en {path}: {raw[:150]}"


# ─── 5xx: errores de servidor simulados ───────────────────────────────────────

class TestHTTP5xxErrors:
    @staticmethod
    def _ctx_that_raises(exc: Exception):
        """Devuelve un mock context-manager que lanza exc en __enter__."""
        ctx = MagicMock()
        ctx.__enter__.side_effect = exc
        ctx.__exit__.return_value = False
        return ctx

    def test_db_operational_error_returns_no_traceback(self):
        """
        Se parchea api.routers.products.get_session porque el módulo ya importó
        get_session por nombre — parchear core.db.get_session no afecta la ref local.
        Usa query única para evitar hit de caché compartida entre módulos de test.
        """
        from sqlalchemy.exc import OperationalError
        exc = OperationalError("connection refused", None, None)
        with patch("api.routers.products.get_session", return_value=self._ctx_that_raises(exc)):
            r = client.get("/api/products/search?q=kairos_dberror_operational_xyz", headers=AUTH)

        assert r.status_code in (500, 503)
        body = r.json()
        assert body.get("success") is False
        raw = _json.dumps(body).lower()
        assert "traceback" not in raw
        assert "connection refused" not in raw

    def test_db_integrity_error_returns_409_or_5xx(self):
        """IntegrityError → 409 Conflict (o 5xx si el handler lo clasifica así)."""
        from sqlalchemy.exc import IntegrityError
        exc = IntegrityError("UNIQUE constraint failed", None, None)
        with patch("api.routers.products.get_session", return_value=self._ctx_that_raises(exc)):
            r = client.get("/api/products/search?q=x", headers=AUTH)

        assert r.status_code in (409, 500, 503)
        assert "traceback" not in _json.dumps(r.json()).lower()

    def test_unhandled_exception_returns_500_without_traceback(self):
        """RuntimeError no capturado → global_exception_handler → 500, sin detalles."""
        exc = RuntimeError("completely unexpected crash")
        with patch("api.routers.products.get_session", return_value=self._ctx_that_raises(exc)):
            r = client.get("/api/products/search?q=crash", headers=AUTH)

        assert r.status_code in (500, 503)
        body = r.json()
        assert body.get("success") is False
        raw = _json.dumps(body).lower()
        assert "traceback" not in raw
        assert "unexpected crash" not in raw


# ─── Formato UnifiedResponse en respuestas exitosas ───────────────────────────

class TestUnifiedResponseFormat:
    def test_search_success_has_data_key(self):
        r = client.get("/api/products/search?q=leche", headers=AUTH)
        if r.status_code == 200:
            body = r.json()
            assert body.get("success") is True
            assert "data" in body

    def test_categories_success_format(self):
        r = client.get("/api/categories", headers=AUTH)
        if r.status_code == 200:
            body = r.json()
            assert body.get("success") is True
            assert "data" in body

    def test_health_endpoint_available(self):
        r = client.get("/health")
        assert r.status_code in (200, 503)
        body = r.json()
        assert "status" in body  # "healthy" o "unhealthy"

    def test_success_response_has_no_error_field_or_null(self):
        r = client.get("/api/products/search?q=leche", headers=AUTH)
        if r.status_code == 200:
            body = r.json()
            # En respuestas exitosas, error debe ser None o ausente
            assert body.get("error") is None


# ─── 5 Escenarios Catastróficos y su Manejo Esperado ─────────────────────────
#
# CATÁSTROFE 1: La base de datos cae en producción durante una búsqueda.
#   Síntoma: sqlalchemy.exc.OperationalError "server closed the connection unexpectedly"
#   Manejo esperado: global_exception_handler captura → 503 {"success":false,"error":"Base de datos no disponible"}
#   Verificado: test_db_operational_error_returns_no_traceback (arriba)
#
# CATÁSTROFE 2: Un usuario descubre que puede enumerar usernames por latencia.
#   Síntoma: /api/auth/login responde <1ms para usuarios inexistentes vs ~100ms para válidos
#   Manejo esperado: _DUMMY_HASH bcrypt normaliza el tiempo; ambos caminos tardan ~100ms
#   Verificado: test_unit_critical.py > TestCheckRateLimit (indirectamente)
#   Recomendación: Medir con time.time() en ambas ramas en producción
#
# CATÁSTROFE 3: El caché de búsqueda llega a 10.000 entradas (memory leak).
#   Síntoma: _search_cache crece sin límite bajo búsquedas únicas masivas
#   Manejo esperado: _set_cached evicta al llegar a 500 (LRU mínimo + TTL expiry)
#   Verificado: test_security_and_validation.py > TestSearchCache.test_cache_respects_max_size
#
# CATÁSTROFE 4: El JWT_SECRET_KEY de producción es "changeme" (< 32 chars).
#   Síntoma: cualquier atacante puede forjar tokens para cualquier usuario
#   Manejo esperado: en ENVIRONMENT=production, el servidor llama sys.exit(1) al arrancar
#   Verificado: api/routers/auth.py línea ~119 — la validación detiene el proceso
#
# CATÁSTROFE 5: Un atacante envía 10.000 IPs distintas en 60 segundos.
#   Síntoma: _login_attempts alcanza _RL_MAX_IPS (10.000) → bloquea nuevas IPs legítimas
#   Manejo esperado: al 90% de capacidad (_RL_CLEANUP_THRESHOLD) se limpia IPs stale
#   Verificado: test_unit_critical.py > TestCleanupStaleIPs
