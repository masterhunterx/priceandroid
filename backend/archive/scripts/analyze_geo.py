from core.db import get_session
from core.models import Branch
from sqlalchemy import func

def get_geographic_stats():
    with get_session() as session:
        # Group by region and city
        stats = session.query(
            Branch.region, 
            Branch.city,
            func.avg(Branch.latitude),
            func.avg(Branch.longitude),
            func.count(Branch.id)
        ).filter(Branch.latitude.isnot(None)).group_by(Branch.region, Branch.city).all()
        
        # Build hierarchy
        hierarchy = {}
        for region, city, avg_lat, avg_lng, count in stats:
            if not region: region = "Otras"
            if region not in hierarchy:
                hierarchy[region] = []
            
            hierarchy[region].append({
                "comuna": city,
                "lat": avg_lat,
                "lng": avg_lng,
                "stores": count
            })
            
        import json
        with open("geo_data.json", "w", encoding="utf-8") as f:
            json.dump(hierarchy, f, ensure_ascii=False, indent=2)
            
        print(f"Stats exported for {len(hierarchy)} regions.")

if __name__ == "__main__":
    get_geographic_stats()
