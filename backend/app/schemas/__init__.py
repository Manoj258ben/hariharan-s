from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
import datetime

# --- Product Schemas ---
class ProductBase(BaseModel):
    product_name: str
    category: str
    brand: Optional[str] = "Generic"
    unit: Optional[str] = "pack"
    purchase_price: float = Field(ge=0.0)
    selling_price: float = Field(ge=0.0)
    current_stock: float = Field(default=0.0, ge=0.0)
    barcode: Optional[str] = None
    sku: Optional[str] = None
    supplier_id: Optional[str] = None
    supplier_lead_time_days: Optional[int] = 2
    shelf_life_days: Optional[int] = 90
    supplier_pack_size: Optional[int] = 1
    minimum_order_qty: Optional[int] = 1
    reorder_safety_stock_days: Optional[int] = 2
    storage_capacity_units: Optional[int] = 100
    perishable: Optional[bool] = False

class ProductCreate(ProductBase):
    product_id: str

class ProductUpdate(BaseModel):
    product_name: Optional[str] = None
    category: Optional[str] = None
    brand: Optional[str] = None
    unit: Optional[str] = None
    purchase_price: Optional[float] = Field(default=None, ge=0.0)
    selling_price: Optional[float] = Field(default=None, ge=0.0)
    current_stock: Optional[float] = Field(default=None, ge=0.0)
    barcode: Optional[str] = None
    sku: Optional[str] = None
    supplier_id: Optional[str] = None
    supplier_lead_time_days: Optional[int] = None
    shelf_life_days: Optional[int] = None
    supplier_pack_size: Optional[int] = None
    minimum_order_qty: Optional[int] = None
    reorder_safety_stock_days: Optional[int] = None
    storage_capacity_units: Optional[int] = None
    perishable: Optional[bool] = None

class ProductResponse(ProductBase):
    product_id: str
    is_archived: bool
    created_at: Optional[datetime.datetime] = None
    updated_at: Optional[datetime.datetime] = None
    supplier_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

# --- Inventory Operations ---
class StockAdjustmentRequest(BaseModel):
    product_id: str
    quantity: float = Field(description="Quantity to add/subtract or new absolute level")
    movement_type: str = Field(description="'STOCK_IN', 'STOCK_OUT', 'ADJUSTMENT'")
    reason: Optional[str] = "Manual operational update"
    reference_id: Optional[str] = None

class StockMovementResponse(BaseModel):
    id: int
    product_id: str
    movement_type: str
    quantity_change: float
    previous_stock: float
    new_stock: float
    reason: Optional[str]
    created_at: datetime.datetime

# --- Sales Schemas ---
class SaleCreate(BaseModel):
    product_id: str
    quantity_sold: float = Field(gt=0.0)
    unit_selling_price: Optional[float] = None
    customer_name: Optional[str] = "Counter Customer"
    payment_method: Optional[str] = "UPI"
    sale_date: Optional[str] = None  # YYYY-MM-DD, defaults to Today

class SaleResponse(BaseModel):
    sale_id: str
    sale_date: str
    product_id: str
    product_name: Optional[str] = None
    quantity_sold: float
    unit_selling_price: float
    line_total: float
    unit_cost: float
    gross_profit_estimate: float
    payment_method: str
    transaction_status: str

# --- Purchase Order Schemas ---
class POItemCreate(BaseModel):
    product_id: str
    quantity_ordered: float = Field(gt=0.0)
    unit_cost: float = Field(ge=0.0)

class POCreate(BaseModel):
    supplier_id: str
    order_date: Optional[str] = None
    expected_delivery_date: Optional[str] = None
    notes: Optional[str] = None
    items: List[POItemCreate]

class POItemResponse(BaseModel):
    id: int
    product_id: str
    product_name: Optional[str] = None
    quantity_ordered: float
    quantity_received: float
    unit_cost: float
    subtotal: float

class POResponse(BaseModel):
    po_id: str
    po_number: str
    supplier_id: str
    supplier_name: Optional[str] = None
    order_date: str
    status: str
    total_amount: float
    expected_delivery_date: Optional[str]
    received_date: Optional[str]
    notes: Optional[str]
    items: List[POItemResponse] = []

class POReceiveRequest(BaseModel):
    received_date: Optional[str] = None
    lot_id: Optional[str] = None
    expiry_date: Optional[str] = None

# --- Forecast & Accuracy Schemas ---
class ForecastRunRequest(BaseModel):
    model_name: Optional[str] = "14_DAY_MOVING_AVERAGE"  # or "RANDOM_FOREST"
    horizon_days: Optional[int] = 14
    product_ids: Optional[List[str]] = None

class ForecastPoint(BaseModel):
    date: str
    predicted_demand: float
    model_name: str

class ProductForecastResult(BaseModel):
    product_id: str
    product_name: str
    category: str
    current_stock: float
    daily_average_demand: float
    demand_stability: str
    selected_model: str
    forecast_points: List[ForecastPoint]
    total_7_day_demand: float
    total_14_day_demand: float

class BacktestRequest(BaseModel):
    evaluation_window_days: Optional[int] = 14
    compare_advanced_model: Optional[bool] = True

