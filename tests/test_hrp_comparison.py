import numpy as np
import pandas as pd

from scripts.run_hrp_comparison import run_equal_weight
from scripts.run_hrp_comparison import _summarize
from src.investable import investable_columns


def test_vectorized_equal_weight_matches_point_in_time_investability() -> None:
    dates = pd.date_range("2020-01-01", periods=45, freq="B")
    returns = pd.DataFrame(
        {
            "full_history": np.linspace(-0.01, 0.01, len(dates)),
            "late_listing": [np.nan] * 10 + list(np.linspace(-0.02, 0.02, len(dates) - 10)),
            "constant": 0.0,
        },
        index=dates,
    )

    result = run_equal_weight(returns)
    weight_columns = [f"weight_{column}" for column in returns.columns]
    actual = result.set_index("date")[weight_columns]
    actual.columns = returns.columns

    expected_rows = []
    for date in returns.index:
        active = investable_columns(returns[returns.index < date], min_observations=30)
        row = pd.Series(0.0, index=returns.columns)
        if active:
            row.loc[active] = 1.0 / len(active)
        expected_rows.append(row)
    expected = pd.DataFrame(expected_rows, index=returns.index)
    expected.index.name = "date"

    pd.testing.assert_frame_equal(actual, expected, check_freq=False)


def test_hrp_summary_accepts_date_aligned_risk_free_returns() -> None:
    dates = pd.date_range("2020-01-01", periods=4, freq="B")
    result = pd.DataFrame(
        {
            "date": dates,
            "portfolio_return": [0.0, 0.01, -0.005, 0.002],
            "turnover": 0.0,
        }
    )
    risk_free = pd.Series(0.0001, index=dates)

    summary = _summarize(
        "model",
        result,
        "2020-01-01",
        {"risk_free_rate": risk_free, "trading_days_per_year": 243},
    )

    assert summary["model"] == "model"
    assert np.isfinite(summary["sharpe_ratio"])
