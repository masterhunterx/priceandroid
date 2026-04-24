"""
Product Matching Engine
========================
Matches products across different stores using multi-signal scoring:
  - Brand match (35%)
  - Weight/volume match (25%)
  - Fuzzy name similarity (30%)
  - Category match (10%)
"""

import re
import unicodedata
from collections import defaultdict

from rapidfuzz import fuzz


# ---------------------------------------------------------------------------
# Weight / Volume Extraction
# ---------------------------------------------------------------------------

# Pattern: "397 g", "1.5 kg", "500 ml", "1 lt", "6 un", "330 cc"
WEIGHT_PATTERN = re.compile(
    r'(\d+(?:[.,]\d+)?)\s*(g|gr|grs|kg|kgs|ml|l|lt|lts|cc|oz|un|und|unid)\b',
    re.IGNORECASE
)

# Normalization: convert everything to grams (solids) or ml (liquids)
UNIT_CONVERSIONS = {
    # Mass
    "g": ("g", 1.0),
    "gr": ("g", 1.0),
    "grs": ("g", 1.0),
    "kg": ("g", 1000.0),
    "kgs": ("g", 1000.0),
    "oz": ("g", 28.3495),
    # Volume
    "ml": ("ml", 1.0),
    "cc": ("ml", 1.0),
    "l": ("ml", 1000.0),
    "lt": ("ml", 1000.0),
    "lts": ("ml", 1000.0),
    # Units
    "un": ("un", 1.0),
    "und": ("un", 1.0),
    "unid": ("un", 1.0),
}

# Pack pattern: "Pack 6", "6x", "x6", "6x330ml", "6 unidades"
PACK_PATTERN = re.compile(
    r'(?:pack|pck)\s*(?:de\s*)?(\d+)|(\d+)\s*x(?=\s|\d)|x\s*(\d+)',
    re.IGNORECASE
)


def extract_weight(name):
    """
    Extract weight/volume from a product name.
    Returns: (normalized_value, normalized_unit) or (None, None)

    Examples:
        "Leche Condensada 397 g"    -> (397.0, "g")
        "Aceite de Oliva 500 ml"    -> (500.0, "ml")
        "Arroz Pregraneado 1 kg"    -> (1000.0, "g")
        "Pack 6 Cervezas 350ml"     -> (350.0, "ml")  (pack info separate)
    """
    matches = WEIGHT_PATTERN.findall(name)
    if not matches:
        return None, None

    # Take the last match (usually the most specific)
    value_str, unit = matches[-1]
    value_str = value_str.replace(",", ".")

    try:
        value = float(value_str)
    except ValueError:
        return None, None

    unit_lower = unit.lower()
    if unit_lower in UNIT_CONVERSIONS:
        norm_unit, factor = UNIT_CONVERSIONS[unit_lower]
        return value * factor, norm_unit

    return value, unit_lower


def extract_pack_size(name):
    """Extract pack quantity (e.g., 'Pack 6' -> 6, '6x330ml' -> 6)."""
    match = PACK_PATTERN.search(name)
    if match:
        for group in match.groups():
            if group:
                try:
                    return int(group)
                except ValueError:
                    pass
    return 1


# ---------------------------------------------------------------------------
# Name Cleaning
# ---------------------------------------------------------------------------

def normalize_text(text):
    """
    Remove accents and normalize unicode.
    "café" -> "cafe", "año" -> "ano"
    """
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.category(c).startswith("M"))


def clean_product_name(name):
    """
    Clean a product name for fuzzy comparison.
    Removes weight info, punctuation, extra whitespace.
    Returns lowercase, accent-stripped, cleaned name.
    """
    if not name:
        return ""

    cleaned = name.lower()

    # Remove weight/volume info
    cleaned = WEIGHT_PATTERN.sub("", cleaned)

    # Remove pack info
    cleaned = PACK_PATTERN.sub("", cleaned)

    # Remove common filler words
    fillers = [
        r'\bx\s+un\b', r'\bx\s+und\b', r'\bunidad(es)?\b',
        r'\bcaja\b', r'\bbolsa\b', r'\bbotella\b', r'\bfrasco\b',
        r'\btarro\b', r'\bsobre\b', r'\benvase\b',
    ]
    for filler in fillers:
        cleaned = re.sub(filler, "", cleaned, flags=re.IGNORECASE)

    # Remove punctuation
    cleaned = re.sub(r'[^\w\s]', ' ', cleaned)

    # Normalize accents
    cleaned = normalize_text(cleaned)

    # Collapse whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    return cleaned


