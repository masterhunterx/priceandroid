"""
Audit: diagnóstico completo de cobertura por tienda y búsqueda
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.db import get_session
from core.models import StoreProduct, Store, Product

with get_session() as s:
    stores = s.query(Store).all()
    print("=" * 60)
    print("COBERTURA POR TIENDA")
    print("=" * 60)
    for st in stores:
        cnt = s.query(StoreProduct).filter_by(store_id=st.id).count()
        in_stock = s.query(StoreProduct).filter_by(store_id=st.id, in_stock=True).count()
        with_canonical = s.query(StoreProduct).filter(
            StoreProduct.store_id == st.id,
            StoreProduct.product_id != None
        ).count()
        print(f"\n{st.name} (slug: {st.slug})")
        print(f"  Total StoreProducts : {cnt}")
        print(f"  En stock            : {in_stock}")
        print(f"  Con producto canón. : {with_canonical}")
    
    print()
    total_canonical = s.query(Product).count()
    total_sp = s.query(StoreProduct).count()
    print(f"Total Productos Canónicos: {total_canonical}")
    print(f"Total StoreProducts      : {total_sp}")
    
    print()
    print("=" * 60)
    print("BÚSQUEDA DE 'chiquitin' POR TIENDA")
    print("=" * 60)
    for st in stores:
        results = s.query(StoreProduct).filter(
            StoreProduct.store_id == st.id,
            StoreProduct.name.ilike('%chiquit%')
        ).all()
        print(f"\n{st.name}: {len(results)} resultados")
        for r in results:
            print(f"  - [{r.id}] {r.name} | product_id={r.product_id} | in_stock={r.in_stock}")
    
    print()
    print("=" * 60)
    print("PRUEBA DE BÚSQUEDA SIN TILDE ('chiquitin' vs 'chiquitín')")  
    print("=" * 60)
    
    import unicodedata
    def strip_accents(text):
        return ''.join(
            c for c in unicodedata.normalize('NFD', text)
            if unicodedata.category(c) != 'Mn'
        )
    
    sample_names = [r.name for r in s.query(StoreProduct).filter(StoreProduct.name.ilike('%chiquit%')).limit(5).all()]
    for name in sample_names:
        normalized = strip_accents(name.lower())
        search_no_tilde = strip_accents("chiquitin")
        search_with_tilde = strip_accents("chiquitín")
        print(f"  DB Name: '{name}'")
        print(f"  Normalized: '{normalized}'")
        print(f"  Match sin tilde: {'YES' if search_no_tilde in normalized else 'NO'}")
        print(f"  Match con tilde: {'YES' if search_with_tilde in normalized else 'NO'}")
        print()
