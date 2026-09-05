from dataclasses import replace
import json

import numpy as np
import pandas as pd
import pytest
import scripts.run_weekly_constraint_research as research

from scripts.run_weekly_constraint_research import VARIANTS, check_result, variant_config, unfiltered_returns, result_summary
from src.convex_adaptive_rrp import ConvexRRPConfig, rebalance_dates_for_frequency, run_convex_adaptive_schedule_backtest, scenario_cvar, solve_convex_rrp


def sample():
    rng = np.random.default_rng(73)
    return pd.DataFrame(rng.normal(0.0002, [0.0001, 0.002, 0.012, 0.01], (150, 4)),
                        index=pd.bdate_range("2020-01-01", periods=150),
                        columns=["日利ETF", "信用债ETF", "沪深300ETF", "黄金ETF"])


def config():
    return ConvexRRPConfig(max_weight=0.4, group_bounds={"cash": (0, .3)}, lookback_days=100, rebalance_frequency="W")


def test_fixed_ablations_preserve_independent_caps():
    cfg = config()
    assert len(VARIANTS) == 9
    assert variant_config(cfg, "no_cash_cap").max_weight == .4
    assert "cash" not in variant_config(cfg, "no_cash_cap").group_bounds
    assert variant_config(cfg, "no_asset_cap").group_bounds == cfg.group_bounds
    assert variant_config(cfg, "no_asset_cap").max_weight == 1
    assert cfg.group_bounds == {"cash": (0, .3)}
    assert variant_config(cfg, "ledoit_wolf").covariance_method == "ledoit_wolf"
    assert not variant_config(cfg, "ledoit_wolf").covariance_allow_fallback


def test_unfiltered_returns_keep_crashes_and_do_not_change_with_future_prices():
    dates = pd.bdate_range("2020-01-01", periods=120)
    prices = pd.DataFrame({"a": 100 * np.cumprod(1 + np.r_[np.repeat(.001, 90), -.3, np.repeat(.001, 29)])}, index=dates)
    prices["late"] = np.nan
    prices.loc[dates[100]:, "late"] = np.arange(20) + 50
    before = unfiltered_returns(prices.iloc[:100])
    after = unfiltered_returns(prices)
    pd.testing.assert_frame_equal(before, after.loc[before.index], check_freq=False)
    assert after.loc[dates[90], "a"] == pytest.approx(-.3)
    assert after.loc[:dates[100], "late"].isna().all()


def test_legacy_reproduction_is_isolated_from_production_returns():
    changes = np.r_[np.repeat(.001, 90), -.30, np.repeat(.001, 9)]
    dates = pd.bdate_range("2020-01-01", periods=len(changes))
    prices = pd.DataFrame({"asset": 100 * np.cumprod(1 + changes)}, index=dates)
    assert dates[90] not in research.legacy_reproduction_returns(prices).index
    assert research.price_to_returns(prices).loc[dates[90], "asset"] == pytest.approx(-.30)
    pd.testing.assert_frame_equal(research.unfiltered_returns(prices), research.price_to_returns(prices))


def test_empirical_cvar_matches_epigraph_with_fractional_tail():
    import cvxpy as cp
    losses = np.array([-2, 0, 1, 1, 8.])
    eta = cp.Variable()
    for beta in [.5, .73, .95]:
        problem = cp.Problem(cp.Minimize(eta + cp.sum(cp.pos(losses - eta)) / (len(losses) * (1 - beta))))
        problem.solve(solver="CLARABEL")
        assert scenario_cvar(losses, beta) == pytest.approx(problem.value, abs=1e-6)


def test_optional_diagnostics_and_relative_cvar_are_consistent():
    data = sample()
    previous = np.array([.3, .3, .2, .2])
    w, old = solve_convex_rrp(data, previous, config())
    detailed, diag = solve_convex_rrp(data, previous, config(), collect_constraint_diagnostics=True)
    assert "constraints_json" not in old
    np.testing.assert_allclose(w, detailed, atol=1e-9)
    records = json.loads(diag["constraints_json"])
    assert any(r["constraint"] == "group_cash_upper" for r in records)
    assert all(np.isfinite(r["dual"]) for r in records)
    assert min(r["slack"] for r in records) >= -5e-5
    relative, constrained = solve_convex_rrp(data, previous, config(), collect_constraint_diagnostics=True, relative_cvar_to_baseline=True)
    assert scenario_cvar(-data.values @ relative) <= scenario_cvar(-data.values @ w) + 5e-5
    np.testing.assert_allclose(relative, w, atol=5e-5)
    assert constrained["relative_cvar_baseline"] == pytest.approx(scenario_cvar(-data.values @ w))


