import pytest
from fastapi.testclient import TestClient
import os
import sys

# Ensure backend can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.main import app

client = TestClient(app)
API_KEY = os.environ.get("API_KEY", "") # safe
HEADERS = {"X-API-Key": API_KEY}

def test_health_check_via_stores():
    """Verify that the API is up and answering with our schema."""
    response = client.get("/api/stores", headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert isinstance(data["data"], list)

def test_search_logic():
    """Verify that search returns results in the UnifiedResponse format."""
    response = client.get("/api/products/search?q=leche", headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    # If DB is empty this might be empty, but we expect data structure
    assert "data" in data

def test_unauthorized_access():
    """Security check: verify that requests without API key are blocked."""
    response = client.get("/api/stores")
    assert response.status_code == 403

def test_categories_api():
    """Verify that the categories endpoint is functioning."""
    response = client.get("/api/categories", headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["success"] is True
