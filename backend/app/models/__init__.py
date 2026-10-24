import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Index, Text
)
from sqlalchemy.orm import relationship
from ..database import Base

class Supplier(Base):
    __tablename__ = "suppliers"

    supplier_id = Column(String(50), primary_key=True)
    supplier_name = Column(String(200), nullable=False)
    product_specialty = Column(String(200))
    typical_delivery_time = Column(String(100), default="2-3 days")
    payment_terms = Column(String(100), default="Net 15")
    contact_phone_demo = Column(String(50))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    products = relationship("Product", back_populates="supplier")
    purchase_orders = relationship("PurchaseOrder", back_populates="supplier")


class Product(Base):
    __tablename__ = "products"

    product_id = Column(String(50), primary_key=True)
    barcode = Column(String(100), unique=True, index=True, nullable=True)
    sku = Column(String(100), unique=True, index=True, nullable=True)
    product_name = Column(String(200), nullable=False, index=True)
    category = Column(String(100), nullable=False, index=True)
    brand = Column(String(100), default="Generic")
    unit = Column(String(50), default="pack")
    purchase_price = Column(Float, nullable=False, default=0.0)
    selling_price = Column(Float, nullable=False, default=0.0)
    current_stock = Column(Float, nullable=False, default=0.0)
    supplier_id = Column(String(50), ForeignKey("suppliers.supplier_id"), nullable=True)
    supplier_lead_time_days = Column(Integer, default=2)
    shelf_life_days = Column(Integer, default=90)
    supplier_pack_size = Column(Integer, default=1)
    minimum_order_qty = Column(Integer, default=1)
    reorder_safety_stock_days = Column(Integer, default=2)
    storage_capacity_units = Column(Integer, default=100)
    perishable = Column(Boolean, default=False)
    is_archived = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    supplier = relationship("Supplier", back_populates="products")
    sales = relationship("Sale", back_populates="product")
    movements = relationship("InventoryMovement", back_populates="product")
    lots = relationship("InventoryLot", back_populates="product")


