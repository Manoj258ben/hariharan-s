"""
Comprehensive test suite verifying Rural Data Collection, Offline Sync Idempotency,
and Secure Administrator RBAC, Rate-Limiting, Audit Logs, and Backup Integrity.
"""
import pytest
import uuid
import sqlite3
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import Base, get_customer_db, get_db, get_user_db
from backend.app.main import app
from backend.app.models import Product, Supplier, User, UserSession, AuditLogV2, OfflineSyncQueue
from backend.app.services.auth import hash_password
from backend.app.services import backup as backup_service

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
    
    # 1. Suppliers and Products
    sup = Supplier(supplier_id="S_RURAL", supplier_name="Rural Gramin Distributors")
    p1 = Product(
        product_id="P_CHAI",
        barcode=None, # Verified: barcode is completely optional
        sku="SKU-CHAI-01",
        product_name="Tata Tea Premium 250g",
        category="Beverages",
        purchase_price=75.0,
        selling_price=90.0,
        current_stock=50.0,
        supplier_id="S_RURAL",
        supplier_lead_time_days=2,
        shelf_life_days=365
    )
    p2 = Product(
        product_id="P_TEL",
        barcode="8901234560002",
        sku="SKU-TEL-01",
        product_name="Fortune Mustard Oil 1L",
        category="Oil",
        purchase_price=120.0,
        selling_price=145.0,
        current_stock=30.0,
        supplier_id="S_RURAL",
        supplier_lead_time_days=3,
        shelf_life_days=180
    )
    p3 = Product(
        product_id="P_BISCUIT",
        barcode="8901234560003",
        sku="SKU-PARLE-01",
        product_name="Parle-G Glucose Biscuit 250g",
        category="Biscuits",
        purchase_price=15.0,
        selling_price=20.0,
        current_stock=40.0,
        supplier_id="S_RURAL",
        supplier_lead_time_days=2,
        shelf_life_days=180
    )
    
    # 2. Users (Admin and Shopkeeper)
    admin_user = User(
        username="admin_test",
        hashed_password=hash_password("AdminSecret@123"),
        full_name="System Admin",
        role="admin",
        is_active=True
    )
    shop_user = User(
        username="shopkeeper_test",
        hashed_password=hash_password("ShopSecret@123"),
        full_name="Ramesh Shopkeeper",
        role="shopkeeper",
        is_active=True
    )
    
    db.add_all([sup, p1, p2, p3, admin_user, shop_user])
    db.commit()
    db.close()
    
    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_customer_db, None)
    app.dependency_overrides.pop(get_user_db, None)
    Base.metadata.drop_all(bind=test_engine)

client = TestClient(app)

# Helper to generate authorization headers by authenticating through /api/auth/login
def get_auth_header(username: str, password: str) -> dict:
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed for {username}: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

# ==============================================================================
# PART A: RURAL WORKFLOWS TESTS
# ==============================================================================

