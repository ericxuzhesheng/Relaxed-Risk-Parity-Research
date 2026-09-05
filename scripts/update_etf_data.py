from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.asset_universe import asset_mapping_frame, etf_names
from src.data_loader import fetch_from_tushare, fetch_tushare_trade_date_snapshots
from src.utils import resolve_path


def _ensure_tushare_token(provider: str) -> None:
    """Fail fast with a clear message when the Tushare token is missing.

    Tushare is the default upstream for this pipeline. Without an explicit
    token the SDK returns opaque server-side errors that look like
    network failures, so the previous behavior was to retry through the
    AkShare/yfinance fallback chain — which both masked the misconfiguration
    and silently degraded data quality. This check surfaces the problem
    immediately so the operator can set the variable before any work happens.
    """
    if provider in {"akshare", "tencent", "yfinance"}:
        return
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise EnvironmentError(
            "TUSHARE_TOKEN is not set. Configure it before running update_etf_data.py.\n"
            "  PowerShell:  $env:TUSHARE_TOKEN = '<your token>'\n"
            "  bash:        export TUSHARE_TOKEN=<your token>\n"
            "Or run with --provider akshare / --provider tencent / --provider yfinance "
            "to skip Tushare."
        )


LEGACY_NAMES = {"0-5中高信用票", "中证转债", "豆粕连续", "银华日利ETF"}


def merge_adjusted_history(existing: pd.DataFrame, refreshed: pd.DataFrame) -> pd.DataFrame:
    """Merge an overlapping adjusted-price refresh without a level break."""
    old = existing.apply(pd.to_numeric, errors="coerce").sort_index().copy()
    new = refreshed.apply(pd.to_numeric, errors="coerce").sort_index().copy()
    old.index = pd.to_datetime(old.index)
    new.index = pd.to_datetime(new.index)
    if old.empty:
        return new
    if new.empty:
        return old
    if list(old.columns) != list(new.columns):
        raise ValueError("Existing and refreshed ETF columns do not match.")

    scaled = old.copy()
    overlap = old.index.intersection(new.index)
    if overlap.empty:
        raise ValueError("Incremental ETF refresh requires at least one overlapping date.")
    for column in old.columns:
        common = pd.concat(
            [old.loc[overlap, column].rename("old"), new.loc[overlap, column].rename("new")],
            axis=1,
        ).dropna()
        if common.empty:
            raise ValueError(f"No overlapping adjusted price for {column}.")
        anchor = common.iloc[-1]
        if float(anchor["old"]) == 0.0:
            raise ValueError(f"Zero cached anchor price for {column}.")
        scaled[column] *= float(anchor["new"] / anchor["old"])

    return pd.concat([scaled, new]).groupby(level=0).last().sort_index()


def refresh_tushare_prices(start_date: str, end_date: str) -> pd.DataFrame:
    """Refresh only the uncached tail while preserving adjusted-price history."""
    cache_path = resolve_path("data/processed/etf_prices_updated.csv")
    if not cache_path.exists() or cache_path.stat().st_size == 0:
        return fetch_from_tushare(start_date=start_date, end_date=end_date)

    existing = pd.read_csv(cache_path, index_col=0, parse_dates=True).sort_index()
    requested_end = pd.Timestamp(end_date)
    cached_end = pd.Timestamp(existing.index.max())
    if requested_end <= cached_end:
        return existing.loc[existing.index <= requested_end]

    snapshot_dates = [
        date.strftime("%Y%m%d")
        for date in pd.bdate_range(cached_end, requested_end)
    ]
    refreshed = fetch_tushare_trade_date_snapshots(snapshot_dates)
    merged = merge_adjusted_history(existing, refreshed)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(cache_path)
    return merged


def refresh_akshare_prices(start_date: str, end_date: str) -> pd.DataFrame:
    """Refresh the cached tail through AkShare after an explicit provider choice."""
    cache_path = resolve_path("data/processed/etf_prices_updated.csv")
    if not cache_path.exists() or cache_path.stat().st_size == 0:
        return fetch_from_akshare(start_date, end_date)

    existing = pd.read_csv(cache_path, index_col=0, parse_dates=True).sort_index()
    requested_end = pd.Timestamp(end_date)
    cached_start = pd.Timestamp(existing.index.min())
    cached_end = pd.Timestamp(existing.index.max())
    if requested_end <= cached_end:
        return existing.loc[existing.index <= requested_end]

    overlap_start = max(cached_start, cached_end - pd.Timedelta(days=10))
    refreshed = fetch_from_akshare(
        overlap_start.strftime("%Y%m%d"),
        requested_end.strftime("%Y%m%d"),
        write_cache=False,
    )
    merged = merge_adjusted_history(existing, refreshed)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(cache_path)
    return merged


