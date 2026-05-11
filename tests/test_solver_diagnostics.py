"""Reliability tests for the SLSQP and convex solvers.

These tests focus on the diagnostics channel introduced for solver
fallbacks, covariance health, and investable-universe freezing. They are
deliberately lightweight: small synthetic returns, no large CSV fixtures,
deterministic seeds. They cover:

* ``src.risk_parity`` records solver status + fallback flag in the
  ``diagnostics`` dict.
* ``src.risk_parity`` weights satisfy the simplex constraint.
* ``src.risk_parity`` falls back gracefully on a malformed (NaN) covariance
  and records the exception type.
* ``src.convex_adaptive_rrp`` weights satisfy the simplex + max-weight
  constraints and emit covariance diagnostics + solver name.
* ``src.backtest.run_static_backtest`` populates the diagnostics_out channel
  with solver / covariance / universe DataFrames.
* ``src.risk_parity`` source no longer contains ``except: pass`` patterns.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.backtest import run_static_backtest
from src.convex_adaptive_rrp import ConvexRRPConfig, solve_convex_rrp
from src.risk_parity import (
    optimize_with_leverage,
    solve_relaxed_rp,
    solve_standard_rp,
)
from src.utils import get_config


# --- shared synthetic fixtures ----------------------------------------------

def _synthetic_returns(n_assets: int = 4, n_obs: int = 200, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2022-01-03", periods=n_obs)
    data = rng.normal(loc=0.0003, scale=0.01, size=(n_obs, n_assets))
    return pd.DataFrame(data, index=dates, columns=[f"asset_{i}" for i in range(n_assets)])


def _wellposed_cov(n: int = 4) -> np.ndarray:
    rng = np.random.default_rng(42)
    a = rng.normal(size=(n, n))
    cov = a @ a.T / n + np.eye(n) * 0.04
    return cov


# --- src.risk_parity --------------------------------------------------------

def test_solve_standard_rp_returns_simplex_and_records_success():
    cov = _wellposed_cov(4)
    diag: dict = {}
    weights = solve_standard_rp(cov, 4, get_config(), diagnostics=diag)
    assert weights.shape == (4,)
    assert np.all(weights >= -1e-9)
    assert weights.sum() == pytest.approx(1.0, abs=1e-6)
    assert diag["solver_name"] == "scipy_slsqp"
    assert "solver_success" in diag
    assert isinstance(diag["solver_success"], bool)
    # Either SLSQP converged, or the fallback flag is on. Both branches must
    # populate the diagnostic so silent failures are impossible.
    assert diag["solver_success"] is True or diag["fallback_used"] is True


def test_solve_standard_rp_falls_back_on_nan_covariance():
    cov = np.full((4, 4), np.nan)
    diag: dict = {}
    weights = solve_standard_rp(cov, 4, get_config(), diagnostics=diag)
    assert weights.shape == (4,)
    assert weights.sum() == pytest.approx(1.0, abs=1e-9)
    assert diag["solver_success"] is False
    assert diag["fallback_used"] is True
    assert diag["fallback_method"] == "equal_weight"
    # Either SciPy raised inside SLSQP (exception_type populated) or it
    # returned an unsuccessful status — both are acceptable failure modes
    # for an entirely-NaN covariance, but the diagnostic must reflect one.
    assert diag["exception_type"] or diag["solver_message"]


def test_solve_relaxed_rp_falls_back_to_standard_rp():
    cov = np.full((4, 4), np.nan)
    mu = np.zeros(4)
    theta = np.eye(4)
    diag: dict = {}
    weights = solve_relaxed_rp(cov, mu, theta, 4, 0.0, get_config(), diagnostics=diag)
    assert weights.shape == (4,)
    assert weights.sum() == pytest.approx(1.0, abs=1e-9)
    if diag["fallback_used"]:
        assert diag["fallback_method"] == "standard_rp_solution"


def test_optimize_with_leverage_returns_two_arrays_and_records_diag():
    cov = _wellposed_cov(4)
    diag: dict = {}
    weights, leverage = optimize_with_leverage(
        cov, 4, bond_indices=[0], config=get_config(), diagnostics=diag
    )
    assert weights.shape == (4,)
    assert leverage.shape == (4,)
    assert weights.sum() == pytest.approx(1.0, abs=1e-6)
    assert leverage[0] >= 1.0 - 1e-9
    assert leverage[1] == pytest.approx(1.0, abs=1e-9)
    assert "solver_name" in diag
    assert diag["solver_name"] == "scipy_slsqp"


# --- src.convex_adaptive_rrp -----------------------------------------------

def test_solve_convex_rrp_returns_feasible_simplex_with_max_weight():
    returns = _synthetic_returns(n_assets=5, n_obs=120, seed=11)
    cfg = ConvexRRPConfig(
        max_weight=0.40,
        turnover_cap=None,
        cvar_penalty=0.0,
        ema_deviation_enabled=False,
    )
    weights, diag = solve_convex_rrp(returns, previous_weights=None, config=cfg)
    assert weights.shape == (5,)
    assert np.all(weights >= -1e-9)
    assert np.all(weights <= cfg.max_weight + 1e-6)
    assert weights.sum() == pytest.approx(1.0, abs=1e-5)
    assert diag["solver_name"] is not None
    assert "covariance_observations" in diag
    assert "covariance_assets" in diag
    assert "covariance_condition_number" in diag
    assert diag["covariance_assets"] == 5


def test_solve_convex_rrp_records_solver_status():
    returns = _synthetic_returns(n_assets=4, n_obs=100, seed=21)
    cfg = ConvexRRPConfig(cvar_penalty=0.0, ema_deviation_enabled=False)
    _, diag = solve_convex_rrp(returns, previous_weights=None, config=cfg)
    # A successful cvxpy solve sets solver_status to a string like "optimal".
    # A fallback path sets fallback_used to True and reports the scipy status.
    assert diag["fallback_used"] in (True, False)
    if diag["fallback_used"]:
        assert diag["solver_name"] == "scipy_slsqp_fallback"
    else:
        assert diag["solver_status"] is not None


# --- src.backtest.run_static_backtest --------------------------------------

def test_static_backtest_populates_diagnostics_channel():
    returns = _synthetic_returns(n_assets=4, n_obs=300, seed=5)
    diagnostics: dict = {}
    result = run_static_backtest(
        returns, model_type="relaxed", diagnostics_out=diagnostics
    )
    assert {"solver", "covariance", "universe"} <= diagnostics.keys()
    assert isinstance(diagnostics["solver"], pd.DataFrame)
    assert isinstance(diagnostics["covariance"], pd.DataFrame)
    assert isinstance(diagnostics["universe"], pd.DataFrame)
    # At least one rebalance happens in a 300-day window.
    assert len(diagnostics["universe"]) >= 1
    universe = diagnostics["universe"]
    assert {"date", "asset_count", "included_assets", "excluded_assets"}.issubset(universe.columns)
    cov = diagnostics["covariance"]
    if not cov.empty:
        assert "n_obs_to_n_assets_ratio" in cov.columns
        assert "covariance_condition_number" in cov.columns
    solver = diagnostics["solver"]
    if not solver.empty:
        assert "solver_success" in solver.columns
        assert "fallback_used" in solver.columns
    # The primary result frame is still produced.
    assert len(result) == len(returns)


def test_static_backtest_universe_uses_only_prior_data():
    """Universe at rebalance date d must depend only on data with index < d."""
    returns = _synthetic_returns(n_assets=4, n_obs=250, seed=13)
    # Introduce a column that becomes valid only after a known date — the
    # universe diagnostic should record it as excluded for rebalances that
    # precede that date.
    late_col = returns["asset_3"].copy()
    cutoff = returns.index[120]
    returns["asset_3"] = np.where(returns.index < cutoff, np.nan, late_col.values)

    diagnostics: dict = {}
    run_static_backtest(returns, model_type="relaxed", diagnostics_out=diagnostics)
    universe = diagnostics["universe"]
    early = universe[universe["date"] < cutoff]
    if not early.empty:
        assert all("asset_3" in row for row in early["excluded_assets"].tolist())


# --- guardrail: no bare excepts ---------------------------------------------

def test_risk_parity_source_has_no_bare_except_pass():
    """Scan code lines only (skip strings/docstrings/comments) for bare excepts."""
    import ast
    import io
    import tokenize

    src = Path(__file__).resolve().parent.parent / "src" / "risk_parity.py"
    text = src.read_text(encoding="utf-8")

    # 1. AST level: no ExceptHandler with type=None (i.e., bare ``except:``).
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            assert node.type is not None, (
                f"bare except: found at src/risk_parity.py line {node.lineno}"
            )

    # 2. Token level: strip strings and comments, then assert the pattern is
    #    absent from executable code.
    code_tokens = []
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type in (tokenize.STRING, tokenize.COMMENT):
            continue
        code_tokens.append(tok.string)
    code_only = " ".join(code_tokens)
    assert "except : pass" not in code_only
    assert "except: pass" not in code_only
