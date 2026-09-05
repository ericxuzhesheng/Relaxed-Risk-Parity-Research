import numpy as np
import pandas as pd

from scripts.run_hrp_comparison import run_equal_weight
from scripts.run_hrp_comparison import _summarize


def test_equal_weight_rebalances_monthly_and_drifts_between_rebalances() -> None:
    dates = pd.date_range("2020-01-01", periods=100, freq="B")
    returns = pd.DataFrame(
        {
            "asset_a": np.linspace(-0.01, 0.02, len(dates)),
            "asset_b": np.linspace(0.015, -0.005, len(dates)),
        },
        index=dates,
    )

    result = run_equal_weight(returns)
    first_investment = result.index[result["turnover"].gt(0.0)][0]

    assert result.loc[first_investment, "turnover"] == 1.0
    assert result.loc[first_investment, "weight_asset_a"] == 0.5
    assert result.loc[first_investment + 1, "weight_asset_a"] != 0.5


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
