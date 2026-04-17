"""
Bulk Ingest Script for Unimarc Coverage
========================================
Targets high-priority categories to reach parity with Jumbo/Lider.
"""
import sys
import os
import time
import subprocess

CATEGORIES = [
    "leche", "arroz", "aceite", "pan", "carne", "pollo", 
    "detergente", "chiquitin", "yogurt", "fideos", 
    "papel higienico", "azucar", "harina", "cafe", "bebidas", "te"
]

def run_ingest(category):
    print(f"\n[UNIMARC INGEST] Target: {category}")
    cmd = [
        "python", "-m", "domain.ingest",
        "--search", category,
        "--pages", "3",
        "--stores", "unimarc"
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()
    
    try:
        subprocess.run(cmd, env=env, check=True)
        print(f"  OK: {category}")
    except Exception as e:
        print(f"  FAILED: {category} - {e}")

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    for cat in CATEGORIES:
        run_ingest(cat)
        time.sleep(2) # Prevent rate limiting
