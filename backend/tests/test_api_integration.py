"""
Tests de integración — endpoints críticos de la API.
Usa SQLite en memoria (conftest.py). No requiere red ni scrapers activos.

Cubre:
  - Autenticación / API key
  - Búsqueda de productos (estructura de respuesta)
  - Endpoint de stores
  - Endpoint de deals
  - Endpoint de pantry
  - Límites de tamaño de payload (seguridad)
  - Rutas honeytrap (deben dar 403)
"""
import pytest


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def test_no_api_key_returns_403(api_client):
    r = api_client.get("/api/stores")
    assert r.status_code == 403


def test_wrong_api_key_returns_403(api_client):
    r = api_client.get("/api/stores", headers={"X-API-Key": "wrong"})
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Stores
# ---------------------------------------------------------------------------

def test_stores_returns_unified_response(api_client, headers):
    r = api_client.get("/api/stores", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)


# ---------------------------------------------------------------------------
# Products / Search
# ---------------------------------------------------------------------------

def test_search_empty_query_ok(api_client, headers):
    r = api_client.get("/api/products/search?q=", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert "data" in body


def test_search_response_schema(api_client, headers):
    r = api_client.get("/api/products/search?q=leche&page=1&page_size=5", headers=headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert "results" in data
    assert "total" in data
    assert "page" in data
    assert isinstance(data["results"], list)


def test_search_page_size_capped(api_client, headers):
    r = api_client.get("/api/products/search?q=leche&page_size=9999", headers=headers)
    # Debe responder 200 o 422 — nunca 500
    assert r.status_code in (200, 422)


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

def test_categories_schema(api_client, headers):
    r = api_client.get("/api/categories", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)


# ---------------------------------------------------------------------------
# Deals
# ---------------------------------------------------------------------------

def test_deals_endpoint_ok(api_client, headers):
    r = api_client.get("/api/deals?limit=5", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True


# ---------------------------------------------------------------------------
# Pantry
# ---------------------------------------------------------------------------

def test_pantry_list_ok(api_client, headers):
    r = api_client.get("/api/pantry", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)


def test_pantry_buy_missing_body_422(api_client, headers):
    r = api_client.post("/api/pantry/purchase", json={}, headers=headers)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Seguridad — honeytokens y límites
# ---------------------------------------------------------------------------

def test_wp_admin_blocked(api_client):
    r = api_client.get("/wp-admin")
    assert r.status_code == 403


def test_env_file_blocked(api_client):
    r = api_client.get("/.env")
    assert r.status_code == 403


def test_large_payload_rejected(api_client, headers):
    # 600 KB de payload → debe ser rechazado (límite 512 KB)
    big = "x" * 620_000
    r = api_client.post(
        "/api/products/search",
        content=big,
        headers={**headers, "Content-Length": str(len(big))},
    )
    assert r.status_code in (413, 405, 422)


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------

def test_root_online(api_client):
    r = api_client.get("/")
    assert r.status_code == 200
    assert r.json()["status"] == "online"