def refresh_tencent_prices(start_date: str, end_date: str) -> pd.DataFrame:
    """Refresh the cached tail through Tencent's public adjusted-price feed."""
    cache_path = resolve_path("data/processed/etf_prices_updated.csv")
    if not cache_path.exists() or cache_path.stat().st_size == 0:
        return fetch_from_tencent(start_date, end_date)

    existing = pd.read_csv(cache_path, index_col=0, parse_dates=True).sort_index()
    requested_end = pd.Timestamp(end_date)
    cached_start = pd.Timestamp(existing.index.min())
    cached_end = pd.Timestamp(existing.index.max())
    if requested_end <= cached_end:
        return existing.loc[existing.index <= requested_end]

    overlap_start = max(cached_start, cached_end - pd.Timedelta(days=10))
    refreshed = fetch_from_tencent(
        overlap_start.strftime("%Y%m%d"),
        requested_end.strftime("%Y%m%d"),
        write_cache=False,
    )
    merged = merge_adjusted_history(existing, refreshed)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(cache_path)
    return merged


def validate_prices(prices: pd.DataFrame) -> None:
    expected = etf_names()
    actual = [str(col) for col in prices.columns]
    if actual != expected:
        raise ValueError(f"ETF price columns do not match asset mapping. Expected {expected}, got {actual}.")
    if LEGACY_NAMES.intersection(actual):
        raise ValueError(f"Legacy non-ETF names remain in updated data: {sorted(LEGACY_NAMES.intersection(actual))}")
    empty = prices.columns[prices.isna().all()].tolist()
    if empty:
        raise ValueError(f"Price columns are entirely missing: {empty}")
    for col in prices.columns:
        first = prices[col].first_valid_index()
        if first is None:
            raise ValueError(f"{col} has no valid prices.")
        if prices.loc[:first, col].iloc[:-1].notna().any():
            raise ValueError(f"{col} has unexpected values before first valid listing date.")


def fetch_from_akshare(
    start_date: str,
    end_date: str | None,
    *,
    write_cache: bool = True,
) -> pd.DataFrame:
    import akshare as ak

    frames = []
    mapping = asset_mapping_frame()
    for _, row in mapping.iterrows():
        ticker = str(row["ticker"])
        symbol = ticker.split(".")[0]
        print(f"Syncing {row['new_name']} ({ticker}) via AkShare...")
        last_error = None
        for attempt in range(4):
            try:
                df = ak.fund_etf_hist_em(
                    symbol=symbol,
                    period="daily",
                    start_date=start_date,
                    end_date=end_date or pd.Timestamp.today().strftime("%Y%m%d"),
                    adjust="qfq",
                )
                break
            except Exception as exc:
                last_error = exc
                time.sleep(1.5 * (attempt + 1))
        else:
            raise RuntimeError(f"AkShare request failed for {row['new_name']} ({ticker}).") from last_error
        if df is None or df.empty:
            raise ValueError(f"No AkShare ETF data returned for {row['new_name']} ({ticker}).")
        df = df.copy()
        df["日期"] = pd.to_datetime(df["日期"])
        price = pd.to_numeric(df["收盘"], errors="coerce")
        price.index = df["日期"]
        frames.append(price.sort_index().rename(row["new_name"]))
    prices = pd.concat(frames, axis=1).sort_index()
    if write_cache:
        out = resolve_path("data/processed/etf_prices_updated.csv")
        out.parent.mkdir(parents=True, exist_ok=True)
        prices.to_csv(out)
    return prices


