"""
Matcher Engine Unit Tests
===========================
Tests for the core matching logic in matcher.py.

Covers:
  - Weight / volume extraction (units, kg/g conversion, packs)
  - Brand normalization and scoring
  - Name cleaning and fuzzy scoring
  - Composite match score for clear matches and clear non-matches
  - Edge cases: multipacks vs singles, brand ambiguity, unknown weights
  - Full batch matching via find_matches()

These are pure unit tests — no I/O, no DB, no network.

Usage:
    cd backend
    python -m pytest tests/test_matcher.py -v
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domain.matcher import (
    extract_weight,
    extract_pack_size,
    clean_product_name,
    normalize_brand,
    brand_score,
    weight_score,
    name_score,
    category_score,
    compute_match_score,
    find_matches,
    enrich_with_weight,
    AUTO_MATCH_THRESHOLD,
    CANDIDATE_THRESHOLD,
)


# ===========================================================================
# 1. Weight / Volume Extraction
# ===========================================================================

class TestExtractWeight:
    """Tests for extract_weight() — the unit extraction and conversion logic."""

    def test_grams(self):
        assert extract_weight("Leche Condensada 397 g") == (397.0, "g")

    def test_kg_converted_to_grams(self):
        val, unit = extract_weight("Arroz Pregraneado 1 kg")
        assert unit == "g"
        assert val == pytest.approx(1000.0)

    def test_ml(self):
        assert extract_weight("Aceite de Oliva 500 ml") == (500.0, "ml")

    def test_litres_converted_to_ml(self):
        val, unit = extract_weight("Jugo de Naranja 1.5 lt")
        assert unit == "ml"
        assert val == pytest.approx(1500.0)

    def test_cc_as_ml(self):
        val, unit = extract_weight("Cerveza 330 cc")
        assert unit == "ml"
        assert val == pytest.approx(330.0)

    def test_units(self):
        val, unit = extract_weight("Huevos 12 un")
        assert unit == "un"
        assert val == pytest.approx(12.0)

    def test_decimal_comma(self):
        """Some Chilean product names use commas as decimal separators."""
        val, unit = extract_weight("Yogurt Natural 1,5 kg")
        assert unit == "g"
        assert val == pytest.approx(1500.0)

    def test_no_weight(self):
        assert extract_weight("Producto sin peso") == (None, None)

    def test_takes_last_match(self):
        """When multiple weights appear, the last (most specific) is used."""
        val, unit = extract_weight("Pack 6 Cervezas 330 ml")
        # "330 ml" is the last match and the actual product weight
        assert unit == "ml"
        assert val == pytest.approx(330.0)


class TestExtractPackSize:
    """Tests for extract_pack_size() — multipack quantity detection."""

    def test_pack_6(self):
        assert extract_pack_size("Pack 6 Cervezas 330 ml") == 6

    def test_6x_format(self):
        assert extract_pack_size("Agua Mineral 6x1.5L") == 6

    def test_x6_format(self):
        assert extract_pack_size("Yogurt x6 unidades") == 6

    def test_single_product_returns_1(self):
        assert extract_pack_size("Leche Entera 1 lt") == 1

    def test_pack_de_12(self):
        assert extract_pack_size("Pack de 12 Huevos") == 12


# ===========================================================================
# 2. Name Cleaning
# ===========================================================================

class TestCleanProductName:
    """Tests for clean_product_name() — the normalization pipeline."""

    def test_lowercases(self):
        assert clean_product_name("LECHE ENTERA") == "leche entera"

    def test_removes_weight(self):
        result = clean_product_name("Leche Entera 1 lt")
        assert "lt" not in result
        assert "1" not in result

    def test_removes_accents(self):
        result = clean_product_name("Café Molido")
        assert "é" not in result
        assert "cafe" in result

    def test_removes_pack_info(self):
        result = clean_product_name("Pack 6 Cervezas 330 ml")
        # The pack reference should be cleaned
        assert "pack" not in result
        assert "6" not in result

    def test_removes_filler_words(self):
        result = clean_product_name("Leche Entera Caja 1 lt")
        assert "caja" not in result

    def test_empty_string(self):
        assert clean_product_name("") == ""

    def test_none_safe(self):
        assert clean_product_name(None) == ""

    def test_collapses_whitespace(self):
        result = clean_product_name("Leche   Entera")
        assert "  " not in result


# ===========================================================================
# 3. Individual Scoring Functions
# ===========================================================================

class TestBrandScore:
    """Tests for brand_score()."""

    def test_exact_match(self):
        assert brand_score("Nestlé", "Nestlé") == 1.0

    def test_case_insensitive(self):
        assert brand_score("NESTLE", "nestle") == 1.0

    def test_accent_insensitive(self):
        """Nestlé vs Nestle should still score very high."""
        score = brand_score("Nestlé", "Nestle")
        assert score >= 0.9

    def test_clearly_different_brand(self):
        assert brand_score("Colun", "Soprole") == 0.0

    def test_unknown_brand_is_neutral(self):
        """If brand is missing, scoring should be neutral (0.5) not 0.0."""
        assert brand_score("", "Colun") == 0.5
        assert brand_score("Colun", "") == 0.5
        assert brand_score("", "") == 0.5

    def test_close_misspelling(self):
        """Minor typo or abbreviation should give partial credit."""
        score = brand_score("Soprole", "Soproles")
        assert score >= 0.5


class TestWeightScore:
    """Tests for weight_score() — the core multipack/size edge case handler."""

    def test_exact_match(self):
        assert weight_score(1000.0, "g", 1000.0, "g") == 1.0

    def test_rounding_tolerance(self):
        """1 kg parsed as 1000g vs 1001g (rounding) should still match."""
        assert weight_score(1000.0, "g", 1000.0, "g") == 1.0

    def test_within_5_percent(self):
        """Weights within 5% of each other earn partial credit."""
        # 397g vs 400g is ~0.75% difference
        score = weight_score(397.0, "g", 400.0, "g")
        assert score == 0.8

    def test_different_units_scores_zero(self):
        """g vs ml should score 0 — these are incompatible units."""
        assert weight_score(500.0, "g", 500.0, "ml") == 0.0

    def test_single_vs_pack_scores_low(self):
        """
        EDGE CASE: 330ml (single) vs 1980ml (6-pack of 330ml).
        These should NOT match — the weight mismatch should drive a low score.
        """
        # 6 * 330 = 1980ml; single = 330ml → ratio = 330/1980 ≈ 0.167 (< 0.95)
        score = weight_score(330.0, "ml", 1980.0, "ml")
        assert score == 0.0, (
            f"Single (330ml) vs 6-pack (1980ml) should score 0.0, got {score}"
        )

    def test_unknown_weight_is_neutral(self):
        """If weight can't be extracted, scoring should be neutral (0.5)."""
        assert weight_score(None, None, 500.0, "g") == 0.5
        assert weight_score(500.0, "g", None, None) == 0.5
        assert weight_score(None, None, None, None) == 0.5