def normalize_brand(brand):
    """Normalize brand for comparison."""
    if not brand:
        return ""
    return normalize_text(brand.lower().strip())


# ---------------------------------------------------------------------------
# Matching Scores
# ---------------------------------------------------------------------------

def brand_score(brand_a, brand_b):
    """Score brand similarity. Exact match = 1.0, fuzzy match partial credit."""
    a = normalize_brand(brand_a)
    b = normalize_brand(brand_b)

    if not a or not b:
        return 0.5  # Unknown brand, neutral

    if a == b:
        return 1.0

    # Partial credit for fuzzy brand match (e.g., "Nestle" vs "Nestl")
    ratio = fuzz.ratio(a, b)
    if ratio >= 85:
        return 0.9
    if ratio >= 70:
        return 0.5

    return 0.0


def weight_score(weight_a, unit_a, weight_b, unit_b):
    """Score weight/volume similarity."""
    if weight_a is None or weight_b is None:
        return 0.5  # Unknown weight, neutral

    if unit_a != unit_b:
        return 0.0  # Different measurement types (mass vs volume)

    if abs(weight_a - weight_b) < 0.01:
        return 1.0  # Exact match

    # Close match (within 5% tolerance for rounding differences)
    ratio = min(weight_a, weight_b) / max(weight_a, weight_b) if max(weight_a, weight_b) > 0 else 0
    if ratio >= 0.95:
        return 0.8

    return 0.0


def name_score(name_a, name_b):
    """Score name similarity using fuzzy matching."""
    a = clean_product_name(name_a)
    b = clean_product_name(name_b)

    if not a or not b:
        return 0.0

    # token_sort_ratio handles word reordering
    return fuzz.token_sort_ratio(a, b) / 100.0


def category_score(cat_a, cat_b):
    """Score category similarity."""
    if not cat_a or not cat_b:
        return 0.5  # Unknown, neutral

    a = normalize_text(cat_a.lower().strip())
    b = normalize_text(cat_b.lower().strip())

    if a == b:
        return 1.0

    # Partial credit for fuzzy category match.
    # Threshold is 50 to handle broad parent-category overlaps like
    # 'Lacteos y Huevos' vs 'Lacteos'.
    ratio = fuzz.ratio(a, b)
    if ratio >= 70:
        return 0.7
    if ratio >= 50:
        return 0.4

    return 0.0


# ---------------------------------------------------------------------------
# Composite Match Score
# ---------------------------------------------------------------------------

# Weights for each signal
BRAND_WEIGHT = 0.35
WEIGHT_WEIGHT = 0.25
NAME_WEIGHT = 0.30
CATEGORY_WEIGHT = 0.10

# Thresholds
AUTO_MATCH_THRESHOLD = 0.80
CANDIDATE_THRESHOLD = 0.50

# Minimum name similarity required for auto-match regardless of brand/weight.
# Prevents "Pan Lactal" from matching "Pan Integral" when brand+weight are identical.
MIN_NAME_SCORE = 0.65


# Hard penalty applied when two products have known sizes that differ by > 2x.
# This prevents a single unit from falsely auto-matching a multipack when
# name + brand similarity is high enough to push the weighted score to threshold.
SIZE_MISMATCH_PENALTY = 0.30

# Extreme penalty when product types are fundamentally different (Leche vs Crema)
TYPE_MISMATCH_PENALTY = 0.90

