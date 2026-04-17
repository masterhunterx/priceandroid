import os
import sys
# Add current dir to path
sys.path.append(os.getcwd())

from core.db import get_session
from core.models import Branch

def inspect():
    with get_session() as session:
        count = session.query(Branch).count()
        print(f"Total branches: {count}")
        
        # Check first 5
        branches = session.query(Branch).limit(5).all()
        for b in branches:
            print(f"ID: {b.id}, Name: {b.name}, Store: {b.store_id}, City: {b.city}, Region: {b.region}, Lat: {b.latitude}, Lng: {b.longitude}")

if __name__ == "__main__":
    inspect()
