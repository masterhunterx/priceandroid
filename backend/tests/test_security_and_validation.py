"""
Tests de seguridad, validación de inputs y thread-safety.
Cubre los puntos identificados en la auditoría:
  - Thread-safety del _search_counter (race condition fix)
  - Cache de búsqueda (30s TTL)
  - Validación de inputs (OptimizeCartRequest, ultraplan)
  - Protección brute-force de API key
"""

import os
import sys
import threading
import time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app, raise_server_exceptions=False)

VALID_KEY = os.environ.get("API_KEY", "")
AUTH = {"X-API-Key": VALID_KEY}
BAD_AUTH = {"X-API-Key": "wrong-key-00000"}


# ---------------------------------------------------------------------------
# Auth flow
# ---------------------------------------------------------------------------

class TestAuthFlow:
    def test_valid_key_accepted(self):
        r = client.get("/api/stores", headers=AUTH)
        assert r.status_code == 200

    def test_missing_key_blocked(self):
        r = client.get("/api/stores")
        assert r.status_code == 403

    def test_wrong_key_blocked(self):
        r = client.get("/api/stores", headers=BAD_AUTH)
        assert r.status_code in (401, 403)

    def test_brute_force_blocks_after_threshold(self):
        """10 consecutive wrong-key requests should trigger IP block (429 or 403)."""
        from api import middleware as mw
        # Reset failure state for clean test
        with mw._apikey_lock:
            mw._apikey_failures.clear()

        for _ in range(11):
            r = client.get("/api/stores", headers=BAD_AUTH)

        # After threshold, should be blocked
        assert r.status_code in (403, 429)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestInputValidation:
    def test_optimize_cart_empty_list_rejected(self):
        r = client.post("/api/products/optimize-cart", json={"items": []}, headers=AUTH)
        assert r.status_code == 422

    def test_optimize_cart_too_many_items_rejected(self):
        items = [{"product_id": i + 1, "name": f"prod{i}", "quantity": 1} for i in range(101)]
        r = client.post("/api/products/optimize-cart", json={"items": items}, headers=AUTH)
        assert r.status_code == 422

    def test_optimize_cart_negative_id_rejected(self):
        r = client.post(
            "/api/products/optimize-cart",
            json={"items": [{"product_id": -1, "name": "x", "quantity": 1}]},
            headers=AUTH,
        )
        assert r.status_code == 422

    def test_optimize_cart_zero_quantity_rejected(self):
        r = client.post(
            "/api/products/optimize-cart",
            json={"items": [{"product_id": 1, "name": "leche", "quantity": 0}]},
            headers=AUTH,
        )
        assert r.status_code == 422

    def test_ultraplan_empty_list_rejected(self):
        r = client.post("/api/deals/ultraplan", json={"product_ids": []}, headers=AUTH)
        assert r.status_code in (400, 422)

    def test_ultraplan_over_100_items_rejected(self):
        r = client.post(
            "/api/deals/ultraplan",
            json={"product_ids": list(range(1, 102))},
            headers=AUTH,
        )
        assert r.status_code in (400, 422)

    def test_ultraplan_negative_id_rejected(self):
        r = client.post(
            "/api/deals/ultraplan",
            json={"product_ids": [-5, 1, 2]},
            headers=AUTH,
        )
        assert r.status_code in (400, 422)


# ---------------------------------------------------------------------------
# Thread-safety: _search_counter
# ---------------------------------------------------------------------------

class TestSearchCounterThreadSafety:
    def test_concurrent_increments_are_consistent(self):
        from api.routers.deals import track_search_term, _search_counter
        _search_counter.clear()

        errors = []

        def increment_many():
            for _ in range(500):
                try:
                    track_search_term("leche")
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=increment_many) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"
        assert _search_counter["leche"] == 5000

    def test_short_term_ignored(self):
        from api.routers.deals import track_search_term, _search_counter
        _search_counter.clear()
        track_search_term("a")   # < 2 chars
        track_search_term("")
        assert len(_search_counter) == 0


# ---------------------------------------------------------------------------
# Search cache
# ---------------------------------------------------------------------------

class TestSearchCache:
    def test_same_query_hits_cache(self):
        """Two identical searches should return the same object (cache hit)."""
        from api.routers.products import _get_cached, _set_cached
        _set_cached("test_key", {"result": 42})
        hit = _get_cached("test_key")
        assert hit == {"result": 42}

    def test_cache_expires_after_ttl(self):
        from api.routers import products as prod_mod
        from api.routers.products import _set_cached, _get_cached, _search_cache

        # Inject an expired entry (timestamp 100 seconds ago)
        with prod_mod._search_cache_lock:
            _search_cache["stale_key"] = (time.time() - 100, {"old": True})

        result = _get_cached("stale_key")
        assert result is None

    def test_cache_respects_max_size(self):
        """Cache should not grow beyond 500 entries."""
        from api.routers.products import _set_cached, _search_cache, _search_cache_lock

        for i in range(600):
            _set_cached(f"key_{i}", i)

        with _search_cache_lock:
            size = len(_search_cache)

        assert size <= 500
