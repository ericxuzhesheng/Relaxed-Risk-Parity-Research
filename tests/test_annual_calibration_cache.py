import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts import run_global_rrp_rolling_calibration as rolling
from src.utils import DEFAULT_CONFIG


@pytest.fixture
def experiment(monkeypatch, tmp_path):
    dates = pd.bdate_range("2018-01-01", "2021-08-31", name="date")
    returns = pd.DataFrame(np.random.default_rng(8).normal(0, .01, (len(dates), 2)),
                           index=dates, columns=["a", "b"])
    returns.iloc[:4, 1] = np.nan
    returns["zero"] = 0.0
    calls, neutral_calls = [], []
    monkeypatch.setattr(rolling, "FIRST_SCHEDULE_YEAR", 2020)
    monkeypatch.setattr(rolling, "LAST_SCHEDULE_YEAR", 2021)
    monkeypatch.setattr(rolling, "_calibration_contract", lambda: {"specification": 1})

    def neutral(data, model, config, diagnostics):
        neutral_calls.append(True)
        diagnostics["solver"] = pd.DataFrame({"date": data.index})

    def annual(data, year, diagnostics):
        calls.append(year)
        prior = data.loc[data.index < pd.Timestamp(f"{year}-01-01")]
        penalty = 1 + float(prior.a.sum())
        end = str(prior.index[-1].date())
        row = {"effective_date": f"{year}-01-01", "information_end": end,
               "rrp_variance_penalty": penalty, "lambda_pen": 2.,
               "candidate_count": 9, "within_one_standard_error_count": 9}
        frame = pd.DataFrame([
            {"schedule_year": year, "variance_penalty": penalty + rank,
             "shortfall_penalty": 2., "selected": rank == 0,
             "within_one_standard_error": True, "validation_end": end,
             "future_information_count": 0}
            for rank in range(9)
        ])
        return row, frame

    monkeypatch.setattr(rolling, "run_static_backtest", neutral)
    monkeypatch.setattr(rolling, "_calibrate_year", annual)
    result = rolling.calibrate_parameters(returns, force=True, output=tmp_path)
    rolling._save_calibration_cache(tmp_path, returns, *result)
    calls.clear()
    neutral_calls.clear()
    return returns, tmp_path, calls, neutral_calls, result


def test_append_reuses_every_year_and_matches_full_calibration(experiment):
    returns, output, calls, neutral_calls, full = experiment
    extra = pd.DataFrame([[.02, -.01, 0.]], index=pd.DatetimeIndex(["2021-09-01"], name="date"),
                         columns=returns.columns)
    cached = rolling.calibrate_parameters(pd.concat([returns, extra]), output=output)
    assert calls == [] and neutral_calls == []
    assert cached[0] == full[0]
    pd.testing.assert_frame_equal(cached[1], full[1])


def test_history_revision_recomputes_only_affected_years(experiment):
    returns, output, calls, neutral_calls, full = experiment
    changed = returns.copy()
    changed.loc["2020-06-01", "a"] += .1
    incremental = rolling.calibrate_parameters(changed, output=output)
    assert calls == [2021] and len(neutral_calls) == 1
    recomputed = rolling.calibrate_parameters(changed, force=True, output=output)
    assert incremental[0] == recomputed[0]
    pd.testing.assert_frame_equal(incremental[1], recomputed[1])
    assert incremental[0][0] == full[0][0]
    assert incremental[0][1] != full[0][1]


def test_new_year_reuses_old_years(experiment, monkeypatch):
    returns, output, calls, neutral_calls, _ = experiment
    monkeypatch.setattr(rolling, "LAST_SCHEDULE_YEAR", 2022)
    schedules, candidates, _ = rolling.calibrate_parameters(returns, output=output)
    assert calls == [2022] and len(neutral_calls) == 1
    assert len(schedules) == 3 and len(candidates) == 27


@pytest.mark.parametrize("reason", ["force", "contract", "broken_cache"])
def test_cache_miss_and_force_recompute_all_years(experiment, monkeypatch, reason):
    returns, output, calls, neutral_calls, _ = experiment
    if reason == "contract":
        monkeypatch.setattr(rolling, "_calibration_contract", lambda: {"specification": 2})
    elif reason == "broken_cache":
        (output / "calibration_cache.json").write_text("{broken", encoding="utf-8")
    rolling.calibrate_parameters(returns, force=reason == "force", output=output)
    assert calls == [2020, 2021] and len(neutral_calls) == 1


def test_invalid_cached_candidate_is_not_reused(experiment):
    returns, output, calls, _, _ = experiment
    path = output / "calibration_cache.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    cache = rolling._read_calibration_cache(output, record["contract"])
    inputs, schedule, candidates = cache
    candidates.loc[candidates.schedule_year.eq(2021), "future_information_count"] = 1
    rolling._save_calibration_cache(output, inputs, schedule.to_dict("records"),
                                    candidates, record["contract"])
    rolling.calibrate_parameters(returns, output=output)
    assert calls == [2021]


def test_contract_tracks_solver_settings_but_ignores_evaluation_end(monkeypatch):
    before = rolling._calibration_contract()
    monkeypatch.setitem(DEFAULT_CONFIG, "evaluation_end_date", "2026-10-23")
    assert rolling._calibration_contract() == before
    monkeypatch.setitem(rolling.BASE, "transaction_cost_bps", 4.)
    assert rolling._calibration_contract() != before


def test_snapshot_date_and_new_schedule_year_do_not_invalidate_contract(monkeypatch):
    before = rolling._calibration_contract()
    read_text = Path.read_text

    def next_snapshot(path, *args, **kwargs):
        text = read_text(path, *args, **kwargs)
        if path.name in {"utils.py", "data_loader.py", "run_global_rrp_rolling_calibration.py"}:
            text = text.replace("2026-10-16", "2026-10-23").replace("20261016", "20261023")
            text = text.replace("LAST_SCHEDULE_YEAR = 2026", "LAST_SCHEDULE_YEAR = 2027")
        return text

    monkeypatch.setattr(Path, "read_text", next_snapshot)
    assert rolling._calibration_contract() == before


def test_dependency_version_change_invalidates_contract(monkeypatch):
    before = rolling._calibration_contract()
    installed_version = rolling.version
    monkeypatch.setattr(rolling, "version", lambda name: "changed" if name == "numpy" else installed_version(name))
    assert rolling._calibration_contract() != before
