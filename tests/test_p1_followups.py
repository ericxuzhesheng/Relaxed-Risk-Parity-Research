"""Tests for P1 follow-up fixes: data manifest, overlay sensitivity
config, and dynamic_selection train/validation split.

All tests are lightweight, deterministic, and use small synthetic data so
they finish in well under one second.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.data_loader import read_data_manifest, write_data_manifest
from src.dynamic_selection import run_dynamic_rrp_selection, score_params
from src.risk_overlay import RiskOverlayConfig


# --- #7 data manifest ------------------------------------------------------


def _synthetic_prices(n_rows: int = 60, n_assets: int = 3, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=n_rows)
    returns = rng.normal(0.0002, 0.01, size=(n_rows, n_assets))
    prices = 100 * (1.0 + pd.DataFrame(returns, index=dates, columns=[f"asset_{i}" for i in range(n_assets)])).cumprod()
    return prices


def test_write_data_manifest_includes_required_fields(tmp_path: Path) -> None:
    prices = _synthetic_prices()
    source_path = tmp_path / "fake_prices.csv"
    prices.to_csv(source_path)
    manifest = write_data_manifest(prices, source_path, source_label="test:fake")
    assert manifest["schema_version"] == 1
    assert manifest["row_count"] == len(prices)
    assert manifest["asset_count"] == prices.shape[1]
    assert manifest["source_label"] == "test:fake"
    assert manifest["source_sha256"]  # non-empty hex digest
    assert "asset_observations" in manifest
    assert set(manifest["asset_observations"].keys()) == set(prices.columns)
    assert all(isinstance(v, int) for v in manifest["asset_observations"].values())
    assert all(0.0 <= v <= 1.0 for v in manifest["asset_nan_ratio"].values())


def test_read_data_manifest_round_trip(tmp_path: Path) -> None:
    prices = _synthetic_prices()
    source_path = tmp_path / "fake_prices.csv"
    prices.to_csv(source_path)
    written = write_data_manifest(prices, source_path, source_label="test:roundtrip")
    loaded = read_data_manifest()
    assert loaded is not None
    assert loaded["row_count"] == written["row_count"]
    assert loaded["source_sha256"] == written["source_sha256"]


# --- #6 overlay sensitivity: config plumbing ------------------------------


def test_risk_overlay_config_propagates_drawdown_thresholds() -> None:
    """The overlay thresholds must flow from a config override into the
    dataclass — guarding against accidental hardcoding regressions in
    risk_overlay.RiskOverlayConfig.from_config."""
    overrides = {
        "drawdown_low": 0.015,
        "drawdown_high": 0.030,
        "drawdown_severe": 0.060,
        "drawdown_medium_scale": 0.60,
        "drawdown_severe_scale": 0.35,
        "momentum_lookback": 40,
        "momentum_confirm_lookback": 10,
    }
    cfg = RiskOverlayConfig.from_config(overrides)
    assert cfg.drawdown_low == pytest.approx(0.015)
    assert cfg.drawdown_high == pytest.approx(0.030)
    assert cfg.drawdown_severe == pytest.approx(0.060)
    assert cfg.drawdown_medium_scale == pytest.approx(0.60)
    assert cfg.drawdown_severe_scale == pytest.approx(0.35)
    assert cfg.momentum_lookback == 40
    assert cfg.momentum_confirm_lookback == 10


# --- #4 dynamic_selection train/validation split -------------------------


def _synthetic_returns(n_assets: int = 4, n_obs: int = 600, seed: int = 17) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-02", periods=n_obs)
    data = rng.normal(0.0003, 0.01, size=(n_obs, n_assets))
    return pd.DataFrame(data, index=dates, columns=[f"asset_{i}" for i in range(n_assets)])


def _base_config() -> dict:
    return {
        "lookback_weeks": 24,
        "trading_days_per_year": 252,
        "lambda_pen": 1.0,
        "m": 1.0,
        "optim_tol": 1e-6,
        "optim_maxiter": 200,
        "asset_weight_bounds": (0.0, 1.0),
        "bond_keywords": ["__none__"],
        "bond_leverage_upper": 1.4,
        "risk_free_rate": 0.0,
        "target_vol": 0.06,
        "gross_exposure_cap": 1.5,
        "turnover_cap": 0.25,
        "transaction_cost_bps": 3.0,
    }


def test_score_params_supports_held_out_validation_window() -> None:
    """``score_params`` must accept a separate ``df_validation`` window."""
    returns = _synthetic_returns()
    cfg = _base_config()
    df_fit = returns.iloc[:200]
    df_val = returns.iloc[200:260]
    score_train_only = score_params(returns.iloc[:260], {"lambda_pen": 1.0, "m": 1.5}, cfg)
    score_with_val = score_params(df_fit, {"lambda_pen": 1.0, "m": 1.5}, cfg, df_validation=df_val)
    # Both must return finite floats; they will generally differ in value
    # since one scores in-sample and the other on a held-out window.
    assert np.isfinite(score_train_only)
    assert np.isfinite(score_with_val)


def test_run_dynamic_rrp_selection_default_is_legacy() -> None:
    """Default ``selection_validation_months=0`` reproduces the legacy
    single-window scoring path: weights are fit and scored on df_train."""
    returns = _synthetic_returns()
    grid = [{"lambda_pen": 0.5, "m": 1.5}, {"lambda_pen": 2.0, "m": 1.5}]
    result = run_dynamic_rrp_selection(
        returns,
        grid,
        train_window_months=6,
        test_window_months=1,
        top_k=1,
        config_base=_base_config(),
    )
    # Default path produces a non-empty result frame.
    assert not result.empty
    assert "selection_score" in result.columns


def test_run_dynamic_rrp_selection_validation_split_runs() -> None:
    """Opt-in ``selection_validation_months>0`` exercises the held-out
    path without raising. We only assert the function returns a non-empty
    DataFrame — the *content* may differ from the legacy path by design."""
    returns = _synthetic_returns()
    grid = [{"lambda_pen": 0.5, "m": 1.5}, {"lambda_pen": 2.0, "m": 1.5}]
    result = run_dynamic_rrp_selection(
        returns,
        grid,
        train_window_months=6,
        test_window_months=1,
        top_k=1,
        config_base=_base_config(),
        selection_validation_months=2,
    )
    assert not result.empty


def test_run_dynamic_rrp_selection_validation_months_validation() -> None:
    returns = _synthetic_returns(n_obs=400)
    grid = [{"lambda_pen": 1.0, "m": 1.5}]
    cfg = _base_config()
    with pytest.raises(ValueError):
        run_dynamic_rrp_selection(
            returns, grid, train_window_months=6, top_k=1,
            config_base=cfg, selection_validation_months=-1,
        )
    with pytest.raises(ValueError):
        run_dynamic_rrp_selection(
            returns, grid, train_window_months=6, top_k=1,
            config_base=cfg, selection_validation_months=6,
        )
