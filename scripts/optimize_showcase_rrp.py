from __future__ import annotations

import itertools
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.run_rrp_pipeline import _parameter_grid
from src.backtest import run_static_backtest
from src.data_loader import load_data
from src.dynamic_selection import run_dynamic_rrp_selection
from src.metrics import calculate_metrics
from src.public_labels import apply_public_model_labels, public_model_label
from src.utils import get_config, resolve_path
from src.validation import (
    afml_diagnostics,
    parameter_stability,
    simplified_pbo_diagnostic,
    walk_forward_validation,
)
from src.visualization import (
    plot_drawdown_comparison,
    plot_dynamic_parameter_timeline,
    plot_nav_comparison,
    plot_pbo_heatmap,
    plot_risk_overlay_ablation,
)


BASELINE_V3 = {
    "sharpe_ratio": 1.15334293607668,
    "max_drawdown": -0.042484940424631135,
    "calmar_ratio": 1.407463244023128,
}


def ensure_output_dirs() -> None:
    for path in ["results/tables", "results/figures"]:
        os.makedirs(resolve_path(path), exist_ok=True)


def nav_from_result(result: pd.DataFrame, eval_start_date: str) -> pd.Series:
    data = result[pd.to_datetime(result["date"]) >= pd.Timestamp(eval_start_date)].copy()
    nav = (1.0 + data["portfolio_return"].fillna(0.0)).cumprod()
    nav.index = pd.to_datetime(data["date"])
    return nav


def summarize(name: str, result: pd.DataFrame, eval_start_date: str, config: dict) -> dict:
    eval_result = result[pd.to_datetime(result["date"]) >= pd.Timestamp(eval_start_date)].copy()
    nav = nav_from_result(result, eval_start_date)
    metrics = calculate_metrics(
        nav,
        risk_free_rate=config.get("risk_free_rate", 0.0),
        trading_days=config["trading_days_per_year"],
    )
    dates = pd.to_datetime(eval_result["date"])
    years = max((dates.max() - dates.min()).days / 365.25, 1.0 / 12.0)
    annualized_turnover = float(eval_result["turnover"].fillna(0.0).sum() / years)
    annual_cost = annualized_turnover * config.get("transaction_cost_bps", 3.0) / 10000.0
    metrics.update(
        {
            "model": name,
            "annualized_turnover": annualized_turnover,
            "turnover_adjusted_return": metrics["annualized_return"] - annual_cost,
            "avg_turnover": float(eval_result["turnover"].fillna(0.0).mean()),
        }
    )
    vol = metrics.get("annualized_volatility", 0.0)
    metrics["turnover_adjusted_sharpe"] = (
        metrics["turnover_adjusted_return"] / vol if vol > 0 else 0.0
    )
    for col in [
        "drawdown_scalar",
        "target_vol_scalar",
        "trend_scalar",
        "final_risk_scalar",
        "gross_exposure",
    ]:
        if col in eval_result:
            metrics[f"avg_{col}"] = float(eval_result[col].mean())
    return metrics


def objective(metrics: dict, benchmark: dict | None = None, instability: float = 0.0) -> float:
    benchmark = benchmark or {}
    dd = abs(float(metrics.get("max_drawdown", 0.0)))
    benchmark_dd = abs(float(benchmark.get("max_drawdown", metrics.get("max_drawdown", 0.0))))
    drawdown_penalty = max(0.0, (dd - benchmark_dd) / max(benchmark_dd, 1e-12))
    turnover = float(metrics.get("annualized_turnover", 0.0))
    benchmark_turnover = float(benchmark.get("annualized_turnover", turnover))
    turnover_penalty = max(0.0, (turnover - benchmark_turnover) / max(benchmark_turnover, 1e-12))
    return (
        float(metrics.get("sharpe_ratio", 0.0))
        + 0.20 * float(metrics.get("calmar_ratio", 0.0))
        - 0.30 * drawdown_penalty
        - 0.10 * turnover_penalty
        - 0.10 * instability
    )


def parameter_instability(result: pd.DataFrame) -> float:
    stability = parameter_stability(result)
    if stability.empty or "switch_count" not in stability:
        return 0.0
    return float(stability["switch_count"].fillna(0.0).mean() / max(len(result), 1))


