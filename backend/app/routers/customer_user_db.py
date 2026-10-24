from typing import List, Optional, Dict, Any
import io
import datetime
import uuid
from zipfile import BadZipFile
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import get_db, get_customer_db, get_user_db
from ..models import (
    Customer,
    CustomerPurchase,
    UserPurchase,
    PriceRateHistory,
    Product,
    Supplier,
    Sale,
    InventoryMovement,
    InventoryLot,
    AuditLog,
    User
)
from ..schemas import (
    CustomerCreate,
    CustomerResponse,
    CustomerPurchaseCreate,
    CustomerPurchaseResponse,
    UserPurchaseCreate,
    UserPurchaseResponse,
    PriceRateHistoryResponse
)

router = APIRouter(tags=["Customer & User SQLite Database"])


# Auto-seed initial customers and procurement records if table is fresh
def ensure_seed_data(db: Session, customer_db: Session, user_db: Session):
    if customer_db.query(Customer).count() == 0:
        initial_customers = [
            Customer(
                customer_id="CUST001",
                customer_name="Ramesh Kumar",
                phone="9840123456",
                email="ramesh.k@gmail.com",
                city="South Block, Main St",
                loyalty_tier="Gold",
                total_spent=3450.0,
                total_purchases_count=8
            ),
            Customer(
                customer_id="CUST002",
                customer_name="Priya Sharma",
                phone="9840987654",
                email="priya.sharma@yahoo.com",
                city="Green Glen Layout",
                loyalty_tier="Platinum",
                total_spent=5820.0,
                total_purchases_count=12
            ),
            Customer(
                customer_id="CUST003",
                customer_name="Suresh Patel",
                phone="9823456789",
                email="suresh.patel@rediffmail.com",
                city="Market Road",
                loyalty_tier="Silver",
                total_spent=1890.0,
                total_purchases_count=5
            ),
            Customer(
                customer_id="CUST004",
                customer_name="Ananya Rao",
                phone="9876543210",
                email="ananya.rao@gmail.com",
                city="Cross Road #4",
                loyalty_tier="Silver",
                total_spent=2400.0,
                total_purchases_count=6
            ),
            Customer(
                customer_id="CUST005",
                customer_name="Karthik Rajan",
                phone="9789012345",
                email="karthik.rajan@outlook.com",
                city="Temple Street",
                loyalty_tier="Bronze",
                total_spent=950.0,
                total_purchases_count=3
            ),
        ]
        for c in initial_customers:
            customer_db.add(c)
        customer_db.commit()

        # Seed sample customer purchases via barcode scan
        prods = {p.product_id: p for p in db.query(Product).all()}
        sample_scans = [
            ("CUST001", "P001", "890100000001", 2.0, 30.0, "2026-09-28", "CAMERA_SCAN"),
            ("CUST001", "P002", "890100000002", 1.0, 40.0, "2026-09-28", "CAMERA_SCAN"),
            ("CUST002", "P005", "890100000005", 3.0, 65.0, "2026-09-29", "CAMERA_SCAN"),
            ("CUST002", "P006", "890100000006", 1.0, 140.0, "2026-09-29", "USB_SCAN"),
            ("CUST003", "P003", "890100000003", 4.0, 25.0, "2026-09-30", "CAMERA_SCAN"),
            ("CUST004", "P007", "890100000007", 2.0, 20.0, "2026-09-30", "CAMERA_SCAN"),
        ]
        for idx, (cid, pid, bcode, qty, rate, pdate, src) in enumerate(sample_scans, start=1):
            p = prods.get(pid)
            pname = p.product_name if p else f"Product {pid}"
            cat = p.category if p else "General"
            customer_db.add(CustomerPurchase(
                purchase_id=f"CP_SCAN_{idx:04d}",
                customer_id=cid,
                customer_name=dict((c.customer_id, c.customer_name) for c in initial_customers).get(cid, "Customer"),
                product_id=pid,
                product_name=pname,
                barcode=(p.barcode if p and p.barcode else bcode),
                category=cat,
                quantity=qty,
                rate=rate,
                total_amount=round(qty * rate, 2),
                payment_method="UPI",
                scan_source=src,
                purchase_date=pdate
            ))
        customer_db.commit()

    if user_db.query(UserPurchase).count() == 0:
        prods = {p.product_id: p for p in db.query(Product).all()}
        sample_procurement = [
            ("P001", "S001", 50.0, 22.0, 30.0, "INV-2026-09-01", "2026-09-15"),
            ("P002", "S002", 40.0, 28.0, 40.0, "INV-2026-09-02", "2026-09-18"),
            ("P005", "S003", 30.0, 48.0, 65.0, "INV-2026-09-03", "2026-09-22"),
            ("P006", "S004", 25.0, 110.0, 140.0, "INV-2026-09-04", "2026-09-25"),
        ]
        for idx, (pid, sid, qty, cost_rate, sell_rate, inv, pdate) in enumerate(sample_procurement, start=1):
            p = prods.get(pid)
            pname = p.product_name if p else f"Product {pid}"
            user_db.add(UserPurchase(
                user_purchase_id=f"UP_PROC_{idx:04d}",
                user_name="Store Manager",
                product_id=pid,
                product_name=pname,
                supplier_id=sid,
                supplier_name="FreshFarm Wholesale",
                quantity_bought=qty,
                purchase_rate=cost_rate,
                suggested_selling_rate=sell_rate,
                total_cost=round(qty * cost_rate, 2),
                invoice_number=inv,
                payment_status="PAID",
                purchase_date=pdate
            ))
        user_db.commit()


