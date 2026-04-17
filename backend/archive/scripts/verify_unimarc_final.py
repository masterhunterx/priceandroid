from data.sources.unimarc_scraper import create_session, search_products
import sys
import os

def verify():
    s = create_session()
    print("Verifying 'leche' search...")
    p = search_products(s, "leche", max_pages=1)
    if p:
        print(f"  SUCCESS! Found {len(p)} products.")
        print(f"  First: {p[0]['name']}")
        if "leche" in p[0]['name'].lower():
            print("  [OK] Results are RELEVANT.")
        else:
            print("  [WARNING] Results might be irrelevant still.")
    else:
        print("  [FAILED] No products returned.")

if __name__ == "__main__":
    verify()
