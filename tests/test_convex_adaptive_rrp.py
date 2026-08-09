import numpy as np
import pandas as pd

from src.adaptive_risk_budget import REGIME_LABELS, adaptive_budget_target, online_regime_state
from src.asset_graph_features import rolling_correlation_graph_features
from src.convex_adaptive_rrp import (
    ConvexRRPConfig,
    rebalance_dates_for_frequency,
    run_convex_adaptive_backtest,
    solve_convex_rrp,
)
from scripts.run_convex_adaptive_rrp import config_row
from scripts.run_walkforward_validation import split_windows


def sample_returns(n=90, k=5):
    rng = np.random.default_rng(42)
    data = rng.normal(0.0002, 0.01, size=(n, k))
    dates = pd.bdate_range("2021-01-01", periods=n)
    return pd.DataFrame(data, index=dates, columns=[f"asset_{i}" for i in range(k)])


def test_graph_features_are_bounded():
    features = rolling_correlation_graph_features(sample_returns())
    assert 0.0 <= features["correlation_stress_score"] <= 1.0
    assert 0.0 <= features["largest_cluster_size_ratio"] <= 1.0
    assert features["effective_cluster_count"] >= 1.0


def test_online_regime_labels_are_ordered_and_budget_normalized():
    returns = sample_returns()
    graph = rolling_correlation_graph_features(returns)
    state = online_regime_state(returns, graph_features=graph)
    assert state["regime_label"] in REGIME_LABELS
    budget = adaptive_budget_target(returns, graph, state["regime_label"])
    assert np.isclose(float(budget.sum()), 1.0)
    assert (budget >= 0.0).all()


def test_convex_solver_outputs_weights_and_diagnostics():
    returns = sample_returns()
    cfg = ConvexRRPConfig(max_weight=0.60, turnover_cap=0.50, cvar_penalty=0.05)
    weights, diagnostics = solve_convex_rrp(returns, config=cfg)
    assert np.isclose(float(weights.sum()), 1.0)
    assert (weights >= -1e-8).all()
    assert diagnostics["solver_name"]
    assert "fallback_used" in diagnostics


def test_backtest_outputs_solver_graph_and_regime_diagnostics():
    returns = sample_returns(n=150, k=4)
    cfg = ConvexRRPConfig(
        lookback_days=45,
        max_weight=0.70,
        use_graph_features=True,
        use_online_regime=True,
        use_transaction_cost_objective=True,
    )
    result, solver, graph, regime = run_convex_adaptive_backtest(returns, cfg)
    assert not result.empty
    assert {"gross_return", "net_return", "transaction_cost", "turnover"}.issubset(result.columns)
    assert not solver.empty
    assert "fallback_used" in solver.columns
    assert not graph.empty
    assert not regime.empty
    assert set(regime["regime_label"]).issubset(set(REGIME_LABELS))


def test_rebalance_frequency_dates_are_last_available_observations():
    returns = sample_returns(n=90, k=3)

    weekly = rebalance_dates_for_frequency(returns, "W")
    biweekly = rebalance_dates_for_frequency(returns, "2W")
    monthly = rebalance_dates_for_frequency(returns, "M")
    quarterly = rebalance_dates_for_frequency(returns, "Q")

    expected_weekly = set(returns.groupby(returns.index.to_period("W")).tail(1).index)
    expected_monthly = set(returns.groupby(returns.index.to_period("M")).tail(1).index)
    expected_quarterly = set(returns.groupby(returns.index.to_period("Q")).tail(1).index)

    assert weekly == expected_weekly
    assert biweekly.issubset(weekly)
    assert len(biweekly) <= len(weekly)
    assert monthly == expected_monthly
    assert quarterly == expected_quarterly


def test_backtest_accepts_non_monthly_rebalance_frequency():
    returns = sample_returns(n=150, k=4)
    cfg = ConvexRRPConfig(lookback_days=45, max_weight=0.70, rebalance_frequency="W")

    result, solver, _, _ = run_convex_adaptive_backtest(returns, cfg)

    assert not result.empty
    assert int(result["is_rebalance_day"].sum()) >= len(solver)
    assert result["turnover"].fillna(0.0).sum() > 0.0


def test_candidate_config_row_exposes_audit_schema_and_legacy_aliases():
    cfg = ConvexRRPConfig(lookback_days=120, max_weight=0.45, cvar_penalty=0.08, budget_penalty=0.10)
    metrics = {
        "sharpe_ratio": 0.9,
        "calmar_ratio": 1.2,
        "max_drawdown": -0.05,
        "cvar_95_daily_loss": 0.006,
        "annualized_turnover": 0.12,
        "avg_monthly_turnover": 0.01,
        "net_annual_return": 0.06,
    }
    row = config_row("candidate_01", cfg, metrics, fallback_rate=0.0, score=1.23, reject_reason="")

    audit_columns = {
        "candidate_id",
        "candidate_name",
        "selected",
        "selection_score",
        "sharpe",
        "calmar",
        "max_drawdown",
        "cvar",
        "annual_turnover",
        "avg_monthly_turnover",
        "turnover_penalty",
        "cvar_penalty",
        "budget_penalty",
        "max_weight",
        "lookback_days",
        "covariance_method",
        "reject_reason",
        "notes",
    }
    legacy_columns = {"lambda_cvar", "upper_bound_i", "lookback_window", "Sharpe", "Calmar"}
    assert audit_columns.issubset(row)
    assert legacy_columns.issubset(row)
    assert row["candidate_id"] == "candidate_01"
    assert row["lambda_cvar"] == row["cvar_penalty"]
    assert row["upper_bound_i"] == row["max_weight"]
    assert "rolling OOS selection" in row["notes"]
    assert "never select the public historical path" in row["notes"]


def test_walkforward_split_windows_are_ordered_without_future_overlap():
    returns = sample_returns(n=520, k=3)
    splits = split_windows(
        returns,
        train_months=6,
        validation_months=2,
        test_months=1,
        step_months=2,
        max_splits=2,
    )

    assert len(splits) == 2
    for split in splits:
        assert split["train_start"] < split["train_end"] < split["validation_start"]
        assert split["validation_start"] <= split["validation_end"] < split["test_start"]
        assert split["test_start"] <= split["test_end"]