def test_missing_scenarios_and_conflicts_fail_closed():
    data = sample()
    data.iloc[:100, 0] = np.nan
    with pytest.raises(ValueError, match="insufficient complete"):
        solve_convex_rrp(data, config=config(), relative_cvar_to_baseline=True)
    with pytest.raises(ValueError, match="sum to less"):
        solve_convex_rrp(sample(), config=replace(config(), max_weight=.1))
    with pytest.raises(ValueError, match="another hard"):
        solve_convex_rrp(sample(), config=replace(config(), cvar_limit=.1), relative_cvar_to_baseline=True)


def test_ledoit_wolf_uses_fitted_shrinkage_without_fallback():
    weights, diag = solve_convex_rrp(sample(), config=variant_config(config(), "ledoit_wolf"))
    assert 0 <= diag["covariance_shrinkage"] <= 1
    assert not diag["covariance_fallback_used"]
    assert weights.sum() == pytest.approx(1)


def test_weekly_holidays_and_past_only_scheduled_weights():
    data = sample()
    start = data.index[105]  # Initial allocation is the only forced non-week-end event.
    data = data.drop(data.index[107])
    data["纳指ETF"] = np.nan
    data.loc[data.index[-10]:, "纳指ETF"] = .001
    schedule = pd.DataFrame([{"test_start": start, "test_end": data.index[-1], "selected_candidate_id": "c"}])
    cfg = replace(config(), max_weight=.5)
    result, diag, _, _ = run_convex_adaptive_schedule_backtest(data, schedule, {"c": cfg}, collect_constraint_diagnostics=True)
    expected = rebalance_dates_for_frequency(data.loc[start:], "W") | {start}
    assert set(pd.to_datetime(diag.date)) == expected
    assert (pd.to_datetime(diag.information_cutoff) < pd.to_datetime(diag.date)).all()
    assert (result["weight_纳指ETF"] == 0).all()
    changed = data.copy()
    changed.loc[start:, "沪深300ETF"] += .10
    other, _, _, _ = run_convex_adaptive_schedule_backtest(changed, schedule, {"c": cfg})
    np.testing.assert_allclose(result.filter(regex="^weight_").iloc[0], other.filter(regex="^weight_").iloc[0], atol=1e-9)


def test_calendar_uses_thursday_when_friday_absent():
    data = pd.DataFrame(index=pd.to_datetime(["2026-01-05", "2026-01-08", "2026-01-12", "2026-01-16"]))
    # A nonempty value column is required by the calendar helper.
    data["a"] = 0
    assert rebalance_dates_for_frequency(data, "W") == set(pd.to_datetime(["2026-01-08", "2026-01-16"]))


def test_check_result_rejects_corrupt_costs():
    data = sample()
    schedule = pd.DataFrame([{"test_start": data.index[102], "test_end": data.index[-1], "selected_candidate_id": "c"}])
    result, diag, _, _ = run_convex_adaptive_schedule_backtest(data, schedule, {"c": config()}, collect_constraint_diagnostics=True)
    check_result(result, diag, data.loc[data.index[102]:])
    json.dumps(result_summary("test", result, {"risk_free_rate": 0.0, "trading_days_per_year": 243}))
    result.loc[0, "transaction_cost"] += .01
    with pytest.raises(ValueError, match="cost"):
        check_result(result, diag, data.loc[data.index[102]:])


def test_monthly_control_also_checks_accounting_and_information_cutoff():
    data = sample()
    start = data.groupby(data.index.to_period("M")).tail(1).index[3]
    schedule = pd.DataFrame([{"test_start": start, "test_end": data.index[-1], "selected_candidate_id": "c"}])
    result, diag, _, _ = run_convex_adaptive_schedule_backtest(data, schedule, {"c": replace(config(), rebalance_frequency="M")}, collect_constraint_diagnostics=True)
    check_result(result, diag, data.loc[start:], monthly=True)
    diag.loc[0, "information_cutoff"] = start
    with pytest.raises(ValueError, match="future information"):
        check_result(result, diag, data.loc[start:], monthly=True)


