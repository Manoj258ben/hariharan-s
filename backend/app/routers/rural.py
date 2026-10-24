"""
Rural Kirana Data Collection Router for StockSense.
Designed specifically for small shopkeepers on basic Android mobile devices.
Provides touch-friendly manual entry, voice parsing, handwritten notebook OCR,
physical stock counting, and daily closing workflows.
"""
from typing import List, Optional, Dict, Any
import datetime
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Product, Sale, InventoryMovement, InventoryLot, Supplier
from ..models.auth import User, NotebookImport, StockCount
from ..services.auth import get_optional_current_user, record_audit_log
from ..services.rural_nlp import (
    parse_voice_transcript,
    parse_notebook_raw_text,
    find_best_matching_product,
)
from ..services.reorder import get_all_reorder_recommendations
from ..config import DEFAULT_AS_OF_DATE

router = APIRouter(prefix="/api/rural", tags=["Rural Kirana Data Collection"])


# --- Schemas ---
class ManualSaleRequest(BaseModel):
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    quantity: float = Field(gt=0.0)
    unit_price: Optional[float] = Field(default=None, ge=0.0)
    customer_name: Optional[str] = "Counter Customer"
    payment_method: Optional[str] = "Cash"  # Cash, UPI, Khata (Credit)
    sale_date: Optional[str] = None


class ManualDeliveryRequest(BaseModel):
    product_id: Optional[str] = None
    product_name: str = Field(min_length=1)
    category: Optional[str] = "General"
    quantity: float = Field(gt=0.0)
    purchase_price: float = Field(ge=0.0)
    selling_price: Optional[float] = None
    supplier_name: Optional[str] = "Local Vendor"
    delivery_date: Optional[str] = None
    shelf_life_days: Optional[int] = 90
    perishable: Optional[bool] = False


class VoiceParseRequest(BaseModel):
    transcript: str = Field(min_length=1)


class VoiceItemConfirm(BaseModel):
    action: str  # 'SALE' or 'STOCK_IN'
    product_id: Optional[str] = None
    product_name: str
    quantity: float = Field(gt=0.0)
    unit_price: float = Field(ge=0.0)


class VoiceConfirmRequest(BaseModel):
    items: List[VoiceItemConfirm]
    date: Optional[str] = None


class NotebookParseRequest(BaseModel):
    raw_text: str = Field(min_length=1)
    source_type: Optional[str] = "PHOTO"
    filename: Optional[str] = "notebook_photo.jpg"


class NotebookRowConfirm(BaseModel):
    product_id: Optional[str] = None
    product_name: str
    quantity: float = Field(gt=0.0)
    unit_price: float = Field(ge=0.0)
    date: Optional[str] = None
    notes: Optional[str] = None


class NotebookConfirmRequest(BaseModel):
    session_id: Optional[str] = None
    rows: List[NotebookRowConfirm]


class StockCountCompareRequest(BaseModel):
    product_id: str
    counted_stock: float = Field(ge=0.0)


class StockCountCommitRequest(BaseModel):
    product_id: str
    counted_stock: float = Field(ge=0.0)
    reason: Optional[str] = "Regular Physical Verification"


