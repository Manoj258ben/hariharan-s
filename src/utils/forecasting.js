/**
 * Demand Forecasting Utility using Statistical Moving-Average Baseline
 * Explicitly transparent: Does NOT claim black-box AI/ML.
 */

export const getProductSalesHistory = (productId, dailySales = [], days = 90, asOfDate = '2026-09-30') => {
  const asOfTime = new Date(asOfDate).getTime();
  const startTime = asOfTime - days * 24 * 60 * 60 * 1000;

  // Filter sales for this product up to asOfDate
  const filtered = dailySales
    .filter(s => s.product_id === productId)
    .filter(s => {
      const t = new Date(s.date).getTime();
      return t <= asOfTime && t >= startTime;
    })
    .sort((a, b) => new Date(a.date) - new Date(b.date));

  return filtered;
};

export const generateDemandForecast = (product, dailySales = [], config = {}) => {
  const asOfDate = config.asOfDate || '2026-09-30';
  const windowDays = Number(config.forecastWindowDays) || 90;
  const history = getProductSalesHistory(product.product_id, dailySales, windowDays, asOfDate);

  const totalSold = history.reduce((acc, curr) => acc + (Number(curr.qty) || 0), 0);
  const activeDays = history.length;

  const hasInsufficientData = activeDays < 14;
  const hasNoData = totalSold === 0;

  // Moving average daily demand
  const avgDailyDemand = activeDays > 0 ? Number((totalSold / windowDays).toFixed(2)) : 0;
  const leadTime = Number(product.supplier_lead_time_days) || 1;
  const safetyDays = Number(product.reorder_safety_stock_days ?? config.safetyStockDays ?? 2);

  const leadTimeDemand = Number((avgDailyDemand * leadTime).toFixed(2));
  const safetyStock = Number((avgDailyDemand * safetyDays).toFixed(2));
  const targetStock = Number((leadTimeDemand + safetyStock).toFixed(2));

  // Generate 14-day future projection
  const futurePoints = [];
  const asOf = new Date(asOfDate);

  for (let i = 1; i <= 14; i++) {
    const nextDate = new Date(asOf);
    nextDate.setDate(nextDate.getDate() + i);
    const dateStr = nextDate.toISOString().slice(0, 10);
    const dayOfWeek = nextDate.getDay();
    // Slight weekday vs weekend multiplier
    const dayMult = (dayOfWeek === 0 || dayOfWeek === 6) ? 1.15 : 0.95;
    const projectedDemand = Number((avgDailyDemand * dayMult).toFixed(1));

    futurePoints.push({
      date: dateStr,
      day: `Day +${i}`,
      projectedDemand,
      safetyThreshold: safetyStock,
      isWeekend: dayOfWeek === 0 || dayOfWeek === 6
    });
  }

  // Calculate demand variance / stability
  let variance = 0;
  if (history.length > 1) {
    const diffSum = history.reduce((sum, h) => sum + Math.pow(h.qty - avgDailyDemand, 2), 0);
    variance = Math.sqrt(diffSum / history.length);
  }
  const coefficientOfVariation = avgDailyDemand > 0 ? Number((variance / avgDailyDemand).toFixed(2)) : 0;
  const demandStability = coefficientOfVariation < 0.5 ? 'Stable' : coefficientOfVariation < 1.0 ? 'Moderate Fluctuations' : 'Volatile';

  return {
    productId: product.product_id,
    productName: product.product_name,
    category: product.category,
    windowDays,
    activeDays,
    totalSold,
    avgDailyDemand,
    leadTime,
    safetyDays,
    leadTimeDemand,
    safetyStock,
    targetStock,
    hasInsufficientData,
    hasNoData,
    demandStability,
    coefficientOfVariation,
    history,
    futurePoints
  };
};
