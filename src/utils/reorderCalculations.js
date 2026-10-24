/**
 * StockSense Reorder Calculation Engine
 * Implements deterministic inventory optimization formulas for small retail & Kirana stores
 */

export const calculateProductReorderMetrics = (
  product,
  dailySales = [],
  config = {},
  lots = []
) => {
  const asOfDate = config.asOfDate || '2026-09-30';
  const forecastWindowDays = Number(config.forecastWindowDays) || 90;
  const globalSafetyDays = Number(config.safetyStockDays) || 2;
  const expiryBufferDays = Number(config.expiryBufferDays) || 1;

  // 1. Calculate sales in the analysis window [asOfDate - windowDays, asOfDate]
  const asOfTime = new Date(asOfDate).getTime();
  const windowStartTime = asOfTime - forecastWindowDays * 24 * 60 * 60 * 1000;

  let totalUnitsInWindow = 0;
  let activeSaleDaysCount = 0;

  dailySales.forEach(sale => {
    if (sale.product_id === product.product_id) {
      const saleTime = new Date(sale.date).getTime();
      if (saleTime <= asOfTime && saleTime >= windowStartTime) {
        totalUnitsInWindow += Number(sale.qty) || 0;
        if (Number(sale.qty) > 0) activeSaleDaysCount++;
      }
    }
  });

  const dailyAverageDemand = Number((totalUnitsInWindow / forecastWindowDays).toFixed(2));

  // 2. Lead-Time Demand & Safety Stock
  const supplierLeadTime = Number(product.supplier_lead_time_days) || 1;
  const leadTimeDemand = Number((dailyAverageDemand * supplierLeadTime).toFixed(2));

  const safetyStockDays = product.reorder_safety_stock_days !== undefined && product.reorder_safety_stock_days !== null
    ? Number(product.reorder_safety_stock_days)
    : globalSafetyDays;

  const safetyStock = Number((dailyAverageDemand * safetyStockDays).toFixed(2));
  let targetStock = Number((leadTimeDemand + safetyStock).toFixed(2));

  // 3. Perishable stock cap
  let isPerishableCapped = false;
  let perishableCapValue = null;
  const shelfLifeDays = Number(product.shelf_life_days) || 30;

  if (product.perishable) {
    const effectiveShelfLife = Math.max(shelfLifeDays - expiryBufferDays, 1);
    perishableCapValue = Number((dailyAverageDemand * effectiveShelfLife).toFixed(2));
    if (targetStock > perishableCapValue) {
      targetStock = perishableCapValue;
      isPerishableCapped = true;
    }
  }

  // 4. Usable Stock Calculation (Expiry-aware)
  // Check if product has inventory lots
  const productLots = lots.filter(l => l.product_id === product.product_id);
  let expiredQuantity = 0;
  let nearExpiryQuantity = 0;

  productLots.forEach(lot => {
    const expiryTime = new Date(lot.expiry_date).getTime();
    const daysUntil = Math.ceil((expiryTime - asOfTime) / (24 * 60 * 60 * 1000));
    if (daysUntil <= 0) {
      expiredQuantity += Number(lot.quantity_remaining) || 0;
    } else if (daysUntil <= 7) {
      nearExpiryQuantity += Number(lot.quantity_remaining) || 0;
    }
  });

  // Current stock units entered/edited by user
  let usableStock = Math.max(0, Number(product.current_stock) || 0);

  // Days of stock left
  const daysOfStockLeft = dailyAverageDemand > 0
    ? Number((usableStock / dailyAverageDemand).toFixed(1))
    : (usableStock > 0 ? 999 : 0);

  // 5. Raw Reorder Quantity
  let rawOrderQuantity = Math.max(0, Math.ceil(targetStock - usableStock));

  // Round up to Supplier Pack Size
  const packSize = Math.max(1, Number(product.supplier_pack_size) || 1);
  if (rawOrderQuantity > 0 && packSize > 1) {
    rawOrderQuantity = Math.ceil(rawOrderQuantity / packSize) * packSize;
  }

  // Enforce Minimum Order Quantity (MOQ)
  const minOrderQty = Math.max(1, Number(product.minimum_order_qty) || 1);
  if (rawOrderQuantity > 0 && rawOrderQuantity < minOrderQty) {
    rawOrderQuantity = Math.ceil(minOrderQty / packSize) * packSize;
  }

  // Storage Capacity Checks
  const storageCapacity = Math.max(1, Number(product.storage_capacity_units) || 100);
  const availableCapacity = Math.max(0, storageCapacity - usableStock);

  let suggestedOrderQuantity = rawOrderQuantity;
  let capacityStatus = 'NORMAL';
  let capacityMessage = null;

  if (rawOrderQuantity > 0) {
    if (availableCapacity <= 0) {
      suggestedOrderQuantity = 0;
      capacityStatus = 'FULL';
      capacityMessage = 'Capacity full — no reorder possible';
    } else if (rawOrderQuantity > availableCapacity) {
      const fittedPacks = Math.floor(availableCapacity / packSize);
      suggestedOrderQuantity = fittedPacks > 0 ? fittedPacks * packSize : availableCapacity;
      capacityStatus = 'CONSTRAINED';
      capacityMessage = `Capped to available capacity (${availableCapacity} units)`;
    }
  }

  // For products with no sales history (REVIEW state)
  const hasNoSalesHistory = totalUnitsInWindow === 0;
  if (hasNoSalesHistory && usableStock === 0) {
    // Provide a baseline suggested starter batch
    suggestedOrderQuantity = Math.max(packSize, minOrderQty);
  }

  // 6. Financials
  const purchasePrice = Number(product.purchase_price) || 0;
  const sellingPrice = Number(product.selling_price) || 0;
  const unitProfit = Number(Math.max(0, sellingPrice - purchasePrice).toFixed(2));
  const estimatedOrderCost = Number((suggestedOrderQuantity * purchasePrice).toFixed(2));
  const expectedGrossProfit = Number((suggestedOrderQuantity * unitProfit).toFixed(2));

  // 7. Urgency Rules
  let urgency = 'OK';
  let urgencyLabel = 'Healthy Stock';

  if (hasNoSalesHistory) {
    urgency = 'REVIEW';
    urgencyLabel = 'Review Needed';
  } else if (usableStock < leadTimeDemand) {
    urgency = 'CRITICAL';
    urgencyLabel = 'Critical Stock';
  } else if (usableStock < targetStock) {
    urgency = 'LOW';
    urgencyLabel = 'Low Stock';
  } else {
    urgency = 'OK';
    urgencyLabel = 'Healthy Stock';
  }

  // 8. Ranking & Priority Scoring
  // Stockout Risk = Lead-Time Demand / max(Current Stock Units, 1)
  // Profit Score = (Selling Price − Purchase Price) × Daily Average Demand
  // Rank Score = Stockout Risk × Profit Score
  const stockoutRisk = Number((leadTimeDemand / Math.max(usableStock, 1)).toFixed(3));
  const profitScore = Number((unitProfit * dailyAverageDemand).toFixed(3));
  let rankScore = Number((stockoutRisk * profitScore).toFixed(2));

  if (urgency === 'CRITICAL') rankScore += 1000;
  else if (urgency === 'LOW') rankScore += 500;
  else if (urgency === 'REVIEW') rankScore = 10;

  // Warnings
  const leadTimeExceedsShelfLife = supplierLeadTime >= shelfLifeDays;

  // Explanation: "Why this quantity?"
  const explanation = generateExplanation({
    product,
    dailyAverageDemand,
    supplierLeadTime,
    leadTimeDemand,
    safetyStock,
    targetStock,
    usableStock,
    isPerishableCapped,
    perishableCapValue,
    packSize,
    minOrderQty,
    availableCapacity,
    suggestedOrderQuantity,
    capacityStatus,
    hasNoSalesHistory
  });

  return {
    ...product,
    dailyAverageDemand,
    totalUnitsInWindow,
    leadTimeDemand,
    safetyStock,
    targetStock,
    usableStock,
    daysOfStockLeft,
    rawOrderQuantity,
    suggestedOrderQuantity,
    packSize,
    minOrderQty,
    storageCapacity,
    availableCapacity,
    capacityStatus,
    capacityMessage,
    purchasePrice,
    sellingPrice,
    unitProfit,
    estimatedOrderCost,
    expectedGrossProfit,
    urgency,
    urgencyLabel,
    stockoutRisk,
    profitScore,
    rankScore,
    leadTimeExceedsShelfLife,
    expiredQuantity,
    nearExpiryQuantity,
    isPerishableCapped,
    perishableCapValue,
    explanation
  };
};

