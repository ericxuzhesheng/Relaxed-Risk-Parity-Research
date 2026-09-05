import os
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.backtest import run_static_backtest
from src.benchmarks import run_benchmark_backtest
from src.data_loader import load_data
from src.metrics import calculate_metrics, calculate_turnover
from src.public_labels import apply_public_model_labels, public_model_label
from src.utils import get_config, resolve_path
from src.visualization import plot_drawdown_comparison, plot_nav_comparison, plot_weights


LOCAL_ASSETS = [
    "可转债ETF",
    "5年国债ETF",
    "信用债ETF",
    "日利ETF",
    "沪深300ETF",
    "中证500ETF",
    "中证1000ETF",
    "科创50ETF",
    "红利ETF",
    "半导体ETF",
    "人工智能ETF",
    "机器人ETF",
    "新能源ETF",
    "消费电子ETF",
    "通信ETF",
    "云计算ETF",
    "证券ETF",
    "军工ETF",
    "消费ETF",
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
        risk_free_returns=config["risk_free_rate"],
        trading_days=config["trading_days_per_year"],
    )
    metrics["model"] = name
    if "turnover" in result.columns:
        metrics["turnover"] = result.loc[result["date"] >= eval_start_date, "turnover"].mean()
    else:
        metrics["turnover"] = calculate_turnover(result[_weight_cols(result)])
    return metrics


def run_equal_weight(
    returns: pd.DataFrame,
    transaction_cost_bps: float = 3.0,
) -> pd.DataFrame:
    """Run the equal-weight benchmark with monthly rebalancing and drift."""
    return run_benchmark_backtest(
        returns,
        "Equal Weight Benchmark",
        transaction_cost_bps=transaction_cost_bps,
    )


def run_minimum_variance(returns: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Run the minimum-variance benchmark under the common cost convention."""
    return run_benchmark_backtest(
        returns,
        "Minimum Variance Benchmark",
        lookback_days=config["lookback_weeks"] * 5,
        transaction_cost_bps=config["transaction_cost_bps"],
    )


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
        "Equal Weight": run_equal_weight(
            returns[assets_v3], config["transaction_cost_bps"]
        ),
        "Minimum Variance": run_minimum_variance(returns[assets_v3], config),
        "Standard Risk Parity": run_static_backtest(returns[assets_v1], model_type="standard"),
        "Local Relaxed Risk Parity": run_static_backtest(returns[assets_v1], model_type="relaxed"),
        "Global Relaxed Risk Parity": run_static_backtest(returns[assets_v3], model_type="relaxed"),
        "HRP Benchmark": run_static_backtest(returns[assets_v3], model_type="hrp"),
        "HERC Benchmark": run_static_backtest(returns[assets_v3], model_type="herc"),
    }

    summaries = []
    nav_dict = {}
    for name, result in models.items():
        summaries.append(_summarize(name, result, eval_start_date, config))
        nav_dict[name] = _nav_from_result(result, eval_start_date)

    summary_df = pd.DataFrame(summaries)
    metric_cols = ["model"] + [c for c in summary_df.columns if c != "model"]
    summary_df = summary_df[metric_cols]
    apply_public_model_labels(summary_df).to_csv(resolve_path("results/tables/hrp_comparison.csv"), index=False)

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

    hrp_weights = models["HRP Benchmark"][["date"] + _weight_cols(models["HRP Benchmark"])].copy()
    hrp_weights.columns = ["date"] + [c.replace("weight_", "") for c in _weight_cols(models["HRP Benchmark"])]
    plot_weights(
        hrp_weights.set_index("date"),
        f"{public_model_label('HRP')} Weights",
        resolve_path("results/figures/hrp_weights_timeline.png"),
    )

    print(summary_df)
    print("HRP comparison outputs written to results/tables and results/figures.")


if __name__ == "__main__":
    main()
