"""
Dream System: Memory Consolidation Engine
==========================================
Analyzes historical price data for each product to identify trends, 
calculate 'True Lows', and detect significant deals.

Inspired by the 'autoDream' background task in state-of-the-art terminal agents.
"""

from datetime import datetime, timezone, timedelta
import statistics
from sqlalchemy import func
from core.db import get_session
from core.models import Product, StoreProduct, Price, PriceInsight, Store

UTC = timezone.utc

def calculate_deal_score(current_price: float, prices: list[float]) -> int:
    """
    Advanced Deal Score using Standard Deviation (Sigma).
    A 'Genuine Deal' is usually > 1 Sigma below the mean.
    A 'Unicorn Deal' is > 2 Sigma below the mean.
    """
    if not prices or len(prices) < 3:
        return 0
    
    mean = statistics.mean(prices)
    stdev = statistics.stdev(prices) if len(prices) > 1 else 0
    
    if current_price >= mean:
        return 0
    
    # 1. Base Score: Savings vs Mean (up to 50 pts)
    savings_vs_mean = (mean - current_price) / mean
    score = int(savings_vs_mean * 150) 
    
    # 2. Sigma Score: Statistical Significance (up to 30 pts)
    if stdev > 0:
        sigma_dist = (mean - current_price) / stdev
        score += int(min(sigma_dist * 10, 30))
    
    # 3. All-time Low Bonus (20 pts)
    min_p = min(prices)
    if current_price <= (min_p * 1.01): # Within 1% of absolute floor
        score += 20
        
    # 4. Volatility Penalty (Stable prices are more trustworthy)
    # If stdev is huge compared to mean, be more cautious
    volatility = stdev / mean if mean > 0 else 0
    if volatility > 0.3: # >30% fluctuation is "Chaotic"
        score = int(score * 0.8)

    return min(max(score, 0), 100)

def consolidate_memories():
    """Run a consolidation pass over all products."""
    print(f"\n  [Dream System] Starting price consolidation pass...")
    start_time = datetime.now()
    
    with get_session() as session:
        products = session.query(Product).all()
        consolidated_count = 0
        deals_found = 0
        
        for product in products:
            # Get all StoreProducts for this canonical product
            store_products = session.query(StoreProduct).filter_by(product_id=product.id).all()
            if not store_products:
                continue
            
            sp_ids = [sp.id for sp in store_products]
            
            # 1. Fetch historical prices
            history = session.query(Price).filter(Price.store_product_id.in_(sp_ids)).all()
            if not history:
                continue
            
            prices = [p.price for p in history if p.price]
            if not prices:
                continue
            
            # 2. Calculate Stats
            avg_p = sum(prices) / len(prices)
            min_p = min(prices)
            max_p = max(prices)
            
            # 3. Find current 'best' price across all stores
            latest_prices = []
            for sp in store_products:
                lp = sp.latest_price
                if lp and lp.price and sp.in_stock:
                    latest_prices.append((lp.price, sp.store_id))
            
            if not latest_prices:
                continue
            
            best_now, best_store_id = min(latest_prices, key=lambda x: x[0])
            
            # 4. Determine trend
            # Simplified: compare last 3 vs older 3
            trend = "stable"
            if len(prices) >= 6:
                recent_avg = sum(prices[-3:]) / 3
                older_avg = sum(prices[:-3]) / len(prices[:-3])
                if recent_avg < older_avg * 0.95:
                    trend = "falling"
                elif recent_avg > older_avg * 1.05:
                    trend = "rising"
            
            # 5. Deal detection
            deal_score = calculate_deal_score(best_now, prices)
            is_deal = deal_score >= 50 # Threshold increased for higher 'IQ'
            
            # 6. Update PriceInsight
            insight = session.query(PriceInsight).filter_by(product_id=product.id).first()
            if not insight:
                insight = PriceInsight(product_id=product.id)
                session.add(insight)
            
            insight.avg_price = avg_p
            insight.min_price_all_time = min_p
            insight.max_price_all_time = max_p
            insight.cheapest_store_id = best_store_id
            insight.price_trend = trend
            insight.is_deal_now = is_deal
            insight.deal_score = deal_score
            insight.last_consolidated = datetime.now(UTC)
            
            consolidated_count += 1
            if is_deal:
                deals_found += 1

        session.commit()
    
    elapsed = datetime.now() - start_time
    print(f"  [Dream System] Consolidated {consolidated_count} products.")
    print(f"  [Dream System] Found {deals_found} significant deals.")
    print(f"  [Dream System] Pass completed in {elapsed.total_seconds():.2f}s")

if __name__ == "__main__":
    consolidate_memories()
