"""
Scheduled Catalog Crawler
==========================
Runs the full catalog crawl on a recurring schedule (every 72 hours).
Can run as a long-lived process or be triggered by system cron/Task Scheduler.

Usage:
    # Run once immediately
    python scheduler.py --once

    # Run as a daemon (repeats every 72 hours)
    python scheduler.py

    # Custom interval
    python scheduler.py --interval-hours 24
"""

import argparse
import os
import time
import schedule
from datetime import datetime

from dotenv import load_dotenv

# Load .env for local/dev runs. On Railway, env vars are injected directly.
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from data.sources.category_crawler import run_full_crawl
from domain.dream import consolidate_memories
from domain.proactive import generate_proactive_alerts
from domain.heartbeat import sync_favorites


# Default settings
DEFAULT_PAGES_PER_CATEGORY = 3
DEFAULT_WEEKLY_TIME = "03:00"  # UTC


def run_job(pages_per_category, stores):
    """Wrapper for the job to be scheduled."""
    start = datetime.now()
    print(f"\n  Starting crawl at {start.strftime('%Y-%m-%d %H:%M:%S')}")
    try:
        run_full_crawl(stores, pages_per_category)
    except Exception as e:
        print(f"\n  [ERROR] Crawl failed: {e}")
    elapsed = datetime.now() - start
    print(f"\n  Crawl completed in {elapsed}")
    
    # After crawl, trigger 'Dream' and 'Proactive' logic
    print(f"\n  [Post-Crawl] Triggering AI Intelligence layer...")
    try:
        consolidate_memories()
        generate_proactive_alerts()
        sync_favorites()
    except Exception as e:
        print(f"  [ERROR] Intelligence layer failed: {e}")


def run_scheduled(interval_hours=None, pages_per_category=DEFAULT_PAGES_PER_CATEGORY, stores=None):
    """Run the full crawl on a repeating schedule."""
    print(f"\n{'#'*60}")
    print(f"  SCHEDULED CATALOG CRAWLER")
    
    if interval_hours:
        print(f"  Mode: Interval (every {interval_hours} hours)")
        schedule.every(interval_hours).hours.do(run_job, pages_per_category, stores)
    else:
        print(f"  Mode: Weekly (Sundays at {DEFAULT_WEEKLY_TIME} UTC)")
        schedule.every().sunday.at(DEFAULT_WEEKLY_TIME).do(run_job, pages_per_category, stores)
    
    # Regularly run the Dream system and KAIROS independently of full crawls
    # Every 24 hours to ensure price trends are current
    schedule.every(24).hours.do(consolidate_memories)
    schedule.every(24).hours.do(generate_proactive_alerts)
    
    # Priority update for favorites every 6 hours
    schedule.every(6).hours.do(sync_favorites)
        
    print(f"  Pages per category: {pages_per_category}")
    print(f"  Press Ctrl+C to stop")
    print(f"{'#'*60}\n")

    # Run initial check if any scheduled job is pending (or just wait)
    while True:
        schedule.run_pending()
        time.sleep(60) # check every minute


def main():
    parser = argparse.ArgumentParser(
        description="Scheduled full catalog crawler for Chilean supermarkets"
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Run a single crawl and exit (no scheduling)"
    )
    parser.add_argument(
        "--interval-hours", type=int, default=None,
        help="Optional: Run every X hours instead of weekly"
    )
    parser.add_argument(
        "--pages", "-p", type=int, default=DEFAULT_PAGES_PER_CATEGORY,
        help=f"Pages per category (default: {DEFAULT_PAGES_PER_CATEGORY})"
    )
    parser.add_argument(
        "--stores", nargs="+", default=None,
        choices=["jumbo", "unimarc"],
        help="Which stores to crawl (default: all)"
    )

    args = parser.parse_args()

    if args.once:
        run_full_crawl(args.stores, args.pages)
    else:
        run_scheduled(args.interval_hours, args.pages, args.stores)


if __name__ == "__main__":
    main()
