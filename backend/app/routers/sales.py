from typing import List, Optional
import datetime
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Product, Sale, InventoryMovement, AuditLog
from ..schemas import SaleCreate, SaleResponse
from ..config import DEFAULT_AS_OF_DATE

router = APIRouter(prefix="/api/sales", tags=["Sales Management"])

@router.post("", response_model=SaleResponse, status_code=status.HTTP_201_CREATED)
def record_sale(sale_in: SaleCreate, db: Session = Depends(get_db)):
    # 1. Fetch and lock product row
    product = db.query(Product).filter(
        Product.product_id == sale_in.product_id,
        Product.is_archived == False
    ).with_for_update().first()

    if not product:
        raise HTTPException(status_code=404, detail=f"Product '{sale_in.product_id}' not found")

    qty = float(sale_in.quantity_sold)
    current_stk = float(product.current_stock or 0.0)

    # 2. Check stock availability
    if current_stk < qty:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient inventory. Available: {current_stk} {product.unit}s, Requested: {qty}"
        )

    # 3. Calculate sale financial metrics
    unit_price = sale_in.unit_selling_price if sale_in.unit_selling_price is not None else float(product.selling_price)
    line_total = round(qty * unit_price, 2)
    unit_cost = float(product.purchase_price or 0.0)
    profit = round(line_total - (qty * unit_cost), 2)
    sale_date = sale_in.sale_date or datetime.date.today().strftime("%Y-%m-%d")
    sale_id = f"SALE{uuid.uuid4().hex[:8].upper()}"

    # 4. Atomic Database Transaction:
    # A) Create sale record
    sale = Sale(
        sale_id=sale_id,
        sale_date=sale_date,
        customer_name=sale_in.customer_name or "Counter Customer",
        product_id=product.product_id,
        quantity_sold=qty,
        unit_selling_price=unit_price,
        line_total=line_total,
        unit_cost=unit_cost,
        gross_profit_estimate=profit,
        payment_method=sale_in.payment_method or "UPI",
        transaction_status="Completed"
    )
    db.add(sale)

    # B) Deduct stock
    new_stock = current_stk - qty
    product.current_stock = new_stock

    # C) Create inventory movement audit
    movement = InventoryMovement(
        product_id=product.product_id,
        movement_type="SALE",
        quantity_change=-qty,
        previous_stock=current_stk,
        new_stock=new_stock,
        reason=f"Counter sale {sale_id}",
        reference_id=sale_id
    )
    db.add(movement)

    # D) Create audit log
    db.add(AuditLog(
        action="SALE_RECORDED",
        entity="PRODUCT",
        entity_id=product.product_id,
        details=f"Sale {sale_id}: {qty} units sold at ₹{unit_price}. Stock updated {current_stk} -> {new_stock}"
    ))

    # Commit both atomically
    db.commit()
    db.refresh(sale)

    resp = SaleResponse(
        sale_id=sale.sale_id,
        sale_date=sale.sale_date,
        product_id=sale.product_id,
        product_name=product.product_name,
        quantity_sold=sale.quantity_sold,
        unit_selling_price=sale.unit_selling_price,
        line_total=sale.line_total,
        unit_cost=sale.unit_cost,
        gross_profit_estimate=sale.gross_profit_estimate,
        payment_method=sale.payment_method,
        transaction_status=sale.transaction_status
    )
    return resp


@router.get("", response_model=List[SaleResponse])
def get_sales(
    product_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 5000,
    db: Session = Depends(get_db)
):
    query = db.query(Sale).join(Product)

    if product_id:
        query = query.filter(Sale.product_id == product_id)
    if start_date:
        query = query.filter(Sale.sale_date >= start_date)
    if end_date:
        query = query.filter(Sale.sale_date <= end_date)

    sales = query.order_by(Sale.sale_date.desc(), Sale.created_at.desc()).limit(limit).all()

    return [
        SaleResponse(
            sale_id=s.sale_id,
            sale_date=s.sale_date,
            product_id=s.product_id,
            product_name=s.product.product_name if s.product else s.product_id,
            quantity_sold=s.quantity_sold,
            unit_selling_price=s.unit_selling_price,
            line_total=s.line_total,
            unit_cost=s.unit_cost,
            gross_profit_estimate=s.gross_profit_estimate,
            payment_method=s.payment_method,
            transaction_status=s.transaction_status
        )
        for s in sales
    ]
