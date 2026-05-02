from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.run_robustness_tests import build_models, selected_improved_config
from src.benchmarks import BENCHMARK_BUILDERS, run_benchmark_backtest
from src.data_loader import load_data
from src.metrics import calculate_metrics, drawdown_series
from src.utils import get_config

MODEL_ORDER = [
    "Global Relaxed Risk Parity",
    "Improved Convex Adaptive Global RRP",
    "Convex Adaptive Global RRP",
    "Defensive Dynamic Relaxed Risk Parity",
    *BENCHMARK_BUILDERS.keys(),
]


def output_dirs(root: Path) -> tuple[Path, Path]:
    tables = root / "tables"
    figures = root / "figures"
    tables.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    return tables, figures


def load_returns(smoke: bool) -> pd.DataFrame:
    if smoke:
        rng = np.random.default_rng(17)
        dates = pd.bdate_range("2020-01-01", periods=220)
        columns = ["equity_a", "equity_b", "bond_a", "bond_b", "gold_a", "defensive_a"]
        data = rng.normal(0.0002, 0.008, size=(len(dates), len(columns)))
        data[:, 2:4] = rng.normal(0.00008, 0.003, size=(len(dates), 2))
        return pd.DataFrame(data, index=dates, columns=columns)
    returns = load_data(source="tushare", force_update=False).dropna(how="all")
    return returns.loc[:, returns.notna().mean() > 0.95].fillna(0.0)


def return_col(result: pd.DataFrame) -> str:
    return "net_return" if "net_return" in result.columns else "portfolio_return"


def nav(result: pd.DataFrame) -> pd.Series:
    data = result.copy()
    data["date"] = pd.to_datetime(data["date"])
    out = (1.0 + data[return_col(data)].fillna(0.0)).cumprod()
    out.index = data["date"]
    return out


def cvar(series: pd.Series, beta: float = 0.95) -> float:
    losses = -pd.Series(series).dropna()
    if losses.empty:
        return 0.0
    cutoff = losses.quantile(beta)
    tail = losses[losses >= cutoff]
    return float(tail.mean()) if not tail.empty else float(cutoff)


def summarize(name: str, result: pd.DataFrame, config: dict) -> dict:
    data = result.copy()
    data["date"] = pd.to_datetime(data["date"])
    ret = return_col(data)
    gross = data["gross_return"] if "gross_return" in data.columns else data[ret]
    gross_nav = (1.0 + gross.fillna(0.0)).cumprod()
    gross_nav.index = data["date"]
    metrics = calculate_metrics(nav(data), config["risk_free_rate"], config["trading_days_per_year"])
    gross_metrics = calculate_metrics(gross_nav, config["risk_free_rate"], config["trading_days_per_year"])
    months = max(data["date"].dt.to_period("M").nunique(), 1)
    turnover = data.get("turnover", pd.Series(0.0, index=data.index)).fillna(0.0)
    years = max((data["date"].max() - data["date"].min()).days / 365.25, 1.0 / 12.0)
    return {
        "model": name,
        "benchmark_status": data.get("benchmark_status", pd.Series("ok", index=data.index)).iloc[-1],
        "skip_reason": data.get("skip_reason", pd.Series("", index=data.index)).iloc[-1],
        "annual_return": metrics["annualized_return"],
        "volatility": metrics["annualized_volatility"],
        "sharpe": metrics["sharpe_ratio"],
        "sortino": metrics["sortino_ratio"],
        "max_drawdown": metrics["max_drawdown"],
        "calmar": metrics["calmar_ratio"],
        "cvar_95_daily_loss": cvar(data[ret], 0.95),
        "avg_monthly_turnover": float(turnover.sum() / months),
        "net_annual_return": metrics["annualized_return"],
        "transaction_cost_drag": gross_metrics["annualized_return"] - metrics["annualized_return"],
        "turnover_adjusted_sharpe": metrics["sharpe_ratio"],
        "annualized_turnover": float(turnover.sum() / years),
    }


def drawdown_table(models: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, result in models.items():
        dd = drawdown_series(nav(result))
        rows.append(
            {
                "model": name,
                "max_drawdown": float(dd.min()),
                "average_drawdown": float(dd.mean()),
                "drawdown_observations_below_5pct": int((dd <= -0.05).sum()),
                "worst_drawdown_date": dd.idxmin().date().isoformat(),
            }
        )
    return pd.DataFrame(rows)


def plot_navs(models: dict[str, pd.DataFrame], path: Path) -> None:
    plt.figure(figsize=(12, 6))
    for name, result in models.items():
        series = nav(result)
        plt.plot(series.index, series.values, label=name)
    plt.title("Benchmark NAV Comparison")
    plt.ylabel("NAV")
    plt.grid(True, alpha=0.3)
    plt.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def plot_drawdowns(models: dict[str, pd.DataFrame], path: Path) -> None:
    plt.figure(figsize=(12, 6))
    for name, result in models.items():
        series = drawdown_series(nav(result))
        plt.plot(series.index, series.values, label=name)
    plt.title("Benchmark Drawdown Comparison")
    plt.ylabel("Drawdown")
    plt.grid(True, alpha=0.3)
    plt.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run benchmark suite against the public RRP model line.")
    parser.add_argument("--smoke", action="store_true", help="Run a deterministic fast smoke version.")
    parser.add_argument("--output-root", type=Path, default=ROOT_DIR / "results")
    args = parser.parse_args()
    tables, figures = output_dirs(args.output_root)
    config = get_config({"transaction_cost_bps": 3.0, "turnover_cap": 0.25, "target_vol": 0.060})
    if args.smoke:
        config.update({"lookback_weeks": 12, "optim_maxiter": 200})
    returns = load_returns(args.smoke)
    improved_cfg = selected_improved_config(
        config["transaction_cost_bps"],
        ROOT_DIR / "results" / "tables" / "convex_adaptive_improvement_candidates.csv",
        args.smoke,
    )
    if args.smoke:
        improved_cfg.lookback_days = min(improved_cfg.lookback_days, 60)
        improved_cfg.max_weight = max(improved_cfg.max_weight, 0.60)

    models, _ = build_models(returns, config, improved_cfg, include_dynamic=True)
    for name in BENCHMARK_BUILDERS:
        print(f"Running {name}...")
        models[name] = run_benchmark_backtest(
            returns,
            name,
            lookback_days=60 if args.smoke else 240,
            transaction_cost_bps=config["transaction_cost_bps"],
        )

    ordered = {name: models[name] for name in MODEL_ORDER if name in models}
    performance = pd.DataFrame([summarize(name, result, config) for name, result in ordered.items()])
    turnover = performance[["model", "avg_monthly_turnover", "annualized_turnover", "transaction_cost_drag", "turnover_adjusted_sharpe"]].copy()
    drawdowns = drawdown_table(ordered)
    performance.to_csv(tables / "benchmark_performance_summary.csv", index=False)
    turnover.to_csv(tables / "benchmark_turnover_summary.csv", index=False)
    drawdowns.to_csv(tables / "benchmark_drawdown_summary.csv", index=False)
    plot_navs(ordered, figures / "benchmark_nav_comparison.png")
    plot_drawdowns(ordered, figures / "benchmark_drawdown_comparison.png")
    print(f"Benchmark suite written to {args.output_root}")


if __name__ == "__main__":
    main()
