import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from backend.app.database import Base, get_customer_db, get_db, get_user_db
from backend.app.main import app
from backend.app.models import Product, Supplier, Sale, PurchaseOrder
from backend.app.services.reorder import calculate_product_reorder
from backend.app.services.forecasting import run_14_day_moving_average_forecast, backtest_product_models
from backend.app.services.accuracy import calculate_mae, calculate_wape, calculate_portfolio_metrics

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

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_environment():
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_customer_db] = override_get_db
    app.dependency_overrides[get_user_db] = override_get_db
    db = TestingSessionLocal()
    sup = Supplier(supplier_id="SUP_A", supplier_name="Alpha Foods Ltd")
    db.add(sup)

    # Standard product
    p1 = Product(
        product_id="P_RICE",
        barcode="8909990001",
        sku="SKU-RICE-01",
        product_name="Premium Basmati Rice",
        category="Staples",
        purchase_price=60.0,
        selling_price=90.0,
        current_stock=10.0,
        supplier_id="SUP_A",
        supplier_lead_time_days=3,
        supplier_pack_size=5,
        minimum_order_qty=15,
        reorder_safety_stock_days=2,
        shelf_life_days=365,
        perishable=False
    )
    # Perishable product
    p2 = Product(
        product_id="P_MILK",
        barcode="8909990002",
        sku="SKU-MILK-01",
        product_name="Fresh Farm Milk",
        category="Dairy",
        purchase_price=25.0,
        selling_price=35.0,
        current_stock=5.0,
        supplier_id="SUP_A",
        supplier_lead_time_days=1,
        supplier_pack_size=10,
        minimum_order_qty=10,
        reorder_safety_stock_days=1,
        shelf_life_days=3,
        perishable=True
    )
    db.add(p1)
    db.add(p2)

    # Add historical sales for P_RICE over 30 days
    import datetime
    base_dt = datetime.date(2026, 9, 1)
    for day in range(30):
        sale_dt = (base_dt + datetime.timedelta(days=day)).strftime("%Y-%m-%d")
        s = Sale(
            sale_id=f"SALE_TEST_{day:03d}",
            sale_date=sale_dt,
            customer_name="Walk-in",
            product_id="P_RICE",
            quantity_sold=10.0,
            unit_selling_price=90.0,
            line_total=900.0,
            unit_cost=60.0,
            gross_profit_estimate=300.0,
            payment_method="UPI",
            transaction_status="Completed"
        )
        db.add(s)

    db.commit()
    db.close()
    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_customer_db, None)
    app.dependency_overrides.pop(get_user_db, None)
    Base.metadata.drop_all(bind=test_engine)


def test_product_crud_lifecycle():
    # 1. Create product
    new_prod = {
        "product_id": "P_SNACK",
        "barcode": "8908880001",
        "sku": "SKU-SNACK",
        "product_name": "Crunchy Chips",
        "category": "Snacks",
        "purchase_price": 15.0,
        "selling_price": 25.0,
        "current_stock": 50.0,
        "supplier_id": "SUP_A",
        "supplier_pack_size": 12,
        "minimum_order_qty": 24
    }
    res = client.post("/api/products", json=new_prod)
    assert res.status_code == 201
    assert res.json()["product_name"] == "Crunchy Chips"

    # 2. Get product
    res = client.get("/api/products/P_SNACK")
    assert res.status_code == 200
    assert res.json()["current_stock"] == 50.0

    # 3. Patch product
    patch_res = client.patch("/api/products/P_SNACK", json={"selling_price": 30.0, "current_stock": 45.0})
    assert patch_res.status_code == 200
    assert patch_res.json()["selling_price"] == 30.0
    assert patch_res.json()["current_stock"] == 45.0

    # 4. Delete (archive) product
    del_res = client.delete("/api/products/P_SNACK")
    assert del_res.status_code == 200

    # Archived product should not appear in active product list
    list_res = client.get("/api/products")
    ids = [p["product_id"] for p in list_res.json()]
    assert "P_SNACK" not in ids


