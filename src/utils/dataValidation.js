import * as XLSX from 'xlsx';

// Expected Schema Definitions
export const SCHEMAS = {
  products: {
    required: ['product_id', 'product_name', 'category', 'purchase_price', 'selling_price', 'current_stock'],
    optional: ['brand', 'unit', 'supplier_id', 'supplier_name', 'supplier_lead_time_days', 'shelf_life_days', 'supplier_pack_size', 'minimum_order_qty', 'reorder_safety_stock_days', 'storage_capacity_units', 'perishable'],
    numeric: ['purchase_price', 'selling_price', 'current_stock', 'supplier_lead_time_days', 'shelf_life_days', 'supplier_pack_size', 'minimum_order_qty', 'storage_capacity_units']
  },
  sales: {
    required: ['sale_date', 'product_id', 'quantity_sold'],
    optional: ['sale_id', 'product_name', 'category', 'unit_selling_price', 'line_total', 'unit_cost', 'gross_profit_estimate', 'customer_name', 'payment_method', 'transaction_status'],
    numeric: ['quantity_sold', 'unit_selling_price', 'line_total', 'unit_cost']
  },
  lots: {
    required: ['lot_id', 'product_id', 'expiry_date', 'quantity_remaining'],
    optional: ['product_name', 'supplier_id', 'received_date', 'unit_cost'],
    numeric: ['quantity_remaining', 'unit_cost']
  }
};

// Parse an uploaded file buffer into sheet objects
export const parseUploadedFile = async (file) => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();

    reader.onload = (e) => {
      try {
        const data = new Uint8Array(e.target.result);
        const workbook = XLSX.read(data, { type: 'array', cellDates: true });
        
        const sheetsData = {};
        workbook.SheetNames.forEach(sheetName => {
          const worksheet = workbook.Sheets[sheetName];
          const json = XLSX.utils.sheet_to_json(worksheet, { defval: '' });
          sheetsData[sheetName] = json;
        });

        resolve({
          fileName: file.name,
          fileSize: file.size,
          sheetNames: workbook.SheetNames,
          sheets: sheetsData
        });
      } catch (err) {
        reject(new Error(`Failed to parse file: ${err.message}`));
      }
    };

    reader.onerror = () => reject(new Error('Failed to read file from disk.'));
    reader.readAsArrayBuffer(file);
  });
};

// Validate a dataset against a target schema
export const validateDataset = (dataRows, type = 'products') => {
  const schema = SCHEMAS[type];
  if (!schema) return { valid: false, errors: ['Unknown schema type'], warnings: [] };

  if (!dataRows || !Array.isArray(dataRows) || dataRows.length === 0) {
    return { valid: false, errors: ['The uploaded file or sheet contains no rows.'], warnings: [] };
  }

  const columns = Object.keys(dataRows[0]);
  const errors = [];
  const warnings = [];

  // 1. Check required columns
  const missingCols = schema.required.filter(req => !columns.includes(req));
  if (missingCols.length > 0) {
    errors.push(`Missing mandatory columns: ${missingCols.join(', ')}`);
  }

  // 2. Validate row values (check first 200 rows for speed)
  const rowsToCheck = dataRows.slice(0, 200);
  let negativeCount = 0;
  let emptyRequiredCount = 0;

  rowsToCheck.forEach((row, idx) => {
    // Check required values
    schema.required.forEach(req => {
      if (row[req] === undefined || row[req] === null || String(row[req]).trim() === '') {
        emptyRequiredCount++;
      }
    });

    // Check numeric non-negative values
    schema.numeric.forEach(numKey => {
      if (row[numKey] !== undefined && row[numKey] !== '') {
        const val = Number(row[numKey]);
        if (isNaN(val)) {
          errors.push(`Row ${idx + 1}: Column "${numKey}" has invalid non-numeric value "${row[numKey]}".`);
        } else if (val < 0) {
          negativeCount++;
        }
      }
    });
  });

  if (negativeCount > 0) {
    errors.push(`Found ${negativeCount} instance(s) of negative quantities or prices. Values must be non-negative.`);
  }

  if (emptyRequiredCount > 0) {
    warnings.push(`Found ${emptyRequiredCount} row(s) with empty values in recommended fields.`);
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
    rowCount: dataRows.length,
    columns
  };
};

// Download Sample Templates
export const downloadSampleTemplate = (type = 'products') => {
  let sampleData = [];
  let filename = 'StockSense_Sample_Template.xlsx';

  if (type === 'products') {
    filename = 'StockSense_Products_Template.xlsx';
    sampleData = [
      {
        product_id: 'P101',
        product_name: 'Organic Honey 250g',
        category: 'Staples',
        brand: 'BeePure',
        unit: 'jar',
        purchase_price: 120,
        selling_price: 160,
        current_stock: 15,
        supplier_id: 'S001',
        supplier_name: 'FreshFarm Distributors',
        supplier_lead_time_days: 2,
        shelf_life_days: 365,
        supplier_pack_size: 6,
        minimum_order_qty: 6,
        reorder_safety_stock_days: 2,
        storage_capacity_units: 50,
        perishable: false
      },
      {
        product_id: 'P102',
        product_name: 'Greek Yogurt 100g',
        category: 'Dairy',
        brand: 'DailyFresh',
        unit: 'cup',
        purchase_price: 35,
        selling_price: 50,
        current_stock: 8,
        supplier_id: 'S001',
        supplier_name: 'FreshFarm Distributors',
        supplier_lead_time_days: 1,
        shelf_life_days: 14,
        supplier_pack_size: 4,
        minimum_order_qty: 8,
        reorder_safety_stock_days: 1,
        storage_capacity_units: 40,
        perishable: true
      }
    ];
  } else if (type === 'sales') {
    filename = 'StockSense_Sales_Template.xlsx';
    sampleData = [
      {
        sale_date: '2026-09-30',
        product_id: 'P001',
        quantity_sold: 5,
        unit_selling_price: 32,
        payment_method: 'UPI',
        transaction_status: 'Completed'
      },
      {
        sale_date: '2026-09-30',
        product_id: 'P002',
        quantity_sold: 4,
        unit_selling_price: 40,
        payment_method: 'Cash',
        transaction_status: 'Completed'
      }
    ];
  } else if (type === 'lots') {
    filename = 'StockSense_Lots_Template.xlsx';
    sampleData = [
      {
        lot_id: 'LOT1001',
        product_id: 'P001',
        received_date: '2026-09-25',
        expiry_date: '2026-10-02',
        quantity_remaining: 10,
        unit_cost: 25
      }
    ];
  }

  const ws = XLSX.utils.json_to_sheet(sampleData);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, 'Template');
  XLSX.writeFile(wb, filename);
};
