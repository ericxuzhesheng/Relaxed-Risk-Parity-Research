from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import tushare as ts

from src.asset_universe import ETF_UNIVERSE, etf_names, old_to_new_name
from src.utils import get_config, resolve_path


logger = logging.getLogger(__name__)


ASSET_MAP = {item.new_name: (item.ticker, "E") for item in ETF_UNIVERSE}
MANIFEST_PATH = resolve_path("data/MANIFEST.json")


def _file_sha256(path: Path, chunk: int = 65536) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def write_data_manifest(
    prices: pd.DataFrame,
    source_path: Path | str,
    source_label: str,
    manifest_path: Path | str | None = None,
) -> dict:
    """Write a JSON manifest describing the loaded price cache.

    Records: load timestamp (UTC ISO 8601), source file mtime + sha256, row
    count, first/last valid date, the trading-day count per asset, and the
    per-asset NaN ratio. The manifest is written to ``data/MANIFEST.json``
    by default so reproducibility checks can confirm exactly which snapshot
    fed a given backtest run; pass ``manifest_path`` to redirect the output
    (tests must do this to avoid clobbering the repository manifest).
    """
    source = Path(source_path)
    if not source.exists():
        logger.warning("write_data_manifest: source file %s does not exist", source)
        return {}

    mtime = datetime.fromtimestamp(source.stat().st_mtime, tz=timezone.utc).isoformat()
    sha256 = _file_sha256(source)
    notnull = prices.notna()
    n_obs_per_asset = {col: int(notnull[col].sum()) for col in prices.columns}
    nan_ratio_per_asset = {
        col: float(1.0 - n_obs_per_asset[col] / max(len(prices), 1))
        for col in prices.columns
    }
    first_valid = {
        col: (None if prices[col].first_valid_index() is None else str(prices[col].first_valid_index().date()))
        for col in prices.columns
    }
    last_valid = {
        col: (None if prices[col].last_valid_index() is None else str(prices[col].last_valid_index().date()))
        for col in prices.columns
    }
    first_overall = prices.dropna(how="all").index.min()
    last_overall = prices.dropna(how="all").index.max()

    manifest = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "source_label": source_label,
        "source_path": str(source),
        "source_mtime_utc": mtime,
        "source_sha256": sha256,
        "row_count": int(len(prices)),
        "asset_count": int(prices.shape[1]),
        "first_date": (None if pd.isna(first_overall) else str(first_overall.date())),
        "last_date": (None if pd.isna(last_overall) else str(last_overall.date())),
        "asset_observations": n_obs_per_asset,
        "asset_nan_ratio": nan_ratio_per_asset,
        "asset_first_valid": first_valid,
        "asset_last_valid": last_valid,
    }
    out_path = Path(manifest_path) if manifest_path is not None else MANIFEST_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(
        "wrote data manifest -> %s (rows=%d assets=%d range=%s..%s)",
        out_path,
        manifest["row_count"],
        manifest["asset_count"],
        manifest["first_date"],
        manifest["last_date"],
    )
    return manifest


def read_data_manifest(manifest_path: Path | str | None = None) -> dict | None:
    """Return the most recent on-disk manifest, or None if absent."""
    path = Path(manifest_path) if manifest_path is not None else MANIFEST_PATH
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("read_data_manifest: could not parse %s (%s)", path, exc)
        return None


def adjusted_fund_close(close: pd.Series, adj_factor: pd.Series) -> pd.Series:
    """Return a continuous adjusted close without discarding early price history.

    Tushare's ``fund_adj`` history can begin years after ``fund_daily``.  The
    earliest available factor is therefore carried backward to the fund's
    listing history, while ordinary gaps are forward-filled.  Normalising by
    the last factor preserves the latest unadjusted close level.
    """
    close_values = pd.to_numeric(close, errors="coerce").sort_index()
    factor_values = pd.to_numeric(adj_factor, errors="coerce").sort_index()
    aligned_factor = factor_values.reindex(close_values.index).ffill().bfill()
    valid_factor = aligned_factor.dropna()
    if valid_factor.empty:
        return close_values
    base = float(valid_factor.iloc[-1])
    if not np.isfinite(base) or base == 0:
        raise ValueError("The latest ETF adjustment factor must be finite and non-zero.")
    return close_values * aligned_factor / base


