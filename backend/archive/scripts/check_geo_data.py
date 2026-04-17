import os
import sys
sys.path.append(os.getcwd())

from core.db import get_session
from core.models import Branch, Store

def check():
    with get_session() as session:
        all_count = session.query(Branch).count()
        with_coords = session.query(Branch).filter(Branch.latitude.isnot(None)).count()
        print(f"Total branches: {all_count}")
        print(f"Branches with coordinates: {with_coords}")
        
        # Check regions/cities for those with coordinates
        geo_stats = session.query(Branch.region, Branch.city, Branch.latitude, Branch.longitude).filter(Branch.latitude.isnot(None)).all()
        # Unique regions/cities
        regions = sorted(list(set([g[0] for g in geo_stats if g[0]])))
        print(f"\nRegions available ({len(regions)}):")
        print(regions[:10], "...")
        
        # Check for potential duplicates
        # Group by store_id and external_store_id
        dupes = session.query(Branch.store_id, Branch.external_store_id, Branch.name, Branch.latitude, Branch.longitude)\
                      .order_by(Branch.store_id, Branch.external_store_id).all()
        
        # Print first few entries with coordinates to see data format
        print("\nSample entries with coords:")
        count = 0
        for d in dupes:
            if d[3] is not None:
                print(f"Store {d[0]}, Ext {d[1]}: {d[2]} ({d[3]}, {d[4]})")
                count += 1
            if count >= 5: break

if __name__ == "__main__":
    check()
