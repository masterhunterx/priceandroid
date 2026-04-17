import sys
import os
from sqlalchemy.orm import Session
from core.db import get_engine
from core.models import StoreProduct

def test():
    engine = get_engine()
    with Session(engine) as s:
        total = s.query(StoreProduct).count()
        fideos = s.query(StoreProduct).filter(StoreProduct.name.ilike("%fideos%")).count()
        arroz = s.query(StoreProduct).filter(StoreProduct.name.ilike("%arroz%")).count()
        carne = s.query(StoreProduct).filter(StoreProduct.name.ilike("%carne%")).count()
        
        print(f"--- DB Inventory ---")
        print(f"Total Products: {total}")
        print(f"Fideos count: {fideos}")
        print(f"Arroz count: {arroz}")
        print(f"Carne count: {carne}")
        
        if total == 0:
            print("[CRITICAL] Database is empty. Scrapers need to run.")
        elif fideos == 0 or arroz == 0:
            print("[WARNING] Key items missing. Check scrapers or filters.")

if __name__ == "__main__":
    test()
