
import os
import sys

# Ensure backend is in path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from core.db import get_session
from core.models import Branch, Store

def audit_chile_data():
    with get_session() as session:
        # Check total branches per store
        stores = session.query(Store).all()
        print(f"--- Store Statistics ---")
        for s in stores:
            count = session.query(Branch).filter_by(store_id=s.id).count()
            with_coords = session.query(Branch).filter_by(store_id=s.id).filter(Branch.latitude.isnot(None)).count()
            print(f"{s.name}: {count} branches ({with_coords} with coords)")

        # Check for specific locations requested by user
        nuble_count = session.query(Branch).filter(Branch.region.contains('uble')).count()
        yungay_count = session.query(Branch).filter(Branch.city.contains('Yungay')).count()
        print(f"\n--- User Specific Locations ---")
        print(f"Region Ñuble: {nuble_count} branches")
        print(f"Comuna Yungay: {yungay_count} branches")

        # List some branches in Ñuble if they exist
        if nuble_count > 0:
            nuble_branches = session.query(Branch, Store.name).join(Store).filter(Branch.region.contains('uble')).limit(5).all()
            for b, sname in nuble_branches:
                print(f"  {sname}: {b.name} ({b.city}, {b.region}) Coords: {b.latitude},{b.longitude}")

        # List branches in Yungay if they exist
        if yungay_count > 0:
            yungay_branches = session.query(Branch, Store.name).join(Store).filter(Branch.city.contains('Yungay')).limit(5).all()
            for b, sname in yungay_branches:
                print(f"  {sname}: {b.name} ({b.city}) Coords: {b.latitude},{b.longitude}")

if __name__ == "__main__":
    audit_chile_data()