def test_purchase_order_flow_increases_stock_only_upon_receipt():
    # Create PO
    po_payload = {
        "supplier_id": "SUP_A",
        "order_date": "2026-09-25",
        "items": [
            {
                "product_id": "P_RICE",
                "quantity_ordered": 20.0,
                "unit_cost": 60.0
            }
        ]
    }
    po_res = client.post("/api/purchase-orders", json=po_payload)
    assert po_res.status_code == 201
    po_data = po_res.json()
    po_id = po_data["po_id"]
    assert po_data["status"] == "ORDERED"

    # Verify inventory was NOT yet increased
    p_res = client.get("/api/products/P_RICE")
    assert p_res.json()["current_stock"] == 10.0

    # Receive PO
    receive_res = client.post(f"/api/purchase-orders/{po_id}/receive", json={"received_date": "2026-09-28"})
    assert receive_res.status_code == 200
    assert receive_res.json()["status"] == "RECEIVED"

    # Verify inventory was atomically increased by 20 (10 -> 30)
    p_res_after = client.get("/api/products/P_RICE")
    assert p_res_after.json()["current_stock"] == 30.0


def test_reorder_pack_size_and_moq_rounding():
    db = TestingSessionLocal()
    product = db.query(Product).filter(Product.product_id == "P_RICE").first()
    # P_RICE has current stock 30, lead time 3, daily demand ~10. Lead time demand ~30.
    # Set current stock low to trigger reorder
    product.current_stock = 5.0
    rec = calculate_product_reorder(db, product, z_score=1.65, as_of_date="2026-09-30")

    # Suggested order qty must respect pack size (5) and MOQ (15)
    suggested = rec["suggested_order_quantity"]
    assert suggested >= 15
    assert suggested % 5 == 0
    db.close()


def test_reorder_perishable_shelf_life_constraint():
    db = TestingSessionLocal()
    milk = db.query(Product).filter(Product.product_id == "P_MILK").first()
    rec = calculate_product_reorder(db, milk, z_score=1.65, as_of_date="2026-09-30")
    # Perishable product has shelf_life_days=3
    assert rec["perishable"] is True
    assert rec["shelf_life_days"] == 3
    db.close()


def test_smart_import_preview_and_commit():
    text_data = """
    Maggi Noodles 4-pack, 12, 40, 55, 8901234444555, Snacks
    Amul Butter 100g, 20, 50, 60, 8901234444666, Dairy
    """
    res = client.post("/api/imports/preview-text", json={"raw_text": text_data, "target_type": "products"})
    assert res.status_code == 200
    preview = res.json()
    assert preview["total_extracted"] == 2
    records = preview["records"]
    assert records[0]["current_stock"] == 12.0
    assert records[1]["current_stock"] == 20.0

    # Commit imported rows
    commit_payload = {
        "file_name": "whatsapp_supplier_bill.txt",
        "target_type": "products",
        "records": records
    }
    commit_res = client.post("/api/imports/commit", json=commit_payload)
    assert commit_res.status_code == 200
    assert commit_res.json()["imported_count"] == 2

    # Check imported product in DB
    p_check = client.get("/api/products/P_IMP_001")
    assert p_check.status_code == 200
    assert p_check.json()["product_name"] == "Maggi Noodles 4-pack"


def test_duplicate_import_detection():
    # Attempt to import an existing product name or barcode
    text_data = "Premium Basmati Rice, 50, 60, 90, 8909990001, Staples"
    res = client.post("/api/imports/preview-text", json={"raw_text": text_data, "target_type": "products"})
    assert res.status_code == 200
    rec = res.json()["records"][0]
    assert rec["is_duplicate"] is True
    assert "already assigned" in rec["duplicate_reason"] or "already exists" in rec["duplicate_reason"]


def test_forecast_accuracy_backtest_endpoint():
    req_payload = {
        "evaluation_window_days": 14,
        "compare_advanced_model": True
    }
    res = client.post("/api/forecast-accuracy/backtest", json=req_payload)
    assert res.status_code == 200
    data = res.json()
    assert "baseline_portfolio" in data
    assert data["baseline_portfolio"]["mae"] is not None
    assert "total_observations_evaluated" in data
    assert data["total_observations_evaluated"] > 0


def test_reports_endpoints():
    csv_res = client.get("/api/reports/inventory.csv")
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers["content-type"]
    assert "Product ID" in csv_res.text

    xlsx_res = client.get("/api/reports/inventory.xlsx")
    assert xlsx_res.status_code == 200
    assert "application/vnd.openxmlformats" in xlsx_res.headers["content-type"]

    acc_csv = client.get("/api/reports/forecast-accuracy.csv")
    assert acc_csv.status_code == 200
    assert "Baseline MAE" in acc_csv.text

    acc_xlsx = client.get("/api/reports/forecast-accuracy.xlsx")
    assert acc_xlsx.status_code == 200
    assert "application/vnd.openxmlformats" in acc_xlsx.headers["content-type"]
