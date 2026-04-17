from backend.core.discord_bot import search_products_in_db
import json

results = search_products_in_db("costillar")
print(json.dumps(results, indent=2))