def fetch_from_tushare(
    start_date: str = "20000101",
    end_date: str | None = "20260831",
    *,
    write_cache: bool = True,
) -> pd.DataFrame:
    config = get_config()
    token = config.get("tushare_token", "")
    if not token:
        raise RuntimeError("TUSHARE_TOKEN is not set. Set it in the environment before refreshing Tushare data.")
    pro = ts.pro_api(token, timeout=120)
    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")

    frames = []
    for item in ETF_UNIVERSE:
        print(f"Syncing {item.new_name} ({item.ticker})...")
        daily = None
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                daily = pro.fund_daily(
                    ts_code=item.ticker,
                    start_date=start_date,
                    end_date=end_date,
                )
                break
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(2.0 * (attempt + 1))
        if daily is None and last_error is not None:
            raise RuntimeError(
                f"fund_daily request failed for {item.new_name} ({item.ticker})"
            ) from last_error
        if daily is None or daily.empty:
            raise ValueError(f"No fund_daily data returned for {item.new_name} ({item.ticker}).")
        daily = daily.copy()
        daily["trade_date"] = pd.to_datetime(daily["trade_date"])
        daily = daily.set_index("trade_date").sort_index()

        adj = None
        for attempt in range(3):
            try:
                adj = pro.fund_adj(
                    ts_code=item.ticker,
                    start_date=start_date,
                    end_date=end_date,
                )
                break
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(2.0 * (attempt + 1))
        if adj is None and last_error is not None:
            raise RuntimeError(
                f"fund_adj request failed for {item.new_name} ({item.ticker})"
            ) from last_error
        if adj is not None and not adj.empty and {"trade_date", "adj_factor"}.issubset(adj.columns):
            adj = adj.copy()
            adj["trade_date"] = pd.to_datetime(adj["trade_date"])
            adj = adj.set_index("trade_date").sort_index()
            price = adjusted_fund_close(daily["close"], adj["adj_factor"])
        else:
            price = daily["close"].astype(float)
        frames.append(price.rename(item.new_name))
        time.sleep(0.25)

    prices = pd.concat(frames, axis=1).sort_index()
    if write_cache:
        cache_path = resolve_path("data/processed/etf_prices_updated.csv")
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        prices.to_csv(cache_path)
    return prices


def fetch_tushare_trade_date_snapshots(trade_dates: list[str]) -> pd.DataFrame:
    """Fetch all active ETFs in a few market-wide, date-specific requests.

    This path is intended for incremental tail refreshes.  Tushare can return
    the full ETF market for one trade date, avoiding one request per asset.
    """
    config = get_config()
    token = config.get("tushare_token", "")
    if not token:
        raise RuntimeError(
            "TUSHARE_TOKEN is not set. Set it in the environment before refreshing Tushare data."
        )
    pro = ts.pro_api(token, timeout=60)
    daily_frames: list[pd.DataFrame] = []
    adj_frames: list[pd.DataFrame] = []
    for trade_date in sorted(set(trade_dates)):
        print(f"Syncing Tushare ETF market snapshot for {trade_date}...")
        for endpoint, collector in (
            (pro.fund_daily, daily_frames),
            (pro.fund_adj, adj_frames),
        ):
            result = None
            last_error: Exception | None = None
            for attempt in range(3):
                try:
                    result = endpoint(trade_date=trade_date)
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt < 2:
                        time.sleep(2.0 * (attempt + 1))
            if result is None:
                raise RuntimeError(
                    f"Tushare market snapshot request failed for {trade_date}"
                ) from last_error
            if not result.empty:
                collector.append(result)

    if not daily_frames:
        raise ValueError("Tushare returned no ETF market snapshots for the requested dates.")
    daily = pd.concat(daily_frames, ignore_index=True)
    adj = pd.concat(adj_frames, ignore_index=True) if adj_frames else pd.DataFrame()
    expected_tickers = {item.ticker for item in ETF_UNIVERSE}
    observed_tickers = set(daily["ts_code"].astype(str))
    missing_tickers = sorted(expected_tickers - observed_tickers)
    if missing_tickers:
        raise ValueError(
            "Tushare snapshots are missing active ETFs: " + ", ".join(missing_tickers)
        )

    frames = []
    for item in ETF_UNIVERSE:
        item_daily = daily.loc[daily["ts_code"] == item.ticker].copy()
        item_daily["trade_date"] = pd.to_datetime(item_daily["trade_date"])
        item_daily = item_daily.drop_duplicates("trade_date", keep="last").set_index(
            "trade_date"
        ).sort_index()
        if not adj.empty:
            item_adj = adj.loc[adj["ts_code"] == item.ticker].copy()
            item_adj["trade_date"] = pd.to_datetime(item_adj["trade_date"])
            item_adj = item_adj.drop_duplicates("trade_date", keep="last").set_index(
                "trade_date"
            ).sort_index()
        else:
            item_adj = pd.DataFrame()
        if not item_adj.empty and "adj_factor" in item_adj:
            price = adjusted_fund_close(item_daily["close"], item_adj["adj_factor"])
        else:
            price = pd.to_numeric(item_daily["close"], errors="coerce")
        frames.append(price.rename(item.new_name))

    return pd.concat(frames, axis=1).sort_index()


