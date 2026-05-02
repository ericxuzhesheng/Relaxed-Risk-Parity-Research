from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import tushare as ts

from src.asset_universe import ETF_UNIVERSE, etf_names, old_to_new_name
from src.utils import get_config, resolve_path


ASSET_MAP = {item.new_name: (item.ticker, "E") for item in ETF_UNIVERSE}


def fetch_from_tushare(start_date: str = "20180101", end_date: str | None = None) -> pd.DataFrame:
    config = get_config()
    token = config.get("tushare_token", "")
    if not token:
        raise RuntimeError("TUSHARE_TOKEN is not set. Set it in the environment before refreshing Tushare data.")
    ts.set_token(token)
    pro = ts.pro_api()
    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")

    frames = []
    for item in ETF_UNIVERSE:
        print(f"Syncing {item.new_name} ({item.ticker})...")
        daily = pro.fund_daily(ts_code=item.ticker, start_date=start_date, end_date=end_date)
        if daily is None or daily.empty:
            raise ValueError(f"No fund_daily data returned for {item.new_name} ({item.ticker}).")
        daily = daily.copy()
        daily["trade_date"] = pd.to_datetime(daily["trade_date"])
        daily = daily.set_index("trade_date").sort_index()

        adj = pro.fund_adj(ts_code=item.ticker, start_date=start_date, end_date=end_date)
        if adj is not None and not adj.empty and {"trade_date", "adj_factor"}.issubset(adj.columns):
            adj = adj.copy()
            adj["trade_date"] = pd.to_datetime(adj["trade_date"])
            adj = adj.set_index("trade_date").sort_index()
            base = float(adj["adj_factor"].dropna().iloc[-1])
            price = daily["close"].astype(float) * adj["adj_factor"].astype(float) / base
        else:
            price = daily["close"].astype(float)
        frames.append(price.rename(item.new_name))
        time.sleep(0.25)

    prices = pd.concat(frames, axis=1).sort_index()
    cache_path = resolve_path("data/processed/etf_prices_updated.csv")
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    prices.to_csv(cache_path)
    return prices


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
    if source == "tushare":
        cache_path = default_tushare_cache()
        if force_update or not cache_path.exists():
            df = fetch_from_tushare()
        else:
            df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
            if cache_path.name == "tushare_data.csv":
                df = df.rename(columns=old_to_new_name())
                available = [col for col in etf_names() if col in df.columns]
                df = df[available]
    else:
        file_path = str(resolve_path("资产数据.xlsx"))
        df_raw = pd.read_excel(file_path, header=None)
        names = df_raw.iloc[3, 1:].tolist()
        df = df_raw.iloc[5:].copy()
        df.columns = ["date"] + [str(n).strip() for n in names]
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
    return df.apply(pd.to_numeric, errors="coerce").sort_index()


def load_data(source: str = "tushare", force_update: bool = False) -> pd.DataFrame:
    return price_to_returns(load_price_data(source=source, force_update=force_update))


def update_data_from_wind(file_path=None):
    print("Wind update placeholder")
    return None