PRODUCT_TYPES = {
    # Dairy
    "leche": ["leche", "leches"],
    "crema": ["crema", "cremas"],
    "yogur": ["yogur", "yogurt", "yoghurt"],
    "mantequilla": ["mantequilla"],
    "queso": ["queso", "quesos"],
    # Pantry
    "arroz": ["arroz"],
    "aceite": ["aceite"],
    "azucar": ["azucar"],
    "harina": ["harina"],
    "pan": ["pan"],
    "cafe": ["cafe", "coffee"],
    # Proteins (Critical)
    "carne": ["carne", "molida", "vacuno", "sobrecostilla", "lomo", "asado", "huachalomo"],
    "pollo": ["pollo", "pechuga", "trutro", "alitas"],
    "cerdo": ["cerdo", "pulpa", "chuleta", "costillar"],
    "pescado": ["pescado", "salmon", "reineta", "merluza", "atun"],
    # Produce (Critical)
    "vegetal": ["choclo", "arveja", "poroto", "lenteja", "garbanzo", "maiz", "verdura", "ensalada"],
    "fruta": ["manzana", "platano", "naranja", "uva", "pera", "fruta"],
    # Pets
    "mascotas": ["perro", "gato", "mascota", "pedigree", "whiskas", "master dog"],
}

def detect_product_type(name):
    """Identify the fundamental product type from the name."""
    name_lower = name.lower()
    for p_type, keywords in PRODUCT_TYPES.items():
        for kw in keywords:
            if re.search(fr'\b{kw}\b', name_lower):
                return p_type
    return None


def compute_match_score(product_a, product_b):
    """
    Compute a composite match score between two products.

    Args:
        product_a: dict with keys: name, brand, top_category, weight_value, weight_unit
        product_b: dict with same keys

    Returns:
        float: match score between 0.0 and 1.0
    """
    wa = product_a.get("weight_value")
    ua = product_a.get("weight_unit")
    wb = product_b.get("weight_value")
    ub = product_b.get("weight_unit")

    name_a = product_a.get("name", "")
    name_b = product_b.get("name", "")

    # 0. Check for fundamental type mismatch (Leche vs Carne vs Choclo)
    type_a = detect_product_type(name_a)
    type_b = detect_product_type(name_b)
    
    if type_a and type_b and type_a != type_b:
        return 0.0 # High-confidence mismatch (Meat vs Veg, Milk vs Cream, etc.)

    # 1. Category-based blocking (top_category)
    cat_a = normalize_text(product_a.get("top_category", "").lower().strip())
    cat_b = normalize_text(product_b.get("top_category", "").lower().strip())
    
    # Strictly incompatible categories
    REJECT_CATEGORIES = {
        "carnes": ["frutas", "verduras", "congelados", "despensa", "lacteos", "mascotas"],
        "frutas": ["carnes", "mascotas", "limpieza"],
        "verduras": ["carnes", "mascotas", "limpieza"],
        "mascotas": ["carnes", "lacteos", "despensa", "frutas", "verduras"],
    }
    
    for core_cat, opposites in REJECT_CATEGORIES.items():
        if (core_cat in cat_a and any(opp in cat_b for opp in opposites)) or \
           (core_cat in cat_b and any(opp in cat_a for opp in opposites)):
            return 0.0 # Strict mismatch based on high-level category

    # 2. Strict Term Rejection (Mutually Exclusive Variants)
    REJECT_PAIRS = [
        (["costillar", "costilla"], ["chuleta", "chuletita", "pulpa", "lomo", "posta"]),
        (["pechuga"], ["trutro", "tuto", "alita", "ala", "entero", "entera"]),
        (["trutro", "tuto"], ["pechuga", "alita", "ala", "filetillo", "filete", "medallon"]),
        (["entero", "entera"], ["corto", "cortos", "deshuesado", "filetillo", "trozado", "picado", "trozo", "descremada", "semidescremada"]),
        (["descremada"], ["semidescremada"]),
        (["polvo"], ["liquida", "líquida"]),
        (["con gas", "gasificada"], ["sin gas"]),
        (["blanco"], ["tinto", "rose", "rosé", "carmenere", "merlot", "cabernet", "dorado"]),
        (["integral", "integrales"], ["lactal", "molde", "blanco"]),
        (["light", "lite", "zero", "sin azucar"], ["original", "clasico", "clásico", "regular"]),
        (["sin lactosa"], ["con lactosa", "entera", "semidescremada"]),
    ]
    
    name_a_low = name_a.lower()
    name_b_low = name_b.lower()

    for terms_a, terms_b in REJECT_PAIRS:
        has_a_in_1 = any(t in name_a_low for t in terms_a)
        has_b_in_1 = any(t in name_a_low for t in terms_b)
        has_a_in_2 = any(t in name_b_low for t in terms_a)
        has_b_in_2 = any(t in name_b_low for t in terms_b)
        
        # If product 1 has term A but NOT term B, and product 2 has term B but NOT term A
        if (has_a_in_1 and not has_b_in_1 and has_b_in_2 and not has_a_in_2) or \
           (has_b_in_1 and not has_a_in_1 and has_a_in_2 and not has_b_in_2):
            return 0.0 # High-confidence mismatch due to incompatible terms

    bs = brand_score(product_a.get("brand", ""), product_b.get("brand", ""))
    ws = weight_score(wa, ua, wb, ub)
    ns = name_score(name_a, name_b)
    cs = category_score(product_a.get("top_category", ""), product_b.get("top_category", ""))

    score = (
        BRAND_WEIGHT * bs +
        WEIGHT_WEIGHT * ws +
        NAME_WEIGHT * ns +
        CATEGORY_WEIGHT * cs
    )

    # Apply a hard penalty if both products have a known size and they differ
    # by more than 2x (e.g., 330ml single vs 1980ml 6-pack). This prevents
    # the name/brand similarity from pushing a pack mismatch over the threshold.
    if wa and wb and ua == ub and ua in ("g", "ml", "un"):
        ratio = min(wa, wb) / max(wa, wb) if max(wa, wb) > 0 else 0
        if ratio < 0.5:  # sizes differ by more than 2x
            score -= SIZE_MISMATCH_PENALTY

    # Minimum name similarity guard: even with perfect brand+weight match,
    # divergent names (different variants) must not auto-match.
    if ns < MIN_NAME_SCORE and score >= AUTO_MATCH_THRESHOLD:
        score = CANDIDATE_THRESHOLD - 0.01

    return round(max(score, 0.0), 4)


