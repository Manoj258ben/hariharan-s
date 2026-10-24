from typing import List, Optional
import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Product, ForecastRecord
from ..schemas import ForecastRunRequest, ProductForecastResult, ForecastPoint
from ..services.forecasting import (
    get_product_daily_sales_series,
    run_14_day_moving_average_forecast,
    train_advanced_random_forest
)
from ..config import DEFAULT_AS_OF_DATE

router = APIRouter(prefix="/api/forecasts", tags=["Demand Forecasting"])

@router.post("/run", response_model=List[ProductForecastResult])
def run_demand_forecast(
    req: ForecastRunRequest,
    as_of_date: str = DEFAULT_AS_OF_DATE,
    db: Session = Depends(get_db)
):
    query = db.query(Product).filter(Product.is_archived == False)
    if req.product_ids:
        query = query.filter(Product.product_id.in_(req.product_ids))

    products = query.all()
    results = []
    as_of_dt = datetime.datetime.strptime(as_of_date, "%Y-%m-%d").date()

    for p in products:
        series = get_product_daily_sales_series(db, p.product_id, as_of_date=as_of_date, days_back=90)
        daily_units = [s["units"] for s in series]
        avg_demand = round(sum(daily_units) / max(1, len(daily_units)), 2)

        # Predict based on selected model
        if req.model_name == "RANDOM_FOREST":
            preds = train_advanced_random_forest(series, horizon_days=req.horizon_days or 14)
            model_used = "RANDOM_FOREST"
            if not preds:  # Fallback to baseline if insufficient data
                preds = run_14_day_moving_average_forecast(series, horizon_days=req.horizon_days or 14)
                model_used = "14_DAY_MOVING_AVERAGE (Fallback)"
        else:
            preds = run_14_day_moving_average_forecast(series, horizon_days=req.horizon_days or 14)
            model_used = "14_DAY_MOVING_AVERAGE"

        forecast_points = []
        for day_offset, pred in enumerate(preds, start=1):
            target_dt = as_of_dt + datetime.timedelta(days=day_offset)
            t_str = target_dt.strftime("%Y-%m-%d")
            forecast_points.append(ForecastPoint(
                date=t_str,
                predicted_demand=pred,
                model_name=model_used
            ))

        total_7 = sum(p.predicted_demand for p in forecast_points[:7])
        total_14 = sum(p.predicted_demand for p in forecast_points[:14])

        results.append(ProductForecastResult(
            product_id=p.product_id,
            product_name=p.product_name,
            category=p.category,
            current_stock=float(p.current_stock or 0.0),
            daily_average_demand=avg_demand,
            demand_stability="Stable" if avg_demand > 5 else "Moderate",
            selected_model=model_used,
            forecast_points=forecast_points,
            total_7_day_demand=round(total_7, 1),
            total_14_day_demand=round(total_14, 1)
        ))

    return results


@router.get("", response_model=List[ProductForecastResult])
def get_forecasts(
    model_name: str = "14_DAY_MOVING_AVERAGE",
    horizon_days: int = 14,
    as_of_date: str = DEFAULT_AS_OF_DATE,
    db: Session = Depends(get_db)
):
    """
    Returns demand forecasts for all active products.
    """
    req = ForecastRunRequest(
        product_ids=None,
        model_name=model_name,
        horizon_days=horizon_days
    )
    return run_demand_forecast(req, as_of_date=as_of_date, db=db)
