import numpy as np
import pandas as pd
import pytest

from scripts.run_convex_adaptive_rrp import run_hrp_like
from scripts.run_global_rrp_rolling_calibration import BASE
from src.backtest import run_static_backtest
from src.benchmarks import run_benchmark_backtest
from src.incremental_backtest import run_incremental_backtest


@pytest.fixture
def history():
    dates = pd.bdate_range("2024-01-01", periods=140).drop(pd.Timestamp("2024-05-10"))
    data = pd.DataFrame(np.random.default_rng(13).normal(.0002, .007, (len(dates), 3)),
                        index=dates, columns=["沪深300ETF", "5年国债ETF", "黄金ETF"])
    data.iloc[:20, 2] = np.nan
    return data


def runner_for(model, config=None):
    config = {**BASE, **(config or {})}

    def run(data, resume, diagnostics):
        if model == "Global RRP":
            return run_static_backtest(data, "relaxed", config, diagnostics, resume=resume)
        if model in {"hrp", "herc"}:
            return run_hrp_like(data, model, config["transaction_cost_bps"],
                                rebalance_frequency=config["rebalance_frequency"], resume=resume)
        return run_benchmark_backtest(data, model, transaction_cost_bps=config["transaction_cost_bps"],
                                      rebalance_frequency=config["rebalance_frequency"], resume=resume)
    return run


@pytest.mark.parametrize("model", ["Global RRP", "hrp", "herc", "Equal Weight Benchmark", "60/40 Benchmark"])
def test_append_and_repeat_match_full_daily_results_and_diagnostics(history, tmp_path, model):
    runner = runner_for(model)
    contract = {"configuration": BASE, "model": model}
    # Wednesday's provisional rebalance disappears when Thursday arrives.
    split = history.index.get_loc(pd.Timestamp("2024-05-08")) + 1
    path = tmp_path / "backtest.json"
    old = run_incremental_backtest(history.iloc[:split], runner, path=path, contract=contract)
    assert bool(old.is_rebalance_day.iloc[-1])
    actual_diagnostics, expected_diagnostics = {}, {}
    computed = []

    def measured(data, resume, diagnostics):
        result = runner(data, resume, diagnostics)
        computed.append(len(result))
        return result

    actual = run_incremental_backtest(history, measured, path=path, contract=contract,
                                      diagnostics_out=actual_diagnostics)
    expected = runner(history, None, expected_diagnostics)
    pd.testing.assert_frame_equal(actual, expected, check_exact=True)
    assert computed == [len(history) - split + 1]
    for key, value in expected_diagnostics.items():
        pd.testing.assert_frame_equal(actual_diagnostics[key], value, check_exact=True)
    computed.clear()
    repeated = run_incremental_backtest(history, measured, path=path, contract=contract)
    assert computed == []
    pd.testing.assert_frame_equal(repeated, expected, check_exact=True)


@pytest.mark.parametrize("change", ["history", "configuration", "broken", "force"])
def test_revision_or_invalid_state_rebuilds_full_history(history, tmp_path, change):
    path = tmp_path / "backtest.json"
    contract = {"configuration": BASE}
    runner = runner_for("Equal Weight Benchmark")
    run_incremental_backtest(history, runner, path=path, contract=contract)
    revised = history.copy()
    if change == "history":
        revised.iloc[70, 0] += .03
    elif change == "configuration":
        contract = {"configuration": {**BASE, "transaction_cost_bps": 5.}}
        runner = runner_for("Equal Weight Benchmark", contract["configuration"])
    elif change == "broken":
        path.write_text("{broken", encoding="utf-8")
    resumed = []

    def measured(data, resume, diagnostics):
        resumed.append(resume is None)
        return runner(data, resume, diagnostics)

    actual = run_incremental_backtest(revised, measured, path=path, contract=contract, force=change == "force")
    assert resumed == [True]
    pd.testing.assert_frame_equal(actual, runner(revised, None, {}), check_exact=True)


