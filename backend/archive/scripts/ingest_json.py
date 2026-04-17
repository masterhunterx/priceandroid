"""
Ingest script: importa un JSON scrapeado a la DB por store_slug.
"""
import sys
import os
import json
import glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.db import get_session, init_db
from core.models import Store
from domain.ingest import upsert_store_products, run_matching

def ingest_json_file(json_path: str, store_slug: str):
    init_db()
    
    with open(json_path, encoding="utf-8") as f:
        products = json.load(f)
    
    print(f"Loaded {len(products)} products from {json_path}")
    
    with get_session() as session:
        store = session.query(Store).filter_by(slug=store_slug).first()
        if not store:
            print(f"[ERROR] Store '{store_slug}' not found in DB.")
            return
        
        upsert_store_products(session, store, products, branch=None)
        session.commit()
        print(f"Ingested into store: {store.name}")
        
        print("Running matcher...")
        run_matching(session, [store_slug, "jumbo", "unimarc", "santa_isabel"])
        session.commit()
        print("Done.")

if __name__ == "__main__":
    # Find latest lider chiquitin JSON
    for pattern, slug in [
        ("C:/tmp/lider_chiquitin*.json", "lider"),
        ("C:/tmp/santa_isabel_chiquitin*.json", "santa_isabel"),
    ]:
        files = sorted(glob.glob(pattern))
        if files:
            latest = files[-1]
            print(f"\nIngesting: {latest} -> {slug}")
            ingest_json_file(latest, slug)