class TestNameScore:
    """Tests for name_score() — fuzzy token sort ratio."""

    def test_identical_names(self):
        assert name_score("Leche Entera", "Leche Entera") == 1.0

    def test_high_score_for_similar(self):
        score = name_score("Leche Entera Soprole 1lt", "Soprole Leche Entera 1 lt")
        assert score >= 0.85, f"Expected high score, got {score}"

    def test_low_score_for_different(self):
        score = name_score("Leche Entera 1lt", "Arroz Pregraneado 1kg")
        assert score <= 0.35, f"Expected low score for very different names, got {score}"

    def test_empty_name(self):
        assert name_score("", "Leche") == 0.0
        assert name_score("Leche", "") == 0.0


class TestCategoryScore:
    """Tests for category_score()."""

    def test_exact_match(self):
        assert category_score("Lácteos", "Lácteos") == 1.0

    def test_fuzzy_match_partial(self):
        """
        'Lacteos y Huevos' vs 'Lácteos' is a broad parent-category overlap.
        It should earn partial credit (>= 0.4) but not a high match (< 0.7).
        """
        score = category_score("Lacteos y Huevos", "Lácteos")
        assert 0.0 < score < 0.7, f"Expected partial credit (0 < score < 0.7), got {score}"

    def test_different_categories(self):
        score = category_score("Bebidas", "Carnes y Pescados")
        assert score == 0.0

    def test_unknown_category_is_neutral(self):
        assert category_score("", "Bebidas") == 0.5


# ===========================================================================
# 4. Composite Score & Auto-Matching
# ===========================================================================

