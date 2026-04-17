import httpx
import json

async def test():
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                "http://localhost:8000/api/products/search?q=leche",
                headers={"X-API-Key": "antigravity_dev_key"}
            )
            print(f"Status: {resp.status_code}")
            print(f"Body: {resp.text[:200]}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test())