# ==========================================
# 1. CUSTOMER DATABASE ENDPOINTS
# ==========================================

@router.get("/customers", response_model=List[CustomerResponse])
def get_all_customers(
    db: Session = Depends(get_db),
    customer_db: Session = Depends(get_customer_db),
    user_db: Session = Depends(get_user_db),
):
    ensure_seed_data(db, customer_db, user_db)
    customers = customer_db.query(Customer).order_by(Customer.total_spent.desc()).all()
    return customers


@router.post("/customers", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
def create_customer(
    cust_in: CustomerCreate,
    db: Session = Depends(get_db),
    customer_db: Session = Depends(get_customer_db),
):
    cid = cust_in.customer_id or f"CUST{uuid.uuid4().hex[:10].upper()}"
    existing = customer_db.query(Customer).filter(Customer.customer_id == cid).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Customer ID '{cid}' already exists.")

    customer = Customer(
        customer_id=cid,
        customer_name=cust_in.customer_name,
        phone=cust_in.phone,
        email=cust_in.email,
        city=cust_in.city or "Local Area",
        loyalty_tier=cust_in.loyalty_tier or "Silver"
    )
    customer_db.add(customer)
    customer_db.commit()
    customer_db.refresh(customer)
    db.add(AuditLog(
        action="CUSTOMER_CREATED",
        entity="CUSTOMER",
        entity_id=cid,
        details=f"Customer '{cust_in.customer_name}' registered in separate customer SQLite database."
    ))
    try:
        db.commit()
    except Exception:
        customer_db.delete(customer)
        customer_db.commit()
        raise
    return customer


@router.get("/customer-purchases", response_model=List[CustomerPurchaseResponse])
def get_customer_purchases(
    customer_id: Optional[str] = None,
    barcode: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    customer_db: Session = Depends(get_customer_db),
    user_db: Session = Depends(get_user_db),
):
    ensure_seed_data(db, customer_db, user_db)
    query = customer_db.query(CustomerPurchase)
    if customer_id:
        query = query.filter(CustomerPurchase.customer_id == customer_id)
    if barcode:
        query = query.filter(CustomerPurchase.barcode == barcode)
    return query.order_by(CustomerPurchase.created_at.desc()).limit(limit).all()


@router.post("/customer-purchases", response_model=CustomerPurchaseResponse, status_code=status.HTTP_201_CREATED)
def record_customer_barcode_purchase(
    req: CustomerPurchaseCreate,
    db: Session = Depends(get_db),
    customer_db: Session = Depends(get_customer_db),
    user_db: Session = Depends(get_user_db),
):
    """
    Records customer buying products using barcode scan (camera or handheld scanner).
    Updates SQLite inventory, logs transaction, updates customer metrics and global sales.
    """
    ensure_seed_data(db, customer_db, user_db)

    # 1. Lookup customer
    customer = customer_db.query(Customer).filter(Customer.customer_id == req.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail=f"Customer '{req.customer_id}' not found in SQLite.")

    # 2. Lookup product by barcode or product_id
    product = None
    if req.barcode:
        product = db.query(Product).filter(Product.barcode == req.barcode, Product.is_archived == False).first()
    if not product and req.product_id:
        product = db.query(Product).filter(Product.product_id == req.product_id, Product.is_archived == False).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found for the provided barcode/product_id.")

    # 3. Check stock
    qty = float(req.quantity)
    current_stock = float(product.current_stock or 0.0)
    if current_stock < qty:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient inventory for {product.product_name}. Available: {current_stock}, Requested: {qty}"
        )

    # 4. Financials
    rate = float(req.rate) if req.rate is not None and req.rate > 0 else float(product.selling_price or 0.0)
    total_amount = round(qty * rate, 2)
    pdate = req.purchase_date or datetime.date.today().isoformat()
    pid = f"CP_SCAN_{uuid.uuid4().hex[:8].upper()}"
    sale_id = f"SALE_SCAN_{pid[-6:]}"

    # 5. Decrement stock
    product.current_stock = current_stock - qty

    # 6. Update customer totals
    customer.total_spent = round((customer.total_spent or 0.0) + total_amount, 2)
    customer.total_purchases_count = (customer.total_purchases_count or 0) + 1
    if customer.total_spent > 5000:
        customer.loyalty_tier = "Platinum"
    elif customer.total_spent > 2500:
        customer.loyalty_tier = "Gold"

    # 7. Create customer purchase record
    purchase = CustomerPurchase(
        purchase_id=pid,
        customer_id=customer.customer_id,
        customer_name=customer.customer_name,
        product_id=product.product_id,
        product_name=product.product_name,
        barcode=product.barcode or req.barcode,
        category=product.category or "General",
        quantity=qty,
        rate=rate,
        total_amount=total_amount,
        payment_method=req.payment_method or "UPI",
        scan_source=req.scan_source or "CAMERA_SCAN",
        purchase_date=pdate
    )
    customer_db.add(purchase)

    # 8. Record in global Sale table for real-time dashboard analytics
    unit_cost = float(product.purchase_price or 0.0)
    db.add(Sale(
        sale_id=sale_id,
        sale_date=pdate,
        customer_name=f"{customer.customer_name} ({customer.customer_id})",
        product_id=product.product_id,
        quantity_sold=qty,
        unit_selling_price=rate,
        line_total=total_amount,
        unit_cost=unit_cost,
        gross_profit_estimate=round(total_amount - (qty * unit_cost), 2),
        payment_method=req.payment_method or "UPI",
        transaction_status="Completed"
    ))

    # 9. Record inventory movement
    db.add(InventoryMovement(
        product_id=product.product_id,
        movement_type="CUSTOMER_BARCODE_SALE",
        quantity_change=-qty,
        previous_stock=current_stock,
        new_stock=product.current_stock,
        reason=f"Customer {customer.customer_name} barcode purchase",
        reference_id=pid
    ))

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    try:
        customer_db.commit()
    except Exception:
        customer_db.rollback()
        product.current_stock = current_stock
        db.query(Sale).filter(Sale.sale_id == sale_id).delete()
        db.query(InventoryMovement).filter(InventoryMovement.reference_id == pid).delete()
        db.commit()
        raise
    customer_db.refresh(purchase)
    return purchase


