from data.sources.unimarc_scraper import create_session, search_products
import sys
import os

def test():
    s = create_session()
    print("Searching 'leche'...")
    p1 = search_products(s, "leche", max_pages=1)
    print(f"  Got {len(p1)} products. First: {p1[0]['name'] if p1 else 'None'}")
    
    print("Searching 'arroz'...")
    p2 = search_products(s, "arroz", max_pages=1)
    print(f"  Got {len(p2)} products. First: {p2[0]['name'] if p2 else 'None'}")
    
    if p1 and p2 and p1[0]['product_id'] == p2[0]['product_id']:
        print("\n[WARNING] Unimarc API is returning the SAME products for different searches!")
    else:
        print("\n[OK] Unimarc API returns different products.")

if __name__ == "__main__":
    test()
