"""
Unit tests for MAE and WAPE formulas conforming to Section 7 of the master prompt.
"""
from backend.app.services.accuracy import calculate_mae, calculate_wape, calculate_portfolio_metrics

def test_known_numerical_mae_and_wape():
    """
    Test case directly from user specification:
    Actual sales: 10, 20, 30
    Forecast sales: 12, 18, 25
    Absolute errors: 2, 2, 5
    MAE = (2 + 2 + 5) / 3 = 3 units
    WAPE = (9 / 60) * 100 = 15%
    """
    actuals = [10.0, 20.0, 30.0]
    forecasts = [12.0, 18.0, 25.0]

    mae, n, total_error = calculate_mae(actuals, forecasts)
    assert n == 3
    assert total_error == 9.0
    assert mae == 3.0, f"Expected MAE 3.0, got {mae}"

    wape, total_actual, _ = calculate_wape(actuals, forecasts)
    assert total_actual == 60.0
    assert wape == 15.0, f"Expected WAPE 15.0%, got {wape}%"


def test_zero_sales_wape_handling():
    """
    Rule: If total actual sales are zero, report WAPE as None (N/A) rather than dividing by zero.
    MAE must still be calculated.
    """
    actuals = [0.0, 0.0, 0.0]
    forecasts = [2.0, 3.0, 1.0]

    mae, n, total_error = calculate_mae(actuals, forecasts)
    assert mae == 2.0
    assert total_error == 6.0

    wape, total_actual, _ = calculate_wape(actuals, forecasts)
    assert total_actual == 0.0
    assert wape is None, f"Expected WAPE None when actuals are 0, got {wape}"


def test_portfolio_wape_aggregation():
    """
    Rule: Portfolio WAPE must aggregate absolute errors and actual sales
    across all observations BEFORE calculating the percentage.
    It must NEVER average individual product WAPE percentages.
    """
    # Product A: actuals [10], forecasts [15] -> err 5, act 10 -> WAPE 50%
    # Product B: actuals [100], forecasts [110] -> err 10, act 100 -> WAPE 10%
    # Average of WAPEs would be (50 + 10) / 2 = 30% (WRONG)
    # Correct Portfolio WAPE: (5 + 10) / (10 + 100) = 15 / 110 = 13.64% (CORRECT)
    product_obs = {
        "P_A": [{"actual": 10.0, "forecast": 15.0}],
        "P_B": [{"actual": 100.0, "forecast": 110.0}]
    }

    result = calculate_portfolio_metrics(product_obs)
    assert result["n_observations"] == 2
    assert result["total_error"] == 15.0
    assert result["total_actual"] == 110.0
    assert result["wape"] == 13.64, f"Expected Portfolio WAPE 13.64%, got {result['wape']}%"
