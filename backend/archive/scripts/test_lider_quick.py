"""Quick endpoint test"""
import requests, json

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

query = 'query Search($query: String, $page: Int, $prg: Prg!, $ps: Int) { search(query: $query, page: $page, prg: $prg, ps: $ps, pageType: "SearchPage") { searchResult { aggregatedCount } } }'
variables = {"query": "leche", "page": 1, "prg": "mWeb", "ps": 5}

url = "https://super.lider.cl/orchestra/graphql/search"
try:
    r = session.post(url, json={"query": query, "variables": variables}, timeout=15)
    print(f"Status: {r.status_code}")
    text = r.text
    print(f"First 500 chars: {text[:500]}")
    if r.status_code == 200:
        data = r.json()
        print(f"Keys: {list(data.keys())}")
        if 'data' in data:
            print(f"Data keys: {list(data['data'].keys()) if data['data'] else 'None'}")
        if 'errors' in data:
            print(f"Errors: {data['errors']}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