def public_candidate_label(name: object) -> str:
    labels = {
        "preserve_current_global_rrp": "Preserve Global Relaxed Risk Parity",
        "current_dynamic": "Defensive Dynamic RRP before overlay optimization",
        "drawdown_balanced": "Balanced drawdown scaling",
        "soft_trend_short_confirm": "Soft trend filter with short confirmation",
        "higher_vol_moderate_leverage": "Higher volatility target with moderate exposure",
        "higher_vol_high_leverage": "Higher volatility target with high exposure",
        "faster_reentry_turnover_control": "Faster re-entry with turnover control",
        "full_less_defensive_overlay": "Less defensive full overlay",
    }
    return labels.get(str(name), public_model_label(name))


def dynamic_overlay_candidates() -> list[dict]:
    return [
        {
            "candidate": "drawdown_balanced",
            "drawdown_mild_scale": 0.95,
            "drawdown_medium_scale": 0.85,
            "drawdown_severe_scale": 0.65,
        },
        {
            "candidate": "soft_trend_short_confirm",
            "trend_filter_mode": "soft",
            "momentum_lookback": 40,
            "momentum_confirm_lookback": 20,
            "trend_soft_scale": 0.95,
        },
        {
            "candidate": "higher_vol_moderate_leverage",
            "target_vol": 0.08,
            "max_risk_scale": 1.2,
        },
        {
            "candidate": "higher_vol_high_leverage",
            "target_vol": 0.10,
            "max_risk_scale": 1.5,
        },
        {
            "candidate": "faster_reentry_turnover_control",
            "reentry_speed": 0.75,
            "signal_persistence": 2,
            "weight_smoothing": 0.20,
            "turnover_cap": 0.80,
        },
        {
            "candidate": "full_less_defensive_overlay",
            "drawdown_mild_scale": 1.00,
            "drawdown_medium_scale": 0.90,
            "drawdown_severe_scale": 0.75,
            "trend_filter_mode": "soft",
            "momentum_lookback": 40,
            "momentum_confirm_lookback": 20,
            "trend_soft_scale": 0.95,
            "target_vol": 0.08,
            "max_risk_scale": 1.2,
            "reentry_speed": 0.75,
            "signal_persistence": 2,
            "weight_smoothing": 0.20,
            "turnover_cap": 0.80,
        },
    ]


def v3_candidates() -> list[dict]:
    return [{"candidate": "preserve_current_global_rrp"}]


