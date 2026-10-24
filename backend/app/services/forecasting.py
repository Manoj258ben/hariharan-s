"""
StockSense Demand Forecasting Engine
Implements 14-Day Moving Average Baseline & Time-Lagged Random Forest Regression with Holdout Validation.
"""
from typing import List, Dict, Any, Optional, Tuple
import datetime
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..models import Sale, Product
from .accuracy import calculate_mae, calculate_wape

def get_product_daily_sales_series(
    db: Session,
    product_id: str,
    as_of_date: Optional[str] = None,
    days_back: int = 180
) -> List[Dict[str, Any]]:
    """
    Extracts daily chronological sales for a product up to as_of_date.
    Ensures zero sales days within the period are explicitly filled.
    """
    query = db.query(
        Sale.sale_date,
        func.sum(Sale.quantity_sold).label("daily_units"),
        func.sum(Sale.line_total).label("daily_revenue")
    ).filter(
        Sale.product_id == product_id,
        Sale.transaction_status == "Completed"
    )

    if as_of_date:
        query = query.filter(Sale.sale_date <= as_of_date)

    query = query.group_by(Sale.sale_date).order_by(Sale.sale_date.asc())
    results = query.all()

    if not results:
        return []

    # Map existing dates
    date_map = {r.sale_date: {"units": float(r.daily_units), "revenue": float(r.daily_revenue)} for r in results}

    start_date_str = results[0].sale_date
    end_date_str = as_of_date or results[-1].sale_date

    start_dt = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end_dt = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()

    # If requested days_back is smaller, trim start_dt
    min_dt = end_dt - datetime.timedelta(days=days_back)
    if min_dt > start_dt:
        start_dt = min_dt

    series = []
    curr = start_dt
    while curr <= end_dt:
        d_str = curr.strftime("%Y-%m-%d")
        record = date_map.get(d_str, {"units": 0.0, "revenue": 0.0})
        series.append({
            "date": d_str,
            "units": record["units"],
            "revenue": record["revenue"],
            "day_of_week": curr.weekday()  # 0=Monday, 6=Sunday
        })
        curr += datetime.timedelta(days=1)

    return series


def run_14_day_moving_average_forecast(series: List[Dict[str, Any]], horizon_days: int = 14) -> List[float]:
    """
    Computes 14-day moving average baseline.
    """
    if not series:
        return [0.0] * horizon_days

    # Take the latest 14 days of actuals
    recent_units = [s["units"] for s in series[-14:]]
    if not recent_units:
        return [0.0] * horizon_days

    baseline_daily = sum(recent_units) / len(recent_units)
    baseline_daily = round(baseline_daily, 2)
    return [baseline_daily] * horizon_days


def train_advanced_random_forest(series: List[Dict[str, Any]], horizon_days: int = 14) -> Optional[List[float]]:
    """
    Fits a Scikit-Learn Random Forest Regressor on time-lagged sales features
    when at least 30 observations are available.
    """
    if len(series) < 30:
        return None

    try:
        from sklearn.ensemble import RandomForestRegressor
    except ImportError:
        return None

    # Feature engineering: lag_1, lag_7, rolling_7_mean, day_of_week
    X, y = [], []
    units = [s["units"] for s in series]
    dows = [s["day_of_week"] for s in series]

    for i in range(7, len(series)):
        lag_1 = units[i - 1]
        lag_7 = units[i - 7]
        roll_7 = float(np.mean(units[i - 7:i]))
        dow = dows[i]

        X.append([lag_1, lag_7, roll_7, dow])
        y.append(units[i])

    if len(X) < 15:
        return None

    model = RandomForestRegressor(n_estimators=30, random_state=42, max_depth=5)
    model.fit(X, y)

    # Autoregressive recursive projection for horizon_days
    future_preds = []
    sim_units = list(units)
    last_dt = datetime.datetime.strptime(series[-1]["date"], "%Y-%m-%d").date()

    for step in range(1, horizon_days + 1):
        target_dt = last_dt + datetime.timedelta(days=step)
        target_dow = target_dt.weekday()

        lag_1 = sim_units[-1]
        lag_7 = sim_units[-7] if len(sim_units) >= 7 else lag_1
        roll_7 = float(np.mean(sim_units[-7:]))

        feat = np.array([[lag_1, lag_7, roll_7, target_dow]])
        pred = max(0.0, float(model.predict(feat)[0]))
        pred = round(pred, 2)

        future_preds.append(pred)
        sim_units.append(pred)

    return future_preds


def backtest_product_models(
    series: List[Dict[str, Any]],
    holdout_days: int = 14
) -> Optional[Dict[str, Any]]:
    """
    Time-ordered holdout validation:
    Splits series into [Training Period] and [Holdout Evaluation Period (last 14 days)].
    Evaluates MAE and WAPE on the holdout period.
    """
    if len(series) < holdout_days + 14:
        return None

    train_series = series[:-holdout_days]
    test_series = series[-holdout_days:]

    actuals = [s["units"] for s in test_series]
    holdout_dates = [s["date"] for s in test_series]

    # 1. Baseline Model on train_series
    baseline_val = round(sum(s["units"] for s in train_series[-14:]) / 14.0, 2)
    baseline_forecasts = [baseline_val] * holdout_days

    b_mae, b_n, b_err = calculate_mae(actuals, baseline_forecasts)
    b_wape, b_act, _ = calculate_wape(actuals, baseline_forecasts)

    # 2. Advanced Model on train_series
    adv_forecasts = train_advanced_random_forest(train_series, horizon_days=holdout_days)
    adv_mae, adv_wape = None, None

    if adv_forecasts:
        adv_mae, _, _ = calculate_mae(actuals, adv_forecasts)
        adv_wape, _, _ = calculate_wape(actuals, adv_forecasts)

    winning_model = "14_DAY_MOVING_AVERAGE"
    if adv_mae is not None and adv_mae < b_mae:
        winning_model = "RANDOM_FOREST"

    return {
        "holdout_start": holdout_dates[0],
        "holdout_end": holdout_dates[-1],
        "n_observations": len(actuals),
        "actuals": actuals,
        "baseline_forecasts": baseline_forecasts,
        "baseline_mae": b_mae,
        "baseline_wape": b_wape,
        "advanced_forecasts": adv_forecasts,
        "advanced_mae": adv_mae,
        "advanced_wape": adv_wape,
        "winning_model": winning_model
    }
