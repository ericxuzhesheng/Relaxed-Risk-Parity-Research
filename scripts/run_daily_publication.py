"""Refresh a complete market snapshot, then run the existing publication chain.

Snapshot dates remain explicit in the checked-in research configuration. Updating
those date literals preserves the existing, date-neutral calibration contract.
"""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd
import tushare as ts

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.update_etf_data import merge_adjusted_history, validate_prices
from src.data_loader import fetch_tushare_trade_date_snapshots, price_to_returns
from src.incremental_backtest import same_return_history
from src.utils import get_config


def next_weekly_decision(cutoff, calendar):
    """Last open exchange day in the first future weekly decision period."""
    cutoff = pd.Timestamp(cutoff)
    opened = pd.DatetimeIndex(pd.to_datetime(
        calendar.loc[calendar.is_open.astype(int).eq(1), "cal_date"])).sort_values()
    frame = pd.Series(opened, index=opened)
    decisions = frame.groupby(frame.index.to_period("W-FRI")).last()
    # Discard the calendar query's potentially incomplete final week.
    calendar_end = pd.to_datetime(calendar.cal_date).max()
    decisions = decisions[decisions.index.end_time.normalize() <= calendar_end]
    future = decisions[decisions > cutoff]
    if future.empty:
        raise ValueError("Exchange calendar has no complete future weekly decision")
    return future.iloc[0].date().isoformat()


def update_snapshot_dates(root, previous, actual):
    """Update only publication date literals; do not change model settings."""
    paths = (
        "src/utils.py", "src/data_loader.py", "scripts/update_etf_data.py",
        "scripts/run_global_rrp_rolling_calibration.py",
        "scripts/run_primary_diagnostics.py", "scripts/sync_global_rrp_docs.py", "AGENTS.md",
    )
    for name in paths:
        path = root / name
        original = path.read_text(encoding="utf-8")
        revised = original.replace(previous, actual).replace(
            previous.replace("-", ""), actual.replace("-", ""))
        if revised != original:
            path.write_text(revised, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--end-date", default=None, help="Requested closed trading date, YYYY-MM-DD")
    args = parser.parse_args()
    now = pd.Timestamp.now(tz="Asia/Shanghai")
    requested = pd.Timestamp(args.end_date or now.date()).normalize()
    if requested.date() > now.date() or (requested.date() == now.date() and now.hour < 17):
        raise ValueError("Daily refresh starts at 17:00 Asia/Shanghai after market close")
    token = os.environ.get("TUSHARE_TOKEN")
    if not token:
        raise RuntimeError("TUSHARE_TOKEN is not set")
    previous = get_config()["evaluation_end_date"]
    if requested < pd.Timestamp(previous):
        raise ValueError("Daily refresh cannot move the published snapshot backwards")
    if requested.year != pd.Timestamp(previous).year:
        raise ValueError("New calendar year requires extending annual schedule and audit coverage first")
    path = ROOT / "data/processed/etf_prices_updated.csv"
    existing = pd.read_csv(path, index_col=0, parse_dates=True)
    # Recheck five recent observations for upstream revisions as well as new days.
    start = existing.index[-5]
    calendar = ts.pro_api(token, timeout=60).trade_cal(
        exchange="SSE", start_date=start.strftime("%Y%m%d"),
        end_date=(requested + pd.Timedelta(days=21)).strftime("%Y%m%d"))
    opened = pd.to_datetime(calendar.loc[calendar.is_open.astype(int).eq(1), "cal_date"])
    dates = sorted(opened[opened.le(requested)].dt.strftime("%Y%m%d").tolist())
    refreshed = fetch_tushare_trade_date_snapshots(dates)
    expected = pd.DatetimeIndex(pd.to_datetime(dates))
    refreshed = refreshed.reindex(expected)
    complete = refreshed.notna().all(axis=1)
    # Entirely absent trailing days are upstream publication delays, not zero returns.
    present = refreshed.notna().any(axis=1)
    if not present.any():
        raise ValueError("No usable market snapshot returned")
    actual = refreshed.index[present][-1]
    refreshed = refreshed.loc[:actual]
    if not complete.loc[:actual].all() or not np.isfinite(refreshed.to_numpy()).all():
        raise ValueError("Incomplete ETF snapshot; retained published data and results")
    if (refreshed <= 0).any().any():
        raise ValueError("Nonpositive ETF price")
    merged = merge_adjusted_history(existing, refreshed)
    validate_prices(merged)
    changed = not same_return_history(price_to_returns(existing), price_to_returns(merged))
    completed_path = ROOT / "results/tables/daily_publication_completed.json"
    completed = json.loads(completed_path.read_text("utf-8")) if completed_path.exists() else {}
    if (not changed and actual <= pd.Timestamp(previous)
            and completed.get("evaluation_end") == previous and completed.get("status") == "passed"):
        print("No new returns or historical revisions; publication unchanged.")
        return
    decision = next_weekly_decision(actual, calendar)
    completed_path.parent.mkdir(parents=True, exist_ok=True)
    completed_path.write_text(json.dumps({"evaluation_end": actual.date().isoformat(),
                                         "status": "running"}, indent=2), encoding="utf-8")
    merged.to_csv(path)
    update_snapshot_dates(ROOT, previous, actual.date().isoformat())
    print(f"Publishing through {actual.date()}; next weekly decision {decision}", flush=True)
    subprocess.run([
        sys.executable, "scripts/run_primary_publication_pipeline.py", "--skip-data-refresh",
        "--end-date", actual.strftime("%Y%m%d"), "--rebalance-date", decision,
    ], cwd=ROOT, check=True)
    completed_path.write_text(json.dumps({"evaluation_end": actual.date().isoformat(),
                                         "status": "passed"}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
