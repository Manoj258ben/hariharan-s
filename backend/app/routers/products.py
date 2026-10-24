from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Product, Supplier, AuditLog, PriceRateHistory
from ..schemas import (
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    ProductRateModifyRequest,
    PriceRateHistoryResponse
)

router = APIRouter(prefix="/api/products", tags=["Products"])

@router.get("", response_model=List[ProductResponse])
def get_products(
    search: Optional[str] = None,
    category: Optional[str] = None,
    supplier_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Product).filter(Product.is_archived == False)

    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            (Product.product_name.ilike(search_filter)) |
            (Product.product_id.ilike(search_filter)) |
            (Product.barcode.ilike(search_filter)) |
            (Product.brand.ilike(search_filter))
        )

    if category and category != "ALL":
        query = query.filter(Product.category == category)

    if supplier_id and supplier_id != "ALL":
        query = query.filter(Product.supplier_id == supplier_id)

    products = query.order_by(Product.product_name.asc()).all()
    # Populate supplier_name
    results = []
    for p in products:
        p_dict = ProductResponse.model_validate(p)
        p_dict.supplier_name = p.supplier.supplier_name if p.supplier else None
        results.append(p_dict)
    return results


@router.get("/barcode/{barcode}", response_model=ProductResponse)
def get_product_by_barcode(barcode: str, db: Session = Depends(get_db)):
    product = db.query(Product).filter(
        Product.barcode == barcode,
        Product.is_archived == False
    ).first()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No product registered with barcode '{barcode}'"
        )

    resp = ProductResponse.model_validate(product)
    resp.supplier_name = product.supplier.supplier_name if product.supplier else None
    return resp


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: str, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found")
    resp = ProductResponse.model_validate(product)
    resp.supplier_name = product.supplier.supplier_name if product.supplier else None
    return resp


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(product_in: ProductCreate, db: Session = Depends(get_db)):
    existing = db.query(Product).filter(Product.product_id == product_in.product_id).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Product ID '{product_in.product_id}' already exists")

    if product_in.barcode:
        existing_barcode = db.query(Product).filter(Product.barcode == product_in.barcode).first()
        if existing_barcode:
            raise HTTPException(status_code=400, detail=f"Barcode '{product_in.barcode}' already assigned to {existing_barcode.product_name}")

    product = Product(**product_in.model_dump())
    db.add(product)
    db.add(AuditLog(
        action="PRODUCT_CREATE",
        entity="PRODUCT",
        entity_id=product.product_id,
        details=f"Created product '{product.product_name}' (Stock: {product.current_stock})"
    ))
    db.commit()
    db.refresh(product)

    resp = ProductResponse.model_validate(product)
    resp.supplier_name = product.supplier.supplier_name if product.supplier else None
    return resp


@router.patch("/{product_id}", response_model=ProductResponse)
def update_product(product_id: str, product_update: ProductUpdate, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found")

    update_data = product_update.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(product, field, val)

    db.add(AuditLog(
        action="PRODUCT_UPDATE",
        entity="PRODUCT",
        entity_id=product.product_id,
        details=f"Updated fields: {list(update_data.keys())}"
    ))
    db.commit()
    db.refresh(product)

    resp = ProductResponse.model_validate(product)
    resp.supplier_name = product.supplier.supplier_name if product.supplier else None
    return resp


@router.delete("/{product_id}", status_code=status.HTTP_200_OK)
def delete_product(product_id: str, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found")

    product.is_archived = True
    db.add(AuditLog(
        action="PRODUCT_ARCHIVE",
        entity="PRODUCT",
        entity_id=product.product_id,
        details=f"Archived product '{product.product_name}'"
    ))
    db.commit()
    return {"message": f"Product '{product_id}' archived successfully."}


@router.put("/{product_id}/rate", response_model=ProductResponse)
def modify_product_rate(
    product_id: str,
    rate_req: ProductRateModifyRequest,
    db: Session = Depends(get_db)
):
    """
    Directly modifies the selling price and/or purchase price rate in SQLite
    and logs the audit trace to price_rate_history.
    """
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found in SQLite.")

    old_selling = float(product.selling_price or 0.0)
    old_purchase = float(product.purchase_price or 0.0)
    
    # Handle both new_selling_price and selling_price aliases
    if rate_req.new_selling_price is not None:
        new_selling = float(rate_req.new_selling_price)
    elif rate_req.selling_price is not None:
        new_selling = float(rate_req.selling_price)
    else:
        new_selling = old_selling

    # Handle both new_purchase_price and purchase_price aliases
    if rate_req.new_purchase_price is not None:
        new_purchase = float(rate_req.new_purchase_price)
    elif rate_req.purchase_price is not None:
        new_purchase = float(rate_req.purchase_price)
    else:
        new_purchase = old_purchase

    # Update in SQLite
    product.selling_price = new_selling
    product.purchase_price = new_purchase

    # Record in PriceRateHistory
    history_entry = PriceRateHistory(
        product_id=product.product_id,
        product_name=product.product_name,
        old_purchase_price=old_purchase,
        new_purchase_price=new_purchase,
        old_selling_price=old_selling,
        new_selling_price=new_selling,
        modified_by=rate_req.modified_by or "Store Admin",
        reason=rate_req.reason or "Direct rate update"
    )
    db.add(history_entry)

    db.add(AuditLog(
        action="RATE_MODIFIED",
        entity="PRODUCT",
        entity_id=product.product_id,
        details=f"Rate modified for {product.product_name}: Retail ₹{old_selling} -> ₹{new_selling}, Cost ₹{old_purchase} -> ₹{new_purchase}. Reason: {rate_req.reason}"
    ))

    db.commit()
    db.refresh(product)

    resp = ProductResponse.model_validate(product)
    resp.supplier_name = product.supplier.supplier_name if product.supplier else None
    return resp


@router.get("/{product_id}/rate-history", response_model=List[PriceRateHistoryResponse])
def get_product_rate_history(product_id: str, db: Session = Depends(get_db)):
    """Returns the historical rate change audits for a given product."""
    history = db.query(PriceRateHistory).filter(
        PriceRateHistory.product_id == product_id
    ).order_by(PriceRateHistory.timestamp.desc()).all()
    return history


@router.get("/rate-history/recent", response_model=List[PriceRateHistoryResponse])
def get_all_recent_rate_history(limit: int = 50, db: Session = Depends(get_db)):
    """Returns the most recent product price modifications across the store."""
    history = db.query(PriceRateHistory).order_by(PriceRateHistory.timestamp.desc()).limit(limit).all()
    return history

