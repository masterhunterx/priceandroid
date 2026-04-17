from curl_cffi import requests as cffi_requests
import json

def debug_unimarc():
    s = cffi_requests.Session(impersonate="chrome")
    q = "leche"
    
    # Try the most likely correct URL + Payload
    url = f"https://bff-unimarc-ecommerce.unimarc.cl/catalog/product/search?searchText={q}"
    payload = {
        "searchText": q,
        "page": 1,
        "order": "",
        "activeFacets": [],
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "version": "1.0.0",
        "source": "web",
        "Origin": "https://www.unimarc.cl",
        "Referer": f"https://www.unimarc.cl/busqueda/{q}",
    }

    
    print(f"Testing URL: {url}")
    res = s.post(url, json=payload, headers=headers)
    
    if res.status_code == 200:
        data = res.json()
        products = data.get("availableProducts", [])
        print(f"Results count: {len(products)}")
        if products:
            p = products[0]
            name = p.get("item", {}).get("name", "N/A")
            print(f"First product name: {name}")
            # If still 'Pechuga...', try another variant
            if "Pechuga" in name:
                print("[WARNING] Still getting default results. Trying 'activeFacets' and 'clusterId'...")
                payload["activeFacets"] = [{"key": "busqueda", "value": q}]
                payload["clusterId"] = "953" # Chillan
                res2 = s.post(url, json=payload, headers=headers)
                products2 = res2.json().get("availableProducts", [])
                if products2:
                    name2 = products2[0].get("item", {}).get("name", "N/A")
                    print(f"Second try (activeFacets + cluster): {name2}")
                else:
                    print("Second try returned NO products.")


if __name__ == "__main__":
    debug_unimarc()