class ModelAccuracyMetric(BaseModel):
    model_name: str
    n_observations: int
    mae: float
    wape: Optional[float]
    total_actual: float
    total_error: float
    plain_language_explanation: str

class ProductAccuracyDetail(BaseModel):
    product_id: str
    product_name: str
    category: str
    n_observations: int
    actual_units: float
    baseline_mae: float
    baseline_wape: Optional[float]
    advanced_mae: Optional[float] = None
    advanced_wape: Optional[float] = None
    winning_model: str

class AccuracySummaryResponse(BaseModel):
    evaluation_period_start: str
    evaluation_period_end: str
    total_observations_evaluated: int
    baseline_portfolio: ModelAccuracyMetric
    advanced_portfolio: Optional[ModelAccuracyMetric] = None
    product_metrics: List[ProductAccuracyDetail]

# --- Reorder Recommendation Schemas ---
class ReorderRecommendationItem(BaseModel):
    rank: int
    product_id: str
    product_name: str
    category: str
    urgency: str
    daily_demand: float
    supplier_lead_time_days: int
    days_of_stock_left: float
    current_stock: float
    usable_stock: float
    safety_stock: float
    reorder_point: float
    suggested_order_quantity: float
    supplier_pack_size: int
    minimum_order_qty: int
    storage_capacity_units: int
    purchase_price: float
    estimated_order_cost: float
    expected_gross_profit: float
    supplier_id: Optional[str]
    supplier_name: Optional[str]
    capacity_status: str
    capacity_message: Optional[str]
    shelf_life_warning: bool
    explanation: str

# --- Import & Conversion Schemas ---
class TextConvertRequest(BaseModel):
    raw_text: str
    target_type: Optional[str] = "products"  # "products", "sales", "lots"

class ColumnMapping(BaseModel):
    source_column: str
    target_field: str

class ImportCommitRequest(BaseModel):
    file_name: str
    target_type: str
    records: List[Dict[str, Any]]

# --- Customer & User Database Schemas ---
class ProductRateModifyRequest(BaseModel):
    new_selling_price: Optional[float] = Field(default=None, ge=0.0, description="New retail selling rate per unit")
    selling_price: Optional[float] = Field(default=None, ge=0.0, description="Alias for new retail selling rate")
    new_purchase_price: Optional[float] = Field(default=None, ge=0.0, description="New wholesale cost rate per unit")
    purchase_price: Optional[float] = Field(default=None, ge=0.0, description="Alias for wholesale cost rate")
    reason: Optional[str] = "Market price revision"
    modified_by: Optional[str] = "Admin User"

class CustomerCreate(BaseModel):
    customer_id: Optional[str] = None
    customer_name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    city: Optional[str] = "Local Area"
    loyalty_tier: Optional[str] = "Silver"

class CustomerResponse(BaseModel):
    customer_id: str
    customer_name: str
    phone: Optional[str]
    email: Optional[str]
    city: Optional[str]
    loyalty_tier: str
    total_spent: float
    total_purchases_count: int
    created_at: Optional[datetime.datetime]

    model_config = ConfigDict(from_attributes=True)

class CustomerPurchaseCreate(BaseModel):
    customer_id: str
    product_id: Optional[str] = None
    barcode: Optional[str] = None
    quantity: float = Field(gt=0.0, default=1.0)
    rate: Optional[float] = None
    payment_method: Optional[str] = "UPI"
    scan_source: Optional[str] = "CAMERA_SCAN"  # CAMERA_SCAN, USB_SCAN, MANUAL_INPUT
    purchase_date: Optional[str] = None

class CustomerPurchaseResponse(BaseModel):
    purchase_id: str
    customer_id: str
    customer_name: str
    product_id: str
    product_name: str
    barcode: Optional[str]
    category: str
    quantity: float
    rate: float
    total_amount: float
    payment_method: str
    scan_source: str
    purchase_date: str
    created_at: Optional[datetime.datetime]

    model_config = ConfigDict(from_attributes=True)

class UserPurchaseCreate(BaseModel):
    user_name: Optional[str] = "Store Admin"
    product_id: str
    supplier_id: Optional[str] = None
    quantity_bought: float = Field(gt=0.0)
    purchase_rate: float = Field(ge=0.0)
    suggested_selling_rate: float = Field(ge=0.0)
    invoice_number: Optional[str] = None
    payment_status: Optional[str] = "PAID"
    purchase_date: Optional[str] = None
    update_product_rates: Optional[bool] = True

class UserPurchaseResponse(BaseModel):
    user_purchase_id: str
    user_name: str
    product_id: str
    product_name: str
    supplier_id: Optional[str]
    supplier_name: Optional[str]
    quantity_bought: float
    purchase_rate: float
    suggested_selling_rate: float
    total_cost: float
    invoice_number: Optional[str]
    payment_status: str
    purchase_date: str
    created_at: Optional[datetime.datetime]

    model_config = ConfigDict(from_attributes=True)

class PriceRateHistoryResponse(BaseModel):
    id: int
    product_id: str
    product_name: str
    old_purchase_price: float
    new_purchase_price: float
    old_selling_price: float
    new_selling_price: float
    modified_by: str
    reason: str
    timestamp: datetime.datetime

    model_config = ConfigDict(from_attributes=True)
