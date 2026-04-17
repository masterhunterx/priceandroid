import pytest
from datetime import datetime, timezone
UTC = timezone.utc
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.models import Base, Store, Branch, Location, StoreProduct, Price
from domain.ingest import upsert_store_products

@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_multi_branch_upsert(db_session):
    # 1. Setup: Store, Location, and two Branches
    store = Store(name="Jumbo", slug="jumbo", base_url="https://jumbo.cl")
    db_session.add(store)
    
    loc = Location(name="Santiago", region_code="RM")
    db_session.add(loc)
    db_session.flush()
    
    b1 = Branch(
        store=store, 
        location=loc, 
        name="Jumbo Costanera", 
        external_store_id="costanera_id"
    )
    b2 = Branch(
        store=store, 
        location=loc, 
        name="Jumbo Bilbao", 
        external_store_id="bilbao_id"
    )
    db_session.add_all([b1, b2])
    db_session.flush()

    # 2. Mock Scraped Data (Same product, different prices)
    product_data = {
        "product_id": "SKU123",
        "name": "Leche Entera",
        "brand": "Soprole",
        "price": 1000,
        "in_stock": True,
    }

    # 3. Ingest for Branch 1
    upsert_store_products(db_session, store, [product_data], branch=b1)
    
    # 4. Ingest for Branch 2 (same product, different price)
    product_data_b2 = product_data.copy()
    product_data_b2["price"] = 1100
    upsert_store_products(db_session, store, [product_data_b2], branch=b2)

    # 5. Assertions
    # Note: Currently, StoreProduct is indexed by (store_id, external_id).
    # If we want branch-specific StoreProducts, we need to update the UniqueConstraint.
    # In the current implementation, we are linking the SAME StoreProduct to the LAST branch seen,
    # OR we are just ensuring the PRICE is branched.
    
    # Let's check how many StoreProducts we have.
    sps = db_session.query(StoreProduct).all()
    
    # Based on the current UniqueConstraint("store_id", "external_id"), 
    # there is only ONE StoreProduct per SKU across the whole chain.
    # BUT the Price table now has branch_id.
    assert len(sps) == 1
    
    prices = db_session.query(Price).all()
    assert len(prices) == 2
    
    # Check branch IDs on prices
    p1 = db_session.query(Price).filter_by(branch_id=b1.id).one()
    p2 = db_session.query(Price).filter_by(branch_id=b2.id).one()
    
    assert p1.price == 1000
    assert p2.price == 1100
    print("\n[SUCCESS] Successfully recorded branch-specific prices for the same SKU.")

def test_legacy_chain_wide_upsert(db_session):
    # Setup
    store = Store(name="Lider", slug="lider", base_url="https://lider.cl")
    db_session.add(store)
    db_session.flush()

    product_data = {
        "product_id": "L1",
        "name": "Arroz",
        "price": 800,
    }

    # Ingest WITH NO BRANCH (Legacy mode)
    upsert_store_products(db_session, store, [product_data], branch=None)

    sp = db_session.query(StoreProduct).filter_by(external_id="L1").one()
    assert sp.branch_id is None
    
    price = db_session.query(Price).filter_by(store_product_id=sp.id).one()
    assert price.branch_id is None
    assert price.price == 800
    print("\n[SUCCESS] Legacy chain-wide ingestion still works correctly.")

def test_location_registry(db_session):
    loc = Location(name="Valparaíso", region_code="V")
    db_session.add(loc)
    db_session.commit()
    
    saved = db_session.query(Location).filter_by(name="Valparaíso").first()
    assert saved is not None
    assert saved.region_code == "V"
