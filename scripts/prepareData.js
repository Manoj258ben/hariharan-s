import fs from 'fs';
import xlsx from 'xlsx';

const wb = xlsx.readFile('StockSense_Demo_Data_With_Manual_Stock_and_Today.xlsx');

// 1. Config
const configSheet = xlsx.utils.sheet_to_json(wb.Sheets['Config']);
const config = {
  asOfDate: '2026-09-30',
  safetyStockDays: 2,
  expiryBufferDays: 1,
  forecastWindowDays: 90,
  serviceLevelTarget: 0.95,
  storeName: 'My Kirana Store'
};

// 2. Suppliers from Excel
const suppliersExcel = xlsx.utils.sheet_to_json(wb.Sheets['Suppliers']);

// 3. Products from Excel & Current Inventory
const productsExcel = xlsx.utils.sheet_to_json(wb.Sheets['Products']);
const currentInvExcel = xlsx.utils.sheet_to_json(wb.Sheets['Current Inventory']);
const lotsExcel = xlsx.utils.sheet_to_json(wb.Sheets['Inventory Lots']);

const initialProducts = [];

productsExcel.forEach(p => {
  const inv = currentInvExcel.find(c => c.product_id === p.product_id) || {};
  initialProducts.push({
    product_id: p.product_id,
    product_name: p.product_name,
    category: p.category,
    brand: p.brand || 'Generic',
    unit: p.unit || 'pack',
    purchase_price: Number(p.purchase_price),
    selling_price: Number(p.selling_price),
    current_stock: inv.usable_stock !== undefined ? Number(inv.usable_stock) : (inv.current_stock_on_hand || 10),
    stock_on_hand: inv.current_stock_on_hand !== undefined ? Number(inv.current_stock_on_hand) : 10,
    supplier_id: p.supplier_id,
    supplier_name: p.supplier_name,
    supplier_lead_time_days: Number(p.supplier_lead_time_days || 2),
    shelf_life_days: Number(p.shelf_life_days || 30),
    supplier_pack_size: Number(p.supplier_pack_size || 1),
    minimum_order_qty: Number(p.minimum_order_qty || 1),
    reorder_safety_stock_days: Number(p.reorder_safety_stock_days || 2),
    storage_capacity_units: Number(p.storage_capacity_units || 100),
    perishable: Boolean(p.perishable)
  });
});

