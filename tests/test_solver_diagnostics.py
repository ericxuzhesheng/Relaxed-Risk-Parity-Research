"""Reliability tests for the DCP-compliant convex solvers.

These tests focus on the diagnostics channel introduced for solver
fallbacks, covariance health, and investable-universe freezing. They are
deliberately lightweight: small synthetic returns, no large CSV fixtures,
deterministic seeds. They cover:

* ``src.risk_parity`` records solver status + DCP and fallback flags in the
  ``diagnostics`` dict.
* ``src.risk_parity`` weights satisfy the simplex constraint.
* ``src.risk_parity`` fails closed on a malformed covariance.
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
    assert diag["solver_name"] in {"CLARABEL", "ECOS", "SCS"}
    assert diag["solver_success"] is True
    assert diag["problem_is_dcp"] is True
    assert diag["fallback_used"] is False


def test_solve_standard_rp_fails_closed_on_nan_covariance():
    cov = np.full((4, 4), np.nan)
    diag: dict = {}
    with pytest.raises(ValueError, match="non-finite"):
        solve_standard_rp(cov, 4, get_config(), diagnostics=diag)
    assert diag == {}


def test_solve_relaxed_rp_fails_closed_on_nan_covariance():
    cov = np.full((4, 4), np.nan)
    mu = np.zeros(4)
    theta = np.eye(4)
    diag: dict = {}
    with pytest.raises(ValueError, match="non-finite"):
        solve_relaxed_rp(cov, mu, theta, 4, 0.0, get_config(), diagnostics=diag)
    assert diag == {}


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
    assert diag["solver_name"] in {"CLARABEL", "ECOS", "SCS"}
    assert diag["problem_is_dcp"] is True
    assert diag["fallback_used"] is False


def test_optimize_with_leverage_has_no_hidden_retry_or_fallback():
    cov = _wellposed_cov(4)
    diag: dict = {}
    optimize_with_leverage(
        cov, 4, bond_indices=[0], config=get_config(), diagnostics=diag
    )
    assert "retry_count" not in diag
    assert diag["fallback_used"] is False


def test_relaxed_leverage_formulation_is_dcp_and_feasible():
    cov = _wellposed_cov(4)
    cfg = get_config()
    diag: dict = {}
    weights, leverage = optimize_with_leverage(
        cov,
        4,
        bond_indices=[0],
        mu=np.array([0.03, 0.08, 0.07, 0.06]),
        R_base=0.06,
        is_relaxed=True,
        config=cfg,
        diagnostics=diag,
    )
    assert diag["problem_is_dcp"] is True
    assert diag["max_constraint_violation"] <= 1e-6
    assert weights.sum() == pytest.approx(1.0, abs=1e-6)
    assert 1.0 - 1e-6 <= leverage[0] <= cfg["bond_leverage_upper"] + 1e-6


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


def test_universe_diagnostic_invariant_under_future_perturbation():
    """Mutating returns AFTER rebalance date d must not change the universe
    or solver diagnostics computed AT date d. This is the strict
    point-in-time invariant the audit asked for: inclusion decisions depend
    only on data strictly preceding d.
    """
    base = _synthetic_returns(n_assets=4, n_obs=300, seed=99)
    diag_base: dict = {}
    run_static_backtest(base, model_type="relaxed", diagnostics_out=diag_base)
    universe_base = diag_base["universe"].copy()

    # Build a perturbed series that is byte-identical for all dates < pivot
    # and totally different (random noise, possibly NaN) for dates >= pivot.
    pivot = base.index[200]
    rng = np.random.default_rng(0)
    perturbed = base.copy()
    mask = perturbed.index >= pivot
    perturbed.loc[mask, :] = rng.normal(0.0, 0.05, size=(mask.sum(), perturbed.shape[1]))
    # Sprinkle some NaNs into the future too.
    perturbed.loc[mask, perturbed.columns[0]] = np.where(
        rng.random(mask.sum()) < 0.3, np.nan, perturbed.loc[mask, perturbed.columns[0]].values
    )

    diag_pert: dict = {}
    run_static_backtest(perturbed, model_type="relaxed", diagnostics_out=diag_pert)
    universe_pert = diag_pert["universe"]

    # For every rebalance date strictly before the pivot, the universe rows
    # must be identical between the two runs.
    cols = ["asset_count", "min_observations_required", "included_assets", "excluded_assets"]
    a = universe_base[universe_base["date"] < pivot][cols].reset_index(drop=True)
    b = universe_pert[universe_pert["date"] < pivot][cols].reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b)


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
