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
            "net_return": np.where(dates < pd.Timestamp("2018-01-02"), 0.002, -0.002),
            "portfolio_return": np.where(dates < pd.Timestamp("2018-01-02"), 0.002, -0.002),
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


def test_scheduled_backtest_keeps_positions_and_charges_switch_turnover(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.convex_adaptive_rrp as module
    from src.convex_adaptive_rrp import ConvexRRPConfig, run_convex_adaptive_schedule_backtest

    dates = pd.bdate_range("2020-01-01", periods=100)
    returns = pd.DataFrame({"asset_a": 0.001, "asset_b": 0.0}, index=dates)
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
    assert first["selected_candidate_id"] == "candidate_a"
    assert first["turnover"] == pytest.approx(1.0)
    assert switch["selected_candidate_id"] == "candidate_b"
    assert switch["weight_asset_a"] == pytest.approx(0.0)
    assert switch["weight_asset_b"] == pytest.approx(1.0)
    assert switch["turnover"] == pytest.approx(2.0)
    assert switch["transaction_cost"] == pytest.approx(2.0 * 3.0 / 10000.0)
    assert solver.loc[solver["date"].eq(second_start), "selected_candidate_id"].item() == "candidate_b"
