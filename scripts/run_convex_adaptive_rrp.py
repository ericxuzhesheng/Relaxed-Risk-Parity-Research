from __future__ import annotations

import os
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.asset_graph_features import graph_feature_frame
from src.backtest import run_static_backtest
from src.convex_adaptive_rrp import ConvexRRPConfig, run_convex_adaptive_backtest
from src.data_loader import load_data
from src.dynamic_selection import run_dynamic_rrp_selection
from src.hierarchical_risk_parity import solve_herc, solve_hrp
from src.metrics import calculate_metrics
from src.public_labels import public_model_label
from src.utils import get_config, resolve_path
from src.visualization import plot_drawdown_comparison, plot_nav_comparison


def ensure_output_dirs() -> None:
    for path in ["results/tables", "results/figures"]:
        os.makedirs(resolve_path(path), exist_ok=True)


def monthly_rebalance_dates(returns: pd.DataFrame) -> set[pd.Timestamp]:
    return set(returns.groupby(returns.index.to_period("M")).tail(1).index)


def nav_from_return(result: pd.DataFrame, return_col: str, eval_start_date: str) -> pd.Series:
    data = result[pd.to_datetime(result["date"]) >= pd.Timestamp(eval_start_date)].copy()
    nav = (1.0 + data[return_col].fillna(0.0)).cumprod()
    nav.index = pd.to_datetime(data["date"])
    return nav


def cvar(returns: pd.Series, beta: float = 0.95) -> float:
    losses = -pd.Series(returns).dropna()
    if losses.empty:
        return 0.0
    var = losses.quantile(beta)
    tail = losses[losses >= var]
    return float(tail.mean()) if not tail.empty else float(var)


def summarize_result(name: str, result: pd.DataFrame, eval_start_date: str, config: dict) -> dict:
    eval_result = result[pd.to_datetime(result["date"]) >= pd.Timestamp(eval_start_date)].copy()
    if "gross_return" not in result and "turnover" in result:
        result = result.copy()
        result["gross_return"] = result["portfolio_return"] + (config.get("transaction_cost_bps", 0.0) / 10000.0) * result["turnover"].fillna(0.0)
    if "net_return" not in result:
        result = result.copy()
        result["net_return"] = result["portfolio_return"]
    eval_result = result[pd.to_datetime(result["date"]) >= pd.Timestamp(eval_start_date)].copy()
    gross_nav = nav_from_return(result, "gross_return", eval_start_date)
    net_nav = nav_from_return(result, "net_return", eval_start_date)
    gross_metrics = calculate_metrics(gross_nav, config.get("risk_free_rate", 0.0), config["trading_days_per_year"])
    net_metrics = calculate_metrics(net_nav, config.get("risk_free_rate", 0.0), config["trading_days_per_year"])
    dates = pd.to_datetime(eval_result["date"])
    years = max((dates.max() - dates.min()).days / 365.25, 1.0 / 12.0)
    annualized_turnover = float(eval_result["turnover"].fillna(0.0).sum() / years)
    avg_monthly_turnover = float(eval_result["turnover"].fillna(0.0).sum() / max(len(dates.dt.to_period("M").unique()), 1))
    tc_drag = gross_metrics["annualized_return"] - net_metrics["annualized_return"]
    vol = net_metrics["annualized_volatility"]
    return {
        "model": name,
        "gross_annual_return": gross_metrics["annualized_return"],
        "net_annual_return": net_metrics["annualized_return"],
        "transaction_cost_drag": tc_drag,
        "annualized_volatility": net_metrics["annualized_volatility"],
        "sharpe_ratio": net_metrics["sharpe_ratio"],
        "turnover_adjusted_sharpe": (net_metrics["annualized_return"] / vol) if vol > 0 else 0.0,
        "sortino_ratio": net_metrics["sortino_ratio"],
        "max_drawdown": net_metrics["max_drawdown"],
        "calmar_ratio": net_metrics["calmar_ratio"],
        "total_return": net_metrics["total_return"],
        "avg_monthly_turnover": avg_monthly_turnover,
        "annualized_turnover": annualized_turnover,
        "cvar_95_daily_loss": cvar(eval_result["net_return"], 0.95),
    }


