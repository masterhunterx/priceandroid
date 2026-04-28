"""Quick scraper health check for all 4 stores."""
import os
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
from dotenv import load_dotenv
load_dotenv('.env')
import sys
sys.path.insert(0, '.')

STORES = []

def run_scraper(label, search_fn, create_fn):
    print(f"\n=== {label.upper()} ===")
    try:
        s = create_fn()
        results = search_fn(s, 'leche', max_pages=1)
        # Some scrapers return (list, total), others return list
        if isinstance(results, tuple):
            results, total = results[0], results[1]
        else:
            total = len(results)
        print(f"OK: {total} total available, {len(results)} normalized on page 1")
        if results:
            r = results[0]
            print(f"  Sample: {r.get('name')} | ${r.get('price')} | in_stock={r.get('in_stock')}")
        STORES.append((label, "OK", len(results)))
    except Exception as e:
        print(f"ERROR: {e}")
        STORES.append((label, "FAIL", str(e)[:80]))


# ── JUMBO ──────────────────────────────────────────────────────────────────────
from data.sources import jumbo_scraper as j
run_scraper("Jumbo", j.search_products, j.create_session)

# ── SANTA ISABEL ───────────────────────────────────────────────────────────────
from data.sources import santa_isabel_scraper as si
run_scraper("Santa Isabel", si.search_products, si.create_session)

# ── UNIMARC ────────────────────────────────────────────────────────────────────
from data.sources import unimarc_scraper as u
run_scraper("Unimarc", u.search_products, u.create_session)

# ── LIDER ─────────────────────────────────────────────────────────────────────
from data.sources import lider_scraper as l
run_scraper("Lider", l.search_products, l.create_session)

# ── SUMMARY ───────────────────────────────────────────────────────────────────
print("\n" + "="*50)
print("SCRAPER STATUS SUMMARY")
print("="*50)
for store, status, detail in STORES:
    icon = "[OK]" if status == "OK" else "[FAIL]"
    print(f"{icon} {store}: {detail}")
