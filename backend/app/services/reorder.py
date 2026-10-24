"""
StockSense Smart Reorder Engine
Implements Section 8 of the master prompt with safety stock formula:
SS = z * sigma_demand * sqrt(lead_time), pack rounding, MOQ, and shelf-life constraints.
"""
from typing import List, Dict, Any, Optional
import math
import numpy as np
from sqlalchemy.orm import Session
from ..models import Product, Sale, InventoryLot, PurchaseOrder, PurchaseOrderItem
from ..config import DEFAULT_SERVICE_LEVEL_Z, DEFAULT_AS_OF_DATE, DEFAULT_EXPIRY_BUFFER_DAYS
from .forecasting import get_product_daily_sales_series

def calculate_product_reorder(
    db: Session,
    product: Product,
    z_score: float = DEFAULT_SERVICE_LEVEL_Z,
    as_of_date: str = DEFAULT_AS_OF_DATE,
    expiry_buffer_days: int = DEFAULT_EXPIRY_BUFFER_DAYS
) -> Dict[str, Any]:
    # 1. Sales series over the latest 90 days
    series = get_product_daily_sales_series(db, product.product_id, as_of_date=as_of_date, days_back=90)
    units_series = [s["units"] for s in series]

    total_units_sold = sum(units_series)
    n_days = max(1, len(units_series))
    daily_demand = round(total_units_sold / n_days, 2) if n_days > 0 else 0.0

    lead_time = max(1, product.supplier_lead_time_days or 2)
    lead_time_demand = round(daily_demand * lead_time, 2)

    # 2. Safety Stock Calculation
    # Formula: SS = z * std_dev * sqrt(lead_time)
    if len(units_series) >= 14 and daily_demand > 0:
        std_dev = float(np.std(units_series))
        safety_stock = round(z_score * std_dev * math.sqrt(lead_time), 2)
    else:
        # Fallback to configured safety days if history is scarce
        safety_days = product.reorder_safety_stock_days or 2
        safety_stock = round(daily_demand * safety_days, 2)

    reorder_point = round(lead_time_demand + safety_stock, 2)

    # 3. Usable Stock (Excluding Expired Lots as of as_of_date)
    lots = db.query(InventoryLot).filter(InventoryLot.product_id == product.product_id).all()
    expired_qty = 0.0
    for lot in lots:
        if lot.expiry_date <= as_of_date:
            expired_qty += lot.quantity_remaining

    # Usable physical stock
    usable_stock = max(0.0, float(product.current_stock or 0.0))

    # 4. Incoming Confirmed Purchase Orders (Status: 'ORDERED')
    incoming_pos = db.query(PurchaseOrderItem).join(PurchaseOrder).filter(
        PurchaseOrderItem.product_id == product.product_id,
        PurchaseOrder.status == "ORDERED"
    ).all()
    incoming_stock = sum(item.quantity_ordered - item.quantity_received for item in incoming_pos)

    # 5. Raw Shortage
    raw_order_qty = max(0.0, reorder_point - usable_stock - incoming_stock)

    # 6. Supplier Pack Size Rounding
    pack_size = max(1, product.supplier_pack_size or 1)
    if raw_order_qty > 0 and pack_size > 1:
        raw_order_qty = math.ceil(raw_order_qty / pack_size) * pack_size

    # 7. Minimum Order Quantity (MOQ)
    moq = max(1, product.minimum_order_qty or 1)
    if raw_order_qty > 0 and raw_order_qty < moq:
        raw_order_qty = math.ceil(moq / pack_size) * pack_size

    # 8. Perishable Shelf-Life Cap
    shelf_life_warning = False
    shelf_life_cap = None
    if product.perishable:
        effective_shelf_life = max((product.shelf_life_days or 7) - expiry_buffer_days, 1)
        shelf_life_cap = round(daily_demand * effective_shelf_life, 2)

        if lead_time >= (product.shelf_life_days or 7):
            shelf_life_warning = True

        if raw_order_qty + usable_stock > shelf_life_cap and daily_demand > 0:
            max_allowed_order = max(0.0, shelf_life_cap - usable_stock)
            if max_allowed_order < moq:
                shelf_life_warning = True  # Conflict: MOQ exceeds shelf-life demand
            else:
                raw_order_qty = math.floor(max_allowed_order / pack_size) * pack_size

    # 9. Storage Capacity Limit
    storage_capacity = max(1, product.storage_capacity_units or 100)
    available_capacity = max(0.0, storage_capacity - usable_stock)
    suggested_order_qty = raw_order_qty
    capacity_status = "NORMAL"
    capacity_message = None

    if raw_order_qty > 0:
        if available_capacity <= 0:
            suggested_order_qty = 0.0
            capacity_status = "FULL"
            capacity_message = "Capacity full — no reorder possible"
        elif raw_order_qty > available_capacity:
            suggested_order_qty = math.floor(available_capacity / pack_size) * pack_size
            capacity_status = "CONSTRAINED"
            capacity_message = f"Capped to available storage ({available_capacity} units)"

    # Handle new products with zero sales (REVIEW state)
    has_no_history = total_units_sold == 0
    if has_no_history and usable_stock == 0:
        suggested_order_qty = max(pack_size, moq)

    # 10. Financials
    purchase_price = float(product.purchase_price or 0.0)
    selling_price = float(product.selling_price or 0.0)
    unit_profit = max(0.0, selling_price - purchase_price)
    estimated_order_cost = round(suggested_order_qty * purchase_price, 2)
    expected_gross_profit = round(suggested_order_qty * unit_profit, 2)

    # 11. Urgency & Ranking
    days_stock_left = round(usable_stock / daily_demand, 1) if daily_demand > 0 else (999.0 if usable_stock > 0 else 0.0)

    if has_no_history:
        urgency = "REVIEW"
    elif usable_stock < lead_time_demand:
        urgency = "CRITICAL"
    elif usable_stock < reorder_point:
        urgency = "LOW"
    else:
        urgency = "OK"

    stockout_risk = round(lead_time_demand / max(usable_stock, 1.0), 3)
    profit_score = round(unit_profit * daily_demand, 3)
    rank_score = round(stockout_risk * profit_score, 2)

    if urgency == "CRITICAL":
        rank_score += 1000.0
    elif urgency == "LOW":
        rank_score += 500.0
    elif urgency == "REVIEW":
        rank_score = 10.0

    # 12. Explanation Generation
    explanation = (
        f"Daily demand {daily_demand}/d × {lead_time}d lead time = {lead_time_demand} LTD. "
        f"Safety stock: {safety_stock} units (z={z_score}). Reorder point = {reorder_point}. "
        f"Usable stock: {usable_stock}, incoming: {incoming_stock}. Pack size: {pack_size}, MOQ: {moq}. "
        f"Recommended order: {suggested_order_qty} units."
    )

    return {
        "product_id": product.product_id,
        "product_name": product.product_name,
        "category": product.category,
        "urgency": urgency,
        "daily_demand": daily_demand,
        "supplier_lead_time_days": lead_time,
        "days_of_stock_left": days_stock_left,
        "current_stock": float(product.current_stock or 0.0),
        "usable_stock": usable_stock,
        "safety_stock": safety_stock,
        "reorder_point": reorder_point,
        "suggested_order_quantity": suggested_order_qty,
        "supplier_pack_size": pack_size,
        "minimum_order_qty": moq,
        "storage_capacity_units": storage_capacity,
        "purchase_price": purchase_price,
        "estimated_order_cost": estimated_order_cost,
        "expected_gross_profit": expected_gross_profit,
        "supplier_id": product.supplier_id,
        "supplier_name": product.supplier.supplier_name if product.supplier else "General Supplier",
        "capacity_status": capacity_status,
        "capacity_message": capacity_message,
        "shelf_life_warning": shelf_life_warning,
        "perishable": bool(product.perishable),
        "shelf_life_days": product.shelf_life_days,
        "rank_score": rank_score,
        "explanation": explanation
    }


def get_all_reorder_recommendations(
    db: Session,
    z_score: float = DEFAULT_SERVICE_LEVEL_Z,
    as_of_date: str = DEFAULT_AS_OF_DATE
) -> List[Dict[str, Any]]:
    products = db.query(Product).filter(Product.is_archived == False).all()
    recommendations = [
        calculate_product_reorder(db, p, z_score=z_score, as_of_date=as_of_date)
        for p in products
    ]
    recommendations.sort(key=lambda x: x["rank_score"], reverse=True)
    for idx, item in enumerate(recommendations, start=1):
        item["rank"] = idx
    return recommendations