def run_hrp_like(returns: pd.DataFrame, model_type: str, transaction_cost_bps: float) -> pd.DataFrame:
    dates = returns.index
    rebalance_dates = monthly_rebalance_dates(returns)
    weights = np.ones(len(returns.columns)) / len(returns.columns)
    rows = []
    cost_rate = transaction_cost_bps / 10000.0
    for date in dates:
        turnover = 0.0
        if date in rebalance_dates:
            window = returns[returns.index < date].iloc[-240:]
            if len(window) >= 30:
                previous = weights.copy()
                if model_type == "hrp":
                    weights = solve_hrp(window).values
                else:
                    weights = solve_herc(window).values
                turnover = float(np.abs(weights - previous).sum())
        gross = float(np.dot(returns.loc[date].fillna(0.0).values, weights))
        cost = cost_rate * turnover
        row = {"date": date, "gross_return": gross, "net_return": gross - cost, "portfolio_return": gross - cost, "turnover": turnover}
        for i, asset in enumerate(returns.columns):
            row[f"weight_{asset}"] = weights[i]
        rows.append(row)
    return pd.DataFrame(rows)


def plot_transaction_cost(summary: pd.DataFrame, save_path: str) -> None:
    plot_df = summary.set_index("model")[["gross_annual_return", "net_annual_return"]]
    ax = plot_df.plot(kind="bar", figsize=(12, 6))
    ax.set_title("Gross vs Net Annual Return")
    ax.set_ylabel("Annual return")
    ax.grid(axis="y", alpha=0.3)
    plt.xticks(rotation=25, ha="right")
    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()


def plot_feature_timeline(df: pd.DataFrame, value_cols: list[str], title: str, save_path: str) -> None:
    plt.figure(figsize=(12, 5))
    if df.empty:
        plt.text(0.5, 0.5, "No diagnostics", ha="center", va="center")
        plt.axis("off")
    else:
        data = df.copy()
        data["date"] = pd.to_datetime(data["date"])
        for col in value_cols:
            if col in data:
                plt.plot(data["date"], data[col], label=col)
        plt.title(title)
        plt.legend()
        plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()


