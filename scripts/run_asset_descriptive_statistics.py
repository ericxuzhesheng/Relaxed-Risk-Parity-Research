from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.data_loader import load_price_data, price_to_returns
from src.metrics import drawdown_series
from src.utils import resolve_path


OUTPUT_COLUMNS = [
    "etf",
    "ticker",
    "asset_class",
    "first_valid_date",
    "last_valid_date",
    "available_observations",
    "missing_ratio",
    "daily_mean_return",
    "daily_volatility",
    "annualized_return",
    "annualized_volatility",
    "max_drawdown",
]


def _annualized_return(price: pd.Series, trading_days: int) -> float:
    clean = price.dropna()
    if len(clean) < 2:
        return 0.0
    total_return = float(clean.iloc[-1] / clean.iloc[0] - 1.0)
    years = max((clean.index[-1] - clean.index[0]).days / 365.25, 1.0 / trading_days)
    return float((1.0 + total_return) ** (1.0 / years) - 1.0)


def compute_asset_statistics(
    prices: pd.DataFrame,
    mapping: pd.DataFrame,
    trading_days: int = 243,
) -> pd.DataFrame:
    prices = prices.apply(pd.to_numeric, errors="coerce").sort_index()
    returns = price_to_returns(prices)
    rows: list[dict] = []

    for _, item in mapping.iterrows():
        etf = str(item["new_name"])
        if etf not in prices.columns:
            continue
        price = prices[etf]
        ret = returns[etf] if etf in returns.columns else pd.Series(dtype=float)
        clean_price = price.dropna()
        clean_ret = ret.dropna()
        nav = clean_price / clean_price.iloc[0] if len(clean_price) > 0 else pd.Series(dtype=float)

        rows.append(
            {
                "etf": etf,
                "ticker": str(item["ticker"]),
                "asset_class": str(item["asset_class"]),
                "first_valid_date": clean_price.index.min().date().isoformat() if len(clean_price) else "",
                "last_valid_date": clean_price.index.max().date().isoformat() if len(clean_price) else "",
                "available_observations": int(clean_price.count()),
                "missing_ratio": float(price.isna().mean()),
                "daily_mean_return": float(clean_ret.mean()) if len(clean_ret) else 0.0,
                "daily_volatility": float(clean_ret.std()) if len(clean_ret) > 1 else 0.0,
                "annualized_return": _annualized_return(price, trading_days),
                "annualized_volatility": float(clean_ret.std() * np.sqrt(trading_days)) if len(clean_ret) > 1 else 0.0,
                "max_drawdown": float(drawdown_series(nav).min()) if len(nav) else 0.0,
            }
        )

    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)


def main() -> None:
    mapping = pd.read_csv(resolve_path("data/processed/etf_asset_mapping.csv"))
    prices = load_price_data(source="tushare", force_update=False)
    stats = compute_asset_statistics(prices, mapping)
    output = resolve_path("results/tables/asset_descriptive_statistics.csv")
    output.parent.mkdir(parents=True, exist_ok=True)
    stats.to_csv(output, index=False)
    print(f"Wrote {len(stats)} asset descriptive rows to {output}")


if __name__ == "__main__":
    main()
