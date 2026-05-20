"""Futures continuous contract data for the Bridgewater-style extension experiment.

Constructs a daily continuous return series for each futures product by:
1. Generating the set of quarterly/monthly contract codes for the study period.
2. Fetching daily close prices for each contract via Tushare pro.fut_daily().
3. Rolling to the next contract 15 calendar days before expiry (the roll window).
4. Splicing RETURNS (not prices) at roll dates to avoid gap jumps.

The resulting DataFrame has the same format as ETF returns from data_loader.py
and can be directly merged into the combined asset universe.
"""

from __future__ import annotations

import calendar
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import tushare as ts

from src.data_loader import price_to_returns
from src.utils import get_config, resolve_path


logger = logging.getLogger(__name__)

# ── Contract specifications ────────────────────────────────────────────────────

# Each entry: (exchange, [delivery month numbers], roll_days_before_expiry)
# Quarterly bond futures: March, June, September, December
# Gold (AU/AG): bi-monthly (even months) for AU, all months for AG
# Industrial metals/commodities: main active months
# Accessible exchanges with current Tushare token:
#   CFX (中金所): bond futures T/TF/TS/TL  ✓
#   DCE (大商所): soybean meal M, hog LH    ✓
#   INE (上期能源): crude oil SC             ✓
# Excluded (no data permissions): SHFE (AU/AG/CU/RB), CZCE (ZC)
FUTURES_SPECS: dict[str, tuple[str, list[int], int]] = {
    "国债期货TL": ("CFX", [3, 6, 9, 12], 15),          # 30Y bond futures (2023+)
    "国债期货T":  ("CFX", [3, 6, 9, 12], 15),           # 10Y bond futures
    "国债期货TF": ("CFX", [3, 6, 9, 12], 15),           # 5Y bond futures
    "国债期货TS": ("CFX", [3, 6, 9, 12], 15),           # 2Y bond futures (2018+)
    "豆粕期货":   ("DCE", [1, 3, 5, 7, 8, 9, 11, 12], 15),  # M
    "生猪期货":   ("DCE", [1, 3, 5, 7, 9, 11], 15),     # LH — odd months (2021+)
    "原油期货":   ("INE", list(range(1, 13)), 15),       # SC — all months
}

# Tushare product codes (prefix before YY+MM)
FUTURES_CODES: dict[str, str] = {
    "国债期货TL": "TL",
    "国债期货T":  "T",
    "国债期货TF": "TF",
    "国债期货TS": "TS",
    "豆粕期货":   "M",
    "生猪期货":   "LH",
    "原油期货":   "SC",
}

# Expected first trading dates for products with limited history
PRODUCT_LIST_DATE: dict[str, str] = {
    "国债期货TL": "2023-04-21",   # 30Y bond futures listed 2023-04-21
    "国债期货TS": "2018-08-17",   # 2Y bond futures listed 2018-08-17
    "生猪期货":   "2021-01-08",   # Live hog futures listed 2021-01-08
    "原油期货":   "2018-03-26",   # Crude oil futures listed 2018-03-26
}

FUTURES_CACHE_PATH = resolve_path("data/processed/futures_prices.csv")
FUTURES_UNIVERSE = list(FUTURES_SPECS.keys())


def _contract_expiry_date(year: int, month: int, exchange: str) -> datetime:
    """Approximate expiry date for a futures contract.

    Bond futures (CFX): last Friday of the delivery month.
    SHFE/DCE/INE/CZCE: typically the 15th or last business day of the month;
    we use the 15th as a conservative lower bound.
    """
    if exchange == "CFX":
        # CFX bond futures (T/TF/TS/TL): actual last trading day is the SECOND Friday
        # of the delivery month (not month-end). Using month-end caused the roll window
        # to be triggered only after the contract had already stopped trading.
        first_day = datetime(year, month, 1)
        days_to_friday = (4 - first_day.weekday()) % 7
        first_friday = first_day + timedelta(days=days_to_friday)
        second_friday = first_friday + timedelta(weeks=1)
        return second_friday
    if exchange == "INE":
        # SC crude oil: last trading day is in the month BEFORE delivery (not delivery month).
        # Use the last calendar day of the preceding month as a conservative expiry bound.
        prev_month = month - 1 if month > 1 else 12
        prev_year = year if month > 1 else year - 1
        last_day = calendar.monthrange(prev_year, prev_month)[1]
        return datetime(prev_year, prev_month, last_day)
    # For other commodity futures use the 15th of the month as approximate expiry
    return datetime(year, month, 15)