def fetch_from_tencent(
    start_date: str,
    end_date: str | None,
    *,
    write_cache: bool = True,
) -> pd.DataFrame:
    """Fetch adjusted ETF closes from Tencent's public daily-kline endpoint."""
    import requests

    start = pd.Timestamp(start_date).strftime("%Y-%m-%d")
    end = pd.Timestamp(end_date or pd.Timestamp.today()).strftime("%Y-%m-%d")
    frames = []
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    for _, row in asset_mapping_frame().iterrows():
        ticker = str(row["ticker"])
        market = "sh" if ticker.endswith(".SH") else "sz"
        symbol = f"{market}{ticker.split('.')[0]}"
        print(f"Syncing {row['new_name']} ({ticker}) via Tencent...")
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                response = session.get(
                    "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
                    params={"param": f"{symbol},day,{start},{end},30,qfq"},
                    timeout=30,
                )
                response.raise_for_status()
                payload = response.json()
                symbol_data = payload.get("data", {}).get(symbol, {})
                rows = symbol_data.get("qfqday") or symbol_data.get("day") or []
                if not rows:
                    raise ValueError("response contains no adjusted daily observations")
                dates = pd.to_datetime([item[0] for item in rows])
                closes = pd.to_numeric([item[2] for item in rows], errors="coerce")
                frames.append(pd.Series(closes, index=dates, name=row["new_name"]))
                break
            except Exception as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(1.5 * (attempt + 1))
        else:
            raise RuntimeError(
                f"Tencent request failed for {row['new_name']} ({ticker})."
            ) from last_error

    prices = pd.concat(frames, axis=1).sort_index()
    if write_cache:
        out = resolve_path("data/processed/etf_prices_updated.csv")
        out.parent.mkdir(parents=True, exist_ok=True)
        prices.to_csv(out)
    return prices


def fetch_from_yfinance(start_date: str, end_date: str | None) -> pd.DataFrame:
    import yfinance as yf

    start = pd.to_datetime(start_date).strftime("%Y-%m-%d")
    end = None if end_date is None else (pd.to_datetime(end_date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    frames = []
    mapping = asset_mapping_frame()
    for _, row in mapping.iterrows():
        ticker = str(row["ticker"])
        yf_ticker = ticker.replace(".SH", ".SS")
        print(f"Syncing {row['new_name']} ({ticker}) via yfinance...")
        df = yf.download(yf_ticker, start=start, end=end, progress=False, auto_adjust=True)
        if df is None or df.empty:
            raise ValueError(f"No yfinance ETF data returned for {row['new_name']} ({ticker}).")
        close = df["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        close.index = pd.to_datetime(close.index)
        frames.append(pd.to_numeric(close, errors="coerce").sort_index().rename(row["new_name"]))
    prices = pd.concat(frames, axis=1).sort_index()
    out = resolve_path("data/processed/etf_prices_updated.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    prices.to_csv(out)
    return prices


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh tradable ETF adjusted-close prices from Tushare.")
    parser.add_argument("--start-date", default="20000101", help="Inclusive Tushare start date, YYYYMMDD.")
    parser.add_argument("--end-date", default="20260831", help="Inclusive Tushare end date, YYYYMMDD.")
    parser.add_argument(
        "--provider",
        choices=["auto", "tushare", "akshare", "tencent", "yfinance"],
        default="auto",
        help="Use Tushare, AkShare, Tencent, yfinance, or automatic fallback.",
    )
    args = parser.parse_args()

    _ensure_tushare_token(args.provider)

    mapping = asset_mapping_frame()
    mapping_path = resolve_path("data/processed/etf_asset_mapping.csv")
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    mapping.to_csv(mapping_path, index=False, encoding="utf-8-sig")

    if args.provider == "akshare":
        prices = refresh_akshare_prices(args.start_date, args.end_date)
    elif args.provider == "tencent":
        prices = refresh_tencent_prices(args.start_date, args.end_date)
    elif args.provider == "yfinance":
        prices = fetch_from_yfinance(args.start_date, args.end_date)
    else:
        try:
            prices = refresh_tushare_prices(args.start_date, args.end_date)
        except RuntimeError:
            if args.provider == "tushare":
                raise
            try:
                prices = refresh_akshare_prices(args.start_date, args.end_date)
            except Exception:
                try:
                    prices = refresh_tencent_prices(args.start_date, args.end_date)
                except Exception:
                    prices = fetch_from_yfinance(args.start_date, args.end_date)
    validate_prices(prices)
    print(f"Wrote {resolve_path('data/processed/etf_prices_updated.csv')}")
    print(f"Wrote {mapping_path}")
    print(f"Date range: {prices.index.min().date()} to {prices.index.max().date()}")


if __name__ == "__main__":
    main()
