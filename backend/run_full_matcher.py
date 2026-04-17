from core.db import get_session
from domain.ingest import run_matching
import sys

def match():
    print("Running cross-store matcher for Jumbo, Unimarc, Lider, Santa Isabel...")
    with get_session() as s:
        try:
            run_matching(s, ["jumbo", "unimarc", "lider", "santa_isabel"])
            s.commit()
            print("  SUCCESS! Matching complete.")
        except Exception as e:
            print(f"  FAILED: {e}")
            s.rollback()

if __name__ == "__main__":
    match()
