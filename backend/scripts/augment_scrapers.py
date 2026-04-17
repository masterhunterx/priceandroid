import os

def augment_scraper(filename):
    path = f"c:/Users/Cris/Desktop/Price/backend/data/sources/{filename}"
    if not os.path.exists(path):
        print(f"Error: {path} not found")
        return

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    if "def check_health" in content:
        print(f"{filename} already has check_health")
        return

    # Unified check_health template for Jumbo/Santa Isabel (same BFF structure)
    code = """
def check_health(session=None):
    \"\"\"
    Scraper health check: search for 'leche' and verify we get results.
    Returns: (bool success, str message)
    \"\"\"
    try:
        from curl_cffi import requests as cffi_requests
        s = session or cffi_requests.Session(impersonate="chrome")
        results, total = search_products(s, "leche", max_pages=1)
        if results and total > 0:
            return True, f"OK: Found {total} products for 'leche'"
        return False, "Failed: API returned 0 products or invalid structure."
    except Exception as e:
        return False, f"Error: {e}"

"""
    # Insert before search_products
    target = "def search_products"
    if target in content:
        parts = content.split(target)
        # Assuming we want to insert before the last occurrence if multiple, 
        # but usually there's only one. We'll join everything but the last part.
        new_content = target.join(parts[:-1]) + code + target + parts[-1]
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"Successfully added check_health to {filename}")
    else:
        print(f"Could not find search_products in {filename}")

if __name__ == "__main__":
    for f in ["jumbo_scraper.py", "santa_isabel_scraper.py"]:
        augment_scraper(f)
