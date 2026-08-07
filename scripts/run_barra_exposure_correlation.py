from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.asset_universe import CANDIDATE_UNIVERSE, ETF_UNIVERSE  # noqa: E402
from src.barra_exposure import (  # noqa: E402
    FACTOR_COLUMNS,
    build_barra_style_factors,
    estimate_standardized_exposures,
    exposure_correlation_matrix,
)


PROCESSED_DIR = ROOT_DIR / "data" / "processed"
ACTIVE_PRICE_PATH = PROCESSED_DIR / "etf_prices_updated.csv"
ACTIVE_MAPPING_PATH = PROCESSED_DIR / "etf_asset_mapping.csv"
CANDIDATE_DAILY_PATH = PROCESSED_DIR / "candidate_etf_daily.csv"
ANALYSIS_START = pd.Timestamp("2020-01-20")
MIN_OBSERVATIONS = 120
TRANSITIONS = {
    "562500.SH": "563300.SH",
    "513310.SH": "159981.SZ",
    "516980.SH": "511260.SH",
}


def _load_price_panel() -> tuple[pd.DataFrame, pd.DataFrame]:
    active_mapping = pd.read_csv(ACTIVE_MAPPING_PATH)
    active_prices = pd.read_csv(ACTIVE_PRICE_PATH, parse_dates=["trade_date"]).set_index("trade_date")
    name_to_ticker = active_mapping.set_index("new_name")["ticker"].to_dict()
    active_prices = active_prices.rename(columns=name_to_ticker)
    active_prices = active_prices[[item.ticker for item in ETF_UNIVERSE]]

    candidate_daily = pd.read_csv(CANDIDATE_DAILY_PATH, parse_dates=["trade_date"])
    candidate_prices = candidate_daily.pivot(
        index="trade_date", columns="ts_code", values="adj_close"
    ).sort_index()
    candidate_prices = candidate_prices[[item.ticker for item in CANDIDATE_UNIVERSE]]

    active_codes = set(active_prices.columns)
    candidate_codes = set(candidate_prices.columns)
    if active_codes & candidate_codes:
        raise AssertionError(f"Active/candidate overlap: {sorted(active_codes & candidate_codes)}")
    panel = pd.concat([active_prices, candidate_prices], axis=1).sort_index()
    active_cutoff = active_prices.dropna(how="all").index.max()
    return panel.loc[:active_cutoff], active_mapping


def _pairwise_return_correlation(
    returns: pd.DataFrame,
    left: str,
    right: str,
) -> tuple[float, int]:
    pair = returns[[left, right]].dropna()
    if len(pair) < MIN_OBSERVATIONS:
        return np.nan, int(len(pair))
    return float(pair[left].corr(pair[right])), int(len(pair))


def main() -> None:
    prices, active_mapping = _load_price_panel()
    prices = prices.loc[prices.index >= ANALYSIS_START].apply(pd.to_numeric, errors="coerce")
    returns = prices.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
    factors = build_barra_style_factors(returns)
    exposures = estimate_standardized_exposures(
        returns,
        factors,
        min_observations=MIN_OBSERVATIONS,
    )
    exposure_corr = exposure_correlation_matrix(exposures)

    active_names = active_mapping.set_index("ticker")["new_name"].to_dict()
    candidate_names = {item.ticker: item.new_name for item in CANDIDATE_UNIVERSE}
    all_names = active_names | candidate_names
    active_codes = [item.ticker for item in ETF_UNIVERSE]
    candidate_codes = [item.ticker for item in CANDIDATE_UNIVERSE]
    exposures.insert(1, "name", exposures["ts_code"].map(all_names))
    exposures.insert(
        2,
        "universe_status",
        np.where(exposures["ts_code"].isin(active_codes), "active_30", "candidate_6"),
    )

    candidate_active_rows: list[dict[str, object]] = []
    for candidate in candidate_codes:
        for active in active_codes:
            raw_corr, paired_days = _pairwise_return_correlation(returns, candidate, active)
            candidate_active_rows.append(
                {
                    "candidate_ts_code": candidate,
                    "candidate_name": all_names[candidate],
                    "active_ts_code": active,
                    "active_name": all_names[active],
                    "exposure_vector_correlation": exposure_corr.loc[candidate, active],
                    "daily_return_correlation": raw_corr,
                    "paired_return_days": paired_days,
                }
            )
    candidate_active = pd.DataFrame(candidate_active_rows).sort_values(
        ["candidate_ts_code", "exposure_vector_correlation"], ascending=[True, False]
    )

    transition_rows: list[dict[str, object]] = []
    for old_ticker, new_ticker in TRANSITIONS.items():
        raw_corr, paired_days = _pairwise_return_correlation(returns, old_ticker, new_ticker)
        transition_rows.append(
            {
                "out_ts_code": old_ticker,
                "out_name": all_names[old_ticker],
                "in_ts_code": new_ticker,
                "in_name": all_names[new_ticker],
                "exposure_vector_correlation": exposure_corr.loc[old_ticker, new_ticker],
                "daily_return_correlation": raw_corr,
                "paired_return_days": paired_days,
            }
        )
    transition_summary = pd.DataFrame(transition_rows)

    factors.rename_axis("trade_date").to_csv(PROCESSED_DIR / "barra_style_factor_returns.csv")
    exposures.to_csv(PROCESSED_DIR / "barra_style_etf_exposures.csv", index=False)
    exposure_corr.rename_axis("ts_code").to_csv(
        PROCESSED_DIR / "barra_style_exposure_correlation.csv"
    )
    candidate_active.to_csv(
        PROCESSED_DIR / "barra_style_candidate_active_correlation.csv", index=False
    )
    transition_summary.to_csv(PROCESSED_DIR / "barra_style_transition_summary.csv", index=False)

    methodology = {
        "method": "transparent Barra-style cross-asset proxy exposure analysis",
        "official_barra_model": False,
        "warning": "These are reproducible ETF-return proxies, not licensed MSCI Barra exposures.",
        "analysis_start": str(returns.index.min().date()),
        "analysis_end": str(returns.index.max().date()),
        "active_etf_count": len(active_codes),
        "candidate_etf_count": len(candidate_codes),
        "minimum_pairwise_observations": MIN_OBSERVATIONS,
        "exposure_estimator": "Pearson correlation of ETF return and each factor proxy on their common daily sample",
        "factor_order": FACTOR_COLUMNS,
        "factor_definitions": {
            "china_market": "510300.SH - 511880.SH",
            "china_size": "512100.SH - 510300.SH",
            "china_value": "510880.SH - 510300.SH",
            "duration": "511260.SH - 511880.SH",
            "credit": "511030.SH - 511010.SH",
            "commodity": "equal-weight(159980.SZ,159981.SZ,159985.SZ,518880.SH,162411.SZ) - 511880.SH",
            "global_equity": "equal-weight(159920.SZ,159941.SZ,513500.SH,513880.SH,513030.SH) - 511880.SH",
        },
    }
    (PROCESSED_DIR / "barra_style_methodology.json").write_text(
        json.dumps(methodology, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"Wrote Barra-style exposure diagnostics for {len(exposures)} ETFs "
        f"({len(active_codes)} active + {len(candidate_codes)} candidates); no backtest was run."
    )


if __name__ == "__main__":
    main()
