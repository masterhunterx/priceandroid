
from backend.core.db import get_session
from backend.core.models import Price, StoreProduct
from datetime import datetime

def check_freshness():
    with get_session() as session:
        # Latest prices
        latest_prices = session.query(Price).order_by(Price.scraped_at.desc()).limit(10).all()
        print("--- Latest Prices in DB ---")
        for p in latest_prices:
            print(f"ID: {p.id}, Price: {p.price}, Scraped At: {p.scraped_at}")
            
        # Count prices from today
        today = datetime.now().date()
        today_count = session.query(Price).filter(Price.scraped_at >= today).count()
        print(f"\nPrices scraped today ({today}): {today_count}")
        
        # Count deals from today
        today_deals = session.query(Price).filter(Price.scraped_at >= today, Price.has_discount == True).count()
        print(f"Deals found today: {today_deals}")

if __name__ == "__main__":
    check_freshness()
