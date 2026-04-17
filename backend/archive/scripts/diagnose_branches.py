from core.db import get_session
from core.models import Branch
import sys

def check():
    with get_session() as session:
        res = session.query(Branch).filter(Branch.city == '').all()
        print(f"Sucursales con ciudad vacía: {len(res)}")
        for b in res[:10]:
            print(f"ID: {b.id}, Nombre: {b.name}, Dirección: {b.address}")

if __name__ == "__main__":
    check()
