from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def test_quarterly_oos_windows_use_pre_eval_warmup_embargo_and_full_coverage() -> None:
    from src.afml_oos import generate_quarterly_oos_windows

    index = pd.bdate_range("2015-01-01", "2018-07-31")
    returns = pd.DataFrame({"asset": 0.0}, index=index)

    windows = generate_quarterly_oos_windows(
        returns,
        evaluation_start="2018-01-02",
        evaluation_end="2018-07-31",
        train_months=24,
        validation_months=6,
        embargo_trading_days=1,
    )

    assert len(windows) == 3
    assert windows[0]["train_start"] < pd.Timestamp("2018-01-02")
    assert windows[0]["validation_end"] < windows[0]["embargo_start"] < windows[0]["test_start"]
    assert windows[0]["test_start"] == pd.Timestamp("2018-01-02")
    assert windows[-1]["test_end"] == pd.Timestamp("2018-07-31")

    covered = pd.DatetimeIndex([])
    for window in windows:
        test_days = index[(index >= window["test_start"]) & (index <= window["test_end"])]
        covered = covered.append(test_days)
        assert window["validation_end"] < window["test_start"]
        assert window["train_end"] < window["validation_start"]
    expected = index[(index >= "2018-01-02") & (index <= "2018-07-31")]
    assert covered.equals(expected)


def test_oos_selector_uses_only_pre_test_validation_data() -> None:
    from src.afml_oos import select_oos_candidates

    dates = pd.bdate_range("2017-07-03", "2018-06-29")
    first = pd.DataFrame(
        {
            "date": dates,
            "net_return": np.where(dates < pd.Timestamp("2018-01-02"), 0.001, -0.003),
            "portfolio_return": np.where(dates < pd.Timestamp("2018-01-02"), 0.001, -0.003),
            "turnover": 0.0,
        }
    )
    second = first.copy()
    second["net_return"] = -first["net_return"]
    second["portfolio_return"] = second["net_return"]
    candidate_results = {"candidate_01": first, "candidate_02": second}
    solver = {
        name: pd.DataFrame({"date": dates, "fallback_used": False})
        for name in candidate_results
    }
    windows = [
        {
            "split_id": "oos_01",
            "train_start": pd.Timestamp("2015-07-01"),
            "train_end": pd.Timestamp("2017-06-30"),
            "validation_start": pd.Timestamp("2017-07-03"),
            "validation_end": pd.Timestamp("2017-12-28"),
            "embargo_start": pd.Timestamp("2017-12-29"),
            "embargo_end": pd.Timestamp("2017-12-29"),
            "test_start": pd.Timestamp("2018-01-02"),
            "test_end": pd.Timestamp("2018-03-30"),
        },
        {
            "split_id": "oos_02",
            "train_start": pd.Timestamp("2015-10-01"),
            "train_end": pd.Timestamp("2017-09-29"),
            "validation_start": pd.Timestamp("2017-10-02"),
            "validation_end": pd.Timestamp("2018-03-29"),
            "embargo_start": pd.Timestamp("2018-03-30"),
            "embargo_end": pd.Timestamp("2018-03-30"),
            "test_start": pd.Timestamp("2018-04-02"),
            "test_end": pd.Timestamp("2018-06-29"),
        },
    ]

    selected = select_oos_candidates(windows, candidate_results, solver, risk_free_returns=0.0)

    assert selected["selected_candidate_id"].tolist() == ["candidate_01", "candidate_02"]
    assert (pd.to_datetime(selected["validation_end"]) < pd.to_datetime(selected["test_start"])).all()
    assert selected["uses_future_data"].eq(False).all()