# ==========================================
# 2. USER DATABASE & PROCUREMENT ENDPOINTS
# ==========================================

@router.get("/users")
def get_all_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "full_name": u.full_name or u.username,
            "role": u.role,
            "email": u.email,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None
        }
        for u in users
    ]


@router.get("/user-purchases", response_model=List[UserPurchaseResponse])
def get_user_purchases(
    limit: int = 100,
    db: Session = Depends(get_db),
    customer_db: Session = Depends(get_customer_db),
    user_db: Session = Depends(get_user_db),
):
    ensure_seed_data(db, customer_db, user_db)
    return user_db.query(UserPurchase).order_by(UserPurchase.created_at.desc()).limit(limit).all()


@router.post("/user-purchases", response_model=UserPurchaseResponse, status_code=status.HTTP_201_CREATED)
def record_user_procurement_purchase(
    req: UserPurchaseCreate,
    db: Session = Depends(get_db),
    customer_db: Session = Depends(get_customer_db),
    user_db: Session = Depends(get_user_db),
):
    """
    Stores full details when staff/admin users buy products from wholesale/suppliers.
    Updates SQLite inventory and optionally modifies product rates in SQLite.
    """
    ensure_seed_data(db, customer_db, user_db)

    product = db.query(Product).filter(Product.product_id == req.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail=f"Product '{req.product_id}' not found in SQLite.")

    supplier_name = "Wholesale Supplier"
    if req.supplier_id:
        supp = db.query(Supplier).filter(Supplier.supplier_id == req.supplier_id).first()
        if supp:
            supplier_name = supp.supplier_name

    qty = float(req.quantity_bought)
    purchase_rate = float(req.purchase_rate)
    selling_rate = float(req.suggested_selling_rate)
    total_cost = round(qty * purchase_rate, 2)
    pdate = req.purchase_date or datetime.date.today().isoformat()
    uid = f"UP_BUY_{uuid.uuid4().hex[:8].upper()}"

    prev_stock = float(product.current_stock or 0.0)
    product.current_stock = prev_stock + qty

    # Modify the rate in SQLite if requested
    if req.update_product_rates:
        old_cost = float(product.purchase_price or 0.0)
        old_sell = float(product.selling_price or 0.0)
        product.purchase_price = purchase_rate
        product.selling_price = selling_rate

        db.add(PriceRateHistory(
            product_id=product.product_id,
            product_name=product.product_name,
            old_purchase_price=old_cost,
            new_purchase_price=purchase_rate,
            old_selling_price=old_sell,
            new_selling_price=selling_rate,
            modified_by=req.user_name or "Store User",
            reason=f"Procurement order {req.invoice_number or uid}"
        ))

    # Verify valid supplier for foreign key
    candidate_sup = req.supplier_id or product.supplier_id or "S001"
    existing_sup = db.query(Supplier).filter(Supplier.supplier_id == candidate_sup).first()
    if not existing_sup and product.supplier_id:
        existing_sup = db.query(Supplier).filter(Supplier.supplier_id == product.supplier_id).first()
    if not existing_sup:
        existing_sup = db.query(Supplier).first()
    target_sup_id = existing_sup.supplier_id if existing_sup else None
    supplier_name = existing_sup.supplier_name if existing_sup else "Wholesale Supplier"

    # Add user purchase record
    user_purchase = UserPurchase(
        user_purchase_id=uid,
        user_name=req.user_name or "Store Admin",
        product_id=product.product_id,
        product_name=product.product_name,
        supplier_id=target_sup_id,
        supplier_name=supplier_name,
        quantity_bought=qty,
        purchase_rate=purchase_rate,
        suggested_selling_rate=selling_rate,
        total_cost=total_cost,
        invoice_number=req.invoice_number or f"INV-{uid[-6:]}",
        payment_status=req.payment_status or "PAID",
        purchase_date=pdate
    )
    user_db.add(user_purchase)

    # Add inventory movement
    db.add(InventoryMovement(
        product_id=product.product_id,
        movement_type="USER_PROCUREMENT",
        quantity_change=qty,
        previous_stock=prev_stock,
        new_stock=product.current_stock,
        reason=f"User procurement purchase from {supplier_name}",
        reference_id=uid
    ))

    # Add lot for expiry management
    exp_days = product.shelf_life_days or 90
    exp_date = (datetime.date.today() + datetime.timedelta(days=exp_days)).isoformat()
    if target_sup_id:
        db.add(InventoryLot(
            lot_id=f"LOT_UP_{uid[-6:]}",
            product_id=product.product_id,
            supplier_id=target_sup_id,
            received_date=pdate,
            expiry_date=exp_date,
            quantity_received=qty,
            quantity_remaining=qty,
            unit_cost=purchase_rate
        ))

    try:
        user_db.commit()
    except Exception:
        user_db.rollback()
        raise
    try:
        db.commit()
    except Exception:
        db.rollback()
        user_db.delete(user_purchase)
        user_db.commit()
        raise
    user_db.refresh(user_purchase)
    return user_purchase


