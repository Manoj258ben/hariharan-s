"""
Offline-First Data Collection Synchronization Router for StockSense.
Guarantees idempotent processing of offline queues using client-generated operation IDs (UUIDs).
Prevents double-sales, logs conflicts, and provides synchronization audits.
"""
from typing import List, Dict, Any, Optional
import datetime
import json
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Product, Sale, InventoryMovement
from ..models.auth import OfflineSyncQueue, User
from ..services.auth import get_optional_current_user, record_audit_log

router = APIRouter(prefix="/api/sync", tags=["Offline-First Synchronization"])


class SyncOperationItem(BaseModel):
    operation_id: str = Field(min_length=5, description="Client-generated unique UUID")
    operation_type: str = Field(description="'RECORD_SALE', 'STOCK_IN', 'STOCK_ADJUSTMENT'")
    payload: Dict[str, Any]
    timestamp: Optional[str] = None


class BatchSyncRequest(BaseModel):
    operations: List[SyncOperationItem]


@router.post("/offline")
def sync_offline_batch(
    req: BatchSyncRequest,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    Processes a batch of offline-queued operations with strict idempotency.
    If an operation_id has already been processed, it is marked DUPLICATE and skipped safely.
    """
    results = []
    synced_count = 0
    duplicate_count = 0
    failed_count = 0

    for op in req.operations:
        op_id = op.operation_id.strip()

        # Check existing queue
        existing_queue = db.query(OfflineSyncQueue).filter(
            OfflineSyncQueue.operation_id == op_id
        ).first()

        if existing_queue and existing_queue.status == "SYNCED":
            duplicate_count += 1
            results.append({
                "operation_id": op_id,
                "status": "DUPLICATE",
                "message": "Operation already processed and synchronized previously."
            })
            continue

        # Prepare queue entry if new
        if not existing_queue:
            existing_queue = OfflineSyncQueue(
                operation_id=op_id,
                user_id=current_user.id if current_user else None,
                operation_type=op.operation_type,
                payload=json.dumps(op.payload),
                status="PENDING"
            )
            db.add(existing_queue)
            db.flush()

        # Execute business logic based on operation type
        try:
            p_data = op.payload
            p_id = p_data.get("product_id")
            product = db.query(Product).filter(Product.product_id == p_id).first()

            if not product:
                raise ValueError(f"Product ID '{p_id}' not found in database.")

            qty = float(p_data.get("quantity") or p_data.get("quantity_sold") or 1.0)
            prev_stock = float(product.current_stock or 0.0)

            if op.operation_type in ("RECORD_SALE", "SALE"):
                # Sale: reduce stock
                if prev_stock < qty:
                    # Partial / zero stock safety: adjust to maximum available or zero
                    qty_to_deduct = min(prev_stock, qty)
                else:
                    qty_to_deduct = qty

                new_stock = prev_stock - qty_to_deduct
                product.current_stock = new_stock

                unit_price = float(p_data.get("unit_price") or product.selling_price)
                line_total = round(qty_to_deduct * unit_price, 2)
                sale_date = p_data.get("sale_date") or datetime.date.today().strftime("%Y-%m-%d")

                sale = Sale(
                    sale_id=f"SALE_OFFLINE_{op_id[:8]}",
                    sale_date=sale_date,
                    customer_name=p_data.get("customer_name", "Offline Counter Customer"),
                    product_id=product.product_id,
                    quantity_sold=qty_to_deduct,
                    unit_selling_price=unit_price,
                    line_total=line_total,
                    unit_cost=product.purchase_price,
                    gross_profit_estimate=round(line_total - (qty_to_deduct * product.purchase_price), 2),
                    payment_method=p_data.get("payment_method", "Cash"),
                    transaction_status="Completed"
                )
                db.add(sale)

                db.add(InventoryMovement(
                    product_id=product.product_id,
                    movement_type="SALE",
                    quantity_change=-qty_to_deduct,
                    previous_stock=prev_stock,
                    new_stock=new_stock,
                    reference_id=op_id,
                    reason="Offline Queued Sale Sync"
                ))

            elif op.operation_type in ("STOCK_IN", "DELIVERY"):
                new_stock = prev_stock + qty
                product.current_stock = new_stock
                if p_data.get("purchase_price"):
                    product.purchase_price = float(p_data["purchase_price"])

                db.add(InventoryMovement(
                    product_id=product.product_id,
                    movement_type="STOCK_IN",
                    quantity_change=qty,
                    previous_stock=prev_stock,
                    new_stock=new_stock,
                    reference_id=op_id,
                    reason="Offline Queued Stock-In Sync"
                ))

            elif op.operation_type in ("STOCK_ADJUSTMENT", "STOCK_COUNT"):
                counted = float(p_data.get("counted_stock", qty))
                diff = counted - prev_stock
                product.current_stock = counted

                db.add(InventoryMovement(
                    product_id=product.product_id,
                    movement_type="ADJUSTMENT",
                    quantity_change=diff,
                    previous_stock=prev_stock,
                    new_stock=counted,
                    reference_id=op_id,
                    reason=f"Offline Stock Count Sync: {p_data.get('reason', 'Verification')}"
                ))

            existing_queue.status = "SYNCED"
            existing_queue.synced_at = datetime.datetime.utcnow()
            synced_count += 1
            results.append({
                "operation_id": op_id,
                "status": "SYNCED",
                "message": f"Successfully committed {op.operation_type} for '{product.product_name}'."
            })

        except Exception as ex:
            existing_queue.status = "FAILED"
            existing_queue.error_message = str(ex)
            failed_count += 1
            results.append({
                "operation_id": op_id,
                "status": "FAILED",
                "error": str(ex)
            })

    db.commit()

    if synced_count > 0:
        record_audit_log(
            db,
            action="OFFLINE_SYNC_COMPLETED",
            entity_type="SYNC_QUEUE",
            summary=f"Synchronized {synced_count} offline transactions ({duplicate_count} skipped as duplicates, {failed_count} failed).",
            actor_id=current_user.id if current_user else None,
            actor_username=current_user.username if current_user else "Shopkeeper"
        )

    return {
        "status": "success",
        "total_operations": len(req.operations),
        "synced_count": synced_count,
        "duplicate_count": duplicate_count,
        "failed_count": failed_count,
        "last_synced_at": datetime.datetime.utcnow().isoformat(),
        "results": results
    }


@router.get("/queue")
def get_sync_queue_status(
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Returns recent offline sync queue status and audit trail."""
    queue = db.query(OfflineSyncQueue).order_by(OfflineSyncQueue.id.desc()).limit(limit).all()
    pending_count = db.query(OfflineSyncQueue).filter(OfflineSyncQueue.status == "PENDING").count()
    failed_count = db.query(OfflineSyncQueue).filter(OfflineSyncQueue.status == "FAILED").count()

    return {
        "pending_count": pending_count,
        "failed_count": failed_count,
        "recent_queue": [
            {
                "id": q.id,
                "operation_id": q.operation_id,
                "operation_type": q.operation_type,
                "status": q.status,
                "error_message": q.error_message,
                "created_at": q.created_at.isoformat() if q.created_at else None,
                "synced_at": q.synced_at.isoformat() if q.synced_at else None,
            }
            for q in queue
        ]
    }
