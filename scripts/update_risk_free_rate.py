"""Refresh the point-in-time one-year ChinaBond government yield series."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.risk_free import (  # noqa: E402
    MONTHLY_RISK_FREE_PATH,
    RAW_RISK_FREE_PATH,
    build_monthly_rates,
    collect_risk_free_history,
    merge_provider_yields,
)


TUSHARE_SOURCE_URL = "https://tushare.pro/document/2?doc_id=201"
CHINABOND_HISTORY_URL = "https://yield.chinabond.com.cn/cbweb-czb-web/czb/historyQuery"
CHINABOND_REFERER = "https://yield.chinabond.com.cn/cbweb-czb-web/czb/showHistory?locale=cn_ZH&nameType=1"


def incremental_refresh_start(requested_start: str, raw_path: Path = RAW_RISK_FREE_PATH) -> str:
    """Start at the first day of the latest cached month for overlap auditing."""
    requested = pd.Timestamp(requested_start)
    if not raw_path.exists() or raw_path.stat().st_size == 0:
        return requested.strftime("%Y-%m-%d")
    cached_dates = pd.read_csv(raw_path, usecols=["trade_date"])["trade_date"]
    latest = pd.to_datetime(cached_dates, errors="coerce").max()
    if pd.isna(latest):
        return requested.strftime("%Y-%m-%d")
    overlap_start = latest.to_period("M").start_time
    return max(requested, overlap_start).strftime("%Y-%m-%d")


def merge_incremental_history(cached: pd.DataFrame, fetched: pd.DataFrame) -> pd.DataFrame:
    """Merge a refresh into the audit cache, rejecting changed same-day values."""
    return merge_provider_yields(fetched, cached)


def _date_chunks(start_date: str, end_date: str) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    chunks: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + pd.Timedelta(days=364), end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + pd.Timedelta(days=1)
    return chunks


def _audit_columns(frame: pd.DataFrame, provider: str, source_url: str) -> pd.DataFrame:
    data = frame.copy()
    data["provider"] = provider
    data["ts_code"] = "1001.CB"
    data["curve_name"] = "ChinaBond Government Bond Yield Curve"
    data["curve_type"] = "0"
    data["curve_term"] = 1.0
    data["source_url"] = source_url
    data["retrieved_at_utc"] = datetime.now(timezone.utc).isoformat()
    return data


def fetch_tushare_yields(start_date: str, end_date: str) -> pd.DataFrame:
    import tushare as ts

    token = os.environ.get("TUSHARE_TOKEN", "").strip() or str(ts.get_token() or "").strip()
    if not token:
        raise EnvironmentError("TUSHARE_TOKEN is unavailable in the environment and local Tushare store")
    pro = ts.pro_api(token)
    frames: list[pd.DataFrame] = []
    for start, end in _date_chunks(start_date, end_date):
        frame = pro.yc_cb(
            ts_code="1001.CB",
            curve_type="0",
            curve_term=1.0,
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            fields="trade_date,ts_code,curve_name,curve_type,curve_term,yield",
        )
        if frame is not None and not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=["trade_date", "yield_pct", "provider"])
    data = pd.concat(frames, ignore_index=True)
    data = data.rename(columns={"yield": "yield_pct"})
    data["trade_date"] = pd.to_datetime(data["trade_date"], format="%Y%m%d", errors="coerce")
    data = _audit_columns(data, "tushare_yc_cb", TUSHARE_SOURCE_URL)
    return data.sort_values("trade_date").drop_duplicates("trade_date", keep="last").reset_index(drop=True)


def fetch_chinabond_yields(start_date: str, end_date: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    session = requests.Session()
    headers = {"Referer": CHINABOND_REFERER, "User-Agent": "Mozilla/5.0"}
    for start, end in _date_chunks(start_date, end_date):
        params = {
            "startDate": start.strftime("%Y-%m-%d"),
            "endDate": end.strftime("%Y-%m-%d"),
            "gjqx": "1",
            "locale": "cn_ZH",
            "qxmc": "1",
        }
        response = session.post(CHINABOND_HISTORY_URL, params=params, headers=headers, timeout=60)
        response.raise_for_status()
        payload = response.json()
        if str(payload.get("flag")) not in {"0", "None"} and not payload.get("heList"):
            continue
        for item in payload.get("heList", []):
            if item.get("oneYear") not in {None, ""}:
                rows.append({"trade_date": item.get("workTime"), "yield_pct": item.get("oneYear")})
    if not rows:
        return pd.DataFrame(columns=["trade_date", "yield_pct", "provider"])
    data = pd.DataFrame(rows)
    data["trade_date"] = pd.to_datetime(data["trade_date"], errors="coerce")
    data["yield_pct"] = pd.to_numeric(data["yield_pct"], errors="coerce")
    data = _audit_columns(data, "chinabond_official", CHINABOND_HISTORY_URL)
    return data.sort_values("trade_date").drop_duplicates("trade_date", keep="last").reset_index(drop=True)


def write_outputs(daily: pd.DataFrame) -> None:
    raw_columns = [
        "trade_date",
        "yield_pct",
        "provider",
        "ts_code",
        "curve_name",
        "curve_type",
        "curve_term",
        "source_url",
        "retrieved_at_utc",
    ]
    RAW_RISK_FREE_PATH.parent.mkdir(parents=True, exist_ok=True)
    MONTHLY_RISK_FREE_PATH.parent.mkdir(parents=True, exist_ok=True)
    daily.reindex(columns=raw_columns).to_csv(RAW_RISK_FREE_PATH, index=False)
    monthly = build_monthly_rates(daily)
    monthly.to_csv(MONTHLY_RISK_FREE_PATH, index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", default="20000101")
    parser.add_argument("--end-date", default="20260731")
    parser.add_argument("--required-start-date", default="20171201")
    parser.add_argument("--provider", choices=["auto", "tushare", "chinabond"], default="auto")
    args = parser.parse_args()
    start_date = pd.Timestamp(args.start_date).strftime("%Y-%m-%d")
    end_date = pd.Timestamp(args.end_date).strftime("%Y-%m-%d")
    required_start = pd.Timestamp(args.required_start_date).strftime("%Y-%m-%d")
    refresh_start = incremental_refresh_start(start_date)
    cached = (
        pd.read_csv(RAW_RISK_FREE_PATH)
        if RAW_RISK_FREE_PATH.exists() and RAW_RISK_FREE_PATH.stat().st_size > 0
        else pd.DataFrame(columns=["trade_date", "yield_pct", "provider"])
    )

    if args.provider == "tushare":
        refreshed = collect_risk_free_history(
            refresh_start,
            end_date,
            primary_fetcher=fetch_tushare_yields,
            fallback_fetcher=lambda _start, _end: pd.DataFrame(
                columns=["trade_date", "yield_pct", "provider"]
            ),
            required_start_date=refresh_start,
        )
    elif args.provider == "chinabond":
        refreshed = collect_risk_free_history(
            refresh_start,
            end_date,
            primary_fetcher=fetch_chinabond_yields,
            fallback_fetcher=lambda _start, _end: pd.DataFrame(
                columns=["trade_date", "yield_pct", "provider"]
            ),
            required_start_date=refresh_start,
        )
    else:
        refreshed = collect_risk_free_history(
            refresh_start,
            end_date,
            primary_fetcher=fetch_tushare_yields,
            fallback_fetcher=fetch_chinabond_yields,
            required_start_date=refresh_start,
        )
    merged = merge_incremental_history(cached, refreshed)
    daily = collect_risk_free_history(
        start_date,
        end_date,
        primary_fetcher=lambda _start, _end: merged,
        fallback_fetcher=lambda _start, _end: pd.DataFrame(
            columns=["trade_date", "yield_pct", "provider"]
        ),
        required_start_date=required_start,
    )
    write_outputs(daily)
    monthly = build_monthly_rates(daily)
    print(f"Wrote {RAW_RISK_FREE_PATH}")
    print(f"Wrote {MONTHLY_RISK_FREE_PATH}")
    print(
        f"Risk-free observations: {daily['trade_date'].min().date()} to {daily['trade_date'].max().date()}; "
        f"effective months {monthly['effective_month'].min()} to {monthly['effective_month'].max()}"
    )


if __name__ == "__main__":
    main()
