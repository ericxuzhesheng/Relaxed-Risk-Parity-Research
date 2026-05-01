import argparse
import os
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.backtest import run_static_backtest
from src.data_loader import load_data, update_data_from_wind
from src.metrics import add_turnover_adjusted_metrics, calculate_metrics
from src.public_labels import apply_public_model_labels, public_model_label
from src.dynamic_selection import run_dynamic_rrp_selection
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
    plot_weights,
)


def _ensure_output_dirs():
    for path in ["results/tables", "results/figures"]:
        os.makedirs(resolve_path(path), exist_ok=True)


def _weight_cols(df: pd.DataFrame) -> list[str]:
    return [col for col in df.columns if col.startswith("weight_")]


def _nav_from_result(result: pd.DataFrame, eval_start_date: str) -> pd.Series:
    data = result[result["date"] >= eval_start_date].copy()
    nav = (1.0 + data["portfolio_return"]).cumprod()
    nav.index = pd.to_datetime(data["date"])
    return nav


def _summarize(name: str, result: pd.DataFrame, eval_start_date: str, config: dict) -> dict:
    eval_result = result[result["date"] >= eval_start_date].copy()
    nav = _nav_from_result(result, eval_start_date)
    metrics = calculate_metrics(
        nav,
        risk_free_rate=config["risk_free_rate"],
        trading_days=config["trading_days_per_year"],
    )
    metrics = add_turnover_adjusted_metrics(metrics, eval_result["turnover"], config.get("transaction_cost_bps", 3.0))
    dates = pd.to_datetime(eval_result["date"])
    years = max((dates.max() - dates.min()).days / 365.25, 1.0 / 12.0)
    annualized_turnover = float(eval_result["turnover"].fillna(0.0).sum() / years)
    annual_cost = annualized_turnover * config.get("transaction_cost_bps", 3.0) / 10000.0
    metrics["annualized_turnover"] = annualized_turnover
    metrics["turnover_adjusted_return"] = metrics["annualized_return"] - annual_cost
    metrics["turnover_adjusted_sharpe"] = (
        metrics["turnover_adjusted_return"] / metrics["annualized_volatility"]
        if metrics["annualized_volatility"] > 0
        else 0.0
    )
    metrics["model"] = name
    metrics["avg_turnover"] = eval_result["turnover"].mean()
    if "drawdown_scalar" in result:
        metrics["avg_drawdown_scalar"] = result.loc[result["date"] >= eval_start_date, "drawdown_scalar"].mean()
    if "target_vol_scalar" in result:
        metrics["avg_target_vol_scalar"] = result.loc[result["date"] >= eval_start_date, "target_vol_scalar"].mean()
    return metrics


def _parameter_grid(fast_mode: bool) -> list[dict]:
    grid = [
        {"lambda_pen": 0.01, "m": 1.0, "bond_leverage_upper": 1.2},
        {"lambda_pen": 0.10, "m": 1.9, "bond_leverage_upper": 1.4},
        {"lambda_pen": 1.00, "m": 2.5, "bond_leverage_upper": 1.6},
        {"lambda_pen": 1.90, "m": 3.0, "bond_leverage_upper": 1.8},
    ]
    return grid[:2] if fast_mode else grid


def _save_weights(result: pd.DataFrame, name: str):
    weight_cols = _weight_cols(result)
    out = result[["date"] + weight_cols].copy()
    out.to_csv(resolve_path(f"results/tables/{name.lower()}_weights.csv"), index=False)
    plot_df = out.set_index("date")
    plot_df.columns = [col.replace("weight_", "") for col in plot_df.columns]
    plot_weights(
        plot_df,
        f"{public_model_label(name)} Weights",
        resolve_path(f"results/figures/{name.lower()}_weights.png"),
    )


