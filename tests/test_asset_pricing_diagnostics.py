import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from src.asset_pricing_diagnostics import build_factor_proxies, run_diagnostics


def sample_returns(n=80):
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2022-01-03", periods=n)
    return pd.DataFrame(
        {
            "equity_asset": rng.normal(0.0003, 0.010, n),
            "榛勯噾ETF": rng.normal(0.0001, 0.008, n),
        },
        index=dates,
    )


def sample_model(returns):
    weights = pd.DataFrame(
        {
            "weight_equity_asset": 0.6,
            "weight_榛勯噾ETF": 0.4,
        },
        index=returns.index,
    )
    portfolio_return = returns["equity_asset"] * 0.6 + returns["榛勯噾ETF"] * 0.4
    out = weights.copy()
    out.insert(0, "portfolio_return", portfolio_return.values)
    out.insert(0, "date", returns.index)
    out["turnover"] = 0.0
    return out.reset_index(drop=True)


def test_factor_regression_handles_missing_factor_groups():
    returns = sample_returns()
    factors = build_factor_proxies(returns)
    assert "global_risk" in factors.columns
    assert "bond" not in factors.columns
    outputs = run_diagnostics({"Global Relaxed Risk Parity": sample_model(returns)}, returns)
    assert not outputs.factor_exposure_summary.empty
    assert "available_factors" in outputs.factor_exposure_summary.columns


def test_module_output_does_not_export_generated_weight_recommendations():
    returns = sample_returns()
    outputs = run_diagnostics(
        {
            "Global Relaxed Risk Parity": sample_model(returns),
            "Improved Convex Adaptive Global RRP": sample_model(returns),
        },
        returns,
    )
    for df in [
        outputs.factor_exposure_summary,
        outputs.return_attribution,
        outputs.risk_attribution,
        outputs.rolling_beta_summary,
    ]:
        assert not any(col.startswith("weight_") for col in df.columns)


def test_asset_pricing_smoke_runner_creates_outputs(tmp_path):
    result = subprocess.run(
        [sys.executable, "scripts/run_asset_pricing_diagnostics.py", "--smoke", "--output-root", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Generated asset-pricing diagnostics" in result.stdout
    required = [
        tmp_path / "results/tables/asset_pricing_factor_exposure_summary.csv",
        tmp_path / "results/tables/asset_pricing_return_attribution.csv",
        tmp_path / "results/tables/asset_pricing_risk_attribution.csv",
        tmp_path / "results/tables/asset_pricing_rolling_beta_summary.csv",
        tmp_path / "report/asset_pricing_interpretation.md",
        tmp_path / "results/figures/asset_pricing_risk_attribution.png",
    ]
    for path in required:
        assert path.exists()
        assert path.stat().st_size > 0
    for path in required[:4]:
        assert not pd.read_csv(path).empty


def test_readme_has_no_old_internal_labels():
    text = Path("README.md").read_text(encoding="utf-8")
    for forbidden in ["V1", "V2", "V3", "V3_Global_RRP", "Dynamic_RRP_before"]:
        assert forbidden not in text