# ==========================================
# 3. DATABASE SUMMARY & KPIS
# ==========================================

@router.get("/summary")
def get_database_summary(
    db: Session = Depends(get_db),
    customer_db: Session = Depends(get_customer_db),
    user_db: Session = Depends(get_user_db),
):
    """
    Returns aggregated metrics for Customer DB, User Procurement DB, and Rate History.
    """
    ensure_seed_data(db, customer_db, user_db)

    # Customer metrics
    total_customers = customer_db.query(Customer).count()
    customer_spend_total = customer_db.query(func.sum(Customer.total_spent)).scalar() or 0.0
    customer_scan_count = customer_db.query(CustomerPurchase).count()

    # User metrics
    total_users = db.query(User).count()
    user_purchases_count = user_db.query(UserPurchase).count()
    user_procurement_cost = user_db.query(func.sum(UserPurchase.total_cost)).scalar() or 0.0

    # Rate modifications count
    total_rate_mods = db.query(PriceRateHistory).count()

    # Top customers
    top_customers = customer_db.query(Customer).order_by(Customer.total_spent.desc()).limit(5).all()

    # Recent scans
    recent_scans = customer_db.query(CustomerPurchase).order_by(CustomerPurchase.created_at.desc()).limit(5).all()

    return {
        "customer_db": {
            "total_customers": total_customers,
            "total_revenue": round(float(customer_spend_total), 2),
            "scan_purchases_count": customer_scan_count,
            "top_customers": [
                {
                    "customer_id": c.customer_id,
                    "customer_name": c.customer_name,
                    "phone": c.phone,
                    "tier": c.loyalty_tier,
                    "total_spent": c.total_spent
                }
                for c in top_customers
            ]
        },
        "user_db": {
            "total_staff_users": total_users,
            "procurement_orders_count": user_purchases_count,
            "total_procurement_cost": round(float(user_procurement_cost), 2),
        },
        "rates": {
            "total_modifications": total_rate_mods,
            "active_products_count": db.query(Product).filter(Product.is_archived == False).count()
        },
        "recent_barcode_scans": [
            {
                "purchase_id": p.purchase_id,
                "customer_name": p.customer_name,
                "product_name": p.product_name,
                "barcode": p.barcode,
                "rate": p.rate,
                "quantity": p.quantity,
                "total_amount": p.total_amount,
                "date": p.purchase_date
            }
            for p in recent_scans
        ]
    }


