from pathlib import Path

import pandas as pd
import pytest

from scripts.run_daily_publication import next_weekly_decision, update_snapshot_dates
from scripts import run_global_rrp_rolling_calibration as rolling


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
