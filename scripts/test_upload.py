import urllib.request
import uuid
import os

def test_upload(filepath):
    boundary = uuid.uuid4().hex
    with open(filepath, 'rb') as f:
        file_bytes = f.read()

    body = (
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="file"; filename="{os.path.basename(filepath)}"\r\n'
        f'Content-Type: application/octet-stream\r\n\r\n'
    ).encode('utf-8') + file_bytes + f'\r\n--{boundary}--\r\n'.encode('utf-8')

    req = urllib.request.Request(
        'http://127.0.0.1:8000/api/imports/workbook',
        data=body,
        headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}
    )

    try:
        with urllib.request.urlopen(req) as resp:
            print(f"[{filepath}] Status: {resp.status}")
            print(f"[{filepath}] Response: {resp.read().decode('utf-8')}")
            return True
    except Exception as e:
        print(f"[{filepath}] Error: {e}")
        if hasattr(e, 'read'):
            print(f"[{filepath}] Details: {e.read().decode('utf-8')}")
        return False

if __name__ == '__main__':
    # 1. Test Excel upload
    test_upload('StockSense_Demo_Data_With_Manual_Stock_and_Today.xlsx')
    
    # 2. Test CSV upload
    csv_file = 'scripts/test_sample.csv'
    with open(csv_file, 'w', encoding='utf-8') as f:
        f.write("product_id,product_name,category,current_stock,purchase_price,selling_price,barcode,supplier_lead_time_days,shelf_life_days\n")
        f.write("P201,Golden Tea 250g,Beverages,35,110.0,145.0,890126202001,2,365\n")
        f.write("P202,Crunchy Cashews 200g,Snacks,28,180.0,240.0,890126202002,3,180\n")
    test_upload(csv_file)