// Additional 20 products to make rich 32-item catalog covering Kirana staples, dairy, snacks, bakery, plus 2 NEW review items
const extraProducts = [
  {
    product_id: 'P013',
    product_name: 'Butter 100g',
    category: 'Dairy',
    brand: 'DailyFresh',
    unit: 'pack',
    purchase_price: 48,
    selling_price: 58,
    current_stock: 45,
    stock_on_hand: 45,
    supplier_id: 'S001',
    supplier_name: 'FreshFarm Distributors',
    supplier_lead_time_days: 2,
    shelf_life_days: 60,
    supplier_pack_size: 5,
    minimum_order_qty: 10,
    reorder_safety_stock_days: 2,
    storage_capacity_units: 80,
    perishable: true
  },
  {
    product_id: 'P014',
    product_name: 'Fresh Paneer 200g',
    category: 'Dairy',
    brand: 'FarmNest',
    unit: 'pack',
    purchase_price: 70,
    selling_price: 90,
    current_stock: 4,
    stock_on_hand: 5,
    supplier_id: 'S001',
    supplier_name: 'FreshFarm Distributors',
    supplier_lead_time_days: 1,
    shelf_life_days: 10,
    supplier_pack_size: 2,
    minimum_order_qty: 6,
    reorder_safety_stock_days: 1,
    storage_capacity_units: 40,
    perishable: true
  },
  {
    product_id: 'P015',
    product_name: 'Cheese Slices 200g',
    category: 'Dairy',
    brand: 'DailyFresh',
    unit: 'pack',
    purchase_price: 110,
    selling_price: 140,
    current_stock: 32,
    stock_on_hand: 32,
    supplier_id: 'S001',
    supplier_name: 'FreshFarm Distributors',
    supplier_lead_time_days: 2,
    shelf_life_days: 90,
    supplier_pack_size: 4,
    minimum_order_qty: 8,
    reorder_safety_stock_days: 2,
    storage_capacity_units: 60,
    perishable: true
  },
  {
    product_id: 'P016',
    product_name: 'Pav Buns 6-pack',
    category: 'Bakery',
    brand: 'CityBake',
    unit: 'pack',
    purchase_price: 22,
    selling_price: 30,
    current_stock: 5,
    stock_on_hand: 6,
    supplier_id: 'S002',
    supplier_name: 'City Bakery Supply',
    supplier_lead_time_days: 1,
    shelf_life_days: 4,
    supplier_pack_size: 5,
    minimum_order_qty: 10,
    reorder_safety_stock_days: 1,
    storage_capacity_units: 50,
    perishable: true
  },
  {
    product_id: 'P017',
    product_name: 'Rusk Toast 200g',
    category: 'Bakery',
    brand: 'BakeHouse',
    unit: 'pack',
    purchase_price: 32,
    selling_price: 45,
    current_stock: 48,
    stock_on_hand: 48,
    supplier_id: 'S002',
    supplier_name: 'City Bakery Supply',
    supplier_lead_time_days: 2,
    shelf_life_days: 120,
    supplier_pack_size: 6,
    minimum_order_qty: 12,
    reorder_safety_stock_days: 2,
    storage_capacity_units: 100,
    perishable: false
  },
  {
    product_id: 'P018',
    product_name: 'Brown Eggs 6-pack',
    category: 'Dairy & Eggs',
    brand: 'FarmNest',
    unit: 'pack',
    purchase_price: 45,
    selling_price: 60,
    current_stock: 12,
    stock_on_hand: 12,
    supplier_id: 'S001',
    supplier_name: 'FreshFarm Distributors',
    supplier_lead_time_days: 2,
    shelf_life_days: 21,
    supplier_pack_size: 4,
    minimum_order_qty: 8,
    reorder_safety_stock_days: 2,
    storage_capacity_units: 50,
    perishable: true
  },
  {
    product_id: 'P019',
    product_name: 'Potato Chips 50g',
    category: 'Snacks',
    brand: 'CrispKart',
    unit: 'pack',
    purchase_price: 15,
    selling_price: 20,
    current_stock: 35,
    stock_on_hand: 35,
    supplier_id: 'S003',
    supplier_name: 'Value FMCG Wholesale',
    supplier_lead_time_days: 3,
    shelf_life_days: 120,
    supplier_pack_size: 10,
    minimum_order_qty: 20,
    reorder_safety_stock_days: 2,
    storage_capacity_units: 150,
    perishable: false
  },
  {
    product_id: 'P020',
    product_name: 'Instant Noodles 70g',
    category: 'Snacks',
    brand: 'QuickMeal',
    unit: 'pack',
    purchase_price: 11,
    selling_price: 15,
    current_stock: 110,
    stock_on_hand: 110,
    supplier_id: 'S003',
    supplier_name: 'Value FMCG Wholesale',
    supplier_lead_time_days: 3,
    shelf_life_days: 240,
    supplier_pack_size: 12,
    minimum_order_qty: 24,
    reorder_safety_stock_days: 2,
    storage_capacity_units: 200,
    perishable: false
  },
  {
    product_id: 'P021',
    product_name: 'Salted Peanuts 100g',
    category: 'Snacks',
    brand: 'NutriSnack',
    unit: 'pack',
    purchase_price: 24,
    selling_price: 35,
    current_stock: 22,
    stock_on_hand: 22,
    supplier_id: 'S003',
    supplier_name: 'Value FMCG Wholesale',
    supplier_lead_time_days: 4,
    shelf_life_days: 180,
    supplier_pack_size: 6,
    minimum_order_qty: 12,
    reorder_safety_stock_days: 2,
    storage_capacity_units: 80,
    perishable: false
  },
  {
    product_id: 'P022',
    product_name: 'Wheat Flour (Atta) 5kg',
    category: 'Staples',
    brand: 'ShaktiBhog',
    unit: 'bag',
    purchase_price: 195,
    selling_price: 240,
    current_stock: 8,
    stock_on_hand: 8,
    supplier_id: 'S003',
    supplier_name: 'Value FMCG Wholesale',
    supplier_lead_time_days: 4,
    shelf_life_days: 180,
    supplier_pack_size: 4,
    minimum_order_qty: 8,
    reorder_safety_stock_days: 2,
    storage_capacity_units: 40,
    perishable: false
  },
  {
    product_id: 'P023',
    product_name: 'Toor Dal 1kg',
    category: 'Staples',
    brand: 'BharatGrains',
    unit: 'pack',
    purchase_price: 135,
    selling_price: 165,
    current_stock: 14,
    stock_on_hand: 14,
    supplier_id: 'S003',
    supplier_name: 'Value FMCG Wholesale',
    supplier_lead_time_days: 4,
    shelf_life_days: 365,
    supplier_pack_size: 5,
    minimum_order_qty: 10,
    reorder_safety_stock_days: 2,
    storage_capacity_units: 60,
    perishable: false
  },
  {
    product_id: 'P024',
    product_name: 'Sugar 1kg',
    category: 'Staples',
    brand: 'PureSweet',
    unit: 'pack',
    purchase_price: 42,
    selling_price: 50,
    current_stock: 45,
    stock_on_hand: 45,
    supplier_id: 'S003',
    supplier_name: 'Value FMCG Wholesale',
    supplier_lead_time_days: 3,
    shelf_life_days: 730,
    supplier_pack_size: 10,
    minimum_order_qty: 20,
    reorder_safety_stock_days: 2,
    storage_capacity_units: 120,
    perishable: false
  },
  {
    product_id: 'P025',
    product_name: 'Iodized Salt 1kg',
    category: 'Staples',
    brand: 'OceanPure',
    unit: 'pack',
    purchase_price: 20,
    selling_price: 28,
    current_stock: 65,
    stock_on_hand: 65,
    supplier_id: 'S003',
    supplier_name: 'Value FMCG Wholesale',
    supplier_lead_time_days: 3,
    shelf_life_days: 730,
    supplier_pack_size: 10,
    minimum_order_qty: 20,
    reorder_safety_stock_days: 2,
    storage_capacity_units: 120,
    perishable: false
  },
  {
    product_id: 'P026',
    product_name: 'Tea Leaves 250g',
    category: 'Beverages',
    brand: 'AssamGold',
    unit: 'pack',
    purchase_price: 95,
    selling_price: 130,
    current_stock: 28,
    stock_on_hand: 28,
    supplier_id: 'S004',
    supplier_name: 'Metro Grocery Supply',
    supplier_lead_time_days: 3,
    shelf_life_days: 365,
    supplier_pack_size: 6,
    minimum_order_qty: 12,
    reorder_safety_stock_days: 2,
    storage_capacity_units: 70,
    perishable: false
  },
  {
    product_id: 'P027',
    product_name: 'Instant Coffee 50g',
    category: 'Beverages',
    brand: 'CafeRich',
    unit: 'jar',
    purchase_price: 140,
    selling_price: 185,
    current_stock: 9,
    stock_on_hand: 9,
    supplier_id: 'S004',
    supplier_name: 'Metro Grocery Supply',
    supplier_lead_time_days: 3,
    shelf_life_days: 365,
    supplier_pack_size: 4,
    minimum_order_qty: 8,
    reorder_safety_stock_days: 2,
    storage_capacity_units: 50,
    perishable: false
  },
  {
    product_id: 'P028',
    product_name: 'Packaged Water 1L',
    category: 'Beverages',
    brand: 'AquaClear',
    unit: 'bottle',
    purchase_price: 12,
    selling_price: 20,
    current_stock: 52,
    stock_on_hand: 52,
    supplier_id: 'S004',
    supplier_name: 'Metro Grocery Supply',
    supplier_lead_time_days: 1,
    shelf_life_days: 365,
    supplier_pack_size: 12,
    minimum_order_qty: 24,
    reorder_safety_stock_days: 1,
    storage_capacity_units: 150,
    perishable: false
  },
  {
    product_id: 'P029',
    product_name: 'Mixed Fruit Jam 200g',
    category: 'Condiments',
    brand: 'SweetTreat',
    unit: 'jar',
    purchase_price: 55,
    selling_price: 75,
    current_stock: 20,
    stock_on_hand: 20,
    supplier_id: 'S005',
    supplier_name: 'SweetTreat Wholesale',
    supplier_lead_time_days: 4,
    shelf_life_days: 365,
    supplier_pack_size: 6,
    minimum_order_qty: 12,
    reorder_safety_stock_days: 2,
    storage_capacity_units: 60,
    perishable: false
  },
  {
    product_id: 'P030',
    product_name: 'Dishwash Bar 250g',
    category: 'Household',
    brand: 'SparkleClean',
    unit: 'bar',
    purchase_price: 18,
    selling_price: 25,
    current_stock: 42,
    stock_on_hand: 42,
    supplier_id: 'S004',
    supplier_name: 'Metro Grocery Supply',
    supplier_lead_time_days: 3,
    shelf_life_days: 730,
    supplier_pack_size: 8,
    minimum_order_qty: 16,
    reorder_safety_stock_days: 2,
    storage_capacity_units: 100,
    perishable: false
  },
  // 2 BRAND NEW PRODUCTS with ZERO sales history (REVIEW urgency state!)
  {
    product_id: 'P031',
    product_name: 'Almond Milk 1L',
    category: 'Dairy Alternatives',
    brand: 'NutriPlant',
    unit: 'tetrapack',
    purchase_price: 180,
    selling_price: 230,
    current_stock: 0,
    stock_on_hand: 0,
    supplier_id: 'S001',
    supplier_name: 'FreshFarm Distributors',
    supplier_lead_time_days: 2,
    shelf_life_days: 90,
    supplier_pack_size: 6,
    minimum_order_qty: 6,
    reorder_safety_stock_days: 2,
    storage_capacity_units: 40,
    perishable: true
  },
  {
    product_id: 'P032',
    product_name: 'Organic Quinoa 500g',
    category: 'Health Foods',
    brand: 'SuperGrains',
    unit: 'pouch',
    purchase_price: 160,
    selling_price: 220,
    current_stock: 2,
    stock_on_hand: 2,
    supplier_id: 'S003',
    supplier_name: 'Value FMCG Wholesale',
    supplier_lead_time_days: 4,
    shelf_life_days: 180,
    supplier_pack_size: 4,
    minimum_order_qty: 4,
    reorder_safety_stock_days: 2,
    storage_capacity_units: 30,
    perishable: false
  }
];