const generateExplanation = (params) => {
  const {
    product,
    dailyAverageDemand,
    supplierLeadTime,
    leadTimeDemand,
    safetyStock,
    targetStock,
    usableStock,
    isPerishableCapped,
    perishableCapValue,
    packSize,
    minOrderQty,
    availableCapacity,
    suggestedOrderQuantity,
    capacityStatus,
    hasNoSalesHistory
  } = params;

  if (hasNoSalesHistory) {
    return `This product has zero sales records in the selected analysis window. It is placed under REVIEW with an initial trial order of ${suggestedOrderQuantity} units (based on minimum order quantity ${minOrderQty} and pack size ${packSize}).`;
  }

  const steps = [];
  steps.push(`1. Average Daily Demand: ${dailyAverageDemand} units/day calculated over the 90-day window.`);
  steps.push(`2. Lead-Time Demand: ${dailyAverageDemand} × ${supplierLeadTime} days = ${leadTimeDemand} units.`);
  steps.push(`3. Safety Stock: ${safetyStock} units to buffer against supplier delays.`);
  
  if (isPerishableCapped) {
    steps.push(`4. Perishable Cap Applied: Target capped at ${perishableCapValue} units to prevent spoilage.`);
  } else {
    steps.push(`4. Target Stock: ${leadTimeDemand} + ${safetyStock} = ${targetStock} units.`);
  }

  steps.push(`5. Shortage Gap: Target (${targetStock}) − Current Stock (${usableStock}) = ${Math.max(0, targetStock - usableStock).toFixed(1)} units.`);

  if (packSize > 1) {
    steps.push(`6. Pack Rounding: Rounded up to supplier pack size of ${packSize} units.`);
  }
  if (minOrderQty > 1) {
    steps.push(`7. Minimum Order Quantity (MOQ): Enforced MOQ of ${minOrderQty} units.`);
  }

  if (capacityStatus === 'FULL') {
    steps.push(`8. Storage Capacity: Storage is full (${usableStock}/${product.storage_capacity_units} units). No reorder possible.`);
  } else if (capacityStatus === 'CONSTRAINED') {
    steps.push(`8. Storage Constraint: Reorder capped to available space (${availableCapacity} units).`);
  } else {
    steps.push(`8. Final Recommended Reorder Quantity: ${suggestedOrderQuantity} units.`);
  }

  return steps.join(' ');
};

/**
 * Calculates reorder plans for all products, sorted by descending rank score
 */
export const calculateAllReorders = (
  products = [],
  dailySales = [],
  config = {},
  lots = []
) => {
  const calculated = products.map(p =>
    calculateProductReorderMetrics(p, dailySales, config, lots)
  );

  // Sort descending by rank score
  return calculated.sort((a, b) => b.rankScore - a.rankScore);
};
