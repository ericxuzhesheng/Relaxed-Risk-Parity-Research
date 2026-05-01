import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.backtest import run_static_backtest
from src.data_loader import load_data
from src.dynamic_selection import run_dynamic_rrp_selection
from src.metrics import calculate_metrics, calculate_turnover
from src.utils import get_config, resolve_path
from src.visualization import plot_drawdown_comparison, plot_nav_comparison, plot_weights


LOCAL_ASSETS = [
    "0-5中高信用票",
    "中证转债",
    "沪深300ETF",
    "中证1000ETF",
    "科创50ETF",
    "红利ETF",
    "上证指数ETF",
    "恒生ETF",
    "恒生科技ETF",
    "黄金ETF",
]


def _ensure_output_dirs():
    for path in ["results/tables", "results/figures"]:
        os.makedirs(resolve_path(path), exist_ok=True)


def _weight_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c.startswith("weight_")]


def _nav_from_result(result: pd.DataFrame, eval_start_date: str) -> pd.Series:
    eval_result = result[result["date"] >= eval_start_date].copy()
    nav = (1.0 + eval_result["portfolio_return"]).cumprod()
    nav.index = pd.to_datetime(eval_result["date"])
    return nav


def _summarize(name: str, result: pd.DataFrame, eval_start_date: str, config: dict) -> dict:
    nav = _nav_from_result(result, eval_start_date)
    metrics = calculate_metrics(
        nav,
        risk_free_rate=config["risk_free_rate"],
        trading_days=config["trading_days_per_year"],
    )
    metrics["model"] = name
    if "turnover" in result.columns:
        metrics["turnover"] = result.loc[result["date"] >= eval_start_date, "turnover"].mean()
    else:
        metrics["turnover"] = calculate_turnover(result[_weight_cols(result)])
    return metrics


def _make_weight_result(returns: pd.DataFrame, weights_by_date: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for date in returns.index:
        weights = weights_by_date.loc[date].values
        row = {
            "date": date,
            "portfolio_return": float(np.dot(returns.fillna(0.0).loc[date], weights)),
            "turnover": float(np.abs(weights_by_date.diff().fillna(0.0).loc[date]).sum()),
        }
        for asset, weight in zip(returns.columns, weights):
            row[f"weight_{asset}"] = weight
        rows.append(row)
    return pd.DataFrame(rows)


def run_equal_weight(returns: pd.DataFrame) -> pd.DataFrame:
    weights = pd.DataFrame(
        np.ones((len(returns), len(returns.columns))) / len(returns.columns),
        index=returns.index,
        columns=returns.columns,
    )
    return _make_weight_result(returns, weights)


def _min_variance_weights(window: pd.DataFrame) -> np.ndarray:
    cov = window.ffill().bfill().fillna(0.0).cov().fillna(0.0).values * 10000.0
    n_assets = cov.shape[0]
    diag = np.diag(cov).copy()
    positive = diag[diag > 0]
    floor = positive.min() * 1e-6 if len(positive) else 1e-12
    cov = cov.copy()
    np.fill_diagonal(cov, np.maximum(diag, floor))
    x0 = np.ones(n_assets) / n_assets

    def objective(weights):
        return float(weights @ cov @ weights)

    constraints = [{"type": "eq", "fun": lambda weights: np.sum(weights) - 1.0}]
    bounds = [(0.0, 1.0)] * n_assets
    result = minimize(objective, x0, method="SLSQP", bounds=bounds, constraints=constraints)
    if result.success:
        weights = np.clip(result.x, 0.0, None)
        total = weights.sum()
        if total > 0:
            return weights / total
    return x0


def run_minimum_variance(returns: pd.DataFrame, config: dict) -> pd.DataFrame:
    rebalance_dates = set(returns.groupby(returns.index.to_period("M")).tail(1).index)
    lookback = config["lookback_weeks"] * 5
    current_weights = np.ones(len(returns.columns)) / len(returns.columns)
    weights = []
    for date in returns.index:
        if date in rebalance_dates:
            window = returns[returns.index < date].iloc[-lookback:]
            if len(window) > 20:
                current_weights = _min_variance_weights(window)
        weights.append(current_weights.copy())
    weights_df = pd.DataFrame(weights, index=returns.index, columns=returns.columns)
    return _make_weight_result(returns, weights_df)


def main():
    config = get_config()
    eval_start_date = config.get("plot_start_date", "2021-01-01")
    _ensure_output_dirs()

    returns = load_data(source="tushare", force_update=False).dropna(how="all")
    assets_v1 = [asset for asset in LOCAL_ASSETS if asset in returns.columns]
    if len(assets_v1) < 3:
        assets_v1 = list(returns.columns[: min(10, len(returns.columns))])
    assets_v3 = list(returns.columns)

    models = {
        "Equal Weight": run_equal_weight(returns[assets_v3]),
        "Minimum Variance": run_minimum_variance(returns[assets_v3], config),
        "Standard RP": run_static_backtest(returns[assets_v1], model_type="standard"),
        "Relaxed RRP": run_static_backtest(returns[assets_v1], model_type="relaxed"),
        "Global RRP": run_static_backtest(returns[assets_v3], model_type="relaxed"),
        "HRP": run_static_backtest(returns[assets_v3], model_type="hrp"),
        "HERC": run_static_backtest(returns[assets_v3], model_type="herc"),
    }

    dynamic_grid = [
        {"lambda_pen": 0.01, "m": 1.0, "bond_leverage_upper": 1.2},
        {"lambda_pen": 0.1, "m": 1.9, "bond_leverage_upper": 1.4},
        {"lambda_pen": 1.0, "m": 2.5, "bond_leverage_upper": 1.4},
        {"lambda_pen": 1.9, "m": 3.0, "bond_leverage_upper": 1.6},
    ]
    dynamic = run_dynamic_rrp_selection(
        returns[assets_v3],
        dynamic_grid,
        train_window_months=24,
        selection_metric="sharpe_ratio",
        top_k=2,
        config_base=config,
    )
    if not dynamic.empty:
        models["Dynamic RRP"] = dynamic

    summaries = []
    nav_dict = {}
    for name, result in models.items():
        summaries.append(_summarize(name, result, eval_start_date, config))
        nav_dict[name] = _nav_from_result(result, eval_start_date)

    summary_df = pd.DataFrame(summaries)
    metric_cols = ["model"] + [c for c in summary_df.columns if c != "model"]
    summary_df = summary_df[metric_cols]
    summary_df.to_csv(resolve_path("results/tables/performance_summary.csv"), index=False)
    summary_df.to_csv(resolve_path("results/tables/hrp_comparison.csv"), index=False)

    plot_nav_comparison(
        nav_dict,
        f"NAV Comparison since {eval_start_date}",
        resolve_path("results/figures/nav_comparison.png"),
    )
    plot_drawdown_comparison(
        nav_dict,
        f"Drawdown Comparison since {eval_start_date}",
        resolve_path("results/figures/drawdown_comparison.png"),
    )

    hrp_weights = models["HRP"][["date"] + _weight_cols(models["HRP"])].copy()
    hrp_weights.columns = ["date"] + [c.replace("weight_", "") for c in _weight_cols(models["HRP"])]
    plot_weights(
        hrp_weights.set_index("date"),
        "HRP Weights",
        resolve_path("results/figures/hrp_weights_timeline.png"),
    )

    print(summary_df)
    print("HRP comparison outputs written to results/tables and results/figures.")


if __name__ == "__main__":
    main()