const allProducts = [...initialProducts, ...extraProducts];

// 4. Inventory Lots
const allLots = [...lotsExcel];
// Add additional lots for extra products so Expiry Management is rich
allLots.push(
  {
    lot_id: 'LOT0037',
    product_id: 'P014',
    product_name: 'Fresh Paneer 200g',
    supplier_id: 'S001',
    received_date: '2026-09-22',
    expiry_date: '2026-09-28',
    quantity_received: 1,
    quantity_remaining: 1,
    unit_cost: 70,
    lot_status_as_of_2026_09_30: 'Expired',
    days_until_expiry_as_of_2026_09_30: -2,
    disposition_note: 'Demo data only; expired stock should be excluded from usable inventory'
  },
  {
    lot_id: 'LOT0038',
    product_id: 'P014',
    product_name: 'Fresh Paneer 200g',
    supplier_id: 'S001',
    received_date: '2026-09-26',
    expiry_date: '2026-10-02',
    quantity_received: 4,
    quantity_remaining: 4,
    unit_cost: 70,
    lot_status_as_of_2026_09_30: 'Near expiry',
    days_until_expiry_as_of_2026_09_30: 2,
    disposition_note: 'Demo data only; monitor for quick markdown'
  },
  {
    lot_id: 'LOT0039',
    product_id: 'P016',
    product_name: 'Pav Buns 6-pack',
    supplier_id: 'S002',
    received_date: '2026-09-28',
    expiry_date: '2026-10-02',
    quantity_received: 5,
    quantity_remaining: 5,
    unit_cost: 22,
    lot_status_as_of_2026_09_30: 'Near expiry',
    days_until_expiry_as_of_2026_09_30: 2,
    disposition_note: 'Fast turnaround needed'
  },
  {
    lot_id: 'LOT0040',
    product_id: 'P013',
    product_name: 'Butter 100g',
    supplier_id: 'S001',
    received_date: '2026-09-10',
    expiry_date: '2026-11-09',
    quantity_received: 45,
    quantity_remaining: 45,
    unit_cost: 48,
    lot_status_as_of_2026_09_30: 'Usable',
    days_until_expiry_as_of_2026_09_30: 40,
    disposition_note: 'Safe stock'
  }
);