class TestComputeMatchScore:
    """Tests for the overall composite score via compute_match_score()."""

    def _make_product(self, name, brand, category="Lácteos", weight_value=None, weight_unit=None):
        return {
            "name": name,
            "brand": brand,
            "top_category": category,
            "weight_value": weight_value,
            "weight_unit": weight_unit,
        }

    # --- Clear Auto-Matches (should be >= 0.75) ---

    def test_identical_products_auto_match(self):
        """Two identical products should score above the auto-match threshold."""
        a = self._make_product("Leche Entera 1 lt", "Soprole", weight_value=1000.0, weight_unit="ml")
        b = self._make_product("Leche Entera 1 lt", "Soprole", weight_value=1000.0, weight_unit="ml")
        score = compute_match_score(a, b)
        assert score >= AUTO_MATCH_THRESHOLD, f"Expected auto-match, got {score}"

    def test_same_product_different_store_name_format(self):
        """Same real product with minor store name variation should auto-match."""
        a = self._make_product("Soprole Leche Entera 1lt", "Soprole", weight_value=1000.0, weight_unit="ml")
        b = self._make_product("Leche Entera Soprole 1 lt", "Soprole", weight_value=1000.0, weight_unit="ml")
        score = compute_match_score(a, b)
        assert score >= AUTO_MATCH_THRESHOLD, f"Expected auto-match for reformatted names, got {score}"

    # --- Clear Non-Matches (should be < 0.75) ---

    def test_different_brand_scores_low(self):
        """Same product type but completely different brand should not auto-match."""
        a = self._make_product("Leche Entera 1 lt", "Soprole", weight_value=1000.0, weight_unit="ml")
        b = self._make_product("Leche Entera 1 lt", "Colun", weight_value=1000.0, weight_unit="ml")
        score = compute_match_score(a, b)
        assert score < AUTO_MATCH_THRESHOLD, f"Different brands should not auto-match, got {score}"

    def test_different_product_type_scores_low(self):
        """Completely different products should score very low."""
        a = self._make_product("Leche Entera 1 lt", "Soprole", "Lácteos", 1000.0, "ml")
        b = self._make_product("Arroz Pregraneado 1 kg", "Tucapel", "Despensa", 1000.0, "g")
        score = compute_match_score(a, b)
        assert score < 0.4, f"Very different products should score < 0.4, got {score}"

    # --- Multipack Edge Case ---

    def test_single_vs_multipack_does_not_auto_match(self):
        """
        EDGE CASE: A single can (330ml) should NOT match a 6-pack (1980ml).
        The weight signal must dominate enough to prevent a false auto-match.
        """
        single = self._make_product(
            "Cerveza Kunstmann Torobayo 330 ml", "Kunstmann",
            "Cervezas", weight_value=330.0, weight_unit="ml"
        )
        six_pack = self._make_product(
            "Cerveza Kunstmann Torobayo 6 x 330 ml", "Kunstmann",
            "Cervezas", weight_value=1980.0, weight_unit="ml"
        )
        score = compute_match_score(single, six_pack)
        assert score < AUTO_MATCH_THRESHOLD, (
            f"Single (330ml) should NOT auto-match 6-pack (1980ml), got score={score}"
        )

    def test_same_product_same_pack_auto_matches(self):
        """Control: The same 6-pack product from two stores should auto-match."""
        pack_a = self._make_product(
            "Cerveza Kunstmann Torobayo Pack 6 x 330ml", "Kunstmann",
            "Cervezas", weight_value=1980.0, weight_unit="ml"
        )
        pack_b = self._make_product(
            "Kunstmann Torobayo 6x330 ml", "Kunstmann",
            "Cervezas", weight_value=1980.0, weight_unit="ml"
        )
        score = compute_match_score(pack_a, pack_b)
        assert score >= AUTO_MATCH_THRESHOLD, (
            f"Same 6-pack from two stores should auto-match, got score={score}"
        )

    # --- Brand Ambiguity Edge Case ---

    def test_subbrand_does_not_auto_match_parent(self):
        """
        EDGE CASE: 'Nestlé Nido' vs 'Nestlé La Lechera' — same parent brand,
        completely different products. Should NOT auto-match.
        """
        nido = self._make_product("Nido Crecimiento 1+ 800g", "Nestlé", "Lácteos", 800.0, "g")
        lechera = self._make_product("La Lechera Leche Condensada 397g", "Nestlé", "Lácteos", 397.0, "g")
        score = compute_match_score(nido, lechera)
        assert score < AUTO_MATCH_THRESHOLD, (
            f"Nestlé Nido vs La Lechera should NOT auto-match, got score={score}"
        )


