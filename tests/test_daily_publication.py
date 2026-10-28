from pathlib import Path

import pandas as pd
import pytest

from scripts.run_daily_publication import next_weekly_decision, update_snapshot_dates
from scripts import run_global_rrp_rolling_calibration as rolling
from scripts import run_daily_publication as daily


@pytest.mark.parametrize("cutoff,holiday,expected", [
    ("2026-10-28", None, "2026-10-30"),
    ("2026-10-30", None, "2026-11-06"),
    ("2026-10-28", "2026-10-30", "2026-10-29"),
    ("2026-10-29", "2026-10-30", "2026-11-06"),
])
def test_next_decision_uses_last_exchange_day(cutoff, holiday, expected):
    dates = pd.date_range("2026-10-26", "2026-11-16")
    calendar = pd.DataFrame({"cal_date": dates.strftime("%Y%m%d"),
                             "is_open": (dates.dayofweek < 5).astype(int)})
    if holiday:
        calendar.loc[calendar.cal_date.eq(holiday.replace("-", "")), "is_open"] = 0
    assert next_weekly_decision(cutoff, calendar) == expected


def test_date_update_preserves_calibration_contract(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    files = ["src/utils.py", "src/data_loader.py", "scripts/update_etf_data.py",
             "scripts/run_global_rrp_rolling_calibration.py", "scripts/run_primary_diagnostics.py",
             "scripts/sync_global_rrp_docs.py", "AGENTS.md"]
    for name in files:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((root / name).read_text(encoding="utf-8"), encoding="utf-8")
    before = rolling._calibration_contract()
    previous = rolling.get_config()["evaluation_end_date"]
    update_snapshot_dates(tmp_path, previous, "2026-11-06")
    read_text = Path.read_text
    def updated(path, *args, **kwargs):
        try:
            relative = str(path.relative_to(root)).replace("\\", "/")
        except ValueError:
            relative = ""
        return read_text(tmp_path / relative if relative in files else path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", updated)
    assert rolling._calibration_contract() == before
    assert '"public_evaluation_end": "2026-11-06"' in updated(root / files[3], encoding="utf-8")
    assert '"evaluation_end_date": "2026-11-06"' in updated(root / files[0], encoding="utf-8")


@pytest.mark.parametrize("incomplete", [False, True])
def test_no_change_or_incomplete_data_does_not_publish(tmp_path, monkeypatch, incomplete):
    dates = pd.bdate_range("2026-10-19", "2026-10-23", name="trade_date")
    prices = pd.DataFrame({"a": range(100, 105), "b": range(200, 205)}, index=dates)
    path = tmp_path / "data/processed/etf_prices_updated.csv"
    path.parent.mkdir(parents=True)
    prices.to_csv(path)
    original = path.read_bytes()
    completion = tmp_path / "results/tables/daily_publication_completed.json"
    completion.parent.mkdir(parents=True)
    completion.write_text('{"evaluation_end": "2026-10-23", "status": "passed"}', encoding="utf-8")
    refreshed = prices.copy()
    if incomplete:
        refreshed.loc[pd.Timestamp("2026-10-26")] = [105, float("nan")]
    calendar_dates = pd.date_range("2026-10-19", "2026-11-16")
    calendar = pd.DataFrame({"cal_date": calendar_dates.strftime("%Y%m%d"),
                             "is_open": (calendar_dates.dayofweek < 5).astype(int)})
    class Provider:
        def trade_cal(self, **kwargs):
            return calendar
    monkeypatch.setattr(daily, "ROOT", tmp_path)
    monkeypatch.setenv("TUSHARE_TOKEN", "test-only")
    monkeypatch.setattr(daily.sys, "argv", ["daily", "--end-date", "2026-10-27"])
    monkeypatch.setattr(daily, "get_config", lambda: {"evaluation_end_date": "2026-10-23"})
    monkeypatch.setattr(daily.ts, "pro_api", lambda *a, **kw: Provider())
    monkeypatch.setattr(daily, "fetch_tushare_trade_date_snapshots", lambda dates: refreshed)
    monkeypatch.setattr(daily, "validate_prices", lambda prices: None)
    def unexpected(*args, **kwargs):
        pytest.fail("Unchanged/incomplete market data must not update files or publish")
    monkeypatch.setattr(daily, "update_snapshot_dates", unexpected)
    monkeypatch.setattr(daily.subprocess, "run", unexpected)
    if incomplete:
        with pytest.raises(ValueError, match="Incomplete"):
            daily.main()
    else:
        daily.main()
    assert path.read_bytes() == original
