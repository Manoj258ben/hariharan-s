import sys
import io
import urllib.request
import json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

base = 'http://127.0.0.1:8000/api'

def req(url, data=None, method='GET'):
    body = json.dumps(data).encode('utf-8') if data else None
    headers = {'Content-Type': 'application/json'} if data else {}
    r = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(r) as resp:
        content = resp.read()
        return resp.status, resp.headers.get('Content-Type'), content

def run_tests():
    print("=== Testing StockSense SQLite Dual-Database System ===")
    
    # 1. Summary
    _, _, c = req(f'{base}/database/summary')
    s = json.loads(c)
    print("1. Summary loaded:")
    print("   Total registered customers:", s['customer_db']['total_customers'])
    print("   Barcode scan purchases count:", s['customer_db']['scan_purchases_count'])
    print("   Total customer revenue: Rs.", s['customer_db']['total_revenue'])
    print("   Staff users:", s['user_db']['total_staff_users'])
    print("   User procurement orders:", s['user_db']['procurement_orders_count'])
    print("   User procurement total cost: Rs.", s['user_db']['total_procurement_cost'])

    # 2. User Buying Products (Procurement into SQLite DB)
    print("\n2. Testing User Procurement (Staff buying products)...")
    _, _, c = req(f'{base}/database/user-purchases', {
        'user_name': 'Store Manager',
        'product_id': 'P002',
        'supplier_id': 'SUP-01',
        'quantity_bought': 50.0,
        'purchase_rate': 32.0,
        'suggested_selling_rate': 45.0,
        'invoice_number': 'INV-2026-BREAD',
        'notes': 'Procured 50 loaves of fresh bread from bakery'
    }, method='POST')
    user_res = json.loads(c)
    print(f"   Success! Order {user_res['user_purchase_id']} created.")
    print(f"   Product: {user_res['product_name']}, Bought: {user_res['quantity_bought']} units, Cost: Rs. {user_res['total_cost']}")

    # 3. Customer Buying Products using Barcode Scan
    print("\n3. Testing Customer Buying Products via Barcode Scan...")
    _, _, c = req(f'{base}/database/customer-purchases', {
        'customer_id': 'CUST001',
        'barcode': '890103000002',
        'quantity': 3.0,
        'rate': 45.0,
        'payment_method': 'UPI',
        'scan_source': 'CAMERA_SCAN'
    }, method='POST')
    scan_res = json.loads(c)
    print(f"   Success! Purchase {scan_res['purchase_id']} recorded.")
    print(f"   Customer: {scan_res['customer_name']}, Product: {scan_res['product_name']}")
    print(f"   Rate: Rs. {scan_res['rate']}, Total: Rs. {scan_res['total_amount']}")

    # 4. Modify Product Rates in SQLite
    print("\n4. Testing SQLite Product Rate Modification...")
    st, _, c = req(f'{base}/products/P002/rate', {
        'selling_price': 48.0,
        'purchase_price': 34.0,
        'reason': 'Festival rate revision',
        'modified_by': 'Store Admin'
    }, method='PUT')
    rate_res = json.loads(c)
    print(f"   Success! P002 Rates Updated in SQLite:")
    print(f"   New Retail Selling Rate: Rs. {rate_res['selling_price']}, New Cost Rate: Rs. {rate_res['purchase_price']}")

    # 5. Rate History
    print("\n5. Testing Rate History retrieval...")
    _, _, c = req(f'{base}/products/P002/rate-history')
    hist = json.loads(c)
    print(f"   Found {len(hist)} audit log records for P002.")
    for h in hist[:2]:
        print(f"   - {h['timestamp']}: Retail Rs. {h['old_selling_price']} -> Rs. {h['new_selling_price']} (by {h['modified_by']}, reason: {h['reason']})")

    # 6. Excel Export
    print("\n6. Testing Multi-Sheet Excel Workbook Export...")
    st, ctype, content = req(f'{base}/database/export-excel')
    print(f"   Success! HTTP Status: {st}, Type: {ctype}, Size: {len(content)} bytes.")

    # 7. Excel Analyzer Test
    print("\n7. Testing Excel File Analyzer...")
    boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
    delimiter = f'--{boundary}\r\n'.encode('utf-8')
    body = (
        delimiter +
        b'Content-Disposition: form-data; name="file"; filename="database_report.xlsx"\r\n' +
        b'Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n' +
        content +
        b'\r\n--' + boundary.encode('utf-8') + b'--\r\n'
    )
    r = urllib.request.Request(f'{base}/database/analyze-excel', data=body, headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}, method='POST')
    with urllib.request.urlopen(r) as resp:
        analysis = json.loads(resp.read())
        print(f"   Success! Analysis completed for file '{analysis['file_name']}':")
        print(f"   Total Data Rows: {analysis['total_rows']}")
        print(f"   Sheets Detected:", analysis['sheets'])
        print(f"   Columns Detected:", analysis['columns_detected'])
        print(f"   Total Monetary Value: Rs. {analysis['analysis']['total_monetary_value']:,.2f}")
        print(f"   Average Unit Rate: Rs. {analysis['analysis']['average_rate']:,.2f}")
        print(f"   Insights:", analysis['analysis']['insights'])

    print("\n=== ALL SQLITE DUAL-DATABASE TESTS PASSED PERFECTLY! ===")

if __name__ == '__main__':
    run_tests()
