"""
StockSense Forecast Accuracy Evaluation Module
Implements strictly verified MAE and WAPE formulas conforming to Section 7 of the master prompt.
"""
from typing import List, Dict, Any, Optional, Tuple

def calculate_mae(actuals: List[float], forecasts: List[float]) -> Tuple[float, int, float]:
    """
    MAE = Σ |Actual − Forecast| / N
    Returns: (mae, n_observations, total_absolute_error)
    """
    if not actuals or not forecasts or len(actuals) != len(forecasts):
        return (0.0, 0, 0.0)

    n = len(actuals)
    if n == 0:
        return (0.0, 0, 0.0)

    total_error = sum(abs(a - f) for a, f in zip(actuals, forecasts))
    mae = total_error / n
    return (round(mae, 3), n, round(total_error, 3))


def calculate_wape(actuals: List[float], forecasts: List[float]) -> Tuple[Optional[float], float, float]:
    """
    WAPE (%) = [Σ |Actual − Forecast| / Σ |Actual|] × 100
    Returns: (wape_percent_or_none, total_actual, total_absolute_error)
    Rule: If Σ |Actual| == 0, report WAPE as None (N/A) to prevent division by zero.
    """
    if not actuals or not forecasts or len(actuals) != len(forecasts):
        return (None, 0.0, 0.0)

    total_actual = sum(abs(a) for a in actuals)
    total_error = sum(abs(a - f) for a, f in zip(actuals, forecasts))

    if total_actual == 0:
        return (None, 0.0, round(total_error, 3))

    wape = (total_error / total_actual) * 100.0
    return (round(wape, 2), round(total_actual, 3), round(total_error, 3))


def calculate_portfolio_metrics(
    product_observations: Dict[str, List[Dict[str, float]]]
) -> Dict[str, Any]:
    """
    Portfolio-level aggregation.
    Rule: Aggregates total absolute errors and total actual sales across all observations
    BEFORE calculating portfolio WAPE. Never averages individual product WAPE percentages!
    """
    all_actuals = []
    all_forecasts = []

    for pid, obs_list in product_observations.items():
        for obs in obs_list:
            all_actuals.append(obs["actual"])
            all_forecasts.append(obs["forecast"])

    n = len(all_actuals)
    if n == 0:
        return {
            "n_observations": 0,
            "mae": 0.0,
            "wape": None,
            "total_actual": 0.0,
            "total_error": 0.0,
            "explanation": "No evaluated observations available."
        }

    mae, n_obs, total_error = calculate_mae(all_actuals, all_forecasts)
    wape, total_actual, _ = calculate_wape(all_actuals, all_forecasts)

    wape_str = f"{wape}%" if wape is not None else "N/A (zero sales volume)"
    explanation = (
        f"Portfolio MAE of {mae} units means the forecast missed actual sales by an average of {mae} units per product-day. "
        f"Portfolio WAPE of {wape_str} means total absolute error was {wape_str} of total sales volume over {n} evaluated observations."
    )

    return {
        "n_observations": n,
        "mae": mae,
        "wape": wape,
        "total_actual": total_actual,
        "total_error": total_error,
        "explanation": explanation
    }