// 5. Daily Sales Aggregates from Excel (16,452 rows aggregated by date and product)
const rawSales = xlsx.utils.sheet_to_json(wb.Sheets['Customer Sales']);
const dailyMap = {};

rawSales.forEach(s => {
  const key = s.sale_date + '___' + s.product_id;
  if (!dailyMap[key]) {
    dailyMap[key] = {
      date: s.sale_date,
      product_id: s.product_id,
      product_name: s.product_name,
      category: s.category,
      qty: 0,
      revenue: 0,
      cost: 0,
      profit: 0
    };
  }
  dailyMap[key].qty += s.quantity_sold;
  dailyMap[key].revenue += s.line_total;
  dailyMap[key].cost += (s.unit_cost * s.quantity_sold);
  dailyMap[key].profit += s.gross_profit_estimate;
});

// Add realistic daily sales aggregates for extraProducts (P013 - P030, NOT P031 and P032)
// Spread over the 183 days (2026-04-01 to 2026-09-30)
const dates = [];
let curDate = new Date('2026-04-01');
const endDate = new Date('2026-09-30');
while (curDate <= endDate) {
  dates.push(curDate.toISOString().slice(0, 10));
  curDate.setDate(curDate.getDate() + 1);
}

// Generate realistic daily sales for extra products
extraProducts.forEach(ep => {
  if (ep.product_id === 'P031' || ep.product_id === 'P032') {
    // New products have zero sales history
    return;
  }
  // Target daily sales volume
  const targetAvg = ep.category === 'Dairy' ? 6 :
                    ep.category === 'Bakery' ? 7 :
                    ep.category === 'Snacks' ? 8 :
                    ep.category === 'Staples' ? 4 :
                    ep.category === 'Beverages' ? 5 : 3;

  dates.forEach((d, idx) => {
    // some day-of-week seasonality (weekends slightly higher)
    const dayOfWeek = new Date(d).getDay();
    const mult = (dayOfWeek === 0 || dayOfWeek === 6) ? 1.3 : 0.9;
    const noise = Math.sin(idx * 0.3) * 2;
    const qty = Math.max(0, Math.round(targetAvg * mult + noise));
    if (qty > 0) {
      const revenue = qty * ep.selling_price;
      const cost = qty * ep.purchase_price;
      const profit = revenue - cost;
      const key = d + '___' + ep.product_id;
      dailyMap[key] = {
        date: d,
        product_id: ep.product_id,
        product_name: ep.product_name,
        category: ep.category,
        qty: qty,
        revenue: revenue,
        cost: cost,
        profit: profit
      };
    }
  });
});

