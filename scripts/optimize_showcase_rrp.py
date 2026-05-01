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
    excess_dd = max(0.0, dd - benchmark_dd)
    turnover = float(metrics.get("annualized_turnover", 0.0))
    return (
        float(metrics.get("sharpe_ratio", 0.0))
        + 0.15 * float(metrics.get("calmar_ratio", 0.0))
        - 6.0 * excess_dd
        - 0.015 * turnover
        - 0.10 * instability
    )


def parameter_instability(result: pd.DataFrame) -> float:
    stability = parameter_stability(result)
    if stability.empty or "switch_count" not in stability:
        return 0.0
    return float(stability["switch_count"].fillna(0.0).mean() / max(len(result), 1))


def dynamic_overlay_candidates() -> list[dict]:
    return [
        {"candidate": "current_dynamic"},
        {
            "candidate": "milder_drawdown_soft_trend",
            "drawdown_mild": 0.035,
            "drawdown_medium": 0.060,
            "drawdown_medium_scale": 0.90,
            "drawdown_severe_scale": 0.70,
            "trend_filter_mode": "soft",
            "trend_soft_scale": 0.92,
            "target_vol": 0.070,
            "max_risk_scale": 1.0,
            "reentry_speed": 0.50,
            "signal_persistence": 2,
            "weight_smoothing": 0.15,
        },
        {
            "candidate": "vol_only_high_target",
            "drawdown_mild": 1.0,
            "drawdown_medium": 1.0,
            "drawdown_severe": 1.0,
            "trend_filter_mode": "off",
            "target_vol": 0.075,
            "max_risk_scale": 1.0,
            "weight_smoothing": 0.10,
        },
        {
            "candidate": "soft_trend_no_turnover_cap",
            "trend_filter_mode": "soft",
            "trend_soft_scale": 0.95,
            "target_vol": 0.070,
            "turnover_cap": None,
            "weight_smoothing": 0.20,
        },
        {
            "candidate": "gentle_full_overlay",
            "drawdown_mild": 0.050,
            "drawdown_medium": 0.080,
            "drawdown_medium_scale": 0.95,
            "drawdown_severe_scale": 0.80,
            "trend_filter_mode": "soft",
            "trend_soft_scale": 0.97,
            "target_vol": 0.080,
            "realized_vol_window": 180,
            "ewma_halflife": 63,
            "reentry_speed": 0.75,
            "signal_persistence": 2,
            "weight_smoothing": 0.25,
            "turnover_cap": 0.35,
        },
    ]


def v3_candidates() -> list[dict]:
    lookbacks = [120, 180, 252, 504]
    lambdas = [0.3, 0.5, 0.7, 1.0]
    multiplier_values = [0.85, 1.00, 1.15]
    candidates = [{"candidate": "preserve_current_v3"}]
    for lookback, lambda_pen in itertools.product(lookbacks, lambdas):
        candidates.append(
            {
                "candidate": f"lookback_{lookback}_lambda_{lambda_pen}",
                "lookback_weeks": max(4, round(lookback / 5)),
                "lambda_pen": lambda_pen,
            }
        )
    for asset_class in ["equity", "bond", "commodity_gold", "defensive"]:
        for value in multiplier_values:
            if value == 1.0:
                continue
            candidates.append(
                {
                    "candidate": f"{asset_class}_multiplier_{value}",
                    "asset_class_budget_multipliers": {asset_class: value},
                }
            )
    return candidates


def run_dynamic_candidates(returns: pd.DataFrame, config: dict, eval_start_date: str) -> tuple[pd.DataFrame, dict]:
    base_grid = _parameter_grid(False)
    rows = []
    results = {}
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
        metrics = summarize(name, result, eval_start_date, cfg)
        metrics["objective_score"] = objective(metrics, instability=parameter_instability(result))
        rows.append(metrics)
        results[name] = {"result": result, "config": cfg}
    ranking = pd.DataFrame(rows).sort_values("objective_score", ascending=False)
    return ranking, results


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
    baseline = v3_ranking[v3_ranking["model"] == "preserve_current_v3"].iloc[0]
    for _, row in v3_ranking.iterrows():
        if row["model"] == "preserve_current_v3":
            return "preserve_current_v3"
        sharpe_gain = row["sharpe_ratio"] - baseline["sharpe_ratio"]
        dd_worse = abs(row["max_drawdown"]) - abs(baseline["max_drawdown"])
        turnover_worse = row["annualized_turnover"] - baseline["annualized_turnover"]
        if sharpe_gain >= 0.05 and dd_worse <= 0.005 and turnover_worse <= 0.50:
            return str(row["model"])
    return "preserve_current_v3"


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