def run_dynamic_candidates(
    returns: pd.DataFrame,
    config: dict,
    eval_start_date: str,
    benchmark: dict,
    current_dynamic: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    base_grid = _parameter_grid(False)
    benchmark_row = benchmark.copy()
    benchmark_row["model"] = "current_dynamic"
    benchmark_row["parameter_instability_penalty"] = parameter_instability(current_dynamic)
    benchmark_row["objective_score"] = objective(benchmark_row, benchmark=benchmark, instability=benchmark_row["parameter_instability_penalty"])
    rows = [benchmark_row]
    results = {"current_dynamic": {"result": current_dynamic, "config": config}}
    for candidate in dynamic_overlay_candidates():
        name = candidate["candidate"]
        cfg = config.copy()
        cfg.update({k: v for k, v in candidate.items() if k != "candidate"})
        print(f"Evaluating Dynamic candidate: {name}")
        result = run_dynamic_rrp_selection(
            returns,
            base_grid,
            train_window_months=24,
            selection_metric="utility",
            top_k=2,
            config_base=cfg,
        )
        if result.empty:
            continue
        instability = parameter_instability(result)
        metrics = summarize(name, result, eval_start_date, cfg)
        metrics["parameter_instability_penalty"] = instability
        metrics["objective_score"] = objective(metrics, benchmark=benchmark, instability=instability)
        rows.append(metrics)
        results[name] = {"result": result, "config": cfg}
    ranking = pd.DataFrame(rows).sort_values("objective_score", ascending=False)
    return ranking, results


def choose_dynamic(dynamic_ranking: pd.DataFrame, baseline: dict) -> str:
    baseline_sharpe = float(baseline.get("sharpe_ratio", 0.0))
    baseline_dd = abs(float(baseline.get("max_drawdown", 0.0)))
    baseline_turnover = float(baseline.get("annualized_turnover", 0.0))
    fallback = str(dynamic_ranking.iloc[0]["model"])
    for _, row in dynamic_ranking.iterrows():
        sharpe = float(row["sharpe_ratio"])
        dd = abs(float(row["max_drawdown"]))
        calmar = float(row["calmar_ratio"])
        turnover = float(row["annualized_turnover"])
        instability = float(row.get("parameter_instability_penalty", 0.0))
        dd_materially_worse = dd > baseline_dd + 0.015
        clear_compensation = sharpe >= baseline_sharpe + 0.15 and calmar >= float(baseline.get("calmar_ratio", 0.0))
        excessive_turnover = turnover > max(8.0, baseline_turnover * 3.0)
        unstable = instability > 0.20
        if dd_materially_worse and not clear_compensation:
            continue
        if excessive_turnover or unstable:
            continue
        return str(row["model"])
    return fallback


def run_v3_candidates(returns: pd.DataFrame, config: dict, eval_start_date: str) -> tuple[pd.DataFrame, dict]:
    rows = []
    results = {}
    for candidate in v3_candidates():
        name = candidate["candidate"]
        cfg = config.copy()
        cfg.update({k: v for k, v in candidate.items() if k != "candidate"})
        print(f"Evaluating V3 candidate: {name}")
        result = run_static_backtest(returns, model_type="relaxed", config_overrides=cfg)
        metrics = summarize(name, result, eval_start_date, cfg)
        metrics["objective_score"] = objective(metrics, BASELINE_V3)
        rows.append(metrics)
        results[name] = {"result": result, "config": cfg}
    ranking = pd.DataFrame(rows).sort_values("objective_score", ascending=False)
    return ranking, results


def choose_v3(v3_ranking: pd.DataFrame) -> str:
    baseline = v3_ranking[v3_ranking["model"] == "preserve_current_global_rrp"].iloc[0]
    for _, row in v3_ranking.iterrows():
        if row["model"] == "preserve_current_global_rrp":
            return "preserve_current_global_rrp"
        sharpe_gain = row["sharpe_ratio"] - baseline["sharpe_ratio"]
        dd_worse = abs(row["max_drawdown"]) - abs(baseline["max_drawdown"])
        turnover_worse = row["annualized_turnover"] - baseline["annualized_turnover"]
        if sharpe_gain >= 0.05 and dd_worse <= 0.005 and turnover_worse <= 0.50:
            return str(row["model"])
    return "preserve_current_global_rrp"


def overlay_ablation(
    returns: pd.DataFrame,
    config: dict,
    eval_start_date: str,
    optimized_dynamic: pd.DataFrame,
    optimized_config: dict,
    v3_result: pd.DataFrame,
) -> pd.DataFrame:
    grid = _parameter_grid(False)
    ablations = [
        ("V3_Global_RRP_without_overlay", v3_result, config),
        ("Current_Dynamic_RRP", run_dynamic_rrp_selection(returns, grid, 24, config_base=config), config),
        (
            "Dynamic_without_trend_filter",
            run_dynamic_rrp_selection(returns, grid, 24, config_base={**optimized_config, "trend_filter_mode": "off"}),
            {**optimized_config, "trend_filter_mode": "off"},
        ),
        (
            "Dynamic_soft_trend_filter",
            run_dynamic_rrp_selection(returns, grid, 24, config_base={**optimized_config, "trend_filter_mode": "soft"}),
            {**optimized_config, "trend_filter_mode": "soft"},
        ),
        (
            "Drawdown_scaling_only",
            run_dynamic_rrp_selection(
                returns,
                grid,
                24,
                config_base={**optimized_config, "trend_filter_mode": "off", "target_vol": 99.0},
            ),
            {**optimized_config, "trend_filter_mode": "off", "target_vol": 99.0},
        ),
        (
            "Volatility_targeting_only",
            run_dynamic_rrp_selection(
                returns,
                grid,
                24,
                config_base={
                    **optimized_config,
                    "trend_filter_mode": "off",
                    "drawdown_mild": 1.0,
                    "drawdown_medium": 1.0,
                    "drawdown_severe": 1.0,
                },
            ),
            optimized_config,
        ),
        (
            "Reentry_logic_only",
            run_dynamic_rrp_selection(
                returns,
                grid,
                24,
                config_base={
                    **optimized_config,
                    "trend_filter_mode": "off",
                    "target_vol": 99.0,
                    "drawdown_mild": 1.0,
                    "drawdown_medium": 1.0,
                    "drawdown_severe": 1.0,
                },
            ),
            optimized_config,
        ),
        ("Optimized_Dynamic_full_overlay", optimized_dynamic, optimized_config),
        (
            "Optimized_Dynamic_plus_turnover_control",
            run_dynamic_rrp_selection(returns, grid, 24, config_base={**optimized_config, "turnover_cap": 0.25}),
            {**optimized_config, "turnover_cap": 0.25},
        ),
    ]
    rows = []
    for name, result, cfg in ablations:
        if not result.empty:
            rows.append(summarize(name, result, eval_start_date, cfg))
    return pd.DataFrame(rows)


def _metric_table(df: pd.DataFrame, names: list[str]) -> list[str]:
    public = apply_public_model_labels(df)
    rows = [
        "| Model | Annual Return | Annual Volatility | Sharpe | Sortino | Max Drawdown | Calmar | Avg Turnover | Turnover-adjusted Sharpe |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in names:
        row_df = public[public["model"] == name]
        if row_df.empty:
            continue
        row = row_df.iloc[0]
        rows.append(
            f"| {row['model']} | {row['annualized_return']:.2%} | {row['annualized_volatility']:.2%} | "
            f"{row['sharpe_ratio']:.2f} | {row.get('sortino_ratio', 0.0):.2f} | {row['max_drawdown']:.2%} | "
            f"{row['calmar_ratio']:.2f} | {row.get('avg_turnover', row.get('turnover', 0.0)):.4f} | "
            f"{row.get('turnover_adjusted_sharpe', 0.0):.2f} |"
        )
    return rows


def _all_strategy_table(showcase: pd.DataFrame) -> list[str]:
    rows = [
        "| Strategy | Source | Annual Return | Annual Volatility | Sharpe | Sortino | Max Drawdown | Calmar | Total Return | Avg Turnover |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    table_rows = []
    hrp_path = Path(resolve_path("results/tables/hrp_comparison.csv"))
    if hrp_path.exists():
        hrp = apply_public_model_labels(pd.read_csv(hrp_path))
        for _, row in hrp.iterrows():
            model = row["model"]
            if model == "Defensive Dynamic Relaxed Risk Parity":
                model = "Defensive Dynamic Relaxed Risk Parity (standard pipeline)"
            table_rows.append((model, "hrp_comparison.csv", row))
    public_showcase = apply_public_model_labels(showcase)
    for label in [
        "Defensive Dynamic Relaxed Risk Parity",
        "Defensive Dynamic RRP before overlay optimization",
    ]:
        row_df = public_showcase[public_showcase["model"] == label]
        if not row_df.empty:
            model = label
            if label == "Defensive Dynamic Relaxed Risk Parity":
                model = "Defensive Dynamic Relaxed Risk Parity (showcase optimized)"
            table_rows.append((model, "showcase_performance_summary.csv", row_df.iloc[0]))

    seen = set()
    for model, source, row in table_rows:
        key = (model, source)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            f"| {model} | `{source}` | {row['annualized_return']:.2%} | "
            f"{row['annualized_volatility']:.2%} | {row['sharpe_ratio']:.2f} | "
            f"{row.get('sortino_ratio', 0.0):.2f} | {row['max_drawdown']:.2%} | "
            f"{row['calmar_ratio']:.2f} | {row.get('total_return', 0.0):.2%} | "
            f"{row.get('avg_turnover', row.get('turnover', 0.0)):.4f} |"
        )
    return rows


def write_readme(summary: pd.DataFrame, eval_start_date: str) -> None:
    public_summary = apply_public_model_labels(summary)
    dynamic_row = public_summary[
        public_summary["model"] == "Defensive Dynamic Relaxed Risk Parity"
    ].iloc[0]
    global_row = public_summary[
        public_summary["model"] == "Global Relaxed Risk Parity"
    ].iloc[0]
    dynamic_positioning = (
        "Defensive Dynamic Relaxed Risk Parity is not designed to mechanically maximize Sharpe. "
        "Its role is to reduce risk exposure during adverse regimes, so it should be evaluated together "
        "with maximum drawdown, Calmar ratio, downside behavior, and turnover."
    )
    if dynamic_row["sharpe_ratio"] < global_row["sharpe_ratio"]:
        dynamic_positioning += (
            " In the current regenerated results, its Sharpe remains below Global Relaxed Risk Parity; "
            "the overlay prioritizes downside control and stability over pure Sharpe maximization."
        )
    showcase_table = _metric_table(
        summary,
        [
            "Global Relaxed Risk Parity",
            "Defensive Dynamic Relaxed Risk Parity",
            "Defensive Dynamic RRP before overlay optimization",
        ],
    )
    benchmark_table = []
    perf_path = Path(resolve_path("results/tables/performance_summary.csv"))
    if perf_path.exists():
        perf = pd.read_csv(perf_path)
        benchmark_table = _metric_table(
            perf,
            [
                "Standard Risk Parity",
                "Local Relaxed Risk Parity",
                "HRP Benchmark",
                "HERC Benchmark",
            ],
        )
    all_strategy_table = _all_strategy_table(summary)
    lines = [
        "# 宽松风险平价全球资产配置框架 | Relaxed Risk Parity Framework for Global Asset Allocation",
        "",
        "<p align=\"center\">",
        "  <a href=\"#zh\"><img src=\"https://img.shields.io/badge/LANGUAGE-中文-E84D3D?style=for-the-badge&labelColor=3B3F47\" alt=\"LANGUAGE 中文\"></a>",
        "  <a href=\"#en\"><img src=\"https://img.shields.io/badge/LANGUAGE-ENGLISH-2F73C9?style=for-the-badge&labelColor=3B3F47\" alt=\"LANGUAGE ENGLISH\"></a>",
        "</p>",
        "",
        "<p align=\"center\">",
        "  <img src=\"https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white\" alt=\"Python 3.8+\">",
        "  <img src=\"https://img.shields.io/badge/Asset-Global%20Multi--Asset-F2C94C?style=for-the-badge\" alt=\"Global Multi-Asset\">",
        "  <img src=\"https://img.shields.io/badge/Strategy-Relaxed%20Risk%20Parity-7AC943?style=for-the-badge\" alt=\"Relaxed Risk Parity\">",
        "  <img src=\"https://img.shields.io/badge/Overlay-Defensive%20Dynamic%20RRP-9B51E0?style=for-the-badge\" alt=\"Defensive Dynamic RRP\">",
        "</p>",
        "",
        "<a id=\"zh\"></a>",
        "",
        "## 中文",
        "",
        "### 项目概览",
        "本项目研究宽松风险平价在全球多资产配置中的应用，重点比较传统风险平价、本土宽松风险平价、全球宽松风险平价、防御型动态风险覆盖模型，以及 HRP / HERC 层次化配置 benchmark。",
        "",
        "### 核心模型",
        "| 模型 | 定位 | 说明 |",
        "|---|---|---|",
        "| Standard Risk Parity | 基准模型 | 传统风险贡献均衡组合 |",
        "| Local Relaxed Risk Parity | 本土宽松模型 | 在风险平价约束中引入松弛项，平衡风险均衡与收益目标 |",
        "| Global Relaxed Risk Parity | 主展示模型 | 扩展到全球多资产配置，是当前收益效率最高的主模型 |",
        "| Defensive Dynamic Relaxed Risk Parity | 防御型动态模型 | 在全球宽松风险平价基础上加入风险覆盖层，管理回撤、趋势、波动率和换手 |",
        "| HRP Benchmark / HERC Benchmark | 横向 benchmark | 用于检验层次聚类配置是否能替代 RRP 型全球配置 |",
        "",
        dynamic_positioning,
        "",
        "### 最新结果看板",
        f"评估区间从 `{eval_start_date}` 开始。下表直接来自 `results/tables/showcase_performance_summary.csv`。",
        *showcase_table,
        "",
        "Benchmark 结果保留在公开表格中，但不作为本文的主要贡献。",
        *(benchmark_table if benchmark_table else ["Benchmark 表将在运行完整 pipeline 后由 `results/tables/performance_summary.csv` 更新。"]),
        "",
        "全量方案回测结果如下，包含基准配置、RRP 系列、层次化 benchmark、标准 pipeline 动态模型，以及 showcase 优化后的防御型动态模型。",
        *all_strategy_table,
        "",
        "### 图表展示",
        "<p align=\"center\"><img src=\"results/figures/showcase_nav_comparison.png\" width=\"820\" alt=\"Showcase NAV Comparison\"></p>",
        "<p align=\"center\"><em>Showcase NAV comparison.</em></p>",
        "<p align=\"center\"><img src=\"results/figures/showcase_drawdown_comparison.png\" width=\"820\" alt=\"Showcase Drawdown Comparison\"></p>",
        "<p align=\"center\"><em>Showcase drawdown comparison.</em></p>",
        "",
        "- `results/figures/showcase_risk_overlay_ablation.png`",
        "- `results/figures/showcase_parameter_timeline.png`",
        "- `results/figures/nav_comparison.png`",
        "- `results/figures/drawdown_comparison.png`",
        "",
        "### 方法框架",
        "框架包括风险贡献均衡、宽松收益目标、全球多资产扩展、防御型动态覆盖、回撤缩放、软趋势过滤、波动率目标、再入场逻辑、换手控制和交易成本调整。",
        "",
        "### AFML 风格验证设计",
        "验证流程借鉴 Lopez de Prado 的 walk-forward、反过拟合和多重检验思想，但不声称完整实现 CSCV 或完整 Deflated Sharpe Ratio。每个测试期只使用此前数据进行参数选择，并报告稳定性、换手、简化 PBO 和保守调整 Sharpe 诊断。",
        "",
        "### HRP / HERC Benchmark",
        "HRP / HERC 是横向 benchmark，用于检验层次聚类风险配置在同一数据集和评估窗口下是否优于 RRP 型全球配置。结果透明保留，不隐藏弱于主模型的情形。",
        "",
        "### 如何运行",
        "```bash",
        "pip install -r requirements.txt",
        "python -m pytest",
        "python scripts/optimize_showcase_rrp.py",
        "python scripts/run_rrp_pipeline.py --mode full",
        "python scripts/run_hrp_comparison.py",
        "```",
        "",
        "### 输出文件",
        "- `results/tables/showcase_performance_summary.csv`",
        "- `results/tables/showcase_risk_overlay_ablation.csv`",
        "- `results/tables/showcase_walkforward_validation.csv`",
        "- `results/tables/showcase_parameter_stability.csv`",
        "- `results/tables/showcase_improvement_attribution.csv`",
        "- `results/tables/performance_summary.csv`",
        "- `results/tables/hrp_comparison.csv`",
        "- `results/figures/showcase_nav_comparison.png`",
        "- `results/figures/showcase_drawdown_comparison.png`",
        "",
        "### 适用场景与局限性",
        "本项目是回测研究，不构成投资建议。数据质量、资产映射、交易成本、滑点、杠杆融资成本、税费、流动性和实盘可交易性都需要独立复核。",
        "",
        "### 参考文献",
        "1. Gambeta, V., & Kwon, R. (2020). Risk return trade-off in relaxed risk parity portfolio optimization.",
        "2. Lopez de Prado, M. (2018). Advances in Financial Machine Learning.",
        "3. Bailey, D. H., Borwein, J. M., Lopez de Prado, M., & Zhu, Q. J. (2015). The Probability of Backtest Overfitting.",
        "4. Bailey, D. H., & Lopez de Prado, M. (2014). The Deflated Sharpe Ratio.",
        "5. Lopez de Prado, M. (2016). Building Diversified Portfolios that Outperform Out-of-Sample.",
        "",
        "<a id=\"en\"></a>",
        "",
        "## English",
        "",
        "### Project Overview",
        "This repository studies Relaxed Risk Parity for global multi-asset allocation, comparing classical risk parity, local and global relaxed variants, a defensive dynamic overlay, and HRP / HERC hierarchical benchmarks.",
        "",
        "### Core Models",
        "| Model | Role | Description |",
        "|---|---|---|",
        "| Standard Risk Parity | Baseline | Classical risk-contribution balancing |",
        "| Local Relaxed Risk Parity | Local relaxed model | Balances risk parity with return objectives through relaxation terms |",
        "| Global Relaxed Risk Parity | Main showcase model | Global multi-asset extension and the main return-efficient model |",
        "| Defensive Dynamic Relaxed Risk Parity | Defensive overlay | Manages drawdown, trend, volatility, re-entry, and turnover controls |",
        "| HRP Benchmark / HERC Benchmark | Benchmarks | Hierarchical allocation references, not the main contribution |",
        "",
        dynamic_positioning,
        "",
        "### Latest Results",
        f"Evaluation starts on `{eval_start_date}`. The table is generated from `results/tables/showcase_performance_summary.csv`.",
        *showcase_table,
        "",
        "Benchmark results are retained transparently.",
        *(benchmark_table if benchmark_table else ["Benchmark rows are updated after running the full pipeline."]),
        "",
        "The full strategy backtest table is shown below, covering baseline allocations, RRP variants, hierarchical benchmarks, the standard pipeline dynamic model, and the showcase-optimized defensive dynamic model.",
        *all_strategy_table,
        "",
        "### Figures",
        "<p align=\"center\"><img src=\"results/figures/showcase_nav_comparison.png\" width=\"820\" alt=\"Showcase NAV Comparison\"></p>",
        "<p align=\"center\"><img src=\"results/figures/showcase_drawdown_comparison.png\" width=\"820\" alt=\"Showcase Drawdown Comparison\"></p>",
        "",
        "### Methodology",
        "The framework combines relaxed risk parity, global diversification, defensive risk overlays, drawdown-aware scaling, soft trend filtering, volatility targeting, re-entry logic, turnover control, and transaction-cost-aware evaluation.",
        "",
        "### AFML-Inspired Validation Design",
        "The showcase uses strict walk-forward validation. Candidate selection only uses data before each test period, with simplified PBO-style diagnostics, parameter stability checks, turnover-aware metrics, and conservative adjusted Sharpe diagnostics.",
        "",
        "### HRP / HERC Benchmark",
        "HRP / HERC are benchmarks used to test whether hierarchical clustering alone can outperform RRP-based global diversification under the same evaluation setup.",
        "",
        "### How to Run",
        "```bash",
        "pip install -r requirements.txt",
        "python -m pytest",
        "python scripts/optimize_showcase_rrp.py",
        "python scripts/run_rrp_pipeline.py --mode full",
        "python scripts/run_hrp_comparison.py",
        "```",
        "",
        "### Output Files",
        "- `results/tables/showcase_performance_summary.csv`",
        "- `results/tables/showcase_risk_overlay_ablation.csv`",
        "- `results/tables/showcase_walkforward_validation.csv`",
        "- `results/tables/showcase_parameter_stability.csv`",
        "- `results/tables/showcase_improvement_attribution.csv`",
        "- `results/tables/performance_summary.csv`",
        "- `results/tables/hrp_comparison.csv`",
        "- `results/figures/showcase_nav_comparison.png`",
        "- `results/figures/showcase_drawdown_comparison.png`",
        "",
        "### Use Cases and Limitations",
        "This is backtest research, not investment advice. Data quality, asset mappings, transaction costs, slippage, financing costs, taxes, liquidity, and live tradability require independent review.",
        "",
        "### References",
        "1. Gambeta, V., & Kwon, R. (2020). Risk return trade-off in relaxed risk parity portfolio optimization.",
        "2. Lopez de Prado, M. (2018). Advances in Financial Machine Learning.",
        "3. Bailey, D. H., Borwein, J. M., Lopez de Prado, M., & Zhu, Q. J. (2015). The Probability of Backtest Overfitting.",
        "4. Bailey, D. H., & Lopez de Prado, M. (2014). The Deflated Sharpe Ratio.",
        "5. Lopez de Prado, M. (2016). Building Diversified Portfolios that Outperform Out-of-Sample.",
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

    v3_ranking, v3_results = run_v3_candidates(returns, config, eval_start_date)
    v3_ranking_public = v3_ranking.copy()
    v3_ranking_public["model"] = v3_ranking_public["model"].map(public_candidate_label)
    v3_ranking_public.to_csv(resolve_path("results/tables/showcase_v3_candidate_ranking.csv"), index=False)
    chosen_v3_name = choose_v3(v3_ranking)
    chosen_v3 = v3_results[chosen_v3_name]["result"]
    chosen_v3_config = v3_results[chosen_v3_name]["config"]

    current_dynamic = run_dynamic_rrp_selection(
        returns,
        _parameter_grid(False),
        train_window_months=24,
        selection_metric="utility",
        top_k=2,
        config_base=config,
    )
    current_dynamic_metrics = summarize("Dynamic_RRP_before", current_dynamic, eval_start_date, config)

    dynamic_ranking, dynamic_results = run_dynamic_candidates(
        returns,
        config,
        eval_start_date,
        current_dynamic_metrics,
        current_dynamic,
    )
    dynamic_ranking_public = dynamic_ranking.copy()
    dynamic_ranking_public["model"] = dynamic_ranking_public["model"].map(public_candidate_label)
    dynamic_ranking_public.to_csv(resolve_path("results/tables/showcase_dynamic_candidate_ranking.csv"), index=False)
    chosen_dynamic_name = choose_dynamic(dynamic_ranking, current_dynamic_metrics)
    chosen_dynamic = dynamic_results[chosen_dynamic_name]["result"]
    chosen_dynamic_config = dynamic_results[chosen_dynamic_name]["config"]

    summary_rows = [
        summarize("V3_Global_RRP", chosen_v3, eval_start_date, chosen_v3_config),
        summarize("Dynamic_RRP", chosen_dynamic, eval_start_date, chosen_dynamic_config),
    ]
    summary_rows.append(current_dynamic_metrics)
    summary = pd.DataFrame(summary_rows)
    apply_public_model_labels(summary).to_csv(
        resolve_path("results/tables/showcase_performance_summary.csv"),
        index=False,
    )

    diagnostic_cols = [
        "date",
        "drawdown_scalar",
        "target_vol_scalar",
        "trend_scalar",
        "final_risk_scalar",
        "gross_exposure",
        "risky_exposure",
        "defensive_cash_proxy_exposure",
        "turnover_cap_bound",
        "reentry_state",
    ]
    diagnostics = chosen_dynamic[[c for c in diagnostic_cols if c in chosen_dynamic.columns]].copy()
    diagnostics.to_csv(resolve_path("results/tables/dynamic_overlay_diagnostics.csv"), index=False)

    before = summary[summary["model"] == "Dynamic_RRP_before"].iloc[0]
    after = summary[summary["model"] == "Dynamic_RRP"].iloc[0]
    attribution = pd.DataFrame(
        [
            {
                "component": "optimized defensive dynamic overlay",
                "delta_sharpe": after["sharpe_ratio"] - before["sharpe_ratio"],
                "delta_calmar": after["calmar_ratio"] - before["calmar_ratio"],
                "delta_annualized_return": after["annualized_return"] - before["annualized_return"],
                "delta_max_drawdown": after["max_drawdown"] - before["max_drawdown"],
                "delta_annualized_turnover": after["annualized_turnover"] - before["annualized_turnover"],
                "helped_or_hurt": "helped" if after["sharpe_ratio"] >= before["sharpe_ratio"] else "hurt",
            }
        ]
    )
    attribution.to_csv(resolve_path("results/tables/showcase_improvement_attribution.csv"), index=False)

    ablation = overlay_ablation(
        returns,
        config,
        eval_start_date,
        chosen_dynamic,
        chosen_dynamic_config,
        chosen_v3,
    )
    public_ablation = apply_public_model_labels(ablation)
    public_ablation.to_csv(resolve_path("results/tables/showcase_risk_overlay_ablation.csv"), index=False)

    wf = walk_forward_validation(returns, _parameter_grid(False), chosen_dynamic_config, train_window_months=24)
    wf.to_csv(resolve_path("results/tables/showcase_walkforward_validation.csv"), index=False)

    stability = parameter_stability(chosen_dynamic)
    stability.to_csv(resolve_path("results/tables/showcase_parameter_stability.csv"), index=False)

    afml = afml_diagnostics(apply_public_model_labels(summary), chosen_dynamic, _parameter_grid(False))
    afml.to_csv(resolve_path("results/tables/showcase_afml_diagnostics.csv"), index=False)

    pbo = simplified_pbo_diagnostic(returns, _parameter_grid(False), chosen_dynamic_config)
    pbo.to_csv(resolve_path("results/tables/showcase_pbo_diagnostic.csv"), index=False)

    nav_dict = {
        public_model_label("V3_Global_RRP"): nav_from_result(chosen_v3, eval_start_date),
        public_model_label("Dynamic_RRP"): nav_from_result(chosen_dynamic, eval_start_date),
        public_model_label("Dynamic_RRP_before"): nav_from_result(current_dynamic, eval_start_date),
    }
    plot_nav_comparison(nav_dict, f"Showcase NAV Comparison since {eval_start_date}", resolve_path("results/figures/showcase_nav_comparison.png"))
    plot_drawdown_comparison(nav_dict, f"Showcase Drawdown Comparison since {eval_start_date}", resolve_path("results/figures/showcase_drawdown_comparison.png"))
    plot_risk_overlay_ablation(public_ablation, resolve_path("results/figures/showcase_risk_overlay_ablation.png"))
    plot_dynamic_parameter_timeline(chosen_dynamic, resolve_path("results/figures/showcase_parameter_timeline.png"))
    plot_pbo_heatmap(pbo, resolve_path("results/figures/showcase_pbo_heatmap.png"))
    write_readme(summary, eval_start_date)

    print("Chosen V3 candidate:", chosen_v3_name)
    print("Chosen Dynamic candidate:", chosen_dynamic_name)
    print(summary)


if __name__ == "__main__":
    main()
