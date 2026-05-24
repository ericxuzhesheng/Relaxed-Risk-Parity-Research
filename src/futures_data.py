"""Futures continuous contract data for the Bridgewater-style extension experiment.

Constructs a daily continuous return series for each futures product by:
1. Generating the set of quarterly/monthly contract codes for the study period.
2. Fetching daily close prices for each contract via Tushare (CFX/DCE/INE/GFEX)
   or via akshare Sina (SHFE/CZCE — Tushare token permissions not required).
3. Rolling to the next contract 15 calendar days before expiry (the roll window).
4. Splicing prices proportionally at roll dates to avoid gap jumps.

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

try:
    import akshare as ak
    _AKSHARE_AVAILABLE = True
except ImportError:
    _AKSHARE_AVAILABLE = False

from src.data_loader import price_to_returns
from src.utils import get_config, resolve_path


logger = logging.getLogger(__name__)

# ── Contract specifications ────────────────────────────────────────────────────
#
# Each entry: (exchange, [delivery months], roll_days_before_expiry, use_akshare)
#
# Data source by exchange:
#   CFX  (中金所)     — Tushare  ✓  bond futures T/TF/TS/TL, stock index IF/IC/IH  → ts_code suffix .CFX
#   DCE  (大商所)     — Tushare  ✓  M/LH/I/C/Y               → ts_code suffix .DCE
#   INE  (上期能源)   — Tushare  ✓  SC                        → ts_code suffix .INE
#   GFEX (广期所)     — Tushare  ✓  SI/LC (2022+/2023+)       → ts_code suffix .GFEX
#   SHF  (上期所)     — Tushare  ✓  AU/AG/CU/RB               → ts_code suffix .SHF
#   ZCE  (郑商所)     — Tushare  ✓  SR/CF/OI/ZC               → ts_code suffix .ZCE
#
FUTURES_SPECS: dict[str, tuple[str, list[int], int, bool]] = {
    # ── CFX bond futures (Tushare) ────────────────────────────────────────────
    "国债期货TL": ("CFX",  [3, 6, 9, 12],           15, False),  # 30Y (2023+)
    "国债期货T":  ("CFX",  [3, 6, 9, 12],           15, False),  # 10Y
    "国债期货TF": ("CFX",  [3, 6, 9, 12],           15, False),  # 5Y
    "国债期货TS": ("CFX",  [3, 6, 9, 12],           15, False),  # 2Y (2018+)
    # ── CFX stock index futures (Tushare) ─────────────────────────────────────
    "沪深300股指IF": ("CFX", list(range(1, 13)),    15, False),  # IF (current+next month + quarterly)
    "中证500股指IC": ("CFX", list(range(1, 13)),    15, False),  # IC
    # ── DCE commodity futures (Tushare) ──────────────────────────────────────
    "豆粕期货":   ("DCE",  [1, 3, 5, 7, 8, 9, 11, 12], 15, False),  # M
    "生猪期货":   ("DCE",  [1, 3, 5, 7, 9, 11],     15, False),  # LH (2021+)
    "铁矿石期货": ("DCE",  [1, 3, 5, 7, 9, 11],     15, False),  # I
    "玉米期货":   ("DCE",  [1, 3, 5, 7, 9, 11],     15, False),  # C
    "豆油期货":   ("DCE",  [1, 3, 5, 7, 9, 11],     15, False),  # Y
    # ── INE energy (Tushare) ─────────────────────────────────────────────────
    "原油期货":   ("INE",  list(range(1, 13)),       15, False),  # SC (2018+)
    # ── GFEX new energy materials (Tushare) ──────────────────────────────────
    "工业硅期货": ("GFEX", [1, 3, 5, 7, 9, 11],     15, False),  # SI (2022+)
    "碳酸锂期货": ("GFEX", [1, 3, 5, 7, 9, 11],     15, False),  # LC (2023+)
    # ── SHF precious/industrial metals (Tushare, suffix .SHF) ────────────────
    "黄金期货":   ("SHF",  [2, 4, 6, 8, 10, 12],    15, False),  # AU
    "白银期货":   ("SHF",  list(range(1, 13)),       15, False),  # AG
    "铜期货":     ("SHF",  list(range(1, 13)),       15, False),  # CU
    "螺纹钢期货": ("SHF",  list(range(1, 13)),       15, False),  # RB
    # ── ZCE agricultural + energy (Tushare, suffix .ZCE) ────────────────────
    "白糖期货":   ("ZCE",  list(range(1, 13)),       15, False),  # SR
    "棉花期货":   ("ZCE",  list(range(1, 13)),       15, False),  # CF
    "菜籽油期货": ("ZCE",  list(range(1, 13)),       15, False),  # OI
    "动力煤期货": ("ZCE",  [1, 3, 5, 7, 9, 11],     15, False),  # ZC (coal)
}

# Product code prefix (before YYMM)
FUTURES_CODES: dict[str, str] = {
    "国债期货TL": "TL",
    "国债期货T":  "T",
    "国债期货TF": "TF",
    "国债期货TS": "TS",
    "豆粕期货":   "M",
    "生猪期货":   "LH",
    "铁矿石期货": "I",
    "玉米期货":   "C",
    "豆油期货":   "Y",
    "原油期货":   "SC",
    "工业硅期货": "SI",
    "碳酸锂期货": "LC",
    "黄金期货":   "AU",
    "白银期货":   "AG",
    "铜期货":     "CU",
    "螺纹钢期货": "RB",
    "白糖期货":   "SR",
    "棉花期货":   "CF",
    "菜籽油期货": "OI",
}

# First listing dates for products with limited history
PRODUCT_LIST_DATE: dict[str, str] = {
    "国债期货TL": "2023-04-21",
    "国债期货TS": "2018-08-17",
    "生猪期货":   "2021-01-08",
    "原油期货":   "2018-03-26",
    "工业硅期货": "2022-12-26",
    "碳酸锂期货": "2023-07-21",
}

FUTURES_CACHE_PATH = resolve_path("data/processed/futures_prices.csv")
FUTURES_UNIVERSE = list(FUTURES_SPECS.keys())


# ── Contract code generation ───────────────────────────────────────────────────

def _contract_expiry_date(year: int, month: int, exchange: str) -> datetime:
    """Approximate expiry date for a futures contract."""
    if exchange == "CFX":
        # Bond futures: second Friday of the delivery month
        first_day = datetime(year, month, 1)
        days_to_friday = (4 - first_day.weekday()) % 7
        first_friday = first_day + timedelta(days=days_to_friday)
        return first_friday + timedelta(weeks=1)
    if exchange == "INE":
        # SC crude oil: last trading day is in the preceding month
        prev_month = month - 1 if month > 1 else 12
        prev_year = year if month > 1 else year - 1
        last_day = calendar.monthrange(prev_year, prev_month)[1]
        return datetime(prev_year, prev_month, last_day)
    # SHF/DCE/ZCE/GFEX: use the 15th as a conservative expiry bound
    return datetime(year, month, 15)


def _generate_contract_codes(name: str, start_year: int, end_year: int) -> list[tuple[str, datetime]]:
    """Return (ts_code, expiry_date) pairs for all delivery months in the period.

    All codes use the 2-digit year format (YYMM) which works for both Tushare
    and akshare Sina. For Tushare products the exchange suffix (.CFX/.DCE/etc.)
    is appended; for akshare products the suffix is also appended but stripped
    later in _fetch_contract_akshare().
    """
    exchange, months, _roll, _use_ak = FUTURES_SPECS[name]
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
            ts_code = f"{code}{yy}{month:02d}.{exchange}"
            contracts.append((ts_code, expiry))
    return contracts


# ── Data fetching ──────────────────────────────────────────────────────────────

def _tushare_to_sina_code(ts_code: str) -> str:
    """Strip the exchange suffix to get the Sina futures symbol.

    e.g. AU2412.SFE → AU2412, CF2401.CZCE → CF2401
    """
    return ts_code.split(".")[0]


def _fetch_contract_akshare(ts_code: str) -> pd.Series | None:
    """Fetch daily close price for one contract via akshare (Sina Finance)."""
    if not _AKSHARE_AVAILABLE:
        logger.warning("akshare not installed — cannot fetch %s", ts_code)
        return None
    sina_code = _tushare_to_sina_code(ts_code)
    try:
        df = ak.futures_zh_daily_sina(symbol=sina_code)
    except Exception as exc:
        logger.debug("akshare.futures_zh_daily_sina(%s): %s", sina_code, exc)
        return None
    if df is None or df.empty:
        return None
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    if "volume" in df.columns:
        df = df[df["volume"].fillna(0) > 0]
    if df.empty:
        return None
    return df["close"].astype(float).rename(ts_code)


def _fetch_contract_tushare(pro, ts_code: str, start_date: str, end_date: str) -> pd.Series | None:
    """Fetch daily close price for one contract via Tushare pro.fut_daily()."""
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


def _fetch_contract(
    pro,
    ts_code: str,
    start_date: str,
    end_date: str,
    use_akshare: bool = False,
) -> pd.Series | None:
    """Dispatch to Tushare or akshare based on the use_akshare flag."""
    if use_akshare:
        return _fetch_contract_akshare(ts_code)
    return _fetch_contract_tushare(pro, ts_code, start_date, end_date)


# ── Continuous contract construction ──────────────────────────────────────────

def build_continuous_price(
    name: str,
    contracts: list[tuple[str, datetime]],
    all_prices: dict[str, pd.Series],
    roll_days: int = 15,
) -> pd.Series | None:
    """Build a proportionally back-adjusted continuous price series.

    Roll occurs when the front contract is within ``roll_days`` calendar days
    of its expiry. At each roll the cumulative adjustment factor is updated
    using the ratio of the two contracts' close prices on the roll date.
    """
    available = {code: s for code, s in all_prices.items() if s is not None and len(s) > 0}
    if not available:
        return None

    price_df = pd.concat(list(available.values()), axis=1).sort_index()
    all_dates = price_df.index

    sorted_contracts = sorted(
        [(c, e) for c, e in contracts if c in available],
        key=lambda x: x[1],
    )
    if not sorted_contracts:
        return None

    continuous_prices: list[float] = []
    continuous_index: list[pd.Timestamp] = []
    cumulative_adj = 1.0
    current_contract_idx = 0

    for date in all_dates:
        while current_contract_idx < len(sorted_contracts) - 1:
            curr_code, curr_expiry = sorted_contracts[current_contract_idx]
            roll_date = curr_expiry - timedelta(days=roll_days)
            if date.to_pydatetime() >= roll_date:
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
    return series / series.iloc[0] * 100.0


# ── Top-level fetch / load ─────────────────────────────────────────────────────

def fetch_futures_prices(
    start_date: str = "20180101",
    end_date: str | None = None,
    names: list[str] | None = None,
) -> pd.DataFrame:
    """Fetch and construct continuous contract prices for all futures products.

    Tushare-based products (CFX/DCE/INE/GFEX) and akshare-based products
    (SFE/CZCE) are handled transparently. Products for which data is unavailable
    are skipped with a warning rather than raising an error.
    """
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
        _exchange, _months, roll_days, use_akshare = FUTURES_SPECS[name]
        print(f"Building continuous contract for {name} "
              f"({'akshare' if use_akshare else 'tushare'})...")
        contracts = _generate_contract_codes(name, start_year, end_year)
        all_prices: dict[str, pd.Series] = {}

        for ts_code, expiry in contracts:
            if expiry < datetime.strptime(start_date, "%Y%m%d"):
                continue
            contract_start = (expiry - timedelta(days=365)).strftime("%Y%m%d")
            contract_start = max(contract_start, start_date)
            s = _fetch_contract(pro, ts_code, contract_start, end_date, use_akshare=use_akshare)
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
        raise RuntimeError("No futures data fetched. Check token and permissions.")

    prices = pd.concat(frames, axis=1).sort_index()
    FUTURES_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    prices.to_csv(FUTURES_CACHE_PATH)
    logger.info(
        "Saved futures prices → %s (%d rows, %d assets)",
        FUTURES_CACHE_PATH, len(prices), prices.shape[1],
    )
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
