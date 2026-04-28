"""
Pruebas de seguridad OWASP Top 10.

Cubre (sin duplicar test_security_and_validation.py):
  - A1 SQLi: payloads en q, category, store — respuesta nunca expone traceback/SQL
  - A3 XSS: el payload no se refleja sin escapar en la respuesta JSON
  - A5 Broken Access Control: path traversal, inputs sobredimensionados
  - A7 Broken Authentication: JWT manipulado, expirado, tipo incorrecto (access↔refresh)
  - Content-Type enforcement: toda respuesta de error es application/json
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json as _json
import time
import pytest
import jwt

_HAS_APP = False

try:
    from api.main import app as _unused  # noqa: F401 — solo para detectar si el entorno carga
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


def _no_internals_leaked(body: dict) -> None:
    """Asegura que el body no contiene información interna del servidor."""
    raw = _json.dumps(body).lower()
    assert "traceback" not in raw, f"Traceback en respuesta: {raw[:300]}"
    assert "sqlalchemy" not in raw, f"Detalles SQLAlchemy filtrados: {raw[:300]}"
    assert 'file "' not in raw, f"Ruta de archivo filtrada: {raw[:300]}"
    assert "line " not in raw or "Linea" in body.get("error", ""), \
        f"Stack frame filtrado: {raw[:100]}"


# ─── A1: SQL Injection ─────────────────────────────────────────────────────────

SQLI_PAYLOADS = [
    "'; DROP TABLE products; --",
    "' OR '1'='1",
    "1; SELECT * FROM users--",
    "' UNION SELECT NULL,NULL,NULL--",
    "' AND SLEEP(5)--",
    "%27%20OR%20%271%27%3D%271",   # URL-encoded
]


class TestSQLInjection:
    @pytest.mark.parametrize("payload", SQLI_PAYLOADS)
    def test_search_q_safe(self, payload):
        """SQLi en q: debe devolver 200 o 400, nunca un traceback interno."""
        r = client.get(f"/api/products/search?q={payload}", headers=AUTH)
        assert r.status_code in (200, 400), f"Status inesperado {r.status_code} para: {payload!r}"
        _no_internals_leaked(r.json())

    @pytest.mark.parametrize("payload", SQLI_PAYLOADS)
    def test_search_category_safe(self, payload):
        r = client.get(f"/api/products/search?category={payload}", headers=AUTH)
        assert r.status_code in (200, 400)
        _no_internals_leaked(r.json())

    @pytest.mark.parametrize("payload", SQLI_PAYLOADS)
    def test_search_store_safe(self, payload):
        r = client.get(f"/api/products/search?store={payload}", headers=AUTH)
        assert r.status_code in (200, 400)
        _no_internals_leaked(r.json())

    def test_product_id_non_integer_rejected(self):
        """product_id con payload SQL: el WAF lo bloquea (403) o FastAPI lo rechaza (422)."""
        r = client.get("/api/products/abc'; DROP TABLE--", headers=AUTH)
        assert r.status_code in (403, 404, 422)


# ─── A3: XSS Reflection ───────────────────────────────────────────────────────

XSS_PAYLOADS = [
    "<script>alert(1)</script>",
    "javascript:alert(document.cookie)",
    "<img src=x onerror=alert(1)>",
    '";alert(1)//',
    "<svg/onload=alert(1)>",
]


class TestXSSReflection:
    @pytest.mark.parametrize("payload", XSS_PAYLOADS)
    def test_search_does_not_reflect_xss_unescaped(self, payload):
        """El payload no debe aparecer sin escape en el body de la respuesta."""
        r = client.get(f"/api/products/search?q={payload}", headers=AUTH)
        assert r.headers.get("content-type", "").startswith("application/json"), \
            "La respuesta debe ser JSON incluso con input XSS"
        body_raw = r.text
        # JSON encode de Python escapa < > & → los payloads XSS nunca se reflejan literalmente
        assert "<script>" not in body_raw, f"<script> sin escapar en respuesta"
        assert "onerror=" not in body_raw, f"onerror= sin escapar en respuesta"
        assert "onload=" not in body_raw, f"onload= sin escapar en respuesta"


# ─── A5: Broken Access Control ────────────────────────────────────────────────

class TestAccessControl:
    def test_path_traversal_in_product_route(self):
        """Path traversal: el WAF lo bloquea (403) o FastAPI lo rechaza (404/422)."""
        r = client.get("/api/products/../../../etc/passwd", headers=AUTH)
        assert r.status_code in (403, 404, 422)

    def test_oversized_q_rejected_400(self):
        """Búsqueda con q > 100 chars → 400 con success=false."""
        r = client.get(f"/api/products/search?q={'a' * 101}", headers=AUTH)
        assert r.status_code == 400
        body = r.json()
        assert body.get("success") is False
        _no_internals_leaked(body)

    def test_oversized_category_rejected_400(self):
        r = client.get(f"/api/products/search?category={'z' * 101}", headers=AUTH)
        assert r.status_code == 400
        body = r.json()
        assert body.get("success") is False

    def test_negative_page_rejected(self):
        """page < 1 → FastAPI validation error (422)."""
        r = client.get("/api/products/search?q=leche&page=0", headers=AUTH)
        assert r.status_code == 422

    def test_page_size_over_100_rejected(self):
        r = client.get("/api/products/search?q=leche&page_size=101", headers=AUTH)
        assert r.status_code == 422

    def test_negative_product_id_returns_404(self):
        """ID negativo es entero válido pero no existe en BD."""
        r = client.get("/api/products/-1", headers=AUTH)
        assert r.status_code in (404, 422)
        _no_internals_leaked(r.json())


# ─── A7: Broken Authentication — JWT ──────────────────────────────────────────

class TestBrokenAuthentication:
    def _get_secret(self):
        from api.routers.auth import SECRET_KEY, ALGORITHM
        return SECRET_KEY, ALGORITHM

    def test_tampered_jwt_signature_rejected(self):
        """JWT con firma alterada debe dar 401."""
        import base64, json as _j
        sk, alg = self._get_secret()
        real_token = jwt.encode(
            {"sub": "admin", "type": "access", "exp": int(time.time()) + 3600, "iat": int(time.time())},
            sk, algorithm=alg
        )
        header, _, sig = real_token.split(".")
        fake_payload = base64.urlsafe_b64encode(
            _j.dumps({"sub": "hacker", "type": "access", "exp": 9999999999, "iat": 1}).encode()
        ).rstrip(b"=").decode()
        tampered = f"{header}.{fake_payload}.{sig}"

        r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tampered}"})
        assert r.status_code == 401
        _no_internals_leaked(r.json())

    def test_expired_token_rejected(self):
        """JWT expirado (exp=1, pasado Unix epoch) debe dar 401."""
        sk, alg = self._get_secret()
        expired = jwt.encode(
            {"sub": "admin", "type": "access", "exp": 1, "iat": 1},
            sk, algorithm=alg
        )
        r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"})
        assert r.status_code == 401

    def test_completely_invalid_jwt_rejected(self):
        r = client.get("/api/auth/me", headers={"Authorization": "Bearer not.a.token.at.all"})
        assert r.status_code == 401
        body = r.json()
        assert body.get("success") is False

    def test_refresh_token_rejected_by_me_endpoint(self):
        """Un refresh token usado en /me (que requiere type=access) → 401."""
        sk, alg = self._get_secret()
        refresh = jwt.encode(
            {"sub": "admin", "type": "refresh", "exp": int(time.time()) + 3600, "iat": int(time.time())},
            sk, algorithm=alg
        )
        r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {refresh}"})
        assert r.status_code == 401

    def test_access_token_rejected_by_refresh_endpoint(self):
        """Un access token usado en /refresh (que requiere type=refresh) → 401."""
        sk, alg = self._get_secret()
        access = jwt.encode(
            {"sub": "admin", "type": "access", "exp": int(time.time()) + 3600, "iat": int(time.time())},
            sk, algorithm=alg
        )
        r = client.post("/api/auth/refresh", headers={"Authorization": f"Bearer {access}"})
        assert r.status_code == 401

    def test_wrong_secret_jwt_rejected(self):
        """JWT firmado con una clave diferente → 401."""
        _, alg = self._get_secret()
        evil_token = jwt.encode(
            {"sub": "admin", "type": "access", "exp": int(time.time()) + 3600, "iat": int(time.time())},
            "WRONG_SECRET_KEY_TOTALLY_DIFFERENT",
            algorithm=alg
        )
        r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {evil_token}"})
        assert r.status_code == 401

    def test_no_bearer_prefix_rejected(self):
        """Authorization sin prefijo Bearer → no se extrae token → 401."""
        sk, alg = self._get_secret()
        token = jwt.encode(
            {"sub": "admin", "type": "access", "exp": int(time.time()) + 3600, "iat": int(time.time())},
            sk, algorithm=alg
        )
        # Sin "Bearer " prefix
        r = client.get("/api/auth/me", headers={"Authorization": token})
        assert r.status_code == 401


# ─── Content-Type Enforcement ─────────────────────────────────────────────────

class TestResponseContentType:
    def test_successful_response_is_json(self):
        r = client.get("/api/products/search?q=leche", headers=AUTH)
        assert "application/json" in r.headers.get("content-type", "")

    def test_error_400_is_json(self):
        r = client.get(f"/api/products/search?q={'a' * 101}", headers=AUTH)
        assert "application/json" in r.headers.get("content-type", "")

    def test_error_401_is_json(self):
        r = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid"})
        assert "application/json" in r.headers.get("content-type", "")

    def test_error_403_is_json(self):
        r = client.get("/api/products/search?q=leche")  # sin API key
        assert "application/json" in r.headers.get("content-type", "")

    def test_error_404_is_json(self):
        r = client.get("/api/products/99999999", headers=AUTH)
        assert "application/json" in r.headers.get("content-type", "")