def test_oos_selector_prefers_zero_fallback_candidate_before_score() -> None:
    from src.afml_oos import select_oos_candidates_from_scores

    scores = pd.DataFrame(
        [
            {
                "split_id": "afml_oos_01",
                "candidate_id": "candidate_high_score_fallback",
                "validation_score": 10.0,
                "validation_solver_fallback_rate": 1.0,
                "test_start": "2018-01-02",
                "test_end": "2018-03-30",
            },
            {
                "split_id": "afml_oos_01",
                "candidate_id": "candidate_valid",
                "validation_score": 1.0,
                "validation_solver_fallback_rate": 0.0,
                "test_start": "2018-01-02",
                "test_end": "2018-03-30",
            },
        ]
    )

    selected = select_oos_candidates_from_scores(scores)

    assert selected["selected_candidate_id"].item() == "candidate_valid"
    assert selected["solver_gate_passed"].item() is True


def test_public_selector_keeps_low_turnover_incumbent_without_significant_sharpe_gain() -> None:
    from src.afml_oos import select_public_low_turnover_oos_candidates

    scores = pd.DataFrame(
        [
            {
                "split_id": "warmup_01",
                "candidate_id": "candidate_03",
                "validation_sharpe": 1.00,
                "validation_avg_monthly_turnover": 0.01,
                "validation_solver_fallback_rate": 0.0,
                "validation_observations": 120,
                "test_start": "2017-10-09",
                "test_end": "2017-12-29",
            },
            {
                "split_id": "warmup_01",
                "candidate_id": "candidate_04",
                "validation_sharpe": 0.80,
                "validation_avg_monthly_turnover": 0.01,
                "validation_solver_fallback_rate": 0.0,
                "validation_observations": 120,
                "test_start": "2017-10-09",
                "test_end": "2017-12-29",
            },
            {
                "split_id": "afml_oos_01",
                "candidate_id": "candidate_03",
                "validation_sharpe": 0.90,
                "validation_avg_monthly_turnover": 0.01,
                "validation_solver_fallback_rate": 0.0,
                "validation_observations": 120,
                "test_start": "2018-01-02",
                "test_end": "2018-03-30",
            },
            {
                "split_id": "afml_oos_01",
                "candidate_id": "candidate_04",
                "validation_sharpe": 1.00,
                "validation_avg_monthly_turnover": 0.01,
                "validation_solver_fallback_rate": 0.0,
                "validation_observations": 120,
                "test_start": "2018-01-02",
                "test_end": "2018-03-30",
            },
            {
                "split_id": "afml_oos_01",
                "candidate_id": "candidate_exploratory",
                "validation_sharpe": 9.00,
                "validation_avg_monthly_turnover": 0.50,
                "validation_solver_fallback_rate": 0.0,
                "validation_observations": 120,
                "test_start": "2018-01-02",
                "test_end": "2018-03-30",
            },
        ]
    )

    selected = select_public_low_turnover_oos_candidates(
        scores,
        eligible_candidate_ids=("candidate_03", "candidate_04"),
    )

    assert selected["selected_candidate_id"].tolist() == ["candidate_03", "candidate_03"]
    assert selected["selection_action"].tolist() == ["initialize", "retain_incumbent"]
    assert selected["turnover_gate_passed"].all()


def test_public_selector_switches_after_statistically_significant_sharpe_gain() -> None:
    from src.afml_oos import select_public_low_turnover_oos_candidates

    scores = pd.DataFrame(
        [
            {
                "split_id": split_id,
                "candidate_id": candidate_id,
                "validation_sharpe": sharpe,
                "validation_avg_monthly_turnover": 0.01,
                "validation_solver_fallback_rate": 0.0,
                "validation_observations": 100_000,
                "test_start": test_start,
                "test_end": test_end,
            }
            for split_id, test_start, test_end, candidate_id, sharpe in [
                ("warmup_01", "2017-10-09", "2017-12-29", "candidate_03", 1.00),
                ("warmup_01", "2017-10-09", "2017-12-29", "candidate_04", 0.80),
                ("afml_oos_01", "2018-01-02", "2018-03-30", "candidate_03", 0.50),
                ("afml_oos_01", "2018-01-02", "2018-03-30", "candidate_04", 1.00),
            ]
        ]
    )

    selected = select_public_low_turnover_oos_candidates(
        scores,
        eligible_candidate_ids=("candidate_03", "candidate_04"),
    )

    assert selected["selected_candidate_id"].tolist() == ["candidate_03", "candidate_04"]
    assert selected["selection_action"].tolist() == ["initialize", "switch_significant_sharpe"]


