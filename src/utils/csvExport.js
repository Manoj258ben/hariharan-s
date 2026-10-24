/**
 * CSV Export & WhatsApp Order Text Generator
 */

// Universal CSV downloader
export const downloadCSV = (filename, rows, headers) => {
  if (!rows || !rows.length) {
    alert('No data to export.');
    return;
  }

  const csvRows = [];
  // Header row
  csvRows.push(headers.map(h => `"${(h.label || h).toString().replace(/"/g, '""')}"`).join(','));

  // Data rows
  rows.forEach(row => {
    const values = headers.map(h => {
      const key = h.key || h;
      const val = row[key] !== undefined && row[key] !== null ? row[key] : '';
      return `"${val.toString().replace(/"/g, '""')}"`;
    });
    csvRows.push(values.join(','));
  });

  const csvString = '\uFEFF' + csvRows.join('\r\n'); // UTF-8 BOM for Excel compatibility
  const blob = new Blob([csvString], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.setAttribute('href', url);
  link.setAttribute('download', filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
};

// Export Reorder Recommendations to CSV
export const exportReorderListCSV = (reorderItems, asOfDate = '2026-09-30') => {
  const headers = [
    { key: 'rank', label: 'Priority Rank' },
    { key: 'product_id', label: 'Product ID' },
    { key: 'product_name', label: 'Product Name' },
    { key: 'category', label: 'Category' },
    { key: 'urgency', label: 'Urgency Status' },
    { key: 'dailyAverageDemand', label: 'Daily Average Demand' },
    { key: 'supplier_lead_time_days', label: 'Lead Time (Days)' },
    { key: 'daysOfStockLeft', label: 'Days Stock Left' },
    { key: 'usableStock', label: 'Current Usable Stock' },
    { key: 'targetStock', label: 'Target Stock' },
    { key: 'suggestedOrderQuantity', label: 'Recommended Order Qty' },
    { key: 'supplier_pack_size', label: 'Pack Size' },
    { key: 'purchasePrice', label: 'Purchase Price (INR)' },
    { key: 'estimatedOrderCost', label: 'Estimated Order Cost (INR)' },
    { key: 'expectedGrossProfit', label: 'Expected Gross Profit (INR)' },
    { key: 'supplier_name', label: 'Supplier Name' }
  ];

  const rows = reorderItems.map((item, idx) => ({
    ...item,
    rank: idx + 1
  }));

  downloadCSV(`StockSense_Reorder_List_${asOfDate}.csv`, rows, headers);
};

// Export Inventory to CSV
export const exportInventoryCSV = (products, asOfDate = '2026-09-30') => {
  const headers = [
    { key: 'product_id', label: 'Product ID' },
    { key: 'product_name', label: 'Product Name' },
    { key: 'category', label: 'Category' },
    { key: 'brand', label: 'Brand' },
    { key: 'unit', label: 'Unit' },
    { key: 'purchase_price', label: 'Purchase Price (INR)' },
    { key: 'selling_price', label: 'Selling Price (INR)' },
    { key: 'current_stock', label: 'Current Stock' },
    { key: 'supplier_name', label: 'Supplier' },
    { key: 'supplier_lead_time_days', label: 'Lead Time (Days)' },
    { key: 'shelf_life_days', label: 'Shelf Life (Days)' },
    { key: 'perishable', label: 'Perishable' },
    { key: 'storage_capacity_units', label: 'Storage Capacity' }
  ];

  downloadCSV(`StockSense_Inventory_${asOfDate}.csv`, products, headers);
};

// Export Expiry Report to CSV
export const exportExpiryCSV = (lots, asOfDate = '2026-09-30') => {
  const headers = [
    { key: 'lot_id', label: 'Lot/Batch ID' },
    { key: 'product_name', label: 'Product Name' },
    { key: 'received_date', label: 'Received Date' },
    { key: 'expiry_date', label: 'Expiry Date' },
    { key: 'quantity_remaining', label: 'Remaining Qty' },
    { key: 'unit_cost', label: 'Unit Cost (INR)' },
    { key: 'cost_at_risk', label: 'Cost at Risk (INR)' },
    { key: 'days_until_expiry', label: 'Days Until Expiry' },
    { key: 'status', label: 'Expiry Status' }
  ];

  const asOfTime = new Date(asOfDate).getTime();
  const rows = lots.map(l => {
    const expTime = new Date(l.expiry_date).getTime();
    const daysUntil = Math.ceil((expTime - asOfTime) / (24 * 60 * 60 * 1000));
    const costAtRisk = (Number(l.quantity_remaining) || 0) * (Number(l.unit_cost) || 0);
    const status = daysUntil <= 0 ? 'EXPIRED' : daysUntil <= 7 ? 'EXPIRING SOON' : 'SAFE';

    return {
      lot_id: l.lot_id,
      product_name: l.product_name,
      received_date: l.received_date,
      expiry_date: l.expiry_date,
      quantity_remaining: l.quantity_remaining,
      unit_cost: l.unit_cost,
      cost_at_risk: costAtRisk,
      days_until_expiry: daysUntil,
      status
    };
  });

  downloadCSV(`StockSense_Expiry_Report_${asOfDate}.csv`, rows, headers);
};

// Generate Supplier-Ready WhatsApp Text
export const generateWhatsAppOrderText = (reorderItems, storeName = 'My Kirana Store', targetSupplierId = null, asOfDate = '2026-09-30') => {
  const itemsToOrder = reorderItems.filter(item => {
    const matchesSupplier = !targetSupplierId || item.supplier_id === targetSupplierId;
    return matchesSupplier && (item.suggestedOrderQuantity > 0 || item.urgency === 'REVIEW');
  });

  if (!itemsToOrder.length) {
    return 'No items currently recommended for reorder.';
  }

  // Group by Supplier
  const grouped = {};
  itemsToOrder.forEach(item => {
    const sName = item.supplier_name || 'General Supplier';
    if (!grouped[sName]) grouped[sName] = [];
    grouped[sName].push(item);
  });

  let message = `🛒 *PURCHASE ORDER — ${storeName.toUpperCase()}*\n`;
  message += `📅 *Date:* ${asOfDate}\n`;
  message += `------------------------------------\n\n`;

  let grandTotal = 0;

  Object.entries(grouped).forEach(([supplierName, items]) => {
    message += `🏢 *Supplier:* ${supplierName}\n`;
    let supplierSubtotal = 0;

    items.forEach((item, idx) => {
      const qty = item.suggestedOrderQuantity;
      const cost = item.estimatedOrderCost;
      supplierSubtotal += cost;
      const packNote = item.supplier_pack_size > 1 ? ` (${Math.ceil(qty / item.supplier_pack_size)} packs of ${item.supplier_pack_size})` : '';
      message += `${idx + 1}. *${item.product_name}* — ${qty} ${item.unit || 'units'}${packNote} [₹${cost}]\n`;
    });

    message += `👉 *Subtotal:* ₹${supplierSubtotal.toLocaleString('en-IN')}\n\n`;
    grandTotal += supplierSubtotal;
  });

  message += `------------------------------------\n`;
  message += `💰 *TOTAL ESTIMATED VALUE:* ₹${grandTotal.toLocaleString('en-IN')}\n`;
  message += `🚚 *Please confirm delivery slot and dispatch!*\n`;
  message += `_Generated via StockSense Reorder Planner_`;

  return message;
};
