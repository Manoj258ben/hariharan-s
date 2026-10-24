"""
StockSense SQLite Seeder
Extracts the authentic dataset from StockSense_Demo_Data_With_Manual_Stock_and_Today.xlsx into SQLite.
"""
from pathlib import Path
import datetime
from sqlalchemy.orm import Session
import openpyxl
from ..models import Supplier, Product, Sale, InventoryLot, InventoryMovement, AuditLog

EXCEL_FILE = Path(__file__).resolve().parent.parent.parent.parent / "StockSense_Demo_Data_With_Manual_Stock_and_Today.xlsx"

def seed_database_if_empty(db: Session, force: bool = False):
    """
    Seeds SQLite database from Excel workbook if products table is empty.
    """
    product_count = db.query(Product).count()
    if product_count > 0 and not force:
        print(f"[Seed] Database already contains {product_count} products. Skipping seed.")
        return

    if force:
        print("[Seed] Force resetting database...")
        db.query(Sale).delete()
        db.query(InventoryMovement).delete()
        db.query(InventoryLot).delete()
        db.query(Product).delete()
        db.query(Supplier).delete()
        db.commit()

    if not EXCEL_FILE.exists():
        print(f"[Seed] Excel file {EXCEL_FILE} not found. Skipping Excel seed.")
        return

    print(f"[Seed] Loading data from {EXCEL_FILE}...")
    wb = openpyxl.load_workbook(str(EXCEL_FILE), data_only=True)

    # 1. Seed Suppliers
    if "Suppliers" in wb.sheetnames:
        sheet = wb["Suppliers"]
        headers = [cell.value for cell in sheet[1]]
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if not row[0]:
                continue
            data = dict(zip(headers, row))
            supplier = Supplier(
                supplier_id=str(data["supplier_id"]),
                supplier_name=str(data["supplier_name"]),
                product_specialty=str(data.get("product_specialty", "")),
                typical_delivery_time=str(data.get("typical_delivery_time", "1-2 days")),
                payment_terms=str(data.get("payment_terms", "Net 15")),
                contact_phone_demo=str(data.get("contact_phone_demo", "555-0100"))
            )
            db.merge(supplier)
        db.commit()
        print("[Seed] Suppliers loaded.")

    # 2. Seed Products & Stock
    # Current inventory stock on hand
    stock_map = {}
    if "Current Inventory" in wb.sheetnames:
        c_sheet = wb["Current Inventory"]
        c_headers = [c.value for c in c_sheet[1]]
        for row in c_sheet.iter_rows(min_row=2, values_only=True):
            if not row[0]:
                continue
            c_data = dict(zip(c_headers, row))
            stock_map[str(c_data["product_id"])] = float(c_data.get("usable_stock") or c_data.get("current_stock_on_hand") or 10.0)

    if "Products" in wb.sheetnames:
        sheet = wb["Products"]
        headers = [cell.value for cell in sheet[1]]
        barcode_counter = 890100000001
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if not row[0]:
                continue
            data = dict(zip(headers, row))
            pid = str(data["product_id"])
            current_stk = stock_map.get(pid, 10.0)

            product = Product(
                product_id=pid,
                barcode=str(barcode_counter),
                sku=f"SKU-{pid}",
                product_name=str(data["product_name"]),
                category=str(data.get("category", "General")),
                brand=str(data.get("brand", "Generic")),
                unit=str(data.get("unit", "pack")),
                purchase_price=float(data.get("purchase_price", 0.0)),
                selling_price=float(data.get("selling_price", 0.0)),
                current_stock=current_stk,
                supplier_id=str(data.get("supplier_id", "S001")),
                supplier_lead_time_days=int(data.get("supplier_lead_time_days", 2)),
                shelf_life_days=int(data.get("shelf_life_days", 90)),
                supplier_pack_size=int(data.get("supplier_pack_size", 1)),
                minimum_order_qty=int(data.get("minimum_order_qty", 1)),
                reorder_safety_stock_days=int(data.get("reorder_safety_stock_days", 2)),
                storage_capacity_units=int(data.get("storage_capacity_units", 100)),
                perishable=bool(data.get("perishable", False))
            )
            db.merge(product)
            barcode_counter += 1
        db.commit()
        print("[Seed] Products loaded.")

    # 3. Seed Inventory Lots
    if "Inventory Lots" in wb.sheetnames:
        sheet = wb["Inventory Lots"]
        headers = [cell.value for cell in sheet[1]]
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if not row[0]:
                continue
            data = dict(zip(headers, row))
            lot = InventoryLot(
                lot_id=str(data["lot_id"]),
                product_id=str(data["product_id"]),
                supplier_id=str(data.get("supplier_id", "S001")),
                received_date=str(data.get("received_date", "2026-09-01")),
                expiry_date=str(data["expiry_date"]),
                quantity_received=float(data.get("quantity_received", 10.0)),
                quantity_remaining=float(data.get("quantity_remaining", 10.0)),
                unit_cost=float(data.get("unit_cost", 20.0)),
                disposition_note=str(data.get("disposition_note", ""))
            )
            db.merge(lot)
        db.commit()
        print("[Seed] Inventory lots loaded.")

    # 4. Seed Customer Sales (16,452 transactions)
    if "Customer Sales" in wb.sheetnames:
        sheet = wb["Customer Sales"]
        headers = [cell.value for cell in sheet[1]]
        sales_batch = []
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if not row[0]:
                continue
            data = dict(zip(headers, row))
            sale = Sale(
                sale_id=str(data["sale_id"]),
                sale_date=str(data["sale_date"]),
                customer_id=str(data.get("customer_id", "C001")),
                customer_name=str(data.get("customer_name", "Counter Customer")),
                product_id=str(data["product_id"]),
                quantity_sold=float(data["quantity_sold"]),
                unit_selling_price=float(data["unit_selling_price"]),
                line_total=float(data["line_total"]),
                unit_cost=float(data.get("unit_cost", 0.0)),
                gross_profit_estimate=float(data.get("gross_profit_estimate", 0.0)),
                payment_method=str(data.get("payment_method", "UPI")),
                transaction_status=str(data.get("transaction_status", "Completed"))
            )
            sales_batch.append(sale)
            if len(sales_batch) >= 1000:
                db.bulk_save_objects(sales_batch)
                db.commit()
                sales_batch = []

        if sales_batch:
            db.bulk_save_objects(sales_batch)
            db.commit()
        print("[Seed] 16,452 Customer sales records loaded.")

    # Initial Audit Log
    db.add(AuditLog(
        action="DATABASE_INIT",
        entity="SYSTEM",
        details="Initial SQLite seed loaded from StockSense_Demo_Data_With_Manual_Stock_and_Today.xlsx"
    ))
    db.commit()
    print("[Seed] SQLite database seeding complete!")