def write_readme(summary: pd.DataFrame, solver_diag: pd.DataFrame, eval_start_date: str) -> None:
    rows = []
    for _, row in summary.iterrows():
        rows.append(
            f"| {row['model']} | {row['gross_annual_return']:.2%} | {row['net_annual_return']:.2%} | "
            f"{row['transaction_cost_drag']:.2%} | {row['avg_monthly_turnover']:.3f} | "
            f"{row['turnover_adjusted_sharpe']:.2f} | {row['max_drawdown']:.2%} | {row['calmar_ratio']:.2f} |"
        )
    fallback_rate = float(solver_diag["fallback_used"].mean()) if not solver_diag.empty and "fallback_used" in solver_diag else 0.0
    lines = [
        "# Relaxed Risk Parity Framework | 宽松风险平价全球资产配置框架",
        "",
        "<a id=\"en\"></a>",
        "## English",
        "",
        "This repository studies Relaxed Risk Parity for global multi-asset allocation. The latest extension adds a convex adaptive layer with bounded graph diagnostics, transaction-cost-aware optimization, CVaR regularization, and stable online regime labels. Final portfolio weights are always produced by the optimization layer.",
        "",
        f"Evaluation starts on `{eval_start_date}`. Gross and net results are both shown so transaction costs are visible.",
        "",
        "| Model | Gross Return | Net Return | Cost Drag | Avg Monthly Turnover | Turnover-adjusted Sharpe | Max Drawdown | Calmar |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        *rows,
        "",
        "Key outputs:",
        "- `results/tables/convex_adaptive_performance_summary.csv`",
        "- `results/tables/convex_adaptive_transaction_cost_summary.csv`",
        "- `results/tables/asset_graph_diagnostics.csv`",
        "- `results/tables/online_regime_diagnostics.csv`",
        "- `results/tables/convex_adaptive_solver_diagnostics.csv`",
        "- `results/figures/convex_adaptive_nav_comparison.png`",
        "- `results/figures/convex_adaptive_transaction_cost_comparison.png`",
        "",
        f"Solver fallback rate in the latest convex run: `{fallback_rate:.1%}`. Fallback rows are explicitly flagged in solver diagnostics.",
        "",
        "Run:",
        "```bash",
        "pip install -r requirements.txt",
        "python -m pytest",
        "python scripts/run_convex_adaptive_rrp.py",
        "```",
        "",
        "<a id=\"zh\"></a>",
        "## 中文",
        "",
        "本项目研究宽松风险平价在全球多资产配置中的应用。最新扩展加入凸优化自适应层、轻量资产相关性图诊断、交易成本约束、CVaR 正则项和稳定在线风险状态标签。最终组合权重始终由优化层生成，图特征和状态标签只作为有界风险输入。",
        "",
        f"评估区间从 `{eval_start_date}` 开始。下表同时展示毛收益、净收益和交易成本拖累。",
        "",
        "| 模型 | 毛年化收益 | 净年化收益 | 成本拖累 | 月均换手 | 换手调整夏普 | 最大回撤 | Calmar |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        *rows,
        "",
        "主要输出保存在 `results/tables/` 和 `results/figures/`。本研究不构成投资建议，数据质量、滑点、流动性、税费和实盘可交易性需要独立复核。",
        "",
        "## License",
        "MIT License.",
    ]
    Path(resolve_path("README.md")).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ensure_output_dirs()
    config = get_config({"transaction_cost_bps": 3.0, "turnover_cap": 0.25, "target_vol": 0.060})
    eval_start_date = config.get("plot_start_date", "2021-01-01")
    returns = load_data(source="tushare", force_update=False).dropna(how="all")
    returns = returns.loc[:, returns.notna().mean() > 0.95].fillna(0.0)

    print("Running baseline Global Relaxed Risk Parity...")
    global_rrp = run_static_backtest(returns, model_type="relaxed", config_overrides=config)
    print("Running Defensive Dynamic Relaxed Risk Parity...")
    dynamic = run_dynamic_rrp_selection(
        returns,
        [{"lambda_pen": 0.10, "m": 1.9, "bond_leverage_upper": 1.4}, {"lambda_pen": 1.90, "m": 3.0, "bond_leverage_upper": 1.8}],
        train_window_months=24,
        selection_metric="utility",
        top_k=2,
        config_base=config,
    )
    print("Running HRP and HERC benchmarks...")
    hrp = run_hrp_like(returns, "hrp", config["transaction_cost_bps"])
    herc = run_hrp_like(returns, "herc", config["transaction_cost_bps"])

    base_convex = ConvexRRPConfig(transaction_cost_bps=config["transaction_cost_bps"], cvar_penalty=0.0)
    variants = [
        ("Convex Global Relaxed Risk Parity", base_convex),
        ("Turnover-Aware Convex Global RRP", ConvexRRPConfig(transaction_cost_bps=config["transaction_cost_bps"], turnover_penalty=0.08, turnover_cap=0.20)),
        ("CVaR-Aware Convex Global RRP", ConvexRRPConfig(transaction_cost_bps=config["transaction_cost_bps"], cvar_penalty=0.25)),
        ("Convex Adaptive Global Relaxed Risk Parity", ConvexRRPConfig(transaction_cost_bps=config["transaction_cost_bps"], budget_penalty=0.55)),
        ("Convex Adaptive Global RRP + Asset Graph Features", ConvexRRPConfig(transaction_cost_bps=config["transaction_cost_bps"], budget_penalty=0.55, use_graph_features=True)),
        ("Convex Adaptive Global RRP + Transaction-Cost-Aware Objective", ConvexRRPConfig(transaction_cost_bps=config["transaction_cost_bps"], budget_penalty=0.55, use_transaction_cost_objective=True, turnover_penalty=0.08, turnover_cap=0.20)),
        ("Convex Adaptive Global RRP + Graph + Transaction Cost + Stable Online Regime", ConvexRRPConfig(transaction_cost_bps=config["transaction_cost_bps"], budget_penalty=0.60, use_graph_features=True, use_transaction_cost_objective=True, use_online_regime=True, turnover_penalty=0.08, turnover_cap=0.20, cvar_penalty=0.15)),
    ]

    models: dict[str, pd.DataFrame] = {
        "Global Relaxed Risk Parity": global_rrp,
        "Defensive Dynamic Relaxed Risk Parity": dynamic,
        "HRP Benchmark": hrp,
        "HERC Benchmark": herc,
    }
    solver_diags = []
    graph_diags = []
    regime_diags = []
    for name, cfg in variants:
        print(f"Running {name}...")
        result, solver_diag, graph_diag, regime_diag = run_convex_adaptive_backtest(returns, cfg)
        models[name] = result
        if not solver_diag.empty:
            solver_diag.insert(0, "model", name)
            solver_diags.append(solver_diag)
        if not graph_diag.empty:
            graph_diag.insert(0, "model", name)
            graph_diags.append(graph_diag)
        if not regime_diag.empty:
            regime_diag.insert(0, "model", name)
            regime_diags.append(regime_diag)
        result.to_csv(resolve_path(f"results/tables/{name.lower().replace(' ', '_').replace('+', 'plus')}_returns.csv"), index=False)

    summary = pd.DataFrame([summarize_result(name, result, eval_start_date, config) for name, result in models.items() if not result.empty])
    summary.to_csv(resolve_path("results/tables/convex_adaptive_performance_summary.csv"), index=False)
    tc_summary = summary[
        [
            "model",
            "gross_annual_return",
            "net_annual_return",
            "transaction_cost_drag",
            "avg_monthly_turnover",
            "annualized_turnover",
            "turnover_adjusted_sharpe",
        ]
    ].copy()
    tc_summary.to_csv(resolve_path("results/tables/convex_adaptive_transaction_cost_summary.csv"), index=False)

    solver_diag_df = pd.concat(solver_diags, ignore_index=True) if solver_diags else pd.DataFrame()
    solver_diag_df.to_csv(resolve_path("results/tables/convex_adaptive_solver_diagnostics.csv"), index=False)
    graph_diag_df = pd.concat(graph_diags, ignore_index=True) if graph_diags else graph_feature_frame(returns, monthly_rebalance_dates(returns), 240)
    graph_diag_df.to_csv(resolve_path("results/tables/asset_graph_diagnostics.csv"), index=False)
    regime_diag_df = pd.concat(regime_diags, ignore_index=True) if regime_diags else pd.DataFrame()
    regime_diag_df.to_csv(resolve_path("results/tables/online_regime_diagnostics.csv"), index=False)

    nav_dict = {name: nav_from_return(result, "net_return" if "net_return" in result else "portfolio_return", eval_start_date) for name, result in models.items() if not result.empty}
    plot_nav_comparison(nav_dict, f"Convex Adaptive RRP NAV since {eval_start_date}", resolve_path("results/figures/convex_adaptive_nav_comparison.png"))
    plot_drawdown_comparison(nav_dict, f"Convex Adaptive RRP Drawdown since {eval_start_date}", resolve_path("results/figures/convex_adaptive_drawdown_comparison.png"))
    plot_transaction_cost(tc_summary, resolve_path("results/figures/convex_adaptive_transaction_cost_comparison.png"))
    plot_feature_timeline(graph_diag_df, ["correlation_stress_score", "avg_abs_corr", "largest_cluster_size_ratio"], "Asset Graph Stress Timeline", resolve_path("results/figures/asset_graph_stress_timeline.png"))
    plot_feature_timeline(regime_diag_df, ["raw_stress_score", "smoothed_stress_score"], "Online Regime Timeline", resolve_path("results/figures/online_regime_timeline.png"))
    write_readme(summary, solver_diag_df, eval_start_date)

    print("\nConvex Adaptive Summary:")
    print(summary[["model", "net_annual_return", "sharpe_ratio", "max_drawdown", "calmar_ratio", "cvar_95_daily_loss", "turnover_adjusted_sharpe"]])
    print("Pipeline completed successfully.")


if __name__ == "__main__":
    main()
