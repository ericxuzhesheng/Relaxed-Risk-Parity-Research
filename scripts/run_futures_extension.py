"""Classic All Weather futures benchmark experiment.

This script turns the previous futures-extension comparison into a cleaner
benchmark study:

  Scenario 0: ETF-only Improved Convex Adaptive Global RRP.
  Scenario 1: Classic All Weather Futures Benchmark, 1.0x notional.
  Scenario 2: Vol-targeted All Weather Futures Benchmark, 8% target vol.
  Scenario 3: Vol-targeted All Weather Futures Benchmark, 10% target vol.

The All Weather benchmark is intentionally rules-based:
  - Three risky economic buckets are used: equity/growth, duration/deflation,
    and inflation/commodities.
  - Each bucket is formed from available futures using rolling inverse-vol
    weights.
  - Bucket allocation is inverse-vol weighted with explicit economic bucket
    budgets to approximate classic All Weather risk budgeting.
  - Futures price returns are layered over cash collateral earning r_f.
  - Vol-targeted variants scale monthly notional exposure using past-only
    realized volatility, capped by a configurable gross notional limit.

The result is not a Bridgewater replication. It is a transparent classic
All Weather / risk-parity-style benchmark.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.data_loader import load_data
from src.futures_data import load_futures_returns
from src.metrics import calculate_metrics
from src.utils import get_config, resolve_path
from src.visualization import plot_nav_comparison

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TRADING_DAYS = 243
DEFAULT_LOOKBACK_DAYS = 180
MIN_OBS = 60
DEFAULT_MAX_GROSS_NOTIONAL = 4.0

BUCKET_BUDGETS: dict[str, dict[str, float]] = {
    "balanced": {
        "Equity / Growth": 1.0,
        "Duration / Deflation": 1.0,
        "Inflation / Commodities": 1.0,
    },
    "classic": {
        "Equity / Growth": 0.30,
        "Duration / Deflation": 0.40,
        "Inflation / Commodities": 0.30,
    },
    "defensive": {
        "Equity / Growth": 0.25,
        "Duration / Deflation": 0.50,
        "Inflation / Commodities": 0.25,
    },
    "growth_tilt": {
        "Equity / Growth": 0.35,
        "Duration / Deflation": 0.35,
        "Inflation / Commodities": 0.30,
    },
}

ALL_WEATHER_BUCKETS: dict[str, list[str]] = {
    "Equity / Growth": [
        "沪深300股指IF",
        "中证500股指IC",
        "上证50股指IH",
        "中证1000股指IM",
    ],
    "Duration / Deflation": [
        "国债期货TS",
        "国债期货TF",
        "国债期货T",
        "国债期货TL",
    ],
    "Inflation / Commodities": [
        "黄金期货",
        "白银期货",
        "铜期货",
        "原油期货",
        "豆粕期货",
        "生猪期货",
        "白糖期货",
        "棉花期货",
        "菜籽油期货",
    ],
}


@dataclass
class AllWeatherResult:
    model: str
    returns: pd.Series
    nav: pd.Series
    weights: pd.DataFrame
    turnover: pd.Series
    gross_notional: pd.Series


def _monthly_rebalance_flags(index: pd.DatetimeIndex) -> pd.Series:
    periods = index.to_period("M")
    return pd.Series(periods != periods.shift(1), index=index).fillna(True)


def _row_weighted_return(row: pd.Series, weights: pd.Series) -> float:
    if weights.empty:
        return 0.0
    values = row.reindex(weights.index).astype(float)
    valid = values.notna()
    if not valid.any():
        return 0.0
    w = weights[valid]
    w_sum = float(w.sum())
    if w_sum <= 0:
        return 0.0
    return float((values[valid] * (w / w_sum)).sum())


def _weighted_history_returns(history: pd.DataFrame, weights: pd.Series) -> pd.Series:
    if weights.empty:
        return pd.Series(index=history.index, dtype=float)
    values = history.reindex(columns=weights.index).astype(float)
    numerator = values.mul(weights, axis=1).sum(axis=1, skipna=True)
    denominator = values.notna().mul(weights, axis=1).sum(axis=1)
    return numerator.div(denominator.replace(0.0, np.nan)).fillna(0.0)


def _inverse_vol_weights(history: pd.DataFrame) -> pd.Series:
    counts = history.count()
    valid_cols = counts[counts >= MIN_OBS].index.tolist()
    if not valid_cols:
        return pd.Series(dtype=float)
    vols = history[valid_cols].std(skipna=True)
    vols = vols.replace([np.inf, -np.inf], np.nan).dropna()
    vols = vols[vols > 0]
    if vols.empty:
        return pd.Series(dtype=float)
    inv = 1.0 / vols
    return inv / inv.sum()


def _bucket_weights_from_history(
    history: pd.DataFrame,
    bucket_budget: dict[str, float],
) -> tuple[dict[str, pd.Series], pd.Series]:
    asset_weights: dict[str, pd.Series] = {}
    bucket_hist_returns: dict[str, pd.Series] = {}

    for bucket, assets in ALL_WEATHER_BUCKETS.items():
        available = [asset for asset in assets if asset in history.columns]
        if not available:
            continue
        weights = _inverse_vol_weights(history[available])
        if weights.empty:
            continue
        asset_weights[bucket] = weights
        bucket_hist_returns[bucket] = _weighted_history_returns(history[weights.index], weights)

    if not bucket_hist_returns:
        return {}, pd.Series(dtype=float)

    bucket_frame = pd.DataFrame(bucket_hist_returns).dropna(how="all")
    bucket_vols = bucket_frame.std(skipna=True).replace([np.inf, -np.inf], np.nan).dropna()
    bucket_vols = bucket_vols[bucket_vols > 0]
    if bucket_vols.empty:
        return {}, pd.Series(dtype=float)

    budget = pd.Series(bucket_budget, dtype=float).reindex(bucket_vols.index).fillna(1.0)
    budget = budget.clip(lower=0.0)
    if float(budget.sum()) <= 0:
        budget = pd.Series(1.0, index=bucket_vols.index)

    inv_bucket_vol = budget / bucket_vols
    bucket_weights = inv_bucket_vol / inv_bucket_vol.sum()
    return asset_weights, bucket_weights


def _flatten_asset_weights(
    asset_weights: dict[str, pd.Series],
    bucket_weights: pd.Series,
    columns: pd.Index,
) -> pd.Series:
    out = pd.Series(0.0, index=columns)
    for bucket, b_weight in bucket_weights.items():
        for asset, a_weight in asset_weights[bucket].items():
            out.loc[asset] += float(b_weight * a_weight)
    total = float(out.sum())
    return out / total if total > 0 else out


def _past_vol(series: pd.Series, trading_days: int) -> float:
    clean = series.dropna()
    if len(clean) < MIN_OBS:
        return float("nan")
    return float(clean.std() * np.sqrt(trading_days))


def run_all_weather_benchmark(
    futures_returns: pd.DataFrame,
    eval_start: str,
    risk_free_rate: float,
    target_vol: float | None,
    model: str,
    bucket_budget: dict[str, float],
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    max_gross_notional: float = DEFAULT_MAX_GROSS_NOTIONAL,
    trading_days: int = TRADING_DAYS,
) -> AllWeatherResult:
    logger.info("Running %s", model)
    data = futures_returns.sort_index().dropna(how="all")
    data.index = pd.to_datetime(data.index)
    rebalance_flags = _monthly_rebalance_flags(data.index)
    rf_daily = risk_free_rate / trading_days

    current_asset_weights = pd.Series(0.0, index=data.columns)
    current_notional = 1.0
    rows: list[dict] = []
    returns: list[float] = []
    turnovers: list[float] = []
    gross_notional: list[float] = []
    raw_risky_returns: list[float] = []

    for date in data.index:
        loc = data.index.get_loc(date)
        history = data.iloc[max(0, loc - lookback_days):loc]
        is_rebalance = bool(rebalance_flags.loc[date])

        turnover = 0.0
        if is_rebalance and len(history) >= MIN_OBS:
            asset_weights, bucket_weights = _bucket_weights_from_history(history, bucket_budget)
            if asset_weights and not bucket_weights.empty:
                new_asset_weights = _flatten_asset_weights(asset_weights, bucket_weights, data.columns)
                turnover = float((new_asset_weights - current_asset_weights).abs().sum())
                current_asset_weights = new_asset_weights

                if target_vol is not None:
                    raw_hist = pd.Series(raw_risky_returns[-lookback_days:])
                    realized = _past_vol(raw_hist, trading_days)
                    if pd.notna(realized) and realized > 0:
                        current_notional = min(max_gross_notional, max(0.0, target_vol / realized))
                else:
                    current_notional = 1.0

        risky_return = _row_weighted_return(data.loc[date], current_asset_weights)
        total_return = rf_daily + current_notional * risky_return

        raw_risky_returns.append(risky_return)
        returns.append(total_return)
        turnovers.append(turnover * current_notional if is_rebalance else 0.0)
        gross_notional.append(current_notional)
        rows.append({"date": date, **{asset: current_asset_weights.loc[asset] * current_notional for asset in data.columns}})

    ret = pd.Series(returns, index=data.index, name=model)
    eval_ret = ret[ret.index >= pd.Timestamp(eval_start)]
    nav = (1.0 + eval_ret.fillna(0.0)).cumprod()
    weights = pd.DataFrame(rows).set_index("date")
    turnover_series = pd.Series(turnovers, index=data.index, name="turnover")
    gross_series = pd.Series(gross_notional, index=data.index, name="gross_notional")

    return AllWeatherResult(
        model=model,
        returns=eval_ret,
        nav=nav,
        weights=weights.loc[weights.index >= pd.Timestamp(eval_start)],
        turnover=turnover_series[turnover_series.index >= pd.Timestamp(eval_start)],
        gross_notional=gross_series[gross_series.index >= pd.Timestamp(eval_start)],
    )


def load_scenario0_returns(eval_start: str, config: dict) -> dict:
    path = resolve_path("results/tables/improved_convex_adaptive_global_relaxed_risk_parity_returns.csv")
    if not Path(path).exists():
        logger.warning("ETF baseline CSV not found at %s; run run_convex_adaptive_rrp.py first.", path)
        return {}
    df = pd.read_csv(path, parse_dates=["date"])
    eval_df = df[df["date"] >= eval_start].copy()
    nav = (1.0 + eval_df["portfolio_return"].fillna(0.0)).cumprod()
    nav.index = pd.to_datetime(eval_df["date"])
    metrics = calculate_metrics(nav, config.get("risk_free_rate", 0.0), config["trading_days_per_year"])
    metrics["model"] = "Scenario 0: ETF Baseline (Improved Convex)"
    metrics["avg_monthly_turnover"] = float(eval_df["turnover"].fillna(0.0).mean())
    metrics["avg_gross_notional"] = 1.0
    metrics["target_vol"] = np.nan
    return {"metrics": metrics, "nav": nav}


def metrics_from_all_weather(result: AllWeatherResult, risk_free_rate: float, trading_days: int, target_vol: float | None) -> dict:
    metrics = calculate_metrics(result.nav, risk_free_rate, trading_days)
    metrics["model"] = result.model
    monthly_turnover = result.turnover[result.turnover > 0]
    metrics["avg_monthly_turnover"] = float(monthly_turnover.mean()) if not monthly_turnover.empty else 0.0
    metrics["avg_gross_notional"] = float(result.gross_notional.mean())
    metrics["target_vol"] = target_vol if target_vol is not None else np.nan
    return metrics


def run_parameter_grid(
    futures_returns: pd.DataFrame,
    eval_start: str,
    risk_free_rate: float,
    trading_days: int,
) -> pd.DataFrame:
    rows: list[dict] = []
    target_vols = [0.06, 0.08, 0.10]
    lookbacks = [120, 180]
    gross_limits = [2.5, 3.0, 4.0]
    budget_names = ["balanced", "classic", "defensive", "growth_tilt"]

    for budget_name in budget_names:
        for lookback_days in lookbacks:
            for max_gross in gross_limits:
                for target_vol in target_vols:
                    model = (
                        f"Grid: {budget_name}, {lookback_days}d, "
                        f"{target_vol*100:.0f}% vol, {max_gross:.1f}x cap"
                    )
                    result = run_all_weather_benchmark(
                        futures_returns,
                        eval_start=eval_start,
                        risk_free_rate=risk_free_rate,
                        target_vol=target_vol,
                        model=model,
                        bucket_budget=BUCKET_BUDGETS[budget_name],
                        lookback_days=lookback_days,
                        max_gross_notional=max_gross,
                        trading_days=trading_days,
                    )
                    metrics = metrics_from_all_weather(result, risk_free_rate, trading_days, target_vol)
                    metrics["bucket_budget"] = budget_name
                    metrics["lookback_days"] = lookback_days
                    metrics["max_gross_notional"] = max_gross
                    rows.append(metrics)

    df = pd.DataFrame(rows)
    df = df.sort_values(
        ["sharpe_ratio", "calmar_ratio", "annualized_return"],
        ascending=[False, False, False],
    )
    out = resolve_path("results/tables/futures_extension_grid_search.csv")
    df.to_csv(out, index=False)
    logger.info("Saved futures benchmark grid search -> %s", out)
    print("\nTop All Weather grid candidates:")
    print(
        df[
            [
                "model",
                "annualized_return",
                "annualized_volatility",
                "sharpe_ratio",
                "max_drawdown",
                "calmar_ratio",
                "avg_gross_notional",
            ]
        ]
        .head(10)
        .to_string(index=False)
    )
    return df


def save_comparison_table(all_metrics: list[dict]) -> None:
    df = pd.DataFrame(all_metrics)
    cols_order = [
        "model",
        "annualized_return",
        "annualized_volatility",
        "sharpe_ratio",
        "sortino_ratio",
        "max_drawdown",
        "calmar_ratio",
        "avg_monthly_turnover",
        "avg_gross_notional",
        "target_vol",
    ]
    cols = [c for c in cols_order if c in df.columns] + [c for c in df.columns if c not in cols_order]
    df = df[cols]
    out = resolve_path("results/tables/futures_extension_comparison.csv")
    df.to_csv(out, index=False)
    logger.info("Saved comparison table -> %s", out)
    print("\nClassic All Weather Benchmark Comparison:")
    print(df.to_string(index=False))


def save_nav_chart(nav_dict: dict[str, pd.Series]) -> None:
    out = resolve_path("results/figures/futures_extension_nav.png")
    plot_nav_comparison(
        nav_dict,
        "Classic All Weather Futures Benchmark vs ETF RRP",
        out,
    )
    logger.info("Saved NAV chart -> %s", out)


def save_weights_chart(result: AllWeatherResult) -> None:
    if result.weights.empty:
        return
    mean_abs = result.weights.abs().mean().sort_values(ascending=False)
    top_cols = mean_abs.head(10).index.tolist()
    fig, ax = plt.subplots(figsize=(14, 5))
    result.weights[top_cols].plot.area(ax=ax, alpha=0.75)
    ax.set_title(f"{result.model} - Top-10 Notional Weights")
    ax.set_ylabel("Gross notional weight")
    ax.legend(loc="upper left", fontsize=7, ncol=2)
    plt.tight_layout()
    out = resolve_path("results/figures/futures_extension_weights.png")
    plt.savefig(out, dpi=120)
    plt.close()
    logger.info("Saved weights chart -> %s", out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-update", action="store_true", help="Re-fetch futures data from Tushare")
    parser.add_argument("--eval-start", type=str, default="2019-01-01")
    parser.add_argument("--target-vol-low", type=float, default=0.08)
    parser.add_argument("--target-vol-high", type=float, default=0.10)
    parser.add_argument("--bucket-budget", choices=sorted(BUCKET_BUDGETS), default="classic")
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument("--max-gross-notional", type=float, default=DEFAULT_MAX_GROSS_NOTIONAL)
    parser.add_argument("--grid-search", action="store_true", help="Run a small All Weather parameter grid before final scenarios")
    args = parser.parse_args()

    config = get_config({
        "transaction_cost_bps": 5.0,
        "risk_free_rate": 0.0182,
        "trading_days_per_year": TRADING_DAYS,
    })
    eval_start = args.eval_start
    risk_free_rate = config.get("risk_free_rate", 0.0)

    logger.info("Loading ETF returns to confirm local data cache is available...")
    _ = load_data(source="tushare").dropna(how="all")

    logger.info("Loading futures returns...")
    futures_returns = load_futures_returns(force_update=args.force_update)
    logger.info("Futures universe: %d assets, %d trading days", futures_returns.shape[1], len(futures_returns))
    if args.grid_search:
        run_parameter_grid(futures_returns, eval_start, risk_free_rate, TRADING_DAYS)

    all_metrics: list[dict] = []
    nav_dict: dict[str, pd.Series] = {}

    s0 = load_scenario0_returns(eval_start, config)
    if s0:
        all_metrics.append(s0["metrics"])
        nav_dict["ETF Improved Convex RRP"] = s0["nav"]

    classic = run_all_weather_benchmark(
        futures_returns,
        eval_start=eval_start,
        risk_free_rate=risk_free_rate,
        target_vol=None,
        model="Scenario 1: Classic All Weather Futures Benchmark (1.0x)",
        bucket_budget=BUCKET_BUDGETS[args.bucket_budget],
        lookback_days=args.lookback_days,
        max_gross_notional=args.max_gross_notional,
    )
    low_vol = run_all_weather_benchmark(
        futures_returns,
        eval_start=eval_start,
        risk_free_rate=risk_free_rate,
        target_vol=args.target_vol_low,
        model=f"Scenario 2: Vol-Targeted All Weather Futures ({args.target_vol_low*100:.0f}% target)",
        bucket_budget=BUCKET_BUDGETS[args.bucket_budget],
        lookback_days=args.lookback_days,
        max_gross_notional=args.max_gross_notional,
    )
    high_vol = run_all_weather_benchmark(
        futures_returns,
        eval_start=eval_start,
        risk_free_rate=risk_free_rate,
        target_vol=args.target_vol_high,
        model=f"Scenario 3: Vol-Targeted All Weather Futures ({args.target_vol_high*100:.0f}% target)",
        bucket_budget=BUCKET_BUDGETS[args.bucket_budget],
        lookback_days=args.lookback_days,
        max_gross_notional=args.max_gross_notional,
    )

    for result, target in [
        (classic, None),
        (low_vol, args.target_vol_low),
        (high_vol, args.target_vol_high),
    ]:
        all_metrics.append(metrics_from_all_weather(result, risk_free_rate, TRADING_DAYS, target))
        nav_dict[result.model.replace("Scenario ", "S")] = result.nav

    save_comparison_table(all_metrics)
    save_nav_chart(nav_dict)
    save_weights_chart(high_vol)
    logger.info("Classic All Weather benchmark experiment complete.")


if __name__ == "__main__":
    main()