def test_scheduled_backtest_keeps_positions_and_charges_switch_turnover(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.convex_adaptive_rrp as module
    from src.convex_adaptive_rrp import ConvexRRPConfig, run_convex_adaptive_schedule_backtest

    dates = pd.bdate_range("2020-01-01", periods=100)
    alternating = np.where(np.arange(len(dates)) % 2 == 0, 0.001, -0.001)
    returns = pd.DataFrame({"asset_a": alternating, "asset_b": -alternating}, index=dates)
    first_start = dates[70]
    second_start = dates[80]
    schedule = pd.DataFrame(
        [
            {"test_start": first_start, "test_end": dates[79], "selected_candidate_id": "candidate_a"},
            {"test_start": second_start, "test_end": dates[-1], "selected_candidate_id": "candidate_b"},
        ]
    )
    configs = {
        "candidate_a": ConvexRRPConfig(lookback_days=60, return_reward=1.0),
        "candidate_b": ConvexRRPConfig(lookback_days=60, return_reward=2.0),
    }

    def fake_solver(window, previous_weights=None, config=None, budget_target=None, graph_features=None, regime_label=None):
        weights = np.array([1.0, 0.0]) if config.return_reward == 1.0 else np.array([0.0, 1.0])
        return weights, {"fallback_used": False, "inaccurate_solution": False, "solver_name": "fake"}

    monkeypatch.setattr(module, "solve_convex_rrp", fake_solver)
    result, solver, _, _ = run_convex_adaptive_schedule_backtest(returns, schedule, configs)

    first = result.loc[result["date"].eq(first_start)].iloc[0]
    switch = result.loc[result["date"].eq(second_start)].iloc[0]
    monthly_rebalances = set(returns.groupby(returns.index.to_period("M")).tail(1).index)
    next_rebalance = min(date for date in monthly_rebalances if date >= second_start)
    applied = result.loc[result["date"].eq(next_rebalance)].iloc[0]
    assert first["selected_candidate_id"] == "candidate_a"
    assert first["turnover"] == pytest.approx(1.0)
    assert switch["selected_candidate_id"] == "candidate_b"
    assert switch["weight_asset_a"] == pytest.approx(1.0)
    assert switch["weight_asset_b"] == pytest.approx(0.0)
    assert switch["turnover"] == pytest.approx(0.0)
    assert applied["weight_asset_a"] == pytest.approx(0.0)
    assert applied["weight_asset_b"] == pytest.approx(1.0)
    assert applied["turnover"] == pytest.approx(2.0)
    assert applied["transaction_cost"] == pytest.approx(2.0 * 3.0 / 10000.0)
    assert solver.loc[solver["date"].eq(next_rebalance), "selected_candidate_id"].item() == "candidate_b"


def test_public_oos_repricing_holds_weights_and_turnover_fixed() -> None:
    from scripts.public_oos import reprice_public_result

    source = pd.DataFrame(
        {
            "date": pd.bdate_range("2018-01-02", periods=3),
            "gross_return": [0.01, -0.01, 0.005],
            "turnover": [1.0, 0.0, 0.5],
            "weight_a": [1.0, 1.0, 0.5],
        }
    )

    repriced = reprice_public_result(source, transaction_cost_bps=10.0)

    assert repriced["turnover"].equals(source["turnover"])
    assert repriced["weight_a"].equals(source["weight_a"])
    assert repriced["transaction_cost"].tolist() == pytest.approx([0.001, 0.0, 0.0005])
    assert repriced["net_return"].tolist() == pytest.approx([0.009, -0.01, 0.0045])
