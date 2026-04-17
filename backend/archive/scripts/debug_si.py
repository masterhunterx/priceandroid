import requests
from data.sources.santa_isabel_scraper import HEADERS, SEARCH_ENDPOINT
from urllib.parse import urlencode

def debug_si():
    params = {'ft': 'leche', '_from': 0, '_to': 10}
    url = f"{SEARCH_ENDPOINT}?{urlencode(params)}"
    print(f"URL: {url}")
    r = requests.get(url, headers=HEADERS, timeout=15)
    print(f"Status: {r.status_code}")
    print(f"Headers: {list(r.headers.keys())}")
    resources = r.headers.get("resources")
    print(f"Resources: {resources}")
    if resources:
        print(f"Total results parsed: {resources.split('/')[-1] if '/' in resources else 'N/A'}")

if __name__ == "__main__":
    debug_si()
