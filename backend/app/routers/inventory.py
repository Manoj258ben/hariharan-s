from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Product, InventoryMovement, AuditLog, InventoryLot
from ..schemas import StockAdjustmentRequest, StockMovementResponse

router = APIRouter(prefix="/api/inventory", tags=["Inventory Operations"])

@router.post("/adjustments", response_model=StockMovementResponse)
def adjust_inventory(req: StockAdjustmentRequest, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.product_id == req.product_id).with_for_update().first()
    if not product:
        raise HTTPException(status_code=404, detail=f"Product '{req.product_id}' not found")

    prev_stock = float(product.current_stock or 0.0)

    if req.movement_type == "STOCK_IN":
        qty_change = abs(req.quantity)
        new_stock = prev_stock + qty_change
    elif req.movement_type == "STOCK_OUT":
        qty_change = -abs(req.quantity)
        new_stock = prev_stock + qty_change
        if new_stock < 0:
            raise HTTPException(status_code=400, detail=f"Cannot remove {abs(req.quantity)} units. Current stock is only {prev_stock}")
    elif req.movement_type == "ADJUSTMENT":
        new_stock = max(0.0, req.quantity)
        qty_change = new_stock - prev_stock
    else:
        raise HTTPException(status_code=400, detail=f"Invalid movement_type '{req.movement_type}'")

    # Update product atomically
    product.current_stock = new_stock

    # Record Movement
    movement = InventoryMovement(
        product_id=product.product_id,
        movement_type=req.movement_type,
        quantity_change=qty_change,
        previous_stock=prev_stock,
        new_stock=new_stock,
        reason=req.reason,
        reference_id=req.reference_id
    )
    db.add(movement)

    # Record Audit Log
    db.add(AuditLog(
        action=f"INVENTORY_{req.movement_type}",
        entity="PRODUCT",
        entity_id=product.product_id,
        details=f"Stock changed from {prev_stock} to {new_stock} ({qty_change:+f}). Reason: {req.reason}"
    ))

    db.commit()
    db.refresh(movement)
    return movement


@router.post("/stock-in", response_model=StockMovementResponse)
def stock_in(req: StockAdjustmentRequest, db: Session = Depends(get_db)):
    req.movement_type = "STOCK_IN"
    return adjust_inventory(req, db)


@router.post("/stock-out", response_model=StockMovementResponse)
def stock_out(req: StockAdjustmentRequest, db: Session = Depends(get_db)):
    req.movement_type = "STOCK_OUT"
    return adjust_inventory(req, db)


@router.get("/movements", response_model=List[StockMovementResponse])
def get_movements(
    product_id: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    query = db.query(InventoryMovement)
    if product_id:
        query = query.filter(InventoryMovement.product_id == product_id)
    return query.order_by(InventoryMovement.id.desc()).limit(limit).all()


@router.get("/lots")
def get_inventory_lots(db: Session = Depends(get_db)):
    lots = db.query(InventoryLot).join(Product).all()
    return [
        {
            "lot_id": l.lot_id,
            "product_id": l.product_id,
            "product_name": l.product.product_name if l.product else l.product_id,
            "category": l.product.category if l.product else "General",
            "batch_number": getattr(l, "batch_number", l.lot_id),
            "received_date": l.received_date,
            "expiry_date": l.expiry_date,
            "quantity_received": float(l.quantity_received or 0.0),
            "quantity_remaining": float(l.quantity_remaining or 0.0),
            "unit_cost": float(l.unit_cost or 0.0),
            "disposition_note": l.disposition_note
        }
        for l in lots
    ]