def _generate_contract_codes(name: str, start_year: int, end_year: int) -> list[tuple[str, datetime]]:
    """Return list of (ts_code, expiry_date) for all contracts in the period."""
    exchange, months, _ = FUTURES_SPECS[name]
    code = FUTURES_CODES[name]
    list_date_str = PRODUCT_LIST_DATE.get(name)
    list_date = pd.Timestamp(list_date_str) if list_date_str else pd.Timestamp("2010-01-01")

    contracts: list[tuple[str, datetime]] = []
    for year in range(start_year, end_year + 1):
        yy = str(year)[2:]
        for month in months:
            expiry = _contract_expiry_date(year, month, exchange)
            if pd.Timestamp(expiry) < list_date:
                continue
            if exchange == "CZCE":
                # CZCE uses 3-digit year + 2-digit month: ZC401.CZCE (2024 Jan)
                ts_code = f"{code}{str(year)[1:]}{month:02d}.{exchange}"
            else:
                ts_code = f"{code}{yy}{month:02d}.{exchange}"
            contracts.append((ts_code, expiry))
    return contracts


def _fetch_contract(pro, ts_code: str, start_date: str, end_date: str) -> pd.Series | None:
    """Fetch daily close price for one contract; return None on failure."""
    try:
        df = pro.fut_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
        time.sleep(0.2)
    except Exception as exc:
        logger.debug("fut_daily(%s): %s", ts_code, exc)
        return None
    if df is None or df.empty:
        return None
    df = df.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.set_index("trade_date").sort_index()
    if "vol" in df.columns:
        df = df[df["vol"].fillna(0) > 0]
    if df.empty:
        return None
    return df["close"].astype(float).rename(ts_code)


def build_continuous_price(
    name: str,
    contracts: list[tuple[str, datetime]],
    all_prices: dict[str, pd.Series],
    roll_days: int = 15,
) -> pd.Series | None:
    """Build a continuous price series by stitching contracts at roll dates.

    Roll occurs when the front contract is within ``roll_days`` calendar days
    of its expiry. Prices are back-adjusted at each roll using the ratio of
    the two contracts' close prices on the roll date (proportional adjustment).
    """
    if not all_prices:
        return None

    # Build date-indexed DataFrame of all available contracts
    available = {code: s for code, s in all_prices.items() if s is not None and len(s) > 0}
    if not available:
        return None

    price_df = pd.concat(list(available.values()), axis=1).sort_index()
    all_dates = price_df.index

    # Sort contracts by expiry
    sorted_contracts = sorted(
        [(c, e) for c, e in contracts if c in available],
        key=lambda x: x[1],
    )
    if not sorted_contracts:
        return None

    continuous_prices: list[float] = []
    continuous_index: list[pd.Timestamp] = []
    cumulative_adj = 1.0  # multiplier applied to older prices
    current_contract_idx = 0

    for date in all_dates:
        # Advance to the front contract that has data and hasn't expired + roll window
        while current_contract_idx < len(sorted_contracts) - 1:
            curr_code, curr_expiry = sorted_contracts[current_contract_idx]
            roll_date = curr_expiry - timedelta(days=roll_days)
            if date.to_pydatetime() >= roll_date:
                # Roll: check if next contract has data on this date
                next_code, _ = sorted_contracts[current_contract_idx + 1]
                curr_price = price_df.loc[date, curr_code] if curr_code in price_df.columns else np.nan
                next_price = price_df.loc[date, next_code] if next_code in price_df.columns else np.nan
                if np.isfinite(next_price) and np.isfinite(curr_price) and curr_price > 0:
                    cumulative_adj *= next_price / curr_price
                    current_contract_idx += 1
                else:
                    break
            else:
                break

        curr_code, _ = sorted_contracts[current_contract_idx]
        if curr_code in price_df.columns:
            raw_price = price_df.loc[date, curr_code]
            if np.isfinite(raw_price):
                continuous_prices.append(float(raw_price) * cumulative_adj)
                continuous_index.append(date)

    if not continuous_prices:
        return None

    series = pd.Series(continuous_prices, index=continuous_index, name=name)
    # Normalize so the series starts at 100
    series = series / series.iloc[0] * 100.0
    return series