@pytest.mark.parametrize("frequency", ["2W", "M", "Q"])
def test_sample_boundary_rollback_respects_full_rebalance_calendar(history, tmp_path, frequency):
    config = {**BASE, "rebalance_frequency": frequency}
    runner = runner_for("Equal Weight Benchmark", config)
    path = tmp_path / "backtest.json"
    contract = {"configuration": config}
    run_incremental_backtest(history.iloc[:113], runner, path=path, contract=contract)
    actual = run_incremental_backtest(history, runner, path=path, contract=contract)
    pd.testing.assert_frame_equal(actual, runner(history, None, {}), check_exact=True)


def test_future_schedule_extension_keeps_completed_history(history, tmp_path):
    path = tmp_path / "backtest.json"
    runner = runner_for("Equal Weight Benchmark")
    contract = {"configuration": {**BASE, "rrp_parameter_schedule": []}}
    run_incremental_backtest(history.iloc[:110], runner, path=path, contract=contract)
    contract["configuration"]["rrp_parameter_schedule"] = [
        {"effective_date": "2025-01-01", "rrp_variance_penalty": .1, "lambda_pen": 2.}
    ]
    checkpoints = []

    def measured(data, resume, diagnostics):
        checkpoints.append(resume is not None)
        return runner(data, resume, diagnostics)

    actual = run_incremental_backtest(history, measured, path=path, contract=contract)
    assert checkpoints == [True]
    pd.testing.assert_frame_equal(actual, runner(history, None, {}), check_exact=True)


def test_primary_crosses_year_with_new_annual_parameters(tmp_path):
    dates = pd.bdate_range("2023-09-01", "2024-03-01")
    data = pd.DataFrame(np.random.default_rng(19).normal(.0001, .006, (len(dates), 3)),
                        index=dates, columns=["沪深300ETF", "5年国债ETF", "黄金ETF"])
    old = {**BASE, "rrp_parameter_schedule": [
        {"effective_date": "2023-01-01", "rrp_variance_penalty": .1, "lambda_pen": 2.}
    ]}
    new = {**old, "rrp_parameter_schedule": [*old["rrp_parameter_schedule"],
        {"effective_date": "2024-01-01", "rrp_variance_penalty": .3, "lambda_pen": 4.}
    ]}
    path = tmp_path / "primary.json"
    run_incremental_backtest(data.loc[:"2023-12-27"], runner_for("Global RRP", old),
                              path=path, contract={"configuration": old})
    diagnostics, expected_diagnostics = {}, {}
    checkpoints = []
    runner = runner_for("Global RRP", new)

    def measured(frame, resume, output):
        checkpoints.append(resume is not None)
        return runner(frame, resume, output)

    actual = run_incremental_backtest(data, measured, path=path, contract={"configuration": new},
                                      diagnostics_out=diagnostics)
    expected = runner(data, None, expected_diagnostics)
    assert checkpoints == [True]
    pd.testing.assert_frame_equal(actual, expected, check_exact=True)
    for key in diagnostics:
        pd.testing.assert_frame_equal(diagnostics[key], expected_diagnostics[key], check_exact=True)


def test_credentials_are_not_written_to_checkpoint(history, tmp_path):
    path = tmp_path / "backtest.json"
    run_incremental_backtest(history, runner_for("Equal Weight Benchmark"), path=path,
                              contract={"configuration": {**BASE, "tushare_token": "private-token"}})
    assert "private-token" not in path.read_text(encoding="utf-8")


def test_csv_roundoff_keeps_incremental_prefix(history, tmp_path):
    path = tmp_path / "backtest.json"
    contract = {"configuration": BASE}
    runner = runner_for("Equal Weight Benchmark")
    run_incremental_backtest(history.iloc[:110], runner, path=path, contract=contract)
    revised = history.copy()
    revised.iloc[70, 0] += 5e-16
    resumed = []

    def measured(data, resume, diagnostics):
        resumed.append(resume is not None)
        return runner(data, resume, diagnostics)

    actual = run_incremental_backtest(revised, measured, path=path, contract=contract)
    assert resumed == [True]
    expected = runner(revised, None, {})
    pd.testing.assert_frame_equal(actual, expected, check_exact=False, rtol=0, atol=1e-14)
