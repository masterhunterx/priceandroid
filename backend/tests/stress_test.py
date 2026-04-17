import asyncio
import httpx
import time
import statistics
import json
import os

# --- CONFIGURATION ---
BASE_URL = "http://localhost:8000/api"
API_KEY = "DEV_API_KEY_SC" # We should check if this matches or use the one from .env
HEADERS = {"X-API-Key": API_KEY}
ENDPOINTS = [
    "/products/search?q=leche",
    "/categories",
    "/deals",
    "/assistant/notifications"
]

async def fetch(client, endpoint):
    start_time = time.perf_counter()
    try:
        response = await client.get(f"{BASE_URL}{endpoint}", headers=HEADERS, timeout=10.0)
        end_time = time.perf_counter()
        
        return {
            "endpoint": endpoint,
            "status": response.status_code,
            "latency": end_time - start_time,
            "success": response.status_code == 200
        }
    except Exception as e:
        end_time = time.perf_counter()
        return {
            "endpoint": endpoint,
            "status": -1,
            "latency": end_time - start_time,
            "success": False,
            "error": str(e)
        }

async def run_batch(concurrency):
    async with httpx.AsyncClient() as client:
        tasks = []
        for i in range(concurrency):
            endpoint = ENDPOINTS[i % len(ENDPOINTS)]
            tasks.append(fetch(client, endpoint))
        
        results = await asyncio.gather(*tasks)
        return results

def analyze_results(results, concurrency):
    latencies = [r["latency"] for r in results if r["success"]]
    errors = [r for r in results if not r["success"]]
    
    if not latencies:
        return {
            "concurrency": concurrency,
            "error_rate": 100.0,
            "avg_latency": -1,
            "p95_latency": -1
        }
        
    return {
        "concurrency": concurrency,
        "total_requests": len(results),
        "success_count": len(latencies),
        "error_count": len(errors),
        "error_rate": (len(errors) / len(results)) * 100,
        "avg_latency": statistics.mean(latencies),
        "p95_latency": statistics.quantiles(latencies, n=20)[18], # 95th percentile
        "min_latency": min(latencies),
        "max_latency": max(latencies)
    }

async def main():
    print(f"🚀 Starting Stress to Failure Test against {BASE_URL}")
    print("-" * 50)
    
    ramp_up = [10, 50, 100, 200, 350, 500]
    final_report = []
    
    for c in ramp_up:
        print(f"Testing Concurrency: {c} requests...")
        start_batch = time.perf_counter()
        results = await run_batch(c)
        end_batch = time.perf_counter()
        
        stats = analyze_results(results, c)
        stats["batch_duration"] = end_batch - start_batch
        final_report.append(stats)
        
        print(f"  ✅ Completed in {stats['batch_duration']:.2f}s")
        print(f"  📊 Avg Latency: {stats['avg_latency']:.4f}s | p95: {stats['p95_latency']:.4f}s")
        print(f"  ❌ Errors: {stats['error_count']} ({stats['error_rate']:.2f}%)")
        
        if stats['error_rate'] > 10 or stats['p95_latency'] > 3.0:
            print("🛑 BREAKING POINT REACHED!")
            break
        
        await asyncio.sleep(1) # Cool down

    # Save report
    with open("stress_test_results.json", "w") as f:
        json.dump(final_report, f, indent=2)
    print("-" * 50)
    print(f"🏁 Test Finished. Results saved to stress_test_results.json")

if __name__ == "__main__":
    asyncio.run(main())