# ==========================================
# 4. FULL EXCEL REPORT GENERATION (.xlsx)
# ==========================================

@router.get("/export-excel")
def export_full_database_excel(
    db: Session = Depends(get_db),
    customer_db: Session = Depends(get_customer_db),
    user_db: Session = Depends(get_user_db),
):
    """
    Downloads comprehensive multi-sheet Excel file containing:
    1. Customer Barcode Purchases
    2. User Procurement Orders
    3. Product Catalog & Rates
    4. Price Rate Modification History
    5. Customer Directory
    """
    ensure_seed_data(db, customer_db, user_db)

    wb = openpyxl.Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    # Styles
    header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")
    border_thin = Border(
        left=Side(style='thin', color='E2E8F0'),
        right=Side(style='thin', color='E2E8F0'),
        top=Side(style='thin', color='E2E8F0'),
        bottom=Side(style='thin', color='E2E8F0')
    )

    def style_header(ws, headers):
        ws.append(headers)
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = align_center

    # Sheet 1: Customer Purchases via Barcode Scan
    ws1 = wb.create_sheet(title="Customer Scan Purchases")
    headers1 = [
        "Purchase ID", "Purchase Date", "Customer ID", "Customer Name", "Customer Phone",
        "Product ID", "Product Name", "Barcode", "Category", "Quantity Bought", "Unit Rate (₹)",
        "Total Amount (₹)", "Payment Method", "Scan Source"
    ]
    style_header(ws1, headers1)
    purchases = customer_db.query(CustomerPurchase).order_by(CustomerPurchase.purchase_date.desc()).all()
    # Pre-map customer phones
    cust_phones = {c.customer_id: (c.phone or "N/A") for c in customer_db.query(Customer).all()}
    for p in purchases:
        ws1.append([
            p.purchase_id, p.purchase_date, p.customer_id, p.customer_name,
            cust_phones.get(p.customer_id, "N/A"), p.product_id, p.product_name,
            p.barcode or "N/A", p.category, p.quantity, p.rate, p.total_amount,
            p.payment_method, p.scan_source
        ])
    ws1.column_dimensions['A'].width = 16
    ws1.column_dimensions['D'].width = 20
    ws1.column_dimensions['E'].width = 16
    ws1.column_dimensions['F'].width = 16
    ws1.column_dimensions['G'].width = 24
    ws1.column_dimensions['H'].width = 16

    # Sheet 2: User Procurement Orders
    ws2 = wb.create_sheet(title="User Procurement Orders")
    headers2 = [
        "Procurement ID", "Date", "Staff User", "Product Name", "Supplier",
        "Quantity Bought", "Cost Rate (₹)", "Retail Selling Rate (₹)", "Total Cost (₹)", "Invoice No", "Status"
    ]
    style_header(ws2, headers2)
    user_orders = user_db.query(UserPurchase).order_by(UserPurchase.purchase_date.desc()).all()
    for u in user_orders:
        ws2.append([
            u.user_purchase_id, u.purchase_date, u.user_name, u.product_name, u.supplier_name or "Wholesale",
            u.quantity_bought, u.purchase_rate, u.suggested_selling_rate, u.total_cost, u.invoice_number, u.payment_status
        ])
    ws2.column_dimensions['A'].width = 16
    ws2.column_dimensions['D'].width = 24
    ws2.column_dimensions['E'].width = 22

    # Sheet 3: Product Catalog & Rates
    ws3 = wb.create_sheet(title="Products & Active Rates")
    headers3 = [
        "Product ID", "Barcode", "Product Name", "Category", "Current Stock",
        "Cost Rate (₹)", "Selling Rate (₹)", "Margin (₹)", "Margin %"
    ]
    style_header(ws3, headers3)
    products = db.query(Product).filter(Product.is_archived == False).order_by(Product.category.asc()).all()
    for p in products:
        cost = p.purchase_price or 0.0
        sell = p.selling_price or 0.0
        margin = sell - cost
        margin_pct = f"{round((margin / sell) * 100, 1)}%" if sell > 0 else "0%"
        ws3.append([
            p.product_id, p.barcode or "N/A", p.product_name, p.category,
            p.current_stock, cost, sell, round(margin, 2), margin_pct
        ])
    ws3.column_dimensions['A'].width = 12
    ws3.column_dimensions['B'].width = 16
    ws3.column_dimensions['C'].width = 26

    # Sheet 4: Price Rate Modification History
    ws4 = wb.create_sheet(title="Rate Modification History")
    headers4 = [
        "Log ID", "Date / Time", "Product ID", "Product Name",
        "Old Cost (₹)", "New Cost (₹)", "Old Retail Rate (₹)", "New Retail Rate (₹)", "Modified By", "Reason"
    ]
    style_header(ws4, headers4)
    rate_history = db.query(PriceRateHistory).order_by(PriceRateHistory.timestamp.desc()).all()
    for r in rate_history:
        ws4.append([
            r.id, r.timestamp.strftime("%Y-%m-%d %H:%M:%S") if r.timestamp else "",
            r.product_id, r.product_name, r.old_purchase_price, r.new_purchase_price,
            r.old_selling_price, r.new_selling_price, r.modified_by, r.reason
        ])
    ws4.column_dimensions['D'].width = 24
    ws4.column_dimensions['J'].width = 24

    # Sheet 5: Customer Directory
    ws5 = wb.create_sheet(title="Customers Directory")
    headers5 = [
        "Customer ID", "Customer Name", "Phone", "Email", "City",
        "Loyalty Tier", "Total Spent (₹)", "Total Purchases"
    ]
    style_header(ws5, headers5)
    customers = customer_db.query(Customer).order_by(Customer.total_spent.desc()).all()
    for c in customers:
        ws5.append([
            c.customer_id, c.customer_name, c.phone or "N/A", c.email or "N/A",
            c.city, c.loyalty_tier, c.total_spent, c.total_purchases_count
        ])
    ws5.column_dimensions['A'].width = 14
    ws5.column_dimensions['B'].width = 22
    ws5.column_dimensions['D'].width = 24

    # Output buffer
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    filename = f"StockSense_Full_Database_Report_{datetime.date.today().isoformat()}.xlsx"

    return Response(
        content=out.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ==========================================
# 5. EXCEL FILE ANALYSIS (Analyze Excel File)
# ==========================================

@router.post("/analyze-excel")
async def analyze_uploaded_excel(
    file: UploadFile = File(...)
):
    """
    Accepts an uploaded Excel (.xlsx, .xls) or CSV file, performs deep statistical analysis,
    and returns metrics, category distribution, rate statistics, top transactions, and insights.
    """
    filename = file.filename or "uploaded file"
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    raw_data = []
    sheet_names = []
    if filename.lower().endswith(".csv"):
        import csv
        text = contents.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        sheet_names = ["CSV Data"]
        raw_data.extend(row for row in reader if any(value for value in row.values()))
    elif filename.lower().endswith(".xlsx"):
        try:
            wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True, read_only=True)
        except (BadZipFile, OSError, ValueError, openpyxl.utils.exceptions.InvalidFileException) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid Excel workbook: {exc}") from exc
        sheet_names = wb.sheetnames
        for ws in wb.worksheets:
            headers = [str(cell.value or "").strip() for cell in ws[1]]
            raw_data.extend(
                dict(zip(headers, row))
                for row in ws.iter_rows(min_row=2, values_only=True)
                if any(value is not None and str(value).strip() for value in row)
            )
        wb.close()
    else:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Upload a .xlsx workbook or .csv file; convert legacy .xls files first."
        )

    total_rows = len(raw_data)
    if total_rows == 0:
        return {
            "file_name": filename,
            "total_rows": 0,
            "sheets": sheet_names,
            "summary": "No data found in uploaded workbook."
        }

    def normalized_header(value):
        return "".join(char for char in str(value).lower() if char.isalnum())

    def number_value(value):
        if value is None:
            return None
        text = str(value).strip().replace("₹", "").replace("$", "").replace(",", "")
        if text.startswith("(") and text.endswith(")"):
            text = "-" + text[1:-1]
        try:
            return float(text)
        except (ValueError, TypeError):
            return None

    columns = list(dict.fromkeys(key for row in raw_data for key in row.keys() if key))
    detected_amount_cols = [
        key for key in columns
        if any(token in normalized_header(key) for token in ("totalamount", "amount", "totalcost", "totalvalue"))
    ]
    detected_price_cols = [
        key for key in columns
        if any(token in normalized_header(key) for token in ("rate", "price", "unitcost", "costrate"))
        and key not in detected_amount_cols
    ]
    detected_qty_cols = [
        key for key in columns
        if any(token in normalized_header(key) for token in ("quantity", "qty", "units"))
    ]
    detected_cat_cols = [
        key for key in columns
        if any(token in normalized_header(key) for token in ("category", "group", "department"))
    ]
    detected_name_cols = [
        key for key in columns
        if any(token in normalized_header(key) for token in ("productname", "itemname", "description", "name"))
    ]

    total_financial_volume = 0.0
    all_rates = []
    category_counts = {}
    item_frequencies = {}
    for r in raw_data:
        quantity = number_value(r.get(detected_qty_cols[0])) if detected_qty_cols else None
        unit_rate = number_value(r.get(detected_price_cols[0])) if detected_price_cols else None
        amount = number_value(r.get(detected_amount_cols[0])) if detected_amount_cols else None
        if amount is not None:
            total_financial_volume += amount
        elif unit_rate is not None:
            total_financial_volume += unit_rate * quantity if quantity is not None else unit_rate
        if unit_rate is not None:
            all_rates.append(unit_rate)
        elif amount is not None:
            all_rates.append(amount)

        if detected_cat_cols:
            c = str(r.get(detected_cat_cols[0]) or "General").strip()
            category_counts[c] = category_counts.get(c, 0) + 1
        if detected_name_cols:
            it = str(r.get(detected_name_cols[0]) or "Item").strip()
            item_frequencies[it] = item_frequencies.get(it, 0) + 1

    avg_rate = round(sum(all_rates) / len(all_rates), 2) if all_rates else 0.0
    min_rate = round(min(all_rates), 2) if all_rates else 0.0
    max_rate = round(max(all_rates), 2) if all_rates else 0.0

    top_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    top_items = sorted(item_frequencies.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "file_name": filename,
        "sheets": sheet_names,
        "total_rows": total_rows,
        "columns_detected": columns,
        "analysis": {
            "total_monetary_value": round(total_financial_volume, 2),
            "average_rate": avg_rate,
            "min_rate": min_rate,
            "max_rate": max_rate,
            "top_categories": [{"category": k, "count": v} for k, v in top_categories],
            "top_frequent_items": [{"item": k, "count": v} for k, v in top_items],
            "insights": [
                f"File contains {total_rows} recorded entries across {len(sheet_names)} sheet(s).",
                f"Average monetary rate is ₹{avg_rate} (Range: ₹{min_rate} to ₹{max_rate}).",
                f"Dominant category: {top_categories[0][0]} with {top_categories[0][1]} rows." if top_categories else "Varied product distribution."
            ]
        }
    }
