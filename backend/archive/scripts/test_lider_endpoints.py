"""
Test: Lider API endpoint alternatives
"""
import requests

# Test multiple possible endpoints and variations

session = requests.Session()
session.headers.update({
    'User-Agent': 'okhttp/4.12.0',
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'x-o-bu': 'LIDER-CL',
    'x-o-vertical': 'OD',
    'x-o-platform': 'rweb',
    'x-o-mart': 'B2C',
    'x-o-segment': 'oaoh',
    'accept-language': 'es-CL',
})

# Minimal test query
query = 'query Search($query: String, $page: Int, $prg: Prg!, $ps: Int) { search(query: $query, page: $page, prg: $prg, ps: $ps, pageType: "SearchPage") { searchResult { aggregatedCount } } }'
variables = {"query": "leche", "page": 1, "prg": "mWeb", "ps": 5}

endpoints = [
    "https://super.lider.cl/orchestra/graphql/search",
    "https://www.lider.cl/orchestra/graphql/search",
    "https://api.lider.cl/graphql",
]

for url in endpoints:
    try:
        r = session.post(url, json={"query": query, "variables": variables}, timeout=15)
        print(f"\n✅ {url}")
        print(f"   Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            if "data" in data and "search" in data["data"]:
                count = data["data"]["search"]["searchResult"]["aggregatedCount"]
                print(f"   ✅ FUNCIONA! aggregatedCount={count}")
            elif "errors" in data:
                print(f"  GraphQL errors: {data['errors']}")
            else:
                print(f"  Response: {str(data)[:300]}")
    except requests.exceptions.ConnectionError as e:
        print(f"\n❌ {url}: Cannot connect - {e}")
    except requests.exceptions.Timeout:
        print(f"\n⏳ {url}: Timeout")
    except Exception as e:
        print(f"\n❌ {url}: {type(e).__name__}: {e}")
