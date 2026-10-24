from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Product, ForecastEvaluation
from ..schemas import (
    BacktestRequest,
    AccuracySummaryResponse,
    ModelAccuracyMetric,
    ProductAccuracyDetail
)
from ..services.forecasting import get_product_daily_sales_series, backtest_product_models
from ..services.accuracy import calculate_portfolio_metrics
from ..config import DEFAULT_AS_OF_DATE

router = APIRouter(prefix="/api/forecast-accuracy", tags=["Forecast Accuracy (MAE & WAPE)"])

@router.post("/backtest", response_model=AccuracySummaryResponse)
def run_backtest(
    req: BacktestRequest,
    as_of_date: str = DEFAULT_AS_OF_DATE,
    db: Session = Depends(get_db)
):
    """
    Executes time-ordered holdout backtesting across products using the last N days.
    Calculates MAE and WAPE conforming strictly to mathematical definitions.
    """
    products = db.query(Product).filter(Product.is_archived == False).all()
    holdout_days = req.evaluation_window_days or 14

    baseline_obs: Dict[str, List[Dict[str, float]]] = {}
    advanced_obs: Dict[str, List[Dict[str, float]]] = {}
    product_metrics: List[ProductAccuracyDetail] = []

    period_start = ""
    period_end = ""

    for p in products:
        series = get_product_daily_sales_series(db, p.product_id, as_of_date=as_of_date, days_back=90)
        bt = backtest_product_models(series, holdout_days=holdout_days)

        if not bt:
            continue

        period_start = bt["holdout_start"]
        period_end = bt["holdout_end"]

        # Collect observations
        actuals = bt["actuals"]
        b_forecasts = bt["baseline_forecasts"]
        baseline_obs[p.product_id] = [{"actual": a, "forecast": f} for a, f in zip(actuals, b_forecasts)]

        adv_f = bt.get("advanced_forecasts")
        if adv_f:
            advanced_obs[p.product_id] = [{"actual": a, "forecast": f} for a, f in zip(actuals, adv_f)]

        product_metrics.append(ProductAccuracyDetail(
            product_id=p.product_id,
            product_name=p.product_name,
            category=p.category,
            n_observations=bt["n_observations"],
            actual_units=sum(actuals),
            baseline_mae=bt["baseline_mae"],
            baseline_wape=bt["baseline_wape"],
            advanced_mae=bt["advanced_mae"],
            advanced_wape=bt["advanced_wape"],
            winning_model=bt["winning_model"]
        ))

    # Portfolio Aggregations
    b_port = calculate_portfolio_metrics(baseline_obs)
    adv_port = calculate_portfolio_metrics(advanced_obs) if advanced_obs else None

    # Persist Portfolio Evaluation into database
    db.add(ForecastEvaluation(
        model_name="14_DAY_MOVING_AVERAGE",
        evaluation_date=as_of_date,
        period_start=period_start or as_of_date,
        period_end=period_end or as_of_date,
        n_observations=b_port["n_observations"],
        mae=b_port["mae"],
        wape=b_port["wape"],
        actual_sum=b_port["total_actual"],
        error_sum=b_port["total_error"],
        is_portfolio=True
    ))

    if adv_port and adv_port["n_observations"] > 0:
        db.add(ForecastEvaluation(
            model_name="RANDOM_FOREST",
            evaluation_date=as_of_date,
            period_start=period_start or as_of_date,
            period_end=period_end or as_of_date,
            n_observations=adv_port["n_observations"],
            mae=adv_port["mae"],
            wape=adv_port["wape"],
            actual_sum=adv_port["total_actual"],
            error_sum=adv_port["total_error"],
            is_portfolio=True
        ))

    db.commit()

    return AccuracySummaryResponse(
        evaluation_period_start=period_start,
        evaluation_period_end=period_end,
        total_observations_evaluated=b_port["n_observations"],
        baseline_portfolio=ModelAccuracyMetric(
            model_name="14_DAY_MOVING_AVERAGE",
            n_observations=b_port["n_observations"],
            mae=b_port["mae"],
            wape=b_port["wape"],
            total_actual=b_port["total_actual"],
            total_error=b_port["total_error"],
            plain_language_explanation=b_port["explanation"]
        ),
        advanced_portfolio=ModelAccuracyMetric(
            model_name="RANDOM_FOREST",
            n_observations=adv_port["n_observations"],
            mae=adv_port["mae"],
            wape=adv_port["wape"],
            total_actual=adv_port["total_actual"],
            total_error=adv_port["total_error"],
            plain_language_explanation=adv_port["explanation"]
        ) if adv_port and adv_port["n_observations"] > 0 else None,
        product_metrics=product_metrics
    )


@router.get("/summary", response_model=AccuracySummaryResponse)
def get_accuracy_summary(
    as_of_date: str = DEFAULT_AS_OF_DATE,
    db: Session = Depends(get_db)
):
    """
    Returns latest accuracy summary or runs backtest on demand.
    """
    req = BacktestRequest(evaluation_window_days=14, compare_advanced_model=True)
    return run_backtest(req, as_of_date=as_of_date, db=db)


@router.get("/products", response_model=List[ProductAccuracyDetail])
def get_product_accuracy(
    as_of_date: str = DEFAULT_AS_OF_DATE,
    db: Session = Depends(get_db)
):
    summary = get_accuracy_summary(as_of_date=as_of_date, db=db)
    return summary.product_metrics


@router.get("/history")
def get_accuracy_history(
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """
    Returns historical evaluation audit records.
    """
    evaluations = db.query(ForecastEvaluation).order_by(ForecastEvaluation.id.desc()).limit(limit).all()
    return [
        {
            "id": ev.id,
            "model_name": ev.model_name,
            "evaluation_date": ev.evaluation_date,
            "period_start": ev.period_start,
            "period_end": ev.period_end,
            "n_observations": ev.n_observations,
            "mae": ev.mae,
            "wape": ev.wape,
            "actual_sum": ev.actual_sum,
            "error_sum": ev.error_sum,
            "is_portfolio": ev.is_portfolio,
            "created_at": ev.created_at.isoformat() if ev.created_at else None
        }
        for ev in evaluations
    ]
