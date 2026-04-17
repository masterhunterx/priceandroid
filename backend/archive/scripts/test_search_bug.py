from core.db import get_session
from core.models import StoreProduct
from sqlalchemy import func, or_
import unicodedata

def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )

def test_search():
    q = "chiquitin"
    print(f"Testing search for: {q}")
    
    with get_session() as session:
        main_query = session.query(StoreProduct)
        tokens = q.strip().split()
        
        _ACCENT_MAP = {"a": "á", "e": "é", "i": "í", "o": "ó", "u": "ú"}
        
        for token in tokens:
            tok_lower = token.lower()
            tok_stripped = _strip_accents(tok_lower)
            
            conds = [
                func.lower(StoreProduct.name).like(f"%{tok_lower}%"),
                func.lower(StoreProduct.name).like(f"%{tok_stripped}%")
            ]
            
            # Variant generation logic used in api/main.py
            for char in tok_stripped:
                if char in _ACCENT_MAP:
                    variant = tok_stripped.replace(char, _ACCENT_MAP[char])
                    conds.append(func.lower(StoreProduct.name).like(f"%{variant}%"))
            
            main_query = main_query.filter(or_(*conds))
            
        results = main_query.all()
        print(f"  Found {len(results)} matches.")
        for r in results[:5]:
            print(f"    - [{r.store.slug}] {r.name}")

if __name__ == "__main__":
    test_search()