def default_tushare_cache() -> Path:
    updated = resolve_path("data/processed/etf_prices_updated.csv")
    historical = resolve_path("data/processed/tushare_data.csv")
    return updated if updated.exists() else historical


def price_to_returns(prices: pd.DataFrame) -> pd.DataFrame:
    prices = prices.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    prices = prices.sort_index().ffill()
    returns = prices.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
    first_valid = prices.apply(lambda col: col.first_valid_index())
    for col, first_date in first_valid.items():
        if first_date is not None:
            returns.loc[returns.index <= first_date, col] = np.nan

    def remove_outliers(series: pd.Series) -> pd.Series:
        clean = series.dropna()
        if clean.empty:
            return series
        m, s = clean.mean(), clean.std()
        if not np.isfinite(s) or s <= 0:
            return series
        return series.mask((series - m).abs() > 3 * s)

    return returns.apply(remove_outliers).dropna(how="all")


def load_price_data(source: str = "tushare", force_update: bool = False) -> pd.DataFrame:
    cache_path: Path | None = None
    source_label = source
    if source == "tushare":
        cache_path = default_tushare_cache()
        if force_update or not cache_path.exists():
            df = fetch_from_tushare()
            cache_path = resolve_path("data/processed/etf_prices_updated.csv")
        else:
            df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
            if cache_path.name == "tushare_data.csv":
                df = df.rename(columns=old_to_new_name())
                available = [col for col in etf_names() if col in df.columns]
                df = df[available]
        source_label = f"tushare:{cache_path.name}"
    else:
        file_path = str(resolve_path("资产数据.xlsx"))
        df_raw = pd.read_excel(file_path, header=None)
        names = df_raw.iloc[3, 1:].tolist()
        df = df_raw.iloc[5:].copy()
        df.columns = ["date"] + [str(n).strip() for n in names]
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        cache_path = resolve_path("资产数据.xlsx")
        source_label = "excel:资产数据.xlsx"
    df = df.apply(pd.to_numeric, errors="coerce").sort_index()
    evaluation_end = pd.Timestamp(get_config()["evaluation_end_date"])
    df = df.loc[df.index <= evaluation_end]
    if cache_path is not None and Path(cache_path).exists():
        try:
            write_data_manifest(df, cache_path, source_label)
        except Exception as exc:
            logger.warning("data manifest write failed: %s", exc)
    return df


def load_data(source: str = "tushare", force_update: bool = False) -> pd.DataFrame:
    return price_to_returns(load_price_data(source=source, force_update=force_update))


def update_data_from_wind(file_path=None):
    print("Wind update placeholder")
    return None
