"""Point-in-time monthly Chinese government-bond risk-free rates."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd


ROOT_DIR = Path(__file__).resolve().parent.parent
RAW_RISK_FREE_PATH = ROOT_DIR / "data" / "raw" / "chinabond_1y_yield_daily.csv"
MONTHLY_RISK_FREE_PATH = ROOT_DIR / "data" / "processed" / "risk_free_rate_monthly.csv"

RiskFreeFetcher = Callable[[str, str], pd.DataFrame]


def _normalize_daily(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"trade_date", "yield_pct", "provider"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"risk-free daily data missing columns: {sorted(missing)}")
    data = frame.copy()
    data["trade_date"] = pd.to_datetime(data["trade_date"], errors="coerce")
    data["yield_pct"] = pd.to_numeric(data["yield_pct"], errors="coerce")
    data["provider"] = data["provider"].astype(str)
    data = data.dropna(subset=["trade_date", "yield_pct", "provider"])
    if data.empty:
        return pd.DataFrame(columns=["trade_date", "yield_pct", "provider"])
    invalid = (~np.isfinite(data["yield_pct"])) | data["yield_pct"].lt(-5.0) | data["yield_pct"].gt(20.0)
    if invalid.any():
        raise ValueError("risk-free yields must be finite percentages between -5 and 20")
    return data.sort_values(["trade_date", "provider"]).reset_index(drop=True)


def merge_provider_yields(primary: pd.DataFrame, fallback: pd.DataFrame) -> pd.DataFrame:
    """Prefer primary observations and fail when same-day sources disagree."""
    first = _normalize_daily(primary)
    second = _normalize_daily(fallback)
    if first.empty:
        return second
    if second.empty:
        return first
    overlap = first.merge(second, on="trade_date", suffixes=("_primary", "_fallback"))
    conflicts = overlap.loc[
        ~np.isclose(overlap["yield_pct_primary"], overlap["yield_pct_fallback"], atol=1e-8, rtol=0.0)
    ]
    if not conflicts.empty:
        dates = conflicts["trade_date"].dt.strftime("%Y-%m-%d").tolist()
        raise ValueError(f"risk-free provider conflict on {dates}")
    combined = pd.concat(
        [first, second.loc[~second["trade_date"].isin(first["trade_date"])]], ignore_index=True
    )
    duplicated = combined.duplicated("trade_date", keep=False)
    if duplicated.any():
        dates = combined.loc[duplicated, "trade_date"].dt.strftime("%Y-%m-%d").unique().tolist()
        raise ValueError(f"duplicate risk-free observations remain on {dates}")
    return combined.sort_values("trade_date").reset_index(drop=True)


def _missing_observation_months(
    daily: pd.DataFrame,
    start_date: str | pd.Timestamp,
    end_date: str | pd.Timestamp,
) -> pd.PeriodIndex:
    data = _normalize_daily(daily)
    expected = pd.period_range(pd.Timestamp(start_date).to_period("M"), pd.Timestamp(end_date).to_period("M"), freq="M")
    if data.empty:
        return expected
    observed = pd.PeriodIndex(data["trade_date"].dt.to_period("M").unique(), freq="M")
    return expected.difference(observed)


def collect_risk_free_history(
    start_date: str,
    end_date: str,
    *,
    primary_fetcher: RiskFreeFetcher,
    fallback_fetcher: RiskFreeFetcher,
    required_start_date: str | None = None,
) -> pd.DataFrame:
    """Fetch primary history, fill from official fallback, and require every month."""
    coverage_start = required_start_date or start_date
    try:
        primary = primary_fetcher(start_date, end_date)
    except Exception:
        primary = pd.DataFrame(columns=["trade_date", "yield_pct", "provider"])
    missing = _missing_observation_months(primary, coverage_start, end_date)
    fallback = pd.DataFrame(columns=["trade_date", "yield_pct", "provider"])
    if len(missing):
        fallback = fallback_fetcher(start_date, end_date)
    combined = merge_provider_yields(primary, fallback)
    remaining = _missing_observation_months(combined, coverage_start, end_date)
    if len(remaining):
        labels = ", ".join(str(month) for month in remaining)
        raise ValueError(f"missing monthly risk-free observations for {labels}")
    return combined


def build_monthly_rates(daily: pd.DataFrame) -> pd.DataFrame:
    """Select each month's final observation and make it effective next month."""
    data = _normalize_daily(daily)
    if data.empty:
        return pd.DataFrame(
            columns=["observation_month", "observation_date", "effective_month", "annual_yield", "provider"]
        )
    duplicated = data.duplicated("trade_date", keep=False)
    if duplicated.any():
        dates = data.loc[duplicated, "trade_date"].dt.strftime("%Y-%m-%d").unique().tolist()
        raise ValueError(f"duplicate risk-free observations on {dates}")
    data["observation_month"] = data["trade_date"].dt.to_period("M")
    monthly = data.groupby("observation_month", as_index=False).tail(1).copy()
    monthly["observation_date"] = monthly["trade_date"]
    monthly["effective_month"] = monthly["observation_month"] + 1
    monthly["annual_yield"] = monthly["yield_pct"] / 100.0
    return monthly[
        ["observation_month", "observation_date", "effective_month", "annual_yield", "provider"]
    ].reset_index(drop=True)


def build_daily_risk_free_returns(
    trading_index: pd.DatetimeIndex,
    monthly_rates: pd.DataFrame,
    *,
    trading_days_per_year: int = 243,
) -> pd.Series:
    """Align lagged month-end annual yields to trading days and compound daily."""
    index = pd.DatetimeIndex(pd.to_datetime(trading_index)).sort_values()
    if index.has_duplicates:
        raise ValueError("trading index contains duplicate dates")
    if trading_days_per_year < 1:
        raise ValueError("trading_days_per_year must be positive")
    required = {"effective_month", "annual_yield"}
    missing_columns = required.difference(monthly_rates.columns)
    if missing_columns:
        raise ValueError(f"monthly risk-free data missing columns: {sorted(missing_columns)}")
    monthly = monthly_rates.copy()
    monthly["effective_month"] = monthly["effective_month"].astype("period[M]")
    if monthly["effective_month"].duplicated().any():
        raise ValueError("monthly risk-free data contains duplicate effective months")
    rate_by_month = monthly.set_index("effective_month")["annual_yield"].astype(float)
    required_months = pd.PeriodIndex(index.to_period("M").unique(), freq="M")
    missing_months = required_months.difference(rate_by_month.index)
    if len(missing_months):
        labels = ", ".join(str(month) for month in missing_months)
        raise ValueError(f"missing monthly risk-free rates for {labels}")
    annual = pd.Series(index.to_period("M").map(rate_by_month), index=index, dtype=float)
    daily = np.power(1.0 + annual, 1.0 / float(trading_days_per_year)) - 1.0
    daily.name = "risk_free_return"
    return daily


def load_monthly_risk_free(path: str | Path = MONTHLY_RISK_FREE_PATH) -> pd.DataFrame:
    data = pd.read_csv(path, parse_dates=["observation_date"])
    data["observation_month"] = data["observation_month"].astype("period[M]")
    data["effective_month"] = data["effective_month"].astype("period[M]")
    return data


def load_daily_risk_free_returns(
    trading_index: pd.DatetimeIndex,
    *,
    path: str | Path = MONTHLY_RISK_FREE_PATH,
    trading_days_per_year: int = 243,
) -> pd.Series:
    return build_daily_risk_free_returns(
        trading_index,
        load_monthly_risk_free(path),
        trading_days_per_year=trading_days_per_year,
    )
