"""
Integration tests for FastAPI endpoints, atomic sales, and barcode lookup.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from backend.app.database import Base, get_customer_db, get_db, get_user_db
from backend.app.main import app
from backend.app.models import Product, Supplier

# In-memory SQLite with StaticPool so all connections share the same in-memory DB
TEST_DB_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_customer_db] = override_get_db
    app.dependency_overrides[get_user_db] = override_get_db
    db = TestingSessionLocal()
    sup = Supplier(supplier_id="S_TEST", supplier_name="Test Supplier Ltd")
    prod = Product(
        product_id="P_TEST01",
        barcode="8901234567890",
        sku="SKU-TEST01",
        product_name="Test Basmati Rice 1kg",
        category="Staples",
        purchase_price=80.0,
        selling_price=100.0,
        current_stock=25.0,
        supplier_id="S_TEST",
        supplier_lead_time_days=2,
        shelf_life_days=365
    )
    db.add(sup)
    db.add(prod)
    db.commit()
    db.close()
    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_customer_db, None)
    app.dependency_overrides.pop(get_user_db, None)
    Base.metadata.drop_all(bind=test_engine)

client = TestClient(app)

def test_health_check():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"

def test_barcode_lookup():
    resp = client.get("/api/products/barcode/8901234567890")
    assert resp.status_code == 200
    data = resp.json()
    assert data["product_id"] == "P_TEST01"
    assert data["current_stock"] == 25.0

def test_atomic_sale_reduces_inventory():
    sale_payload = {
        "product_id": "P_TEST01",
        "quantity_sold": 5.0,
        "payment_method": "UPI"
    }
    resp = client.post("/api/sales", json=sale_payload)
    assert resp.status_code == 201
    sale_data = resp.json()
    assert sale_data["line_total"] == 500.0

    # Verify database stock updated from 25 to 20
    prod_resp = client.get("/api/products/P_TEST01")
    assert prod_resp.status_code == 200
    assert prod_resp.json()["current_stock"] == 20.0

def test_sale_rejects_insufficient_stock():
    sale_payload = {
        "product_id": "P_TEST01",
        "quantity_sold": 999.0
    }
    resp = client.post("/api/sales", json=sale_payload)
    assert resp.status_code == 400
    assert "Insufficient inventory" in resp.json()["detail"]

def test_stock_in_increases_inventory():
    stock_in_payload = {
        "product_id": "P_TEST01",
        "quantity": 10.0,
        "movement_type": "STOCK_IN",
        "reason": "Replenishment delivery"
    }
    resp = client.post("/api/inventory/stock-in", json=stock_in_payload)
    assert resp.status_code == 200
    assert resp.json()["new_stock"] == 35.0