# ---------------------------------------------------------------------------
# Batch Matching with Blocking
# ---------------------------------------------------------------------------

def build_blocks(products_by_store):
    """
    Group products into blocks by (normalized_brand).
    Only products within the same block will be compared.

    Args:
        products_by_store: dict mapping store_slug -> list of product dicts

    Returns:
        dict mapping block_key -> list of (store_slug, product_dict) tuples
    """
    blocks = defaultdict(list)

    for store_slug, products in products_by_store.items():
        for product in products:
            brand = normalize_brand(product.get("brand", ""))
            block_key = brand if brand else "__unknown__"
            blocks[block_key].append((store_slug, product))

    return blocks


def find_matches(products_by_store, threshold=CANDIDATE_THRESHOLD):
    """
    Find cross-store product matches using blocking + pairwise scoring.

    Args:
        products_by_store: dict mapping store_slug -> list of product dicts
                          Each product dict must have: name, brand, top_category,
                          plus optional weight_value, weight_unit
        threshold: minimum score to consider as a match

    Returns:
        list of dicts: [
            {
                "product_a": (store_slug, product_dict),
                "product_b": (store_slug, product_dict),
                "score": float,
                "auto_match": bool,
            },
            ...
        ]
    """
    blocks = build_blocks(products_by_store)
    matches = []

    for block_key, members in blocks.items():
        # Group by store within this block
        by_store = defaultdict(list)
        for store_slug, product in members:
            by_store[store_slug].append(product)

        store_slugs = list(by_store.keys())

        # Compare across stores (not within the same store)
        for i in range(len(store_slugs)):
            for j in range(i + 1, len(store_slugs)):
                store_a = store_slugs[i]
                store_b = store_slugs[j]

                for prod_a in by_store[store_a]:
                    best_score = 0.0
                    best_match = None

                    for prod_b in by_store[store_b]:
                        score = compute_match_score(prod_a, prod_b)
                        if score > best_score:
                            best_score = score
                            best_match = prod_b

                    if best_match and best_score >= threshold:
                        matches.append({
                            "product_a": (store_a, prod_a),
                            "product_b": (store_b, best_match),
                            "score": best_score,
                            "auto_match": best_score >= AUTO_MATCH_THRESHOLD,
                        })

    return matches


def enrich_with_weight(product):
    """Add weight_value and weight_unit to a product dict by parsing its name."""
    weight_val, weight_unit = extract_weight(product.get("name", ""))
    product["weight_value"] = weight_val
    product["weight_unit"] = weight_unit
    return product
