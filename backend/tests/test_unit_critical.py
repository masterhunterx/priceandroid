"""
Unit tests críticos — funciones puras sin IO ni HTTP.

Cubre (sin duplicar test_security_and_validation.py):
  - analyze_promo: todos los tipos de oferta, multi-unit, casos límite
  - best_price_info: stock vacío, todos sin stock, precio más bajo
  - _infer_unit_label: variantes de unidades, case-insensitive, desconocidas
  - _check_rate_limit: primer intento, límite exacto, ventana expirada
  - _revoke_token / _is_token_revoked: TTL, cleanup automático, iat independiente
  - _get_approval_if_valid: TTL de aprobaciones, usuario inexistente
  - _cleanup_stale_ips_unsafe: limpia stale, preserva activas
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from types import SimpleNamespace


# ─── analyze_promo ─────────────────────────────────────────────────────────────

class TestAnalyzePromo:
    @pytest.fixture(autouse=True)
    def _fn(self):
        from api.utils import analyze_promo
        self.fn = analyze_promo

    def test_empty_string_returns_defaults(self):
        r = self.fn("")
        assert r == {"is_card": False, "label": "", "offer_type": "generic", "unit_price": None}

    def test_card_keyword_cencosud(self):
        r = self.fn("Precio con tarjeta cencosud válido")
        assert r["is_card"] is True
        assert r["label"] == "Tarjeta Cencosud"
        assert r["offer_type"] == "card"

    def test_card_keyword_club_unimarc(self):
        r = self.fn("Oferta club unimarc esta semana")
        assert r["is_card"] is True
        assert r["offer_type"] == "card"

    def test_card_keyword_tarjeta_lider(self):
        r = self.fn("Descuento con tarjeta lider bci exclusivo")
        assert r["is_card"] is True
        assert r["label"] == "Tarjeta Lider BCI"

    def test_internet_channel(self):
        r = self.fn("Precio exclusivo internet")
        assert r["offer_type"] == "internet"
        assert r["label"] == "Exclusivo Web"
        assert r["is_card"] is False

    def test_web_keyword_also_internet(self):
        r = self.fn("Solo disponible en web")
        assert r["offer_type"] == "internet"

    def test_app_channel(self):
        r = self.fn("Descuento exclusivo app móvil")
        assert r["offer_type"] == "app"
        assert r["label"] == "Exclusivo App"
        assert r["is_card"] is False

    def test_multi_unit_3_por_2000(self):
        r = self.fn("3 por 2000")
        assert r["unit_price"] is not None
        assert abs(r["unit_price"] - 666.666) < 1

    def test_multi_unit_2_x_price_with_dot_separator(self):
        r = self.fn("2 x $1.500")
        assert r["unit_price"] == 750.0

    def test_multi_unit_4_x_no_decimal(self):
        r = self.fn("4 x 1000")
        assert r["unit_price"] == 250.0

    def test_zero_qty_in_promo_does_not_crash(self):
        """qty=0 en promo — la división por cero debe manejarse silenciosamente."""
        r = self.fn("0 por 1000")
        assert r["unit_price"] is None

    def test_card_takes_priority_over_internet(self):
        """Si el texto contiene tanto tarjeta como 'web', la tarjeta gana (primer break)."""
        r = self.fn("Precio tarjeta lider disponible en internet")
        assert r["offer_type"] == "card"

    def test_generic_promo_no_keywords(self):
        r = self.fn("Oferta limitada por tiempo")
        assert r["offer_type"] == "generic"
        assert r["is_card"] is False
        assert r["unit_price"] is None

    def test_case_insensitive_matching(self):
        r = self.fn("CLUB UNIMARC DIAMANTE")
        assert r["is_card"] is True

    def test_no_multi_unit_match_leaves_unit_price_none(self):
        r = self.fn("Precio rebajado a $990")
        assert r["unit_price"] is None


# ─── best_price_info ───────────────────────────────────────────────────────────

def _pp(price=None, in_stock=True, store_name="Jumbo", store_slug="jumbo"):
    return SimpleNamespace(price=price, in_stock=in_stock, store_name=store_name, store_slug=store_slug)


class TestBestPriceInfo:
    @pytest.fixture(autouse=True)
    def _fn(self):
        from api.utils import best_price_info
        self.fn = best_price_info

    def test_empty_list_returns_triple_none(self):
        assert self.fn([]) == (None, None, None)

    def test_all_out_of_stock_returns_triple_none(self):
        points = [_pp(1000, False), _pp(900, False)]
        assert self.fn(points) == (None, None, None)

    def test_all_prices_none_returns_triple_none(self):
        points = [_pp(None, True), _pp(None, True)]
        assert self.fn(points) == (None, None, None)

    def test_single_in_stock_returned(self):
        price, store, slug = self.fn([_pp(999, True, "Lider", "lider")])
        assert price == 999
        assert store == "Lider"
        assert slug == "lider"

    def test_returns_cheapest_in_stock(self):
        points = [
            _pp(2000, True, "Jumbo", "jumbo"),
            _pp(1500, True, "Lider", "lider"),
            _pp(1200, False, "Unimarc", "unimarc"),  # más barato pero sin stock
        ]
        price, store, slug = self.fn(points)
        assert price == 1500
        assert slug == "lider"

    def test_ignores_out_of_stock_even_if_cheaper(self):
        points = [_pp(500, False, "A", "a"), _pp(800, True, "B", "b")]
        price, _, slug = self.fn(points)
        assert price == 800
        assert slug == "b"

    def test_equal_prices_returns_first_found(self):
        points = [_pp(1000, True, "A", "a"), _pp(1000, True, "B", "b")]
        price, _, _ = self.fn(points)
        assert price == 1000

    def test_ignores_none_price_among_valid_ones(self):
        points = [_pp(None, True, "X", "x"), _pp(700, True, "Y", "y")]
        price, _, slug = self.fn(points)
        assert price == 700
        assert slug == "y"


# ─── _infer_unit_label ─────────────────────────────────────────────────────────

class TestInferUnitLabel:
    @pytest.fixture(autouse=True)
    def _fn(self):
        from api.utils import _infer_unit_label
        self.fn = _infer_unit_label

    def test_gram_variants(self):
        for unit in ("g", "gr", "grs", "gramos", "kg", "kgs"):
            assert self.fn(unit) == "$/100g", f"Falló para: {unit!r}"

    def test_liquid_variants(self):
        for unit in ("ml", "cc", "l", "lt", "lts", "litro", "litros"):
            assert self.fn(unit) == "$/100ml", f"Falló para: {unit!r}"

    def test_empty_string_returns_none(self):
        assert self.fn("") is None

    def test_none_returns_none(self):
        assert self.fn(None) is None  # (unit or "").lower() absorbe None

    def test_unknown_units_return_none(self):
        assert self.fn("unidades") is None
        assert self.fn("packs") is None
        assert self.fn("caja") is None

    def test_case_insensitive(self):
        assert self.fn("KG") == "$/100g"
        assert self.fn("ML") == "$/100ml"
        assert self.fn("LITROS") == "$/100ml"

    def test_whitespace_stripped(self):
        assert self.fn("  kg  ") == "$/100g"
        assert self.fn(" ml ") == "$/100ml"


# ─── Auth: _check_rate_limit ───────────────────────────────────────────────────

class TestCheckRateLimit:
    @pytest.fixture(autouse=True)
    def _clean(self):
        from api.routers.auth import _login_attempts, _rl_lock
        with _rl_lock:
            _login_attempts.clear()
        yield
        with _rl_lock:
            _login_attempts.clear()

    def test_first_attempt_always_allowed(self):
        from api.routers.auth import _check_rate_limit
        assert _check_rate_limit("10.0.0.1") is True

    def test_exactly_max_attempts_allowed(self):
        from api.routers.auth import _check_rate_limit, _RL_MAX_ATTEMPTS
        ip = "10.0.0.2"
        results = [_check_rate_limit(ip) for _ in range(_RL_MAX_ATTEMPTS)]
        assert all(results), "Los primeros MAX intentos deben estar permitidos"

    def test_one_over_limit_is_blocked(self):
        from api.routers.auth import _check_rate_limit, _RL_MAX_ATTEMPTS
        ip = "10.0.0.3"
        for _ in range(_RL_MAX_ATTEMPTS):
            _check_rate_limit(ip)
        assert _check_rate_limit(ip) is False

    def test_expired_window_resets_counter(self):
        from api.routers.auth import _check_rate_limit, _login_attempts, _rl_lock, _RL_WINDOW, _RL_MAX_ATTEMPTS
        ip = "10.0.0.4"
        # Inyectar intentos artificialmente viejos (fuera de la ventana de 60s)
        old_ts = time.time() - _RL_WINDOW - 5
        with _rl_lock:
            _login_attempts[ip] = [old_ts] * _RL_MAX_ATTEMPTS
        # El siguiente intento debe ser permitido (la ventana expiró)
        assert _check_rate_limit(ip) is True

    def test_different_ips_are_independent(self):
        from api.routers.auth import _check_rate_limit, _RL_MAX_ATTEMPTS
        ip_a, ip_b = "10.0.1.1", "10.0.1.2"
        for _ in range(_RL_MAX_ATTEMPTS):
            _check_rate_limit(ip_a)
        # ip_a agotado, ip_b debe quedar libre
        assert _check_rate_limit(ip_a) is False
        assert _check_rate_limit(ip_b) is True


# ─── Auth: token revocation ────────────────────────────────────────────────────

class TestTokenRevocation:
    @pytest.fixture(autouse=True)
    def _clean(self):
        from api.routers.auth import _revoked_tokens, _revoked_lock
        with _revoked_lock:
            _revoked_tokens.clear()
        yield
        with _revoked_lock:
            _revoked_tokens.clear()

    def test_fresh_token_not_revoked(self):
        from api.routers.auth import _is_token_revoked
        payload = {"sub": "alice", "iat": time.time(), "exp": time.time() + 3600}
        assert _is_token_revoked(payload) is False

    def test_revoked_token_detected(self):
        from api.routers.auth import _revoke_token, _is_token_revoked
        payload = {"sub": "bob", "iat": time.time(), "exp": time.time() + 3600}
        _revoke_token(payload)
        assert _is_token_revoked(payload) is True

    def test_expired_revoked_entries_cleaned_on_query(self):
        """_is_token_revoked barre entradas expiradas en cada consulta."""
        from api.routers.auth import _is_token_revoked, _revoked_tokens, _revoked_lock
        past_exp = time.time() - 10
        stale_key = ("stale_user", 12345)
        with _revoked_lock:
            _revoked_tokens[stale_key] = past_exp

        # Consultar cualquier token dispara el cleanup
        _is_token_revoked({"sub": "x", "iat": 0})
        with _revoked_lock:
            assert stale_key not in _revoked_tokens

    def test_same_user_different_iat_are_independent(self):
        """Tokens del mismo usuario con distinto iat no se revogan juntos."""
        from api.routers.auth import _revoke_token, _is_token_revoked
        now = time.time()
        payload_a = {"sub": "carol", "iat": now, "exp": now + 3600}
        payload_b = {"sub": "carol", "iat": now + 1, "exp": now + 3601}
        _revoke_token(payload_a)
        assert _is_token_revoked(payload_a) is True
        assert _is_token_revoked(payload_b) is False

    def test_revocation_survives_multiple_queries(self):
        from api.routers.auth import _revoke_token, _is_token_revoked
        payload = {"sub": "dave", "iat": time.time(), "exp": time.time() + 7200}
        _revoke_token(payload)
        for _ in range(5):
            assert _is_token_revoked(payload) is True


# ─── Auth: _get_approval_if_valid ─────────────────────────────────────────────

class TestApprovalTTL:
    @pytest.fixture(autouse=True)
    def _clean(self):
        from api.routers.auth import _pending_approvals
        _pending_approvals.clear()
        yield
        _pending_approvals.clear()

    def test_fresh_approval_returned(self):
        from api.routers.auth import _pending_approvals, _get_approval_if_valid
        _pending_approvals["alice"] = {
            "approved": False, "requested_at": time.time(), "ip": "1.1.1.1", "token": "tok"
        }
        result = _get_approval_if_valid("alice")
        assert result is not None
        assert result["approved"] is False

    def test_approved_flag_in_fresh_approval(self):
        from api.routers.auth import _pending_approvals, _get_approval_if_valid
        _pending_approvals["bob"] = {
            "approved": True, "requested_at": time.time(), "ip": "2.2.2.2", "token": "tok2"
        }
        result = _get_approval_if_valid("bob")
        assert result is not None
        assert result["approved"] is True

    def test_expired_approval_returns_none_and_deletes(self):
        from api.routers.auth import _pending_approvals, _get_approval_if_valid, _APPROVAL_TTL_SECONDS
        _pending_approvals["charlie"] = {
            "approved": False,
            "requested_at": time.time() - _APPROVAL_TTL_SECONDS - 5,
            "ip": "3.3.3.3",
            "token": "old_tok",
        }
        result = _get_approval_if_valid("charlie")
        assert result is None
        assert "charlie" not in _pending_approvals

    def test_nonexistent_user_returns_none(self):
        from api.routers.auth import _get_approval_if_valid
        assert _get_approval_if_valid("nobody") is None

    def test_ttl_boundary_not_expired(self):
        """Aprobación exactamente en el límite del TTL todavía es válida."""
        from api.routers.auth import _pending_approvals, _get_approval_if_valid, _APPROVAL_TTL_SECONDS
        # 2 segundos antes del límite — no debe expirar
        _pending_approvals["diana"] = {
            "approved": False,
            "requested_at": time.time() - _APPROVAL_TTL_SECONDS + 2,
            "ip": "4.4.4.4",
            "token": "tok",
        }
        result = _get_approval_if_valid("diana")
        assert result is not None


# ─── Auth: _cleanup_stale_ips_unsafe ─────────────────────────────────────────

class TestCleanupStaleIPs:
    @pytest.fixture(autouse=True)
    def _clean(self):
        from api.routers.auth import _login_attempts, _rl_lock
        with _rl_lock:
            _login_attempts.clear()
        yield
        with _rl_lock:
            _login_attempts.clear()

    def test_removes_ips_with_only_old_attempts(self):
        from api.routers.auth import _login_attempts, _rl_lock, _cleanup_stale_ips_unsafe, _RL_WINDOW
        old_ts = time.time() - _RL_WINDOW - 10
        with _rl_lock:
            _login_attempts["stale.ip"] = [old_ts]
            _login_attempts["fresh.ip"] = [time.time()]
            _cleanup_stale_ips_unsafe()
            assert "stale.ip" not in _login_attempts
            assert "fresh.ip" in _login_attempts

    def test_keeps_ip_with_at_least_one_recent_attempt(self):
        from api.routers.auth import _login_attempts, _rl_lock, _cleanup_stale_ips_unsafe, _RL_WINDOW
        now = time.time()
        with _rl_lock:
            # Una entrada vieja + una reciente → no debe borrarse
            _login_attempts["mixed.ip"] = [now - _RL_WINDOW - 5, now]
            _cleanup_stale_ips_unsafe()
            assert "mixed.ip" in _login_attempts

    def test_cleans_multiple_stale_ips(self):
        from api.routers.auth import _login_attempts, _rl_lock, _cleanup_stale_ips_unsafe, _RL_WINDOW
        old_ts = time.time() - _RL_WINDOW - 10
        stale_ips = ["s1.ip", "s2.ip", "s3.ip"]
        with _rl_lock:
            for ip in stale_ips:
                _login_attempts[ip] = [old_ts]
            _login_attempts["live.ip"] = [time.time()]
            _cleanup_stale_ips_unsafe()
            for ip in stale_ips:
                assert ip not in _login_attempts
            assert "live.ip" in _login_attempts