# --- 1. Mobile-First Manual Sale ---
@router.post("/manual-sale", status_code=status.HTTP_201_CREATED)
def record_manual_sale(
    req: ManualSaleRequest,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    Records a quick counter sale without needing a barcode scanner.
    Selects product by ID or name with validation and atomic stock decrement.
    """
    # 1. Resolve product
    product = None
    if req.product_id:
        product = db.query(Product).filter(Product.product_id == req.product_id).first()
    elif req.product_name:
        match = find_best_matching_product(db, req.product_name)
        if match:
            product = db.query(Product).filter(Product.product_id == match["product_id"]).first()

    if not product:
        raise HTTPException(
            status_code=404,
            detail=f"Product '{req.product_id or req.product_name}' not found. Please select from inventory.",
        )

    current_stk = float(product.current_stock or 0.0)
    if current_stk < req.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Not enough stock! Available: {current_stk} {product.unit}s, trying to sell: {req.quantity}",
        )

    unit_price = req.unit_price if req.unit_price is not None else float(product.selling_price)
    line_total = round(req.quantity * unit_price, 2)
    unit_cost = float(product.purchase_price or 0.0)
    profit = round(line_total - (req.quantity * unit_cost), 2)
    sale_date = req.sale_date or datetime.date.today().strftime("%Y-%m-%d")
    sale_id = f"SALE_MANUAL_{uuid.uuid4().hex[:8].upper()}"

    # Atomic transaction
    sale = Sale(
        sale_id=sale_id,
        sale_date=sale_date,
        customer_name=req.customer_name or "Counter Customer",
        product_id=product.product_id,
        quantity_sold=req.quantity,
        unit_selling_price=unit_price,
        line_total=line_total,
        unit_cost=unit_cost,
        gross_profit_estimate=profit,
        payment_method=req.payment_method or "Cash",
        transaction_status="Completed",
    )
    db.add(sale)

    new_stock = current_stk - req.quantity
    product.current_stock = new_stock

    db.add(InventoryMovement(
        product_id=product.product_id,
        movement_type="SALE",
        quantity_change=-req.quantity,
        previous_stock=current_stk,
        new_stock=new_stock,
        reference_id=sale_id,
        reason=f"Manual mobile counter sale ({req.payment_method})"
    ))

    db.commit()

    record_audit_log(
        db,
        action="MANUAL_SALE",
        entity_type="SALE",
        entity_id=sale_id,
        summary=f"Sold {req.quantity} {product.unit}s of '{product.product_name}' for INR {line_total}.",
        actor_id=current_user.id if current_user else None,
        actor_username=current_user.username if current_user else "Shopkeeper"
    )

    return {
        "status": "success",
        "sale_id": sale_id,
        "product_name": product.product_name,
        "quantity_sold": req.quantity,
        "unit": product.unit,
        "line_total": line_total,
        "new_stock": new_stock,
        "payment_method": req.payment_method,
    }


# --- 2. Mobile-First Manual Stock Delivery ---
@router.post("/manual-delivery", status_code=status.HTTP_201_CREATED)
def record_manual_delivery(
    req: ManualDeliveryRequest,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    Records incoming stock delivery from local suppliers.
    Updates inventory and cost without requiring purchase order complexity.
    """
    product = None
    if req.product_id:
        product = db.query(Product).filter(Product.product_id == req.product_id).first()
    else:
        match = find_best_matching_product(db, req.product_name)
        if match and match["match_confidence"] >= 80:
            product = db.query(Product).filter(Product.product_id == match["product_id"]).first()

    # Create product if it doesn't exist
    if not product:
        new_pid = f"P_RUR_{uuid.uuid4().hex[:6].upper()}"
        product = Product(
            product_id=new_pid,
            product_name=req.product_name.strip(),
            category=req.category or "General",
            brand="Local",
            unit="pack",
            purchase_price=req.purchase_price,
            selling_price=req.selling_price or round(req.purchase_price * 1.25, 2),
            current_stock=0.0,
            shelf_life_days=req.shelf_life_days or 90,
            perishable=bool(req.perishable),
        )
        db.add(product)
        db.flush()

    previous_stock = float(product.current_stock or 0.0)
    new_stock = previous_stock + req.quantity
    product.current_stock = new_stock
    product.purchase_price = req.purchase_price
    if req.selling_price:
        product.selling_price = req.selling_price

    delivery_date = req.delivery_date or datetime.date.today().strftime("%Y-%m-%d")
    movement_id = f"DELIV_{uuid.uuid4().hex[:8].upper()}"

    db.add(InventoryMovement(
        product_id=product.product_id,
        movement_type="STOCK_IN",
        quantity_change=req.quantity,
        previous_stock=previous_stock,
        new_stock=new_stock,
        reference_id=movement_id,
        reason=f"Supplier delivery from '{req.supplier_name}'"
    ))

    # Add lot for expiry tracking if perishable
    if product.perishable and product.shelf_life_days:
        try:
            exp_date = (
                datetime.datetime.strptime(delivery_date, "%Y-%m-%d")
                + datetime.timedelta(days=product.shelf_life_days)
            ).strftime("%Y-%m-%d")
            db.add(InventoryLot(
                lot_id=f"LOT_{movement_id[:8]}",
                product_id=product.product_id,
                received_date=delivery_date,
                expiry_date=exp_date,
                quantity_received=req.quantity,
                quantity_remaining=req.quantity,
                unit_cost=req.purchase_price,
            ))
        except Exception:
            pass

    db.commit()

    record_audit_log(
        db,
        action="STOCK_DELIVERY",
        entity_type="INVENTORY",
        entity_id=product.product_id,
        summary=f"Received delivery of {req.quantity} {product.unit}s of '{product.product_name}' at INR {req.purchase_price}/unit.",
        actor_id=current_user.id if current_user else None,
        actor_username=current_user.username if current_user else "Shopkeeper"
    )

    return {
        "status": "success",
        "product_id": product.product_id,
        "product_name": product.product_name,
        "quantity_added": req.quantity,
        "new_stock": new_stock,
        "purchase_price": product.purchase_price,
    }


# --- 3. Voice-Based Data Entry ---
@router.post("/voice-parse")
def parse_voice_text(
    req: VoiceParseRequest,
    db: Session = Depends(get_db)
):
    """
    Parses Hindi, Hinglish, or English speech transcripts into structured draft items.
    Example: 'Aaj das biscuit packet bike aur paanch litre tel aaya'
    """
    drafts = parse_voice_transcript(db, req.transcript)
    return {
        "raw_transcript": req.transcript,
        "parsed_items_count": len(drafts),
        "draft_items": drafts
    }


@router.post("/voice-confirm")
def confirm_voice_entries(
    req: VoiceConfirmRequest,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    Commits confirmed voice draft items into sales or stock-in records.
    """
    committed_sales = 0
    committed_stock_ins = 0
    date_str = req.date or datetime.date.today().strftime("%Y-%m-%d")

    for item in req.items:
        # Find product
        prod = None
        if item.product_id:
            prod = db.query(Product).filter(Product.product_id == item.product_id).first()
        if not prod:
            match = find_best_matching_product(db, item.product_name)
            if match:
                prod = db.query(Product).filter(Product.product_id == match["product_id"]).first()

        if not prod:
            continue

        prev_stk = float(prod.current_stock or 0.0)

        if item.action == "SALE":
            if prev_stk < item.quantity:
                continue  # Skip invalid quantity
            new_stk = prev_stk - item.quantity
            prod.current_stock = new_stk
            sale_id = f"SALE_VOICE_{uuid.uuid4().hex[:8].upper()}"

            db.add(Sale(
                sale_id=sale_id,
                sale_date=date_str,
                customer_name="Voice Entry Customer",
                product_id=prod.product_id,
                quantity_sold=item.quantity,
                unit_selling_price=item.unit_price or prod.selling_price,
                line_total=round(item.quantity * (item.unit_price or prod.selling_price), 2),
                unit_cost=prod.purchase_price,
                gross_profit_estimate=round(item.quantity * ((item.unit_price or prod.selling_price) - prod.purchase_price), 2),
                payment_method="Cash",
                transaction_status="Completed"
            ))
            db.add(InventoryMovement(
                product_id=prod.product_id,
                movement_type="SALE",
                quantity_change=-item.quantity,
                previous_stock=prev_stk,
                new_stock=new_stk,
                reference_id=sale_id,
                reason="Voice Entry Sale"
            ))
            committed_sales += 1
        elif item.action == "STOCK_IN":
            new_stk = prev_stk + item.quantity
            prod.current_stock = new_stk
            ref_id = f"IN_VOICE_{uuid.uuid4().hex[:8].upper()}"
            db.add(InventoryMovement(
                product_id=prod.product_id,
                movement_type="STOCK_IN",
                quantity_change=item.quantity,
                previous_stock=prev_stk,
                new_stock=new_stk,
                reference_id=ref_id,
                reason="Voice Entry Stock-In"
            ))
            committed_stock_ins += 1

    db.commit()

    record_audit_log(
        db,
        action="VOICE_ENTRIES_COMMITTED",
        entity_type="RURAL_DATA",
        summary=f"Processed voice draft: {committed_sales} sales and {committed_stock_ins} deliveries committed.",
        actor_id=current_user.id if current_user else None,
        actor_username=current_user.username if current_user else "Shopkeeper"
    )

    return {
        "status": "success",
        "committed_sales": committed_sales,
        "committed_stock_ins": committed_stock_ins,
        "message": f"Successfully recorded {committed_sales} sales and {committed_stock_ins} deliveries."
    }


# --- 4. Handwritten Notebook / Bill Photo to Data ---
@router.post("/notebook-parse")
def parse_notebook_content(
    req: NotebookParseRequest,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    Parses unstructured handwritten notebook lines or bills into staging records.
    Marks uncertain fields and low-confidence matches for user review.
    """
    session_id = f"NB_{uuid.uuid4().hex[:8].upper()}"
    rows = parse_notebook_raw_text(db, req.raw_text)

    # Persist session
    import json
    nb_record = NotebookImport(
        session_id=session_id,
        user_id=current_user.id if current_user else None,
        source_type=req.source_type or "PHOTO",
        original_filename=req.filename or "handwritten_register.jpg",
        status="EXTRACTED",
        extracted_rows=json.dumps(rows),
        rows_committed=0,
    )
    db.add(nb_record)
    db.commit()

    return {
        "session_id": session_id,
        "filename": req.filename,
        "extracted_rows_count": len(rows),
        "rows": rows
    }


@router.post("/notebook-confirm")
def confirm_notebook_rows(
    req: NotebookConfirmRequest,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    Commits validated rows from a notebook photo or bill into SQLite sales and stock.
    """
    committed_count = 0
    date_today = datetime.date.today().strftime("%Y-%m-%d")

    for r in req.rows:
        prod = None
        if r.product_id:
            prod = db.query(Product).filter(Product.product_id == r.product_id).first()
        if not prod:
            match = find_best_matching_product(db, r.product_name)
            if match:
                prod = db.query(Product).filter(Product.product_id == match["product_id"]).first()

        if not prod:
            continue

        prev_stk = float(prod.current_stock or 0.0)
        qty = r.quantity
        if prev_stk < qty:
            # Prevent negative stock, or adjust safely
            qty = max(0.0, prev_stk)
            if qty == 0.0:
                continue

        new_stk = prev_stk - qty
        prod.current_stock = new_stk
        sale_date = r.date or date_today
        sale_id = f"SALE_NB_{uuid.uuid4().hex[:8].upper()}"

        db.add(Sale(
            sale_id=sale_id,
            sale_date=sale_date,
            customer_name="Notebook Register Entry",
            product_id=prod.product_id,
            quantity_sold=qty,
            unit_selling_price=r.unit_price or prod.selling_price,
            line_total=round(qty * (r.unit_price or prod.selling_price), 2),
            unit_cost=prod.purchase_price,
            gross_profit_estimate=round(qty * ((r.unit_price or prod.selling_price) - prod.purchase_price), 2),
            payment_method="Cash",
            transaction_status="Completed"
        ))
        db.add(InventoryMovement(
            product_id=prod.product_id,
            movement_type="SALE",
            quantity_change=-qty,
            previous_stock=prev_stk,
            new_stock=new_stk,
            reference_id=sale_id,
            reason=f"Notebook import: {r.notes or ''}"
        ))
        committed_count += 1

    # Update session if session_id passed
    if req.session_id:
        rec = db.query(NotebookImport).filter(NotebookImport.session_id == req.session_id).first()
        if rec:
            rec.status = "CONFIRMED"
            rec.rows_committed = committed_count
            rec.confirmed_at = datetime.datetime.utcnow()

    db.commit()

    record_audit_log(
        db,
        action="NOTEBOOK_IMPORT_COMMITTED",
        entity_type="NOTEBOOK",
        entity_id=req.session_id,
        summary=f"Confirmed and committed {committed_count} notebook register sales.",
        actor_id=current_user.id if current_user else None,
        actor_username=current_user.username if current_user else "Shopkeeper"
    )

    return {
        "status": "success",
        "rows_committed": committed_count,
        "message": f"Successfully updated inventory for {committed_count} notebook records."
    }


# --- 5. Physical Stock Counting & Reconciliation ---
@router.post("/stock-count/compare")
def compare_physical_stock(
    req: StockCountCompareRequest,
    db: Session = Depends(get_db)
):
    """
    Compares the shopkeeper's physical count against the SQLite system stock.
    Returns variance, shortage or surplus status.
    """
    product = db.query(Product).filter(Product.product_id == req.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    sys_stock = float(product.current_stock or 0.0)
    diff = req.counted_stock - sys_stock
    variance_pct = round((diff / sys_stock) * 100, 1) if sys_stock > 0 else 0.0

    status_str = "MATCH"
    if diff < 0:
        status_str = "SHORTAGE"
    elif diff > 0:
        status_str = "SURPLUS"

    return {
        "product_id": product.product_id,
        "product_name": product.product_name,
        "category": product.category,
        "unit": product.unit,
        "system_stock": sys_stock,
        "counted_stock": req.counted_stock,
        "difference": diff,
        "variance_percentage": variance_pct,
        "status": status_str,
        "financial_impact": round(diff * product.purchase_price, 2),
    }


@router.post("/stock-count/commit")
def commit_physical_stock_adjustment(
    req: StockCountCommitRequest,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    Confirms physical count adjustment and records in movements and stock_counts audit trail.
    """
    product = db.query(Product).filter(Product.product_id == req.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    prev_stock = float(product.current_stock or 0.0)
    counted_stock = float(req.counted_stock)
    diff = counted_stock - prev_stock
    count_id = f"COUNT_{uuid.uuid4().hex[:8].upper()}"

    # Update product
    product.current_stock = counted_stock

    # Record Movement
    db.add(InventoryMovement(
        product_id=product.product_id,
        movement_type="ADJUSTMENT",
        quantity_change=diff,
        previous_stock=prev_stock,
        new_stock=counted_stock,
        reference_id=count_id,
        reason=f"Physical Count Adjustment: {req.reason or 'Verification'}"
    ))

    # Record Stock Count Session
    db.add(StockCount(
        count_id=count_id,
        user_id=current_user.id if current_user else None,
        product_id=product.product_id,
        system_stock=prev_stock,
        counted_stock=counted_stock,
        difference=diff,
        reason=req.reason,
        status="CONFIRMED",
        confirmed_at=datetime.datetime.utcnow()
    ))

    db.commit()

    record_audit_log(
        db,
        action="PHYSICAL_STOCK_COUNT",
        entity_type="INVENTORY",
        entity_id=product.product_id,
        summary=f"Physical count for '{product.product_name}': was {prev_stock}, counted {counted_stock} (Diff: {diff:+0.1f}).",
        actor_id=current_user.id if current_user else None,
        actor_username=current_user.username if current_user else "Shopkeeper"
    )

    return {
        "status": "success",
        "product_id": product.product_id,
        "product_name": product.product_name,
        "previous_stock": prev_stock,
        "new_stock": counted_stock,
        "difference": diff,
        "message": f"Inventory updated from {prev_stock} to {counted_stock} {product.unit}s."
    }


# --- 6. Daily Closing Checklist & Tomorrow's Reorders ---
@router.get("/daily-closing")
def get_daily_closing_summary(
    as_of_date: str = DEFAULT_AS_OF_DATE,
    db: Session = Depends(get_db)
):
    """
    Shopkeeper daily closing checklist summary:
    Total sales today, cash revenue, deliveries received, expiry warnings,
    and simplified 'What should I order tomorrow?' suggestions.
    """
    sales_today = db.query(Sale).filter(Sale.sale_date == as_of_date).all()
    total_sales_units = sum(s.quantity_sold for s in sales_today)
    total_revenue = sum(s.line_total for s in sales_today)
    total_profit = sum(s.gross_profit_estimate for s in sales_today)

    cash_total = sum(s.line_total for s in sales_today if s.payment_method.lower() == "cash")
    upi_total = sum(s.line_total for s in sales_today if "upi" in s.payment_method.lower())

    # Deliveries today
    deliveries_count = db.query(InventoryMovement).filter(
        InventoryMovement.movement_type == "STOCK_IN",
        InventoryMovement.created_at >= datetime.date.today()
    ).count()

    # Expiring lots in next 7 days
    expiring_soon = db.query(InventoryLot).filter(
        InventoryLot.quantity_remaining > 0
    ).all()
    exp_count = 0
    as_of_dt = datetime.datetime.strptime(as_of_date, "%Y-%m-%d").date()
    for lot in expiring_soon:
        try:
            lot_exp = datetime.datetime.strptime(lot.expiry_date, "%Y-%m-%d").date()
            if 0 <= (lot_exp - as_of_dt).days <= 7:
                exp_count += 1
        except Exception:
            pass

    # Top 5 reorder suggestions for tomorrow
    reorders = get_all_reorder_recommendations(db, as_of_date=as_of_date)
    top_5_order = [
        {
            "rank": r["rank"],
            "product_name": r["product_name"],
            "current_stock": r["current_stock"],
            "suggested_order": r["suggested_order_quantity"],
            "pack_size": r["supplier_pack_size"],
            "supplier_name": r["supplier_name"],
            "estimated_cost": r["estimated_order_cost"],
            "urgency": r["urgency"],
            "simple_instruction": f"Order {r['suggested_order_quantity']} {r['category']} from {r['supplier_name']}."
        }
        for r in reorders[:5]
    ]

    return {
        "as_of_date": as_of_date,
        "daily_sales_count": len(sales_today),
        "total_units_sold": total_sales_units,
        "total_revenue": round(total_revenue, 2),
        "total_gross_profit": round(total_profit, 2),
        "cash_in_drawer": round(cash_total, 2),
        "upi_digital_collection": round(upi_total, 2),
        "deliveries_received_today": deliveries_count,
        "items_expiring_this_week": exp_count,
        "checklist": [
            {"task": "Count drawer cash and match with daily cash total", "is_done": False},
            {"task": "Record any credit (Udhaar/Khata) sales in ledger", "is_done": False},
            {"task": "Verify bread, milk, and perishable shelf expiration", "is_done": False},
            {"task": "Send tomorrow's order list to City Bakery & FreshFarm", "is_done": False},
        ],
        "what_to_order_tomorrow": top_5_order,
    }