const allDailySales = Object.values(dailyMap);

// 6. Recent Detailed Transactions (Take latest 1,000 completed sales from Excel for Sales History table)
const recentTransactions = rawSales.slice(-1000).map(s => ({
  sale_id: s.sale_id,
  sale_date: s.sale_date,
  customer_id: s.customer_id,
  customer_name: s.customer_name,
  product_id: s.product_id,
  product_name: s.product_name,
  category: s.category,
  quantity_sold: s.quantity_sold,
  unit_selling_price: s.unit_selling_price,
  line_total: s.line_total,
  gross_profit_estimate: s.gross_profit_estimate,
  payment_method: s.payment_method,
  transaction_status: s.transaction_status
}));

// Output file
const outputContent = `// StockSense Initial Sample Dataset
// Sourced from StockSense_Demo_Data_With_Manual_Stock_and_Today.xlsx + small retail kirana extension
// Analysis As-Of Date: 2026-09-30

export const INITIAL_CONFIG = ${JSON.stringify(config, null, 2)};

export const INITIAL_SUPPLIERS = ${JSON.stringify(suppliersExcel, null, 2)};

export const INITIAL_PRODUCTS = ${JSON.stringify(allProducts, null, 2)};

export const INITIAL_LOTS = ${JSON.stringify(allLots, null, 2)};

export const INITIAL_DAILY_SALES = ${JSON.stringify(allDailySales)};

export const INITIAL_TRANSACTIONS = ${JSON.stringify(recentTransactions, null, 2)};
`;

fs.mkdirSync('src/data', { recursive: true });
fs.writeFileSync('src/data/initialData.js', outputContent, 'utf8');
console.log('Successfully wrote src/data/initialData.js!');
console.log('Products:', allProducts.length);
console.log('Daily Sales Aggregates:', allDailySales.length);
console.log('Recent Transactions:', recentTransactions.length);
console.log('Lots:', allLots.length);
