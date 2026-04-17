import os
import sys
sys.path.append(os.getcwd())

from core.db import get_session
from core.models import Branch

def diagnose():
    with get_session() as session:
        # Search for Biobio branches
        res = session.query(Branch).filter(Branch.region.like('%Biob%')).all()
        print(f"Total branches in Biobio: {len(res)}")
        for b in res:
            print(f"ID: {b.id}, Store: {b.store.name}, City: '{b.city}', Lat: {b.latitude}")

if __name__ == "__main__":
    diagnose()