# ===========================================================================
# 5. enrich_with_weight Helper
# ===========================================================================

class TestEnrichWithWeight:
    """Tests for enrich_with_weight() — auto-parsing weight into a product dict."""

    def test_adds_weight_fields(self):
        p = {"name": "Leche Entera 1 lt", "brand": "Soprole"}
        result = enrich_with_weight(p)
        assert result["weight_value"] == pytest.approx(1000.0)
        assert result["weight_unit"] == "ml"

    def test_no_weight_in_name(self):
        p = {"name": "Producto sin peso", "brand": "X"}
        result = enrich_with_weight(p)
        assert result["weight_value"] is None
        assert result["weight_unit"] is None

    def test_mutates_original_dict(self):
        """enrich_with_weight should return the same dict (mutate in-place)."""
        p = {"name": "Arroz 1 kg", "brand": "Tucapel"}
        result = enrich_with_weight(p)
        assert result is p


# ===========================================================================
# 6. Batch Matching Integration: find_matches()
# ===========================================================================

class TestFindMatches:
    """Integration tests for the full blocking + pairwise batch matcher."""

    def _make_store_products(self):
        """Build a small, realistic cross-store product catalog for testing."""
        lider = [
            enrich_with_weight({"name": "Leche Entera Soprole 1 lt", "brand": "Soprole", "top_category": "Lácteos"}),
            enrich_with_weight({"name": "Arroz Pregraneado Tucapel 1 kg", "brand": "Tucapel", "top_category": "Despensa"}),
            enrich_with_weight({"name": "Cerveza Kunstmann 330 ml", "brand": "Kunstmann", "top_category": "Cervezas"}),
        ]
        jumbo = [
            enrich_with_weight({"name": "Soprole Leche Entera 1lt", "brand": "Soprole", "top_category": "Lácteos"}),
            enrich_with_weight({"name": "Tucapel Arroz Precocido 1 kg", "brand": "Tucapel", "top_category": "Despensa"}),
            # Intentionally different beer to avoid false match with Lider's Kunstmann
            enrich_with_weight({"name": "Cerveza Austral Calafate 330 ml", "brand": "Austral", "top_category": "Cervezas"}),
        ]
        return {"lider": lider, "jumbo": jumbo}

    def test_finds_expected_matches(self):
        """Auto-matches should be found for Soprole milk and Tucapel rice."""
        products = self._make_store_products()
        matches = find_matches(products, threshold=CANDIDATE_THRESHOLD)

        auto_matches = [m for m in matches if m["auto_match"]]
        assert len(auto_matches) >= 2, (
            f"Expected at least 2 auto-matches (leche, arroz), got {len(auto_matches)}: "
            + str([(m["product_a"][1]["name"], m["product_b"][1]["name"], m["score"]) for m in auto_matches])
        )

    def test_cross_store_only(self):
        """Matches should only occur between different stores, never within the same store."""
        products = self._make_store_products()
        matches = find_matches(products, threshold=CANDIDATE_THRESHOLD)

        for m in matches:
            store_a = m["product_a"][0]
            store_b = m["product_b"][0]
            assert store_a != store_b, (
                f"Match found within the same store '{store_a}': "
                f"'{m['product_a'][1]['name']}' vs '{m['product_b'][1]['name']}'"
            )

    def test_different_brand_beers_do_not_auto_match(self):
        """Kunstmann vs Austral should not produce an auto-match."""
        products = self._make_store_products()
        matches = find_matches(products, threshold=CANDIDATE_THRESHOLD)

        beer_auto_matches = [
            m for m in matches
            if m["auto_match"]
            and "Cerveza" in m["product_a"][1]["name"]
            and "Cerveza" in m["product_b"][1]["name"]
        ]
        assert len(beer_auto_matches) == 0, (
            f"Kunstmann vs Austral should NOT auto-match: {beer_auto_matches}"
        )

    def test_empty_input_returns_empty(self):
        assert find_matches({}) == []

    def test_single_store_returns_empty(self):
        """With only one store, cross-store matching is impossible."""
        products = {
            "lider": [
                enrich_with_weight({"name": "Leche 1 lt", "brand": "Soprole", "top_category": "Lácteos"})
            ]
        }
        assert find_matches(products) == []
