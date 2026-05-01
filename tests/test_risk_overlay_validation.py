import numpy as np
import pandas as pd

from src.risk_overlay import (
    RiskOverlayConfig,
    apply_turnover_cap,
    drawdown_scale,
    trend_positive_mask,
    vol_target_scale,
)
from src.validation import walk_forward_validation


def _returns(rows=90, cols=3):
    rng = np.random.default_rng(11)
    dates = pd.bdate_range("2021-01-01", periods=rows)
    data = rng.normal(0.0002, 0.004, size=(rows, cols))
    return pd.DataFrame(data, index=dates, columns=[f"asset_{i}" for i in range(cols)])


def test_drawdown_scaling_thresholds():
    cfg = RiskOverlayConfig()
    assert drawdown_scale(-0.025, cfg) == 1.0
    assert drawdown_scale(-0.030, cfg) == 0.75
    assert drawdown_scale(-0.041, cfg) == 0.50


def test_trend_confirmation_uses_past_window_only():
    df = _returns(rows=80, cols=2)
    df.iloc[-60:, 0] = 0.001
    df.iloc[-20:, 0] = 0.002
    df.iloc[-60:, 1] = 0.001
    df.iloc[-20:, 1] = -0.002
    mask = trend_positive_mask(df, RiskOverlayConfig())
    assert bool(mask["asset_0"])
    assert not bool(mask["asset_1"])


def test_vol_target_never_scales_above_one():
    low_vol = pd.Series(np.full(120, 0.0001))
    assert vol_target_scale(low_vol, RiskOverlayConfig(target_vol=0.06)) <= 1.0


def test_turnover_cap_reduces_l1_change():
    cfg = RiskOverlayConfig(turnover_cap=0.25)
    proposed = np.array([1.0, 0.0, 0.0])
    previous = np.array([1 / 3, 1 / 3, 1 / 3])
    capped, turnover, bound = apply_turnover_cap(proposed, previous, cfg)
    assert bound
    assert turnover <= 0.2500001
    assert np.abs(capped - previous).sum() < np.abs(proposed - previous).sum()


def test_walk_forward_validation_is_past_only():
    returns = _returns(rows=760, cols=3)
    config = {
        "bond_keywords": [],
        "trading_days_per_year": 243,
        "risk_free_rate": 0.0,
        "lookback_weeks": 12,
        "lambda_pen": 0.1,
        "m": 1.0,
        "bond_leverage_upper": 1.2,
        "asset_weight_bounds": (0.0, 1.0),
        "optim_tol": 1e-6,
        "optim_maxiter": 100,
    }
    grid = [{"lambda_pen": 0.1, "m": 1.0, "bond_leverage_upper": 1.2}]
    wf = walk_forward_validation(returns, grid, config, train_window_months=6)
    assert not wf.empty
    assert not wf["uses_future_data"].any()
    assert (pd.to_datetime(wf["train_end"]) < pd.to_datetime(wf["test_start"])).all()
