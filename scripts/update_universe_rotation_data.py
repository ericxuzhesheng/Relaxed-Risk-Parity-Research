from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import tushare as ts


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.asset_universe import (  # noqa: E402
    CANDIDATE_UNIVERSE,
    ETF_UNIVERSE,
    asset_mapping_frame,
)
from src.data_loader import write_data_manifest  # noqa: E402


ACTIVE_PRICE_PATH = ROOT_DIR / "data" / "processed" / "etf_prices_updated.csv"
ACTIVE_MAPPING_PATH = ROOT_DIR / "data" / "processed" / "etf_asset_mapping.csv"
CANDIDATE_DAILY_PATH = ROOT_DIR / "data" / "processed" / "candidate_etf_daily.csv"
CANDIDATE_METADATA_PATH = ROOT_DIR / "data" / "processed" / "candidate_etf_metadata.csv"
MANIFEST_PATH = ROOT_DIR / "data" / "MANIFEST.json"

DAILY_COLUMNS = [
    "trade_date",
    "ts_code",
    "fund_name",
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "change",
    "pct_chg",
    "vol",
    "amount",
    "adj_factor",
    "adj_close",
]
METADATA_COLUMNS = [
    "ts_code",
    "name",
    "management",
    "custodian",
    "fund_type",
    "found_date",
    "list_date",
    "benchmark",
    "data_start",
    "data_end",
    "row_count",
    "source",
    "requested_start_date",
    "adjustment_method",
    "integration_status",
]


