import numpy as np
import pandas as pd

from src.backtest import run_static_backtest
from src.hierarchical_risk_parity import solve_herc, solve_hrp


def _sample_returns(rows: int = 80, cols: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    factors = rng.normal(0.0, 0.006, size=(rows, 2))
    loadings = rng.normal(0.5, 0.2, size=(2, cols))
    noise = rng.normal(0.0, 0.004, size=(rows, cols))
    data = factors @ loadings + noise
    dates = pd.bdate_range("2021-01-01", periods=rows)
    return pd.DataFrame(data, index=dates, columns=[f"asset_{i}" for i in range(cols)])


def test_hrp_weights_sum_to_one():
    weights = solve_hrp(_sample_returns())
    assert np.isclose(weights.sum(), 1.0)


def test_hrp_weights_are_non_negative():
    weights = solve_hrp(_sample_returns())
    assert (weights >= 0.0).all()


def test_hrp_handles_missing_values():
    returns = _sample_returns()
    returns.iloc[3:8, 1] = np.nan
    returns.iloc[12, 3] = np.nan
    weights = solve_hrp(returns)
    assert np.isfinite(weights).all()
    assert np.isclose(weights.sum(), 1.0)


def test_herc_weights_sum_to_one_and_are_non_negative():
    weights = solve_herc(_sample_returns())
    assert np.isclose(weights.sum(), 1.0)
    assert (weights >= 0.0).all()


def test_hrp_backtest_smoke():
    returns = _sample_returns(rows=120, cols=4)
    result = run_static_backtest(
        returns,
        model_type="hrp",
        config_overrides={"lookback_weeks": 4, "transaction_cost_bps": 0},
    )
    weight_cols = [c for c in result.columns if c.startswith("weight_")]
    assert not result.empty
    assert {"date", "portfolio_return", "turnover"}.issubset(result.columns)
    assert np.isfinite(result["portfolio_return"]).all()
    assert np.isclose(result[weight_cols].iloc[-1].sum(), 1.0)
