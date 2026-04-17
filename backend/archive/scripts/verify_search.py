import requests
import json

def test_search():
    url = "http://localhost:8000/api/products/search?q=leche"
    headers = {"X-API-Key": "antigravity_dev_key"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        print(f"Status: {r.status_code}")
        data = r.json()
        if data.get("success"):
            results = data["data"]["results"]
            print(f"Total resultados: {data['data']['total']}")
            print(f"Mostrando: {len(results)}")
            if results:
                print(f"Primer resultado: {results[0]['name']}")
                print(f"Logo de tienda: {results[0].get('best_store_slug')}")
        else:
            print(f"API Error: {data.get('error')}")
    except Exception as e:
        print(f"Error conectando a la API: {e}")

if __name__ == "__main__":
    test_search()
