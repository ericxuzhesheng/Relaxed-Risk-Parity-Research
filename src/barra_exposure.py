from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd


FACTOR_COLUMNS = [
    "china_market",
    "china_size",
    "china_value",
    "duration",
    "credit",
    "commodity",
    "global_equity",
]

COMMODITY_TICKERS = [
    "159980.SZ",
    "159981.SZ",
    "159985.SZ",
    "518880.SH",
    "162411.SZ",
]
GLOBAL_EQUITY_TICKERS = [
    "159920.SZ",
    "159941.SZ",
    "513500.SH",
    "513880.SH",
    "513030.SH",
]


def _require_columns(frame: pd.DataFrame, columns: Iterable[str]) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f"Missing columns required for Barra-style proxies: {missing}")


def build_barra_style_factors(returns: pd.DataFrame) -> pd.DataFrame:
    """Build transparent cross-asset factor proxies from ETF daily returns.

    These series are reproducible Barra-style proxies, not licensed MSCI Barra
    model factors. Equal-weight baskets require at least one constituent return
    on a date; pairwise estimation later handles each ETF's listing window.
    """
    required = {
        "510300.SH",
        "511880.SH",
        "512100.SH",
        "510880.SH",
        "511260.SH",
        "511030.SH",
        "511010.SH",
        *COMMODITY_TICKERS,
        *GLOBAL_EQUITY_TICKERS,
    }
    _require_columns(returns, required)

    cash = returns["511880.SH"]
    factors = pd.DataFrame(index=returns.index)
    factors["china_market"] = returns["510300.SH"] - cash
    factors["china_size"] = returns["512100.SH"] - returns["510300.SH"]
    factors["china_value"] = returns["510880.SH"] - returns["510300.SH"]
    factors["duration"] = returns["511260.SH"] - cash
    factors["credit"] = returns["511030.SH"] - returns["511010.SH"]
    factors["commodity"] = returns[COMMODITY_TICKERS].mean(axis=1, skipna=True) - cash
    factors["global_equity"] = returns[GLOBAL_EQUITY_TICKERS].mean(axis=1, skipna=True) - cash
    return factors[FACTOR_COLUMNS]


def estimate_standardized_exposures(
    returns: pd.DataFrame,
    factors: pd.DataFrame,
    min_observations: int = 120,
) -> pd.DataFrame:
    """Estimate standardized univariate factor loadings for every ETF.

    With both the ETF return and factor standardized on their common sample,
    the slope equals their Pearson correlation. This keeps heterogeneous asset
    classes comparable and avoids unstable multivariate coefficients among the
    deliberately simple proxy factors.
    """
    if min_observations < 2:
        raise ValueError("min_observations must be at least 2")
    factor_names = list(factors.columns)
    rows: list[dict[str, float | int | str]] = []

    for ticker in returns.columns:
        row: dict[str, float | int | str] = {"ts_code": str(ticker)}
        observation_counts: list[int] = []
        for factor_name in factor_names:
            pair = pd.concat(
                [returns[ticker].rename("asset"), factors[factor_name].rename("factor")],
                axis=1,
            ).dropna()
            count = int(len(pair))
            observation_counts.append(count)
            exposure = np.nan
            if count >= min_observations:
                asset_std = float(pair["asset"].std(ddof=1))
                factor_std = float(pair["factor"].std(ddof=1))
                if asset_std > 0.0 and factor_std > 0.0:
                    exposure = float(pair["asset"].corr(pair["factor"]))
            row[f"exposure_{factor_name}"] = exposure
            row[f"observations_{factor_name}"] = count
        row["min_factor_observations"] = min(observation_counts, default=0)
        rows.append(row)

    ordered_columns = ["ts_code"]
    ordered_columns.extend(f"exposure_{name}" for name in factor_names)
    ordered_columns.extend(f"observations_{name}" for name in factor_names)
    ordered_columns.append("min_factor_observations")
    return pd.DataFrame(rows)[ordered_columns]


def exposure_correlation_matrix(exposures: pd.DataFrame) -> pd.DataFrame:
    """Return ETF-by-ETF similarity of their standardized exposure vectors."""
    if "ts_code" not in exposures.columns:
        raise ValueError("exposures must contain a ts_code column")
    exposure_columns = [column for column in exposures if column.startswith("exposure_")]
    if len(exposure_columns) < 2:
        raise ValueError("at least two exposure columns are required")

    vectors = exposures.set_index("ts_code")[exposure_columns].apply(pd.to_numeric, errors="coerce")
    correlation = vectors.T.corr(min_periods=2)
    correlation = correlation.reindex(index=vectors.index, columns=vectors.index)
    for ticker in vectors.index:
        if vectors.loc[ticker].notna().sum() >= 2:
            correlation.loc[ticker, ticker] = 1.0
    return correlation
