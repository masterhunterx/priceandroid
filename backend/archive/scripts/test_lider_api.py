import requests
import json

headers = {
    'User-Agent': 'okhttp/4.12.0',
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'x-o-gql-query': 'query Search',
    'X-APOLLO-OPERATION-NAME': 'Search',
    'x-o-bu': 'LIDER-CL',
    'x-o-vertical': 'OD',
    'x-o-platform': 'rweb',
    'x-o-mart': 'B2C',
    'x-o-segment': 'oaoh',
    'accept-language': 'es-CL',
}

# Try original endpoint
url = "https://super.lider.cl/orchestra/graphql/search"

# Minimal query
query = """query Search($query: String, $page: Int, $prg: Prg!, $ps: Int, $pageType: String! = "SearchPage") {
  search(query: $query, page: $page, prg: $prg, ps: $ps, pageType: $pageType) {
    searchResult { aggregatedCount }
  }
}"""

variables = {"query": "leche", "page": 1, "prg": "mWeb", "ps": 5}
payload = {"query": query, "variables": variables}

try:
    r = requests.post(url, json=payload, headers=headers, timeout=12)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text[:500]}")
except Exception as e:
    print(f"Connection error: {type(e).__name__}: {e}")

# Try alternative Walmart Chile API
print("\n--- Trying alternative endpoint ---")
alt_url = "https://www.lider.cl/supermercado/search"
try:
    r2 = requests.get(alt_url, params={"query": "leche", "page": 1}, 
                     headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    print(f"Status: {r2.status_code}")
    print(f"First 200 chars: {r2.text[:200]}")
except Exception as e:
    print(f"Error: {e}")