def test_missing_token_does_not_touch_existing_results(tmp_path, monkeypatch):
    output = tmp_path / "results/weekly_constraint_research"
    output.mkdir(parents=True)
    marker = output / "summary.csv"
    marker.write_text("existing results", encoding="utf-8")
    monkeypatch.setattr(research, "ROOT", tmp_path)
    monkeypatch.setattr(research.sys, "argv", ["research", "--resume"])
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        research.main()
    assert marker.read_text(encoding="utf-8") == "existing results"
    assert list(output.iterdir()) == [marker]


def test_zero_risk_free_changes_sharpe_but_not_portfolio_performance():
    dates = pd.bdate_range("2024-01-01", periods=80)
    net = np.tile([.001, -.0004, .0005, .0001], 20)
    result = pd.DataFrame({"date": dates, "gross_return": net, "net_return": net,
                           "transaction_cost": 0., "turnover": 0., "is_rebalance_day": False,
                           "weight_日利ETF": 1.})
    zero = result_summary("test", result, {"risk_free_rate": 0., "trading_days_per_year": 243})
    nonzero = result_summary("test", result, {"risk_free_rate": pd.Series(.0001, index=dates), "trading_days_per_year": 243})
    assert zero["sharpe_ratio"] == pytest.approx(net[1:].mean() / net[1:].std(ddof=1) * np.sqrt(243))
    assert zero["sharpe_ratio"] > nonzero["sharpe_ratio"]
    for metric in ("net_annual_return", "annualized_volatility", "max_drawdown", "total_transaction_cost"):
        assert zero[metric] == nonzero[metric]


def test_zero_risk_free_cli_uses_separate_output(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(research, "ROOT", tmp_path)
    monkeypatch.setenv("TUSHARE_TOKEN", "test-only")
    monkeypatch.setattr(research.sys, "argv", ["research", "--risk-free-zero", "--variant", "no_concentration_caps"])
    monkeypatch.setattr(research, "run", lambda output, resume, **kwargs: calls.append((output, kwargs)) or 0)
    with pytest.raises(SystemExit) as exited:
        research.main()
    assert exited.value.code == 0
    assert calls == [(tmp_path / "results/weekly_constraint_research_rf0", {"risk_free_zero": True, "selected_variant": "no_concentration_caps"})]


def test_primary_configuration_matches_approved_ablation_and_preserves_reference():
    from dataclasses import asdict
    from scripts.public_oos import primary_model_config, public_candidate_configs
    from src.utils import get_config
    original = public_candidate_configs(3.)["candidate_03"]
    before = asdict(original)
    primary = primary_model_config(original)
    assert asdict(primary) == asdict(variant_config(original, "no_concentration_caps"))
    assert asdict(original) == before
    assert primary.turnover_cap == original.turnover_cap
    assert "cash" not in primary.group_bounds
    assert get_config()["risk_free_rate"] == 0.


def test_public_variant_defaults_to_primary_and_research_can_opt_out(monkeypatch):
    import scripts.public_oos as public
    captured = []
    dates = pd.bdate_range("2020-01-01", periods=3)
    data = pd.DataFrame({"a": [.01, -.01, .02]}, index=dates)
    schedule = pd.DataFrame([{"test_start": dates[0], "test_end": dates[-1], "selected_candidate_id": "candidate_03"}])
    def fake_run(returns, planned, configs, **kwargs):
        captured.append(configs["candidate_03"])
        frame = pd.DataFrame({"date": dates, "gross_return": .001, "net_return": .001})
        return frame, pd.DataFrame(), None, None
    monkeypatch.setattr(public, "run_convex_adaptive_schedule_backtest", fake_run)
    public.run_public_oos_variant(data, selection=schedule)
    public.run_public_oos_variant(data, selection=schedule, primary_model=False, transform=lambda cfg: variant_config(cfg, "weekly_baseline"))
    assert captured[0].max_weight == 1.
    assert "cash" not in captured[0].group_bounds
    assert captured[1].max_weight == .4
    assert captured[1].group_bounds["cash"][1] == .3
    assert captured[0].rebalance_frequency == captured[1].rebalance_frequency == "W"
