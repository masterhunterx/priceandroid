"""
Advanced Scraping Coordinator
==============================
Orchestrates parallel scraping across multiple supermarket chains and branches
using asyncio and curl_cffi for high-performance, stealthy data extraction.

Inspired by the 'Coordinator Mode' in state-of-the-art terminal agents.
"""

import asyncio
import random
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from curl_cffi.requests import AsyncSession
from sqlalchemy.orm import Session

from core.db import get_session
from core.models import Store, Branch, StoreProduct
from .ingest import upsert_store_products

# Undercover Header Pool (Stealth Mode)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Mobile/15E148 Safari/604.1",
]

class ScrapingCoordinator:
    def __init__(self, concurrency: int = 5):
        self.concurrency = concurrency
        self.semaphore = asyncio.Semaphore(concurrency)
        self.results = []

    async def scrape_branch_task(self, store_slug: str, branch_id: str | None, query: str, pages: int):
        """Individual task to scrape a single branch with rate-limiting semaphore."""
        async with self.semaphore:
            print(f"  [Coordinator] Starting scrape: {store_slug} (Branch: {branch_id or 'Chain-wide'})")
            
            # Selection of a random User-Agent for "Undercover" mode
            ua = random.choice(USER_AGENTS)
            
            # Using curl_cffi AsyncSession to bypass Akamai/PerimeterX
            # Impersonate chrome to get realistic TLS fingerprints
            async with AsyncSession(impersonate="chrome110") as session:
                session.headers.update({"User-Agent": ua})
                
                try:
                    # Dispatch to specific async scraper logic
                    # Note: We will need to update individual scrapers to have async versions
                    # For now, we'll wrap the existing ones in run_in_executor or similar 
                    # until they are fully migrated to async.
                    
                    loop = asyncio.get_event_loop()
                    
                    # Wrapping the synchronous scrape_store in an executor
                    from .ingest import scrape_store
                    scraped_data = await loop.run_in_executor(
                        None, scrape_store, store_slug, query, pages, branch_id
                    )
                    
                    return {
                        "store_slug": store_slug,
                        "branch_id": branch_id,
                        "data": scraped_data,
                        "status": "success"
                    }
                except Exception as e:
                    print(f"  [Coordinator] Error scraping {store_slug}: {e}")
                    return {
                        "store_slug": store_slug,
                        "branch_id": branch_id,
                        "data": [],
                        "status": "error",
                        "error": str(e)
                    }

    async def run_parallel_scrape(self, query: str, pages: int, store_slugs: List[str], all_branches: bool = False):
        """Run the full parallel ingestion pipeline."""
        start_time = time.time()
        tasks = []
        
        with get_session() as db_session:
            for slug in store_slugs:
                store = db_session.query(Store).filter_by(slug=slug).first()
                if not store:
                    continue
                
                if all_branches:
                    branches = db_session.query(Branch).filter_by(store_id=store.id, is_active=True).all()
                    for branch in branches:
                        tasks.append(self.scrape_branch_task(slug, branch.external_store_id, query, pages))
                else:
                    tasks.append(self.scrape_branch_task(slug, None, query, pages))

        print(f"\n  [Coordinator] Launching {len(tasks)} parallel scraping tasks...")
        results = await asyncio.gather(*tasks)
        
        # Phase 2: Sequential Database Insertion (to avoid lock contention in SQLite/PG)
        print(f"\n  [Coordinator] Entering Database Ingestion Phase...")
        with get_session() as db_session:
            for res in results:
                if res["status"] == "success" and res["data"]:
                    store = db_session.query(Store).filter_by(slug=res["store_slug"]).first()
                    branch = None
                    if res["branch_id"]:
                        branch = db_session.query(Branch).filter_by(
                            store_id=store.id, 
                            external_store_id=res["branch_id"]
                        ).first()
                    
                    upsert_store_products(db_session, store, res["data"], branch=branch)
            
            db_session.commit()
            
        elapsed = time.time() - start_time
        print(f"\n  [Coordinator] Parallel Pipeline completed in {elapsed:.2f}s")
        return results

if __name__ == "__main__":
    # Test run
    coordinator = ScrapingCoordinator(concurrency=3)
    asyncio.run(coordinator.run_parallel_scrape("leche", 1, ["jumbo", "unimarc"]))