def test_rural_create_product_without_barcode():
    """Verify products can be added without barcode hardware."""
    admin_headers = get_auth_header("admin_test", "AdminSecret@123")
    resp = client.post("/api/products", headers=admin_headers, json={
        "product_id": "P_NO_BARCODE",
        "barcode": None,
        "product_name": "Gramin Jaggery Gur 1kg",
        "category": "Staples",
        "purchase_price": 45.0,
        "selling_price": 60.0,
        "current_stock": 20.0,
        "supplier_lead_time_days": 2,
        "shelf_life_days": 180
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["product_id"] == "P_NO_BARCODE"
    assert data["barcode"] is None


def test_rural_manual_sale_updates_inventory():
    """Verify manual sale records sale and reduces stock atomically."""
    resp = client.post("/api/rural/manual-sale", json={
        "product_id": "P_CHAI",
        "quantity": 5.0,
        "unit_price": 90.0,
        "payment_method": "Cash",
        "notes": "Evening customer purchase"
    })
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data["status"] == "success"
    assert data["new_stock"] == 45.0
    
    # Check product inventory in DB
    p_resp = client.get("/api/products/P_CHAI")
    assert p_resp.status_code == 200
    assert p_resp.json()["current_stock"] == 45.0


def test_rural_manual_delivery_stock_in():
    """Verify delivery from supplier increases stock and updates purchase price."""
    resp = client.post("/api/rural/manual-delivery", json={
        "product_id": "P_TEL",
        "product_name": "Fortune Mustard Oil 1L",
        "quantity": 20.0,
        "purchase_price": 122.0,
        "supplier_name": "Rural Gramin Distributors"
    })
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data["status"] == "success"
    assert data["new_stock"] == 50.0


def test_rural_voice_parsing_and_confirmation():
    """Verify Hindi/Hinglish speech transcript parser generates structured drafts and saves them."""
    transcript = "Aaj das biscuit packet bike aur paanch litre tel aaya"
    parse_resp = client.post("/api/rural/voice-parse", json={"transcript": transcript})
    assert parse_resp.status_code == 200
    parsed = parse_resp.json()
    drafts = parsed.get("draft_items", [])
    assert len(drafts) >= 2
    
    # Verify parsing extracted quantities
    quantities = [d["quantity"] for d in drafts]
    assert 10.0 in quantities
    assert 5.0 in quantities
    
    # Confirm the parsed draft into real inventory
    confirm_resp = client.post("/api/rural/voice-confirm", json={"items": drafts})
    assert confirm_resp.status_code in (200, 201)
    c_data = confirm_resp.json()
    assert c_data["status"] == "success"
    assert c_data["committed_sales"] + c_data["committed_stock_ins"] >= 2


def test_rural_physical_stock_reconciliation():
    """Verify physical count comparison and variance adjustment."""
    # Compare expected vs counted (POST request)
    comp_resp = client.post("/api/rural/stock-count/compare", json={
        "product_id": "P_CHAI",
        "counted_stock": 42.0
    })
    assert comp_resp.status_code == 200
    comp_data = comp_resp.json()
    assert comp_data["system_stock"] == 50.0
    assert comp_data["counted_stock"] == 42.0
    assert comp_data["difference"] == -8.0 # 8 missing or damaged
    
    # Commit physical adjustment
    commit_resp = client.post("/api/rural/stock-count/commit", json={
        "product_id": "P_CHAI",
        "counted_stock": 42.0,
        "reason": "Physical count mismatch - dampness loss"
    })
    assert commit_resp.status_code == 200
    c_data = commit_resp.json()
    assert c_data["status"] == "success"
    assert c_data["new_stock"] == 42.0
    
    # Verify product stock updated in DB
    p_resp = client.get("/api/products/P_CHAI")
    assert p_resp.json()["current_stock"] == 42.0


def test_offline_sync_idempotency_and_duplicate_handling():
    """Verify offline operations sync idempotently using unique operation_id."""
    op_id = str(uuid.uuid4())
    payload = {
        "operations": [
            {
                "operation_id": op_id,
                "operation_type": "RECORD_SALE",
                "payload": {
                    "product_id": "P_CHAI",
                    "quantity": 10.0,
                    "unit_price": 90.0,
                    "payment_method": "Cash"
                }
            }
        ]
    }
    
    # First sync: must succeed and deduct 10 from 50 (leaving 40)
    sync1 = client.post("/api/sync/offline", json=payload)
    assert sync1.status_code == 200
    s1_data = sync1.json()
    assert s1_data["synced_count"] == 1
    assert s1_data["duplicate_count"] == 0
    assert s1_data["results"][0]["status"] == "SYNCED"
    
    p1 = client.get("/api/products/P_CHAI").json()["current_stock"]
    assert p1 == 40.0
    
    # Second sync with exact SAME operation_id: must be recognized as DUPLICATE and NOT reduce stock again
    sync2 = client.post("/api/sync/offline", json=payload)
    assert sync2.status_code == 200
    s2_data = sync2.json()
    assert s2_data["duplicate_count"] == 1
    assert s2_data["results"][0]["status"] == "DUPLICATE"
    
    p2 = client.get("/api/products/P_CHAI").json()["current_stock"]
    assert p2 == 40.0 # Stock remains unchanged at 40!


# ==============================================================================
# PART B: SECURITY, AUTHENTICATION, RBAC & ADMIN TESTS
# ==============================================================================

def test_unauthenticated_access_rejected():
    """Verify protected admin endpoints reject unauthenticated requests with 401."""
    resp1 = client.get("/api/admin/users")
    assert resp1.status_code == 401
    
    resp2 = client.get("/api/admin/backup/health")
    assert resp2.status_code == 401
    
    resp3 = client.get("/api/admin/audit/logs")
    assert resp3.status_code == 401


def test_shopkeeper_cannot_access_admin_endpoints():
    """Verify shopkeeper role receives 403 Forbidden on administrator endpoints."""
    shop_headers = get_auth_header("shopkeeper_test", "ShopSecret@123")
    
    resp1 = client.get("/api/admin/users", headers=shop_headers)
    assert resp1.status_code == 403
    
    resp2 = client.get("/api/admin/backup/health", headers=shop_headers)
    assert resp2.status_code == 403
    
    resp3 = client.get("/api/admin/audit/logs", headers=shop_headers)
    assert resp3.status_code == 403


def test_login_brute_force_lockout():
    """Verify account locks out after 5 consecutive failed login attempts."""
    for i in range(4):
        resp = client.post("/api/auth/login", json={"username": "shopkeeper_test", "password": "WrongPassword"})
        assert resp.status_code == 401
        assert "Invalid username or password." in resp.json()["detail"]
    
    # 5th attempt locks the account
    resp5 = client.post("/api/auth/login", json={"username": "shopkeeper_test", "password": "WrongPassword"})
    assert resp5.status_code == 401
    assert "locked" in resp5.json()["detail"].lower()
    
    # Subsequent attempt even with CORRECT password is rejected while locked
    resp_locked = client.post("/api/auth/login", json={"username": "shopkeeper_test", "password": "ShopSecret@123"})
    assert resp_locked.status_code == 401
    assert "locked" in resp_locked.json()["detail"].lower()


def test_admin_user_lifecycle_and_last_admin_protection():
    """Verify admin can manage users, change roles, and cannot deactivate the last admin."""
    admin_headers = get_auth_header("admin_test", "AdminSecret@123")
    
    # 1. Create a new user
    create_resp = client.post("/api/admin/users", headers=admin_headers, json={
        "username": "assistant_01",
        "password": "AssistantPass@2026",
        "full_name": "Store Assistant Anita",
        "role": "shopkeeper"
    })
    assert create_resp.status_code == 201
    new_user = create_resp.json()
    assert new_user["username"] == "assistant_01"
    
    # 2. Deactivate the new user
    toggle_resp = client.patch(f"/api/admin/users/{new_user['user_id']}/status", headers=admin_headers, json={"is_active": False})
    assert toggle_resp.status_code == 200
    assert toggle_resp.json()["is_active"] is False
    
    # 3. Deactivated user cannot log in
    login_resp = client.post("/api/auth/login", json={"username": "assistant_01", "password": "AssistantPass@2026"})
    assert login_resp.status_code == 401
    assert "inactive" in login_resp.json()["detail"].lower() or "disabled" in login_resp.json()["detail"].lower()
    
    # 4. Attempt to deactivate the ONLY active admin: must be blocked!
    users_list = client.get("/api/admin/users", headers=admin_headers).json()
    admin_id = next(u["id"] for u in users_list if u["username"] == "admin_test")
    
    deact_admin_resp = client.patch(f"/api/admin/users/{admin_id}/status", headers=admin_headers, json={"is_active": False})
    assert deact_admin_resp.status_code == 400
    assert "last active administrator" in deact_admin_resp.json()["detail"].lower()
    
    # 5. Attempt to demote the ONLY active admin: must be blocked!
    demote_admin_resp = client.patch(f"/api/admin/users/{admin_id}/role", headers=admin_headers, json={"role": "shopkeeper"})
    assert demote_admin_resp.status_code == 400
    assert "last active administrator" in demote_admin_resp.json()["detail"].lower()


def test_audit_logs_capture_sensitive_actions():
    """Verify audit log records user creation, stock adjustment, and admin actions."""
    admin_headers = get_auth_header("admin_test", "AdminSecret@123")
    
    # Perform a sensitive action (create user)
    client.post("/api/admin/users", headers=admin_headers, json={
        "username": "audit_test_user",
        "password": "AuditPass@2026",
        "full_name": "Audit Sample",
        "role": "shopkeeper"
    })

    logs_resp = client.get("/api/admin/audit/logs?limit=50", headers=admin_headers)
    assert logs_resp.status_code == 200
    data = logs_resp.json()
    assert "logs" in data
    logs = data["logs"]
    assert isinstance(logs, list)
    actions = [l["action"] for l in logs]
    assert "USER_CREATED" in actions


def test_admin_database_backup_and_health(tmp_path, monkeypatch):
    """Verify admin can inspect SQLite health and initiate an online backup."""
    database_paths = {
        "stocksense": tmp_path / "stocksense.db",
        "customers": tmp_path / "customers.db",
        "users": tmp_path / "users.db",
    }
    for database_path in database_paths.values():
        with sqlite3.connect(database_path) as connection:
            connection.execute("CREATE TABLE backup_test (id INTEGER PRIMARY KEY)")
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    monkeypatch.setattr(backup_service, "get_db_file_path", lambda: database_paths["stocksense"])
    monkeypatch.setattr(backup_service, "CUSTOMER_DB_PATH", str(database_paths["customers"]))
    monkeypatch.setattr(backup_service, "USER_DB_PATH", str(database_paths["users"]))
    monkeypatch.setattr(backup_service, "BACKUP_DIR", backup_dir)

    admin_headers = get_auth_header("admin_test", "AdminSecret@123")
    
    health_resp = client.get("/api/admin/backup/health", headers=admin_headers)
    assert health_resp.status_code == 200
    h_data = health_resp.json()
    assert "integrity_check" in h_data
    assert "table_row_counts" in h_data
    
    # Create backup
    backup_resp = client.post("/api/admin/backup/create", headers=admin_headers, json={"note": "Automated test backup"})
    assert backup_resp.status_code == 200
    b_data = backup_resp.json()
    assert b_data["status"] == "success"
    assert "backup_filename" in b_data["backup"]
    assert b_data["backup"]["size_bytes"] > 0
    assert {snapshot["database"] for snapshot in b_data["backup"]["related_backups"]} == {
        "customers",
        "users",
    }
    snapshots = [b_data["backup"], *b_data["backup"]["related_backups"]]
    for snapshot in snapshots:
        database_path = database_paths[snapshot["database"]]
        with sqlite3.connect(database_path) as connection:
            connection.execute("INSERT INTO backup_test DEFAULT VALUES")
        restore_resp = client.post(
            "/api/admin/backup/restore",
            headers=admin_headers,
            json={
                "backup_filename": snapshot["backup_filename"],
                "confirm_text": "CONFIRM_RESTORE",
            },
        )
        assert restore_resp.status_code == 200, restore_resp.text
        with sqlite3.connect(database_path) as connection:
            assert connection.execute("SELECT COUNT(*) FROM backup_test").fetchone()[0] == 0


def test_database_backup_checks_all_sources_before_writing(tmp_path, monkeypatch):
    database_paths = {
        "stocksense": tmp_path / "stocksense.db",
        "customers": tmp_path / "customers.db",
        "users": tmp_path / "users.db",
    }
    for name in ("stocksense", "users"):
        with sqlite3.connect(database_paths[name]):
            pass
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    monkeypatch.setattr(backup_service, "get_db_file_path", lambda: database_paths["stocksense"])
    monkeypatch.setattr(backup_service, "CUSTOMER_DB_PATH", str(database_paths["customers"]))
    monkeypatch.setattr(backup_service, "USER_DB_PATH", str(database_paths["users"]))
    monkeypatch.setattr(backup_service, "BACKUP_DIR", backup_dir)

    with TestingSessionLocal() as db:
        with pytest.raises(FileNotFoundError, match="customers database"):
            backup_service.create_database_backup(db)

    assert list(backup_dir.iterdir()) == []
