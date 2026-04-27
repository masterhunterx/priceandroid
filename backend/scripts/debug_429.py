import httpx
import asyncio
import time

async def hit(client, i):
    resp = await client.get("/api/products/search?q=leche")
    if resp.status_code == 429:
        print(f"[{i}] ERROR 429: {resp.json()}")
        return False
    return True

async def main():
    headers = {"X-API-Key": "freshcart_dev_key"}
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", headers=headers) as client:
        tasks = []
        for i in range(50):
            tasks.append(hit(client, i))
        
        results = await asyncio.gather(*tasks)
        print(f"Success: {sum(results)}/50")

if __name__ == "__main__":
    asyncio.run(main())