def _fetch_candidate_history(
    pro: object,
    ticker: str,
    display_name: str,
    start_date: str,
    end_date: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    daily = pro.fund_daily(ts_code=ticker, start_date=start_date, end_date=end_date)
    if daily is None or daily.empty:
        raise ValueError(f"No fund_daily data returned for {ticker}")
    daily = daily.copy()
    daily["trade_date"] = pd.to_datetime(daily["trade_date"], format="%Y%m%d")

    adj = pro.fund_adj(ts_code=ticker, start_date=start_date, end_date=end_date)
    if adj is not None and not adj.empty and {"trade_date", "adj_factor"}.issubset(adj.columns):
        adj = adj.copy()
        adj["trade_date"] = pd.to_datetime(adj["trade_date"], format="%Y%m%d")
        daily = daily.merge(adj[["trade_date", "adj_factor"]], on="trade_date", how="left")
        daily = daily.sort_values("trade_date")
        daily["adj_factor"] = pd.to_numeric(daily["adj_factor"], errors="coerce").ffill().bfill()
        latest_factor = float(daily["adj_factor"].dropna().iloc[-1])
    else:
        daily["adj_factor"] = 1.0
        latest_factor = 1.0
    daily["adj_close"] = (
        pd.to_numeric(daily["close"], errors="coerce") * daily["adj_factor"] / latest_factor
    )
    daily["fund_name"] = display_name
    daily = daily.sort_values("trade_date").reindex(columns=DAILY_COLUMNS)

    basic = pro.fund_basic(ts_code=ticker, market="E")
    basic_row = basic.iloc[0].to_dict() if basic is not None and not basic.empty else {}
    metadata = {
        "ts_code": ticker,
        "name": basic_row.get("name", display_name),
        "management": basic_row.get("management", ""),
        "custodian": basic_row.get("custodian", ""),
        "fund_type": basic_row.get("fund_type", ""),
        "found_date": basic_row.get("found_date", ""),
        "list_date": basic_row.get("list_date", ""),
        "benchmark": basic_row.get("benchmark", ""),
        "data_start": daily["trade_date"].min().date().isoformat(),
        "data_end": daily["trade_date"].max().date().isoformat(),
        "row_count": int(len(daily)),
        "source": "Tushare fund_basic + fund_daily + fund_adj",
        "requested_start_date": start_date,
        "adjustment_method": "close * adj_factor / latest_adj_factor",
        "integration_status": "candidate_only_not_in_backtest",
    }
    return daily, metadata


def _build_active_prices(
    old_prices: pd.DataFrame,
    old_mapping: pd.DataFrame,
    prior_candidate_daily: pd.DataFrame,
    cutoff: str,
) -> pd.DataFrame:
    old_prices = old_prices.copy()
    old_prices["trade_date"] = pd.to_datetime(old_prices["trade_date"])
    old_prices = old_prices.set_index("trade_date").sort_index()
    old_name_by_ticker = old_mapping.set_index("ticker")["new_name"].to_dict()

    prior_candidate_daily = prior_candidate_daily.copy()
    prior_candidate_daily["trade_date"] = pd.to_datetime(prior_candidate_daily["trade_date"])
    candidate_prices = prior_candidate_daily.pivot(
        index="trade_date", columns="ts_code", values="adj_close"
    ).sort_index()

    output = pd.DataFrame(index=old_prices.index)
    for item in ETF_UNIVERSE:
        old_name = old_name_by_ticker.get(item.ticker)
        if old_name is not None and old_name in old_prices.columns:
            output[item.new_name] = pd.to_numeric(old_prices[old_name], errors="coerce")
        elif item.ticker in candidate_prices.columns:
            output[item.new_name] = pd.to_numeric(candidate_prices[item.ticker], errors="coerce").reindex(
                output.index
            )
        else:
            raise ValueError(f"No cached price history available for active ETF {item.ticker}")

    output = output.loc[output.index <= pd.Timestamp(cutoff)]
    if output.shape[1] != 30:
        raise AssertionError(f"Expected 30 active ETFs, got {output.shape[1]}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply the approved 30-ETF universe rotation without backtesting.")
    parser.add_argument("--start-date", default="20150101")
    parser.add_argument("--end-date", default="20260807")
    parser.add_argument("--active-cutoff", default="2026-07-31")
    args = parser.parse_args()

    old_prices = pd.read_csv(ACTIVE_PRICE_PATH)
    old_mapping = pd.read_csv(ACTIVE_MAPPING_PATH)
    prior_candidate_daily = pd.read_csv(CANDIDATE_DAILY_PATH)

    active_prices = _build_active_prices(
        old_prices,
        old_mapping,
        prior_candidate_daily,
        cutoff=args.active_cutoff,
    )

    pro = ts.pro_api()
    candidate_frames: list[pd.DataFrame] = []
    candidate_metadata: list[dict[str, object]] = []
    for item in CANDIDATE_UNIVERSE:
        print(f"Fetching candidate {item.ticker} ({item.new_name})")
        daily, metadata = _fetch_candidate_history(
            pro,
            ticker=item.ticker,
            display_name=item.new_name,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        candidate_frames.append(daily)
        candidate_metadata.append(metadata)
        time.sleep(0.25)

    candidate_daily = pd.concat(candidate_frames, ignore_index=True).sort_values(
        ["ts_code", "trade_date"]
    )
    candidate_meta = pd.DataFrame(candidate_metadata, columns=METADATA_COLUMNS).sort_values("ts_code")
    active_codes = {item.ticker for item in ETF_UNIVERSE}
    candidate_codes = set(candidate_daily["ts_code"])
    if active_codes & candidate_codes:
        raise AssertionError(f"Active/candidate overlap: {sorted(active_codes & candidate_codes)}")
    if len(candidate_codes) != 6:
        raise AssertionError(f"Expected 6 candidate ETFs, got {len(candidate_codes)}")

    ACTIVE_PRICE_PATH.parent.mkdir(parents=True, exist_ok=True)
    active_prices.to_csv(ACTIVE_PRICE_PATH, index_label="trade_date")
    asset_mapping_frame().to_csv(ACTIVE_MAPPING_PATH, index=False)
    candidate_daily.to_csv(CANDIDATE_DAILY_PATH, index=False, date_format="%Y-%m-%d")
    candidate_meta.to_csv(CANDIDATE_METADATA_PATH, index=False)
    write_data_manifest(
        active_prices,
        ACTIVE_PRICE_PATH,
        source_label="approved-universe-rotation: cached Tushare histories; no backtest run",
        manifest_path=MANIFEST_PATH,
    )
    print(
        f"Wrote active={active_prices.shape[1]} through {active_prices.dropna(how='all').index.max().date()} "
        f"and candidates={len(candidate_codes)} through {candidate_daily['trade_date'].max().date()}"
    )


if __name__ == "__main__":
    main()