def fetch_futures_prices(
    start_date: str = "20180101",
    end_date: str | None = None,
    names: list[str] | None = None,
) -> pd.DataFrame:
    """Fetch and construct continuous contract prices for all futures."""
    config = get_config()
    token = config.get("tushare_token", "")
    if not token:
        raise RuntimeError("TUSHARE_TOKEN is not set.")
    ts.set_token(token)
    pro = ts.pro_api()
    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")

    start_year = int(start_date[:4])
    end_year = int(end_date[:4]) + 1
    target_names = names or FUTURES_UNIVERSE

    frames: list[pd.Series] = []
    for name in target_names:
        print(f"Building continuous contract for {name}...")
        contracts = _generate_contract_codes(name, start_year, end_year)
        all_prices: dict[str, pd.Series] = {}
        roll_days = FUTURES_SPECS[name][2]

        for ts_code, expiry in contracts:
            # Only fetch if the contract was active in our window
            if expiry < datetime.strptime(start_date, "%Y%m%d"):
                continue
            contract_start = (expiry - timedelta(days=365)).strftime("%Y%m%d")
            contract_start = max(contract_start, start_date)
            s = _fetch_contract(pro, ts_code, contract_start, end_date)
            if s is not None and not s.empty:
                all_prices[ts_code] = s
                logger.debug("  Fetched %s: %d rows", ts_code, len(s))

        if not all_prices:
            logger.warning("No data for %s — skipping.", name)
            continue

        continuous = build_continuous_price(name, contracts, all_prices, roll_days=roll_days)
        if continuous is not None and not continuous.empty:
            frames.append(continuous)
            print(f"  {name}: {len(continuous)} trading days, "
                  f"{continuous.index[0].date()} to {continuous.index[-1].date()}")
        else:
            logger.warning("Failed to build continuous series for %s.", name)

    if not frames:
        raise RuntimeError("No futures data fetched. Check Tushare token and permissions.")

    prices = pd.concat(frames, axis=1).sort_index()
    FUTURES_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    prices.to_csv(FUTURES_CACHE_PATH)
    logger.info("Saved futures prices → %s (%d rows, %d assets)", FUTURES_CACHE_PATH, len(prices), prices.shape[1])
    return prices


def load_futures_prices(force_update: bool = False) -> pd.DataFrame:
    """Load continuous futures prices from cache or build from scratch."""
    if not force_update and FUTURES_CACHE_PATH.exists():
        df = pd.read_csv(FUTURES_CACHE_PATH, index_col=0, parse_dates=True)
        logger.info("Loaded futures prices from cache: %s (%d assets)", FUTURES_CACHE_PATH, df.shape[1])
        return df
    return fetch_futures_prices()


def load_futures_returns(force_update: bool = False) -> pd.DataFrame:
    """Return daily percentage returns for futures continuous contracts."""
    prices = load_futures_prices(force_update=force_update)
    return price_to_returns(prices)