class Sale(Base):
    __tablename__ = "sales"

    sale_id = Column(String(50), primary_key=True)
    sale_date = Column(String(20), nullable=False, index=True)  # YYYY-MM-DD
    customer_id = Column(String(50), nullable=True)
    customer_name = Column(String(200), default="Walk-in Customer")
    product_id = Column(String(50), ForeignKey("products.product_id"), nullable=False, index=True)
    quantity_sold = Column(Float, nullable=False)
    unit_selling_price = Column(Float, nullable=False)
    line_total = Column(Float, nullable=False)
    unit_cost = Column(Float, nullable=False, default=0.0)
    gross_profit_estimate = Column(Float, nullable=False, default=0.0)
    payment_method = Column(String(50), default="UPI")
    transaction_status = Column(String(50), default="Completed", index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    product = relationship("Product", back_populates="sales")


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(String(50), ForeignKey("products.product_id"), nullable=False, index=True)
    movement_type = Column(String(50), nullable=False, index=True)  # 'SALE', 'STOCK_IN', 'STOCK_OUT', 'ADJUSTMENT', 'PO_RECEIPT'
    quantity_change = Column(Float, nullable=False)  # positive or negative
    previous_stock = Column(Float, nullable=False)
    new_stock = Column(Float, nullable=False)
    reason = Column(String(255), nullable=True)
    reference_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    product = relationship("Product", back_populates="movements")


class InventoryLot(Base):
    __tablename__ = "inventory_lots"

    lot_id = Column(String(50), primary_key=True)
    product_id = Column(String(50), ForeignKey("products.product_id"), nullable=False, index=True)
    supplier_id = Column(String(50), ForeignKey("suppliers.supplier_id"), nullable=True)
    received_date = Column(String(20), nullable=False)
    expiry_date = Column(String(20), nullable=False, index=True)
    quantity_received = Column(Float, nullable=False)
    quantity_remaining = Column(Float, nullable=False)
    unit_cost = Column(Float, nullable=False, default=0.0)
    disposition_note = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    product = relationship("Product", back_populates="lots")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    po_id = Column(String(50), primary_key=True)
    po_number = Column(String(50), unique=True, nullable=False, index=True)
    supplier_id = Column(String(50), ForeignKey("suppliers.supplier_id"), nullable=False)
    order_date = Column(String(20), nullable=False)
    status = Column(String(50), default="DRAFT", index=True)  # 'DRAFT', 'ORDERED', 'RECEIVED', 'CANCELLED'
    total_amount = Column(Float, default=0.0)
    expected_delivery_date = Column(String(20), nullable=True)
    received_date = Column(String(20), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    supplier = relationship("Supplier", back_populates="purchase_orders")
    items = relationship("PurchaseOrderItem", back_populates="purchase_order", cascade="all, delete-orphan")


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    po_id = Column(String(50), ForeignKey("purchase_orders.po_id"), nullable=False, index=True)
    product_id = Column(String(50), ForeignKey("products.product_id"), nullable=False)
    quantity_ordered = Column(Float, nullable=False)
    quantity_received = Column(Float, default=0.0)
    unit_cost = Column(Float, nullable=False)
    subtotal = Column(Float, nullable=False)

    purchase_order = relationship("PurchaseOrder", back_populates="items")
    product = relationship("Product")


class ForecastRecord(Base):
    __tablename__ = "forecast_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(String(50), ForeignKey("products.product_id"), nullable=False, index=True)
    forecast_date = Column(String(20), nullable=False, index=True)  # When forecast was made
    target_date = Column(String(20), nullable=False, index=True)    # Target prediction date
    predicted_demand = Column(Float, nullable=False)
    model_name = Column(String(100), default="14_DAY_MOVING_AVERAGE")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class ForecastEvaluation(Base):
    __tablename__ = "forecast_evaluations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_name = Column(String(100), nullable=False)
    evaluation_date = Column(String(20), nullable=False)
    period_start = Column(String(20), nullable=False)
    period_end = Column(String(20), nullable=False)
    product_id = Column(String(50), ForeignKey("products.product_id"), nullable=True, index=True)  # Null if portfolio
    n_observations = Column(Integer, nullable=False)
    mae = Column(Float, nullable=False)
    wape = Column(Float, nullable=True)  # None if total actual sales is 0
    actual_sum = Column(Float, nullable=False)
    error_sum = Column(Float, nullable=False)
    is_portfolio = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(String(100), nullable=False)
    entity = Column(String(100), nullable=False)
    entity_id = Column(String(100), nullable=True)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)


class ImportRecord(Base):
    __tablename__ = "import_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_name = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)
    target_type = Column(String(50), nullable=False)
    rows_imported = Column(Integer, nullable=False, default=0)
    status = Column(String(50), default="SUCCESS")
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


# Auth, Rural Data, and Offline Sync Models
from .auth import (
    User,
    UserSession,
    AuditLogV2,
    OfflineSyncQueue,
    NotebookImport,
    StockCount,
)


class Customer(Base):
    __tablename__ = "customers"

    customer_id = Column(String(50), primary_key=True)
    customer_name = Column(String(200), nullable=False, index=True)
    phone = Column(String(50), nullable=True, index=True)
    email = Column(String(200), nullable=True)
    city = Column(String(100), default="Local Store Area")
    loyalty_tier = Column(String(50), default="Silver")  # Bronze, Silver, Gold, VIP
    total_spent = Column(Float, default=0.0)
    total_purchases_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    purchases = relationship("CustomerPurchase", back_populates="customer")


class CustomerPurchase(Base):
    """Customer purchases made via Barcode Scan (camera or handheld) with full details."""
    __tablename__ = "customer_purchases"

    purchase_id = Column(String(50), primary_key=True)
    customer_id = Column(String(50), ForeignKey("customers.customer_id"), nullable=False, index=True)
    customer_name = Column(String(200), nullable=False)
    product_id = Column(String(50), nullable=False, index=True)
    product_name = Column(String(200), nullable=False)
    barcode = Column(String(100), nullable=True, index=True)
    category = Column(String(100), default="General")
    quantity = Column(Float, nullable=False, default=1.0)
    rate = Column(Float, nullable=False)  # Selling price / rate per unit
    total_amount = Column(Float, nullable=False)
    payment_method = Column(String(50), default="UPI")  # UPI, Cash, Card
    scan_source = Column(String(50), default="CAMERA_SCAN")  # CAMERA_SCAN, USB_SCAN, MANUAL_INPUT
    purchase_date = Column(String(20), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    customer = relationship("Customer", back_populates="purchases")


class UserPurchase(Base):
    """User (Store Staff/Manager/Admin) procurement purchases from wholesale/suppliers."""
    __tablename__ = "user_purchases"

    user_purchase_id = Column(String(50), primary_key=True)
    user_id = Column(Integer, nullable=True)
    user_name = Column(String(100), nullable=False, default="Store Admin")
    product_id = Column(String(50), nullable=False, index=True)
    product_name = Column(String(200), nullable=False)
    supplier_id = Column(String(50), nullable=True)
    supplier_name = Column(String(200), nullable=True)
    quantity_bought = Column(Float, nullable=False)
    purchase_rate = Column(Float, nullable=False)  # Wholesale Cost Rate per unit
    suggested_selling_rate = Column(Float, nullable=False)  # Configured Retail Rate
    total_cost = Column(Float, nullable=False)
    invoice_number = Column(String(100), nullable=True)
    payment_status = Column(String(50), default="PAID")
    purchase_date = Column(String(20), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)



class PriceRateHistory(Base):
    """Audit log of product price/rate modifications in SQLite."""
    __tablename__ = "price_rate_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(String(50), ForeignKey("products.product_id"), nullable=False, index=True)
    product_name = Column(String(200), nullable=False)
    old_purchase_price = Column(Float, nullable=False)
    new_purchase_price = Column(Float, nullable=False)
    old_selling_price = Column(Float, nullable=False)
    new_selling_price = Column(Float, nullable=False)
    modified_by = Column(String(100), default="Admin User")
    reason = Column(String(255), default="Rate update")
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    product = relationship("Product")
