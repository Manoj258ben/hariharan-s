from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
import datetime
from ..database import get_db
from ..models import Product, Sale, InventoryLot, PurchaseOrder
from ..services.reorder import get_all_reorder_recommendations
from ..services.accuracy import calculate_portfolio_metrics
from ..services.forecasting import get_product_daily_sales_series, backtest_product_models
from ..config import DEFAULT_AS_OF_DATE

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

@router.get("/summary")
def get_dashboard_summary(
    as_of_date: str = DEFAULT_AS_OF_DATE,
    db: Session = Depends(get_db)
):
    # 1. Product & Inventory counts
    products = db.query(Product).filter(Product.is_archived == False).all()
    total_products = len(products)
    current_inventory_units = sum(float(p.current_stock or 0.0) for p in products)

    # 2. Reorder Recommendations
    reorder_list = get_all_reorder_recommendations(db, as_of_date=as_of_date)
    critical_items = [r for r in reorder_list if r["urgency"] == "CRITICAL"]
    low_stock_items = [r for r in reorder_list if r["urgency"] == "LOW"]
    recommended_budget = sum(r["estimated_order_cost"] for r in reorder_list)
    expected_gross_profit = sum(r["expected_gross_profit"] for r in reorder_list)

    # 3. Expiry Risk
    as_of_dt = datetime.datetime.strptime(as_of_date, "%Y-%m-%d").date()
    lots = db.query(InventoryLot).all()
    expiring_soon_count = 0
    expired_count = 0
    cost_at_risk = 0.0

    for lot in lots:
        exp_dt = datetime.datetime.strptime(lot.expiry_date, "%Y-%m-%d").date()
        days_left = (exp_dt - as_of_dt).days
        if days_left <= 0:
            expired_count += 1
            cost_at_risk += lot.quantity_remaining * lot.unit_cost
        elif days_left <= 7:
            expiring_soon_count += 1
            cost_at_risk += lot.quantity_remaining * lot.unit_cost

    # 4. 30-Day Sales Trend
    min_date_str = (as_of_dt - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
    sales_trend_query = db.query(
        Sale.sale_date,
        func.sum(Sale.line_total).label("revenue"),
        func.sum(Sale.quantity_sold).label("units")
    ).filter(
        Sale.sale_date >= min_date_str,
        Sale.sale_date <= as_of_date,
        Sale.transaction_status == "Completed"
    ).group_by(Sale.sale_date).order_by(Sale.sale_date.asc()).all()

    sales_trend = [
        {"date": r.sale_date, "revenue": round(float(r.revenue), 2), "units": round(float(r.units), 2)}
        for r in sales_trend_query
    ]

    # 5. Quick Accuracy Metric (Sample 5 top products)
    sample_obs = {}
    for p in products[:5]:
        series = get_product_daily_sales_series(db, p.product_id, as_of_date=as_of_date, days_back=60)
        bt = backtest_product_models(series, holdout_days=14)
        if bt:
            sample_obs[p.product_id] = [
                {"actual": a, "forecast": f}
                for a, f in zip(bt["actuals"], bt["baseline_forecasts"])
            ]
    portfolio_acc = calculate_portfolio_metrics(sample_obs)

    # 6. Sample Forecast vs Actual for Featured Product
    forecast_vs_actual = []
    featured_product_name = "Overall / Top Product"
    if products:
        top_p = products[0]
        featured_product_name = top_p.product_name
        top_series = get_product_daily_sales_series(db, top_p.product_id, as_of_date=as_of_date, days_back=30)
        bt_top = backtest_product_models(top_series, holdout_days=14)
        if bt_top:
            dates = [s["date"] for s in top_series[-14:]]
            for d, a, f in zip(dates, bt_top["actuals"], bt_top["baseline_forecasts"]):
                forecast_vs_actual.append({
                    "date": d,
                    "actual": a,
                    "forecast": f,
                    "product_name": top_p.product_name
                })

    return {
        "as_of_date": as_of_date,
        "kpis": {
            "total_products": total_products,
            "current_inventory_units": round(current_inventory_units, 1),
            "critical_stockouts": len(critical_items),
            "low_stock_items": len(low_stock_items),
            "expiring_soon_lots": expiring_soon_count,
            "expired_lots": expired_count,
            "cost_at_risk": round(cost_at_risk, 2),
            "recommended_budget": round(recommended_budget, 2),
            "expected_gross_profit": round(expected_gross_profit, 2),
            "portfolio_mae": portfolio_acc.get("mae"),
            "portfolio_wape": portfolio_acc.get("wape")
        },
        "sales_trend": sales_trend,
        "forecast_vs_actual": forecast_vs_actual,
        "featured_product_name": featured_product_name,
        "top_urgent_products": reorder_list[:5],
        "stock_health": {
            "critical": len(critical_items),
            "low": len(low_stock_items),
            "healthy": len([r for r in reorder_list if r["urgency"] == "OK"]),
            "review": len([r for r in reorder_list if r["urgency"] == "REVIEW"])
        }
    }
