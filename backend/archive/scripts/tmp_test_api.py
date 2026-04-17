import requests
import json

url = "http://localhost:8000/api/assistant/optimize_cart"
headers = {
    "X-API-Key": "antigravity_dev_key",
    "Content-Type": "application/json"
}
payload = {
    "items": [{"query": "leche", "qty": 1}]
}

try:
    response = requests.post(url, headers=headers, json=payload)
    print(f"Status Code: {response.status_code}")
    print("Response JSON:")
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print(f"Error: {e}")