def write_readme(summary: pd.DataFrame) -> None:
    front = summary[summary["model"].isin(["V3_Global_RRP", "Dynamic_RRP"])]
    lines = [
        "# Relaxed Risk Parity Research",
        "",
        "This repository studies Relaxed Risk Parity (RRP) with a static global showcase and a walk-forward Dynamic RRP overlay. Generated showcase artifacts are produced by:",
        "",
        "```bash",
        "python scripts/optimize_showcase_rrp.py",
        "python scripts/run_rrp_pipeline.py --mode full",
        "```",
        "",
        "## Showcase Results",
        "",
        "Evaluation starts on 2021-01-01. V3 Global RRP is preserved as the main benchmark unless conservative validation finds a stable improvement. Dynamic RRP is re-optimized because the previous overlay was materially over-defensive.",
        "",
        "| Model | Ann. Return | Volatility | Sharpe | Calmar | Max DD | Ann. Turnover |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in front.iterrows():
        lines.append(
            f"| {row['model']} | {row['annualized_return']:.2%} | {row['annualized_volatility']:.2%} | "
            f"{row['sharpe_ratio']:.2f} | {row['calmar_ratio']:.2f} | {row['max_drawdown']:.2%} | "
            f"{row['annualized_turnover']:.2f} |"
        )
    lines.extend(
        [
            "",
            "HRP and HERC remain secondary diversification benchmarks rather than the main narrative models.",
            "",
            "## Validation Design",
            "",
            "The showcase optimizer uses monthly walk-forward selection. Each rebalance uses only data strictly before the test period. The objective rewards Sharpe and Calmar while penalizing drawdown, turnover, and unstable parameter selections. PBO and adjusted-Sharpe outputs are simplified AFML-inspired diagnostics, not full CSCV or full Deflated Sharpe Ratio implementations.",
            "",
            "## Generated Outputs",
            "",
            "- `results/tables/showcase_performance_summary.csv`",
            "- `results/tables/dynamic_overlay_diagnostics.csv`",
            "- `results/tables/showcase_improvement_attribution.csv`",
            "- `results/tables/showcase_risk_overlay_ablation.csv`",
            "- `results/tables/showcase_walkforward_validation.csv`",
            "- `results/tables/showcase_parameter_stability.csv`",
            "- `results/tables/showcase_afml_diagnostics.csv`",
            "- `results/tables/showcase_pbo_diagnostic.csv`",
            "- `results/figures/showcase_nav_comparison.png`",
            "- `results/figures/showcase_drawdown_comparison.png`",
            "- `results/figures/showcase_risk_overlay_ablation.png`",
            "- `results/figures/showcase_parameter_timeline.png`",
            "- `results/figures/showcase_pbo_heatmap.png`",
            "",
            "## Limitations",
            "",
            "This is backtest research, not investment advice. The data source, asset mappings, transaction cost assumptions, leverage financing costs, and simplified validation diagnostics must be independently reviewed before any live use.",
            "",
            "## References",
            "",
            "1. Gambeta, V., & Kwon, R. (2020). Risk return trade-off in relaxed risk parity portfolio optimization.",
            "2. Lopez de Prado, M. (2018). Advances in Financial Machine Learning.",
            "3. Bailey, D. H., Borwein, J. M., Lopez de Prado, M., & Zhu, Q. J. (2015). The Probability of Backtest Overfitting.",
            "4. Bailey, D. H., & Lopez de Prado, M. (2014). The Deflated Sharpe Ratio.",
            "5. Lopez de Prado, M. (2016). Building Diversified Portfolios that Outperform Out-of-Sample.",
            "",
            "## License",
            "",
            "MIT License.",
        ]
    )
    Path(resolve_path("README.md")).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ensure_output_dirs()
    config = get_config({"transaction_cost_bps": 3.0, "turnover_cap": 0.25, "target_vol": 0.060})
    eval_start_date = config.get("plot_start_date", "2021-01-01")
    returns = load_data(source="tushare", force_update=False).dropna(how="all")

    v3_ranking, v3_results = run_v3_candidates(returns, config, eval_start_date)
    v3_ranking.to_csv(resolve_path("results/tables/showcase_v3_candidate_ranking.csv"), index=False)
    chosen_v3_name = choose_v3(v3_ranking)
    chosen_v3 = v3_results[chosen_v3_name]["result"]
    chosen_v3_config = v3_results[chosen_v3_name]["config"]

    dynamic_ranking, dynamic_results = run_dynamic_candidates(returns, config, eval_start_date)
    dynamic_ranking.to_csv(resolve_path("results/tables/showcase_dynamic_candidate_ranking.csv"), index=False)
    chosen_dynamic_name = str(dynamic_ranking.iloc[0]["model"])
    chosen_dynamic = dynamic_results[chosen_dynamic_name]["result"]
    chosen_dynamic_config = dynamic_results[chosen_dynamic_name]["config"]

    summary_rows = [
        summarize("V3_Global_RRP", chosen_v3, eval_start_date, chosen_v3_config),
        summarize("Dynamic_RRP", chosen_dynamic, eval_start_date, chosen_dynamic_config),
    ]
    current_dynamic = run_dynamic_rrp_selection(
        returns,
        _parameter_grid(False),
        train_window_months=24,
        selection_metric="utility",
        top_k=2,
        config_base=config,
    )
    summary_rows.append(summarize("Dynamic_RRP_before", current_dynamic, eval_start_date, config))
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(resolve_path("results/tables/showcase_performance_summary.csv"), index=False)

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
                "component": "optimized_dynamic_overlay",
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
    ablation.to_csv(resolve_path("results/tables/showcase_risk_overlay_ablation.csv"), index=False)

    wf = walk_forward_validation(returns, _parameter_grid(False), chosen_dynamic_config, train_window_months=24)
    wf.to_csv(resolve_path("results/tables/showcase_walkforward_validation.csv"), index=False)

    stability = parameter_stability(chosen_dynamic)
    stability.to_csv(resolve_path("results/tables/showcase_parameter_stability.csv"), index=False)

    afml = afml_diagnostics(summary, chosen_dynamic, _parameter_grid(False))
    afml.to_csv(resolve_path("results/tables/showcase_afml_diagnostics.csv"), index=False)

    pbo = simplified_pbo_diagnostic(returns, _parameter_grid(False), chosen_dynamic_config)
    pbo.to_csv(resolve_path("results/tables/showcase_pbo_diagnostic.csv"), index=False)

    nav_dict = {
        "V3_Global_RRP": nav_from_result(chosen_v3, eval_start_date),
        "Dynamic_RRP": nav_from_result(chosen_dynamic, eval_start_date),
        "Dynamic_RRP_before": nav_from_result(current_dynamic, eval_start_date),
    }
    plot_nav_comparison(nav_dict, f"Showcase NAV Comparison since {eval_start_date}", resolve_path("results/figures/showcase_nav_comparison.png"))
    plot_drawdown_comparison(nav_dict, f"Showcase Drawdown Comparison since {eval_start_date}", resolve_path("results/figures/showcase_drawdown_comparison.png"))
    plot_risk_overlay_ablation(ablation, resolve_path("results/figures/showcase_risk_overlay_ablation.png"))
    plot_dynamic_parameter_timeline(chosen_dynamic, resolve_path("results/figures/showcase_parameter_timeline.png"))
    plot_pbo_heatmap(pbo, resolve_path("results/figures/showcase_pbo_heatmap.png"))
    write_readme(summary)

    print("Chosen V3 candidate:", chosen_v3_name)
    print("Chosen Dynamic candidate:", chosen_dynamic_name)
    print(summary)


if __name__ == "__main__":
    main()
