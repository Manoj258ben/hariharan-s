from typing import List, Optional
import datetime
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import PurchaseOrder, PurchaseOrderItem, Product, InventoryMovement, InventoryLot, AuditLog
from ..schemas import POCreate, POResponse, POReceiveRequest, POItemResponse

router = APIRouter(prefix="/api/purchase-orders", tags=["Purchase Orders"])

@router.get("", response_model=List[POResponse])
def get_purchase_orders(
    supplier_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(PurchaseOrder)
    if supplier_id:
        query = query.filter(PurchaseOrder.supplier_id == supplier_id)
    if status_filter:
        query = query.filter(PurchaseOrder.status == status_filter)

    orders = query.order_by(PurchaseOrder.created_at.desc()).all()
    results = []
    for po in orders:
        items = [
            POItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product.product_name if item.product else item.product_id,
                quantity_ordered=item.quantity_ordered,
                quantity_received=item.quantity_received,
                unit_cost=item.unit_cost,
                subtotal=item.subtotal
            )
            for item in po.items
        ]
        results.append(POResponse(
            po_id=po.po_id,
            po_number=po.po_number,
            supplier_id=po.supplier_id,
            supplier_name=po.supplier.supplier_name if po.supplier else None,
            order_date=po.order_date,
            status=po.status,
            total_amount=po.total_amount,
            expected_delivery_date=po.expected_delivery_date,
            received_date=po.received_date,
            notes=po.notes,
            items=items
        ))
    return results


@router.post("", response_model=POResponse, status_code=status.HTTP_201_CREATED)
def create_purchase_order(po_in: POCreate, db: Session = Depends(get_db)):
    po_id = f"PO_{uuid.uuid4().hex[:8].upper()}"
    po_number = f"PO-{datetime.date.today().strftime('%Y%m')}-{uuid.uuid4().hex[:4].upper()}"
    order_date = po_in.order_date or datetime.date.today().strftime("%Y-%m-%d")

    total_amount = sum(item.quantity_ordered * item.unit_cost for item in po_in.items)

    po = PurchaseOrder(
        po_id=po_id,
        po_number=po_number,
        supplier_id=po_in.supplier_id,
        order_date=order_date,
        status="ORDERED",  # Mark as ordered directly so it counts towards incoming stock
        total_amount=round(total_amount, 2),
        expected_delivery_date=po_in.expected_delivery_date,
        notes=po_in.notes
    )
    db.add(po)

    for item in po_in.items:
        po_item = PurchaseOrderItem(
            po_id=po_id,
            product_id=item.product_id,
            quantity_ordered=item.quantity_ordered,
            quantity_received=0.0,
            unit_cost=item.unit_cost,
            subtotal=round(item.quantity_ordered * item.unit_cost, 2)
        )
        db.add(po_item)

    db.add(AuditLog(
        action="PO_CREATED",
        entity="PURCHASE_ORDER",
        entity_id=po_id,
        details=f"Created PO {po_number} with {len(po_in.items)} items totaling ₹{total_amount}"
    ))

    db.commit()
    db.refresh(po)
    return get_purchase_orders(status_filter=None, db=db)[0]


@router.post("/{order_id}/receive", response_model=POResponse)
def receive_purchase_order(
    order_id: str,
    receive_in: Optional[POReceiveRequest] = None,
    db: Session = Depends(get_db)
):
    """
    Goods Receipt: Increases product stock atomically upon actual physical delivery.
    """
    po = db.query(PurchaseOrder).filter(PurchaseOrder.po_id == order_id).with_for_update().first()
    if not po:
        raise HTTPException(status_code=404, detail=f"Purchase order '{order_id}' not found")

    if po.status == "RECEIVED":
        raise HTTPException(status_code=400, detail="Purchase order has already been received")

    receipt_date = (receive_in.received_date if receive_in else None) or datetime.date.today().strftime("%Y-%m-%d")
    po.status = "RECEIVED"
    po.received_date = receipt_date

    for item in po.items:
        qty_to_add = item.quantity_ordered - item.quantity_received
        if qty_to_add <= 0:
            continue

        item.quantity_received = item.quantity_ordered

        product = db.query(Product).filter(Product.product_id == item.product_id).with_for_update().first()
        if product:
            prev_stock = float(product.current_stock or 0.0)
            new_stock = prev_stock + qty_to_add
            product.current_stock = new_stock

            # Create Inventory Movement
            db.add(InventoryMovement(
                product_id=product.product_id,
                movement_type="PO_RECEIPT",
                quantity_change=qty_to_add,
                previous_stock=prev_stock,
                new_stock=new_stock,
                reason=f"Received PO {po.po_number}",
                reference_id=po.po_id
            ))

            # Create Lot if expiry given
            exp_date = receive_in.expiry_date if (receive_in and receive_in.expiry_date) else None
            if not exp_date and product.perishable:
                # Compute estimated expiry
                shelf = product.shelf_life_days or 30
                exp_dt = datetime.datetime.strptime(receipt_date, "%Y-%m-%d").date() + datetime.timedelta(days=shelf)
                exp_date = exp_dt.strftime("%Y-%m-%d")

            if exp_date:
                lot_id = f"LOT_{uuid.uuid4().hex[:6].upper()}"
                db.add(InventoryLot(
                    lot_id=lot_id,
                    product_id=product.product_id,
                    supplier_id=po.supplier_id,
                    received_date=receipt_date,
                    expiry_date=exp_date,
                    quantity_received=qty_to_add,
                    quantity_remaining=qty_to_add,
                    unit_cost=item.unit_cost,
                    disposition_note=f"Receipt from PO {po.po_number}"
                ))

    db.add(AuditLog(
        action="PO_RECEIVED",
        entity="PURCHASE_ORDER",
        entity_id=po.po_id,
        details=f"Received PO {po.po_number}. Stock increased for all items."
    ))

    db.commit()
    db.refresh(po)
    return get_purchase_orders(status_filter=None, db=db)[0]
