"""Weekly comparisons share the primary calendar and charge only actual trades."""
import numpy as np
import pandas as pd
import pytest

from scripts.run_convex_adaptive_rrp import run_hrp_like
from src.benchmarks import run_benchmark_backtest


@pytest.mark.parametrize("model", ["hrp", "herc", "Equal Weight Benchmark", "60/40 Benchmark"])
def test_weekly_calendar_costs_and_prior_inputs(model):
    dates = pd.bdate_range("2024-01-01", periods=125)
    # Remove a Friday to cover the holiday week ending on Thursday.
    dates = dates.drop(pd.Timestamp("2024-05-10"))
    data = pd.DataFrame(np.random.default_rng(7).normal(0.0002, 0.008, (len(dates), 3)),
                        index=dates, columns=["沪深300ETF", "5年国债ETF", "黄金ETF"])
    def run(frame):
        if model in {"hrp", "herc"}:
            return run_hrp_like(frame, model, 3.0, rebalance_frequency="W")
        return run_benchmark_backtest(frame, model, rebalance_frequency="W")
    result = run(data)
    actual = set(result.loc[result.is_rebalance_day, "date"])
    expected = set(data.resample("W-FRI").apply(lambda x: x.index[-1]).iloc[:, 0])
    assert actual == expected
    assert pd.Timestamp("2024-05-09") in actual
    assert (result.loc[~result.is_rebalance_day, "turnover"] == 0).all()
    assert result.turnover.gt(0).sum() > 8
    np.testing.assert_allclose(result.gross_return - result.net_return,
                               result.turnover * 0.0003, atol=1e-14)
    decision = pd.Timestamp("2024-05-09")
    changed = data.copy()
    changed.loc[decision:] += 0.2
    alternative = run(changed)
    cols = [c for c in result if c.startswith("weight_")]
    np.testing.assert_allclose(result.loc[result.date.le(decision), cols],
                               alternative.loc[alternative.date.le(decision), cols])