def main():
    parser = argparse.ArgumentParser(description="Relaxed Risk Parity Pipeline")
    parser.add_argument("--mode", type=str, choices=["static", "dynamic", "full"], default="full")
    parser.add_argument("--source", type=str, choices=["excel", "tushare"], default="tushare")
    parser.add_argument("--force-update", action="store_true")
    parser.add_argument("--update-wind", action="store_true")
    parser.add_argument("--train-window-months", type=int, default=24)
    parser.add_argument("--selection-metric", type=str, default="utility")
    parser.add_argument("--top-k", type=int, default=2)
    parser.add_argument("--fast-mode", action="store_true")
    args = parser.parse_args()

    _ensure_output_dirs()
    config = get_config({"transaction_cost_bps": 3.0, "turnover_cap": 0.25, "target_vol": 0.060})
    eval_start_date = config.get("plot_start_date", "2021-01-01")

    if args.update_wind:
        update_data_from_wind()

    returns = load_data(source=args.source, force_update=args.force_update).dropna(how="all")
    assets_v3 = list(returns.columns)
    assets_v1 = list(returns.columns[: min(13, len(returns.columns))])
    param_grid = _parameter_grid(args.fast_mode)

    models: dict[str, pd.DataFrame] = {}
    nav_dict: dict[str, pd.Series] = {}

    if args.mode in ["static", "full"]:
        static_jobs = [
            ("V1_Standard", assets_v1, "standard"),
            ("V2_Relaxed", assets_v1, "relaxed"),
            ("V3_Global_RRP", assets_v3, "relaxed"),
            ("HRP_Benchmark", assets_v3, "hrp"),
            ("HERC_Benchmark", assets_v3, "herc"),
        ]
        for name, assets, model_type in static_jobs:
            print(f"Running {name}...")
            result = run_static_backtest(returns[assets], model_type=model_type, config_overrides=config)
            models[name] = result
            _save_weights(result, name)

    if args.mode in ["dynamic", "full"]:
        print("Running Dynamic_RRP...")
        dynamic = run_dynamic_rrp_selection(
            returns[assets_v3],
            param_grid,
            train_window_months=args.train_window_months,
            selection_metric=args.selection_metric,
            top_k=args.top_k,
            config_base=config,
        )
        models["Dynamic_RRP"] = dynamic
        dynamic.to_csv(resolve_path("results/tables/dynamic_rrp_full.csv"), index=False)
        _save_weights(dynamic, "Dynamic_RRP")
        plot_dynamic_parameter_timeline(
            dynamic,
            resolve_path("results/figures/dynamic_parameter_timeline.png"),
        )

    summaries = []
    for name, result in models.items():
        if result.empty:
            continue
        summaries.append(_summarize(name, result, eval_start_date, config))
        nav_dict[name] = _nav_from_result(result, eval_start_date)

    summary_df = pd.DataFrame(summaries)
    if not summary_df.empty:
        front = ["V3_Global_RRP", "Dynamic_RRP"]
        summary_df["rank_order"] = summary_df["model"].apply(
            lambda model: front.index(model) if model in front else len(front)
        )
        summary_df = summary_df.sort_values(["rank_order", "model"]).drop(columns=["rank_order"])
        summary_df = summary_df[["model"] + [col for col in summary_df.columns if col != "model"]]
        apply_public_model_labels(summary_df).to_csv(
            resolve_path("results/tables/performance_summary.csv"),
            index=False,
        )

    if nav_dict:
        public_nav_dict = {public_model_label(name): nav for name, nav in nav_dict.items()}
        plot_nav_comparison(
            public_nav_dict,
            f"NAV Comparison since {eval_start_date}",
            resolve_path("results/figures/nav_comparison.png"),
        )
        plot_drawdown_comparison(
            public_nav_dict,
            f"Drawdown Comparison since {eval_start_date}",
            resolve_path("results/figures/drawdown_comparison.png"),
        )

    if args.mode in ["dynamic", "full"] and "Dynamic_RRP" in models and not models["Dynamic_RRP"].empty:
        dynamic = models["Dynamic_RRP"]
        stability = parameter_stability(dynamic)
        stability.to_csv(resolve_path("results/tables/parameter_stability.csv"), index=False)

        walkforward = walk_forward_validation(
            returns[assets_v3],
            param_grid,
            config,
            train_window_months=args.train_window_months,
            selection_metric=args.selection_metric,
        )
        walkforward.to_csv(resolve_path("results/tables/walkforward_validation.csv"), index=False)

        diagnostics = afml_diagnostics(apply_public_model_labels(summary_df), dynamic, param_grid)
        diagnostics.to_csv(resolve_path("results/tables/afml_diagnostics.csv"), index=False)

        pbo = simplified_pbo_diagnostic(returns[assets_v3], param_grid, config, args.selection_metric)
        pbo.to_csv(resolve_path("results/tables/pbo_diagnostic.csv"), index=False)
        plot_pbo_heatmap(pbo, resolve_path("results/figures/pbo_heatmap.png"))

        ablation_rows = []
        for name in ["V3_Global_RRP", "Dynamic_RRP"]:
            if name in models and not models[name].empty:
                ablation_rows.append(_summarize(name, models[name], eval_start_date, config))
        no_turnover_config = config.copy()
        no_turnover_config["turnover_cap"] = 10.0
        dynamic_no_cap = run_dynamic_rrp_selection(
            returns[assets_v3],
            param_grid[: max(4, min(8, len(param_grid)))],
            train_window_months=args.train_window_months,
            selection_metric=args.selection_metric,
            top_k=args.top_k,
            config_base=no_turnover_config,
        )
        if not dynamic_no_cap.empty:
            ablation_rows.append(_summarize("Dynamic_RRP_No_Turnover_Cap", dynamic_no_cap, eval_start_date, no_turnover_config))
        ablation = pd.DataFrame(ablation_rows)
        public_ablation = apply_public_model_labels(ablation)
        public_ablation.to_csv(resolve_path("results/tables/risk_overlay_ablation.csv"), index=False)
        plot_risk_overlay_ablation(public_ablation, resolve_path("results/figures/risk_overlay_ablation.png"))

    print("\nSummary Results:")
    print(summary_df if not summary_df.empty else "No summary rows generated.")
    print("Pipeline completed successfully.")


if __name__ == "__main__":
    main()
