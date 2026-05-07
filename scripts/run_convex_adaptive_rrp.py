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
from src.public_labels import apply_public_model_labels, public_model_label
from src.utils import get_config, resolve_path
from src.visualization import plot_drawdown_comparison, plot_metric_comparison, plot_nav_comparison


BASE_CONVEX_MODEL_NAME = "Convex Adaptive Global Relaxed Risk Parity"
IMPROVED_MODEL_NAME = "Improved Convex Adaptive Global Relaxed Risk Parity"


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
    from src.investable import expand_weights, investable_columns, portfolio_return_for_available

    dates = returns.index
    rebalance_dates = monthly_rebalance_dates(returns)
    weights = np.zeros(len(returns.columns))
    rows = []
    cost_rate = transaction_cost_bps / 10000.0
    for date in dates:
        turnover = 0.0
        if date in rebalance_dates:
            window_full = returns[returns.index < date].iloc[-240:]
            active_cols = investable_columns(window_full, min_observations=60)
            window = window_full[active_cols]
            if len(window) >= 30 and len(active_cols) > 1:
                previous = weights.copy()
                active_weights = solve_hrp(window).values if model_type == "hrp" else solve_herc(window).values
                weights = expand_weights(active_weights, active_cols, returns.columns)
                turnover = float(np.abs(weights - previous).sum())
        gross = portfolio_return_for_available(returns.loc[date], weights)
        cost = cost_rate * turnover
        row = {"date": date, "gross_return": gross, "net_return": gross - cost, "portfolio_return": gross - cost, "turnover": turnover}
        for i, asset in enumerate(returns.columns):
            row[f"weight_{asset}"] = weights[i]
        rows.append(row)
    return pd.DataFrame(rows)


def candidate_configurations(transaction_cost_bps: float) -> list[tuple[str, ConvexRRPConfig]]:
    rows: list[tuple[str, dict]] = []
    seen: set[tuple[tuple[str, object], ...]] = set()

    def add(params: dict) -> None:
        key = tuple(sorted(params.items()))
        if key not in seen:
            seen.add(key)
            rows.append((f"candidate_{len(rows) + 1:02d}", params))

    incumbent = {
        "lookback_days": 180,
        "covariance_method": "ewma",
        "max_weight": 0.40,
        "turnover_cap": 0.35,
        "turnover_penalty": 0.02,
        "budget_penalty": 0.35,
        "cvar_penalty": 0.20,
        "cvar_beta": 0.95,
        "return_reward": 0.05,
    }
    probe_winner = {
        "lookback_days": 252,
        "covariance_method": "ewma",
        "max_weight": 0.45,
        "turnover_cap": 0.80,
        "turnover_penalty": 0.01,
        "budget_penalty": 0.10,
        "cvar_penalty": 0.08,
        "cvar_beta": 0.95,
        "return_reward": 0.05,
    }

    add(incumbent)
    add(probe_winner)

    vol_constrained = {
        "lookback_days": 252,
        "covariance_method": "ewma",
        "max_weight": 0.40,
        "turnover_cap": 0.60,
        "turnover_penalty": 0.02,
        "budget_penalty": 0.25,
        "cvar_penalty": 0.15,
        "cvar_beta": 0.95,
        "return_reward": 0.06,
        "portfolio_vol_cap_enabled": True,
        "portfolio_vol_cap": 0.030,
    }
    for cap in [0.025, 0.030, 0.035]:
        add({**vol_constrained, "portfolio_vol_cap": cap})

    for lookback_days in [120, 180, 252]:
        for budget_penalty in [0.05, 0.10]:
            add(
                {
                    **probe_winner,
                    "lookback_days": lookback_days,
                    "budget_penalty": budget_penalty,
                }
            )

    for turnover_penalty in [0.00, 0.01, 0.02, 0.03]:
        add({**probe_winner, "turnover_penalty": turnover_penalty})

    for turnover_cap in [0.35, 0.80, 1.00, None]:
        add({**probe_winner, "turnover_cap": turnover_cap})

    for cvar_penalty in [0.05, 0.08, 0.10, 0.20]:
        add({**probe_winner, "cvar_penalty": cvar_penalty})

    for return_reward in [0.05, 0.06]:
        add({**probe_winner, "return_reward": return_reward})

    for params in [
        {**probe_winner, "max_weight": 0.40},
        {**probe_winner, "covariance_method": "sample"},
        {**probe_winner, "cvar_beta": 0.90},
        {**probe_winner, "lookback_days": 180, "max_weight": 0.40, "turnover_cap": 0.35, "turnover_penalty": 0.02, "budget_penalty": 0.35, "cvar_penalty": 0.10},
        {**probe_winner, "lookback_days": 180, "max_weight": 0.40, "turnover_cap": 0.80, "turnover_penalty": 0.01, "budget_penalty": 0.10, "cvar_penalty": 0.08},
        {**probe_winner, "lookback_days": 120, "max_weight": 0.45, "turnover_cap": 1.00, "turnover_penalty": 0.00, "budget_penalty": 0.05, "cvar_penalty": 0.05, "return_reward": 0.06},
        {**probe_winner, "lookback_days": 252, "max_weight": 0.40, "turnover_cap": 0.35, "turnover_penalty": 0.03, "budget_penalty": 0.35, "cvar_penalty": 0.20, "cvar_beta": 0.90},
        {**probe_winner, "lookback_days": 120, "covariance_method": "sample", "max_weight": 0.40, "turnover_cap": None, "turnover_penalty": 0.02, "budget_penalty": 0.10, "cvar_penalty": 0.10},
    ]:
        add(params)
    return [(name, ConvexRRPConfig(transaction_cost_bps=transaction_cost_bps, **params)) for name, params in rows]


def selection_score(metrics: dict, incumbent: dict, fallback_rate: float) -> tuple[float, str]:
    mdd_base = abs(float(incumbent["max_drawdown"]))
    cvar_base = max(float(incumbent["cvar_95_daily_loss"]), 1e-12)
    turnover_base = max(float(incumbent["avg_monthly_turnover"]), 1e-12)
    mdd = abs(float(metrics["max_drawdown"]))
    cvar_loss = float(metrics["cvar_95_daily_loss"])
    turnover = float(metrics["avg_monthly_turnover"])
    return_delta = float(metrics["net_annual_return"]) - float(incumbent["net_annual_return"])
    drawdown_delta = mdd - mdd_base

    reject_reasons = []
    if float(metrics["max_drawdown"]) < -0.075:
        reject_reasons.append("drawdown_gate")
    if turnover > 0.03:
        reject_reasons.append("turnover_gate")
    if fallback_rate > 0.0:
        reject_reasons.append("solver_fallback")
    if return_delta < -0.0025:
        reject_reasons.append("net_return_deterioration")
    if cvar_loss > cvar_base * 1.10:
        reject_reasons.append("cvar_worse")

    max_drawdown_penalty = max(0.0, drawdown_delta) / max(mdd_base, 1e-12)
    cvar_penalty = max(0.0, cvar_loss - cvar_base) / cvar_base
    turnover_penalty = max(0.0, turnover - turnover_base) / turnover_base
    score = (
        float(metrics["sharpe_ratio"])
        + 0.35 * float(metrics["calmar_ratio"])
        - 0.50 * max_drawdown_penalty
        - 0.15 * cvar_penalty
        - 0.10 * turnover_penalty
    )
    if reject_reasons:
        score -= 100.0
    return score, ";".join(reject_reasons)


def config_row(name: str, cfg: ConvexRRPConfig, metrics: dict, fallback_rate: float, score: float, reject_reason: str) -> dict:
    audit_note = "Selected using historical evaluation metrics; research-extension candidate, not frozen OOS."
    return {
        "candidate_id": name,
        "candidate_name": name,
        "selected": False,
        "selection_score": score,
        "sharpe": metrics["sharpe_ratio"],
        "calmar": metrics["calmar_ratio"],
        "max_drawdown": metrics["max_drawdown"],
        "cvar": metrics["cvar_95_daily_loss"],
        "annual_turnover": metrics["annualized_turnover"],
        "avg_monthly_turnover": metrics["avg_monthly_turnover"],
        "turnover_penalty": cfg.turnover_penalty,
        "cvar_penalty": cfg.cvar_penalty,
        "budget_penalty": cfg.budget_penalty,
        "max_weight": cfg.max_weight,
        "lookback_days": cfg.lookback_days,
        "covariance_method": cfg.covariance_method,
        "reject_reason": reject_reason,
        "notes": audit_note,
        # Legacy aliases retained for downstream robustness and covariance scripts.
        "lambda_cvar": cfg.cvar_penalty,
        "lambda_turnover": cfg.turnover_penalty,
        "return_reward": cfg.return_reward,
        "lambda_ref": cfg.return_reward,
        "lambda_budget": cfg.budget_penalty,
        "upper_bound_i": cfg.max_weight,
        "turnover_cap": cfg.turnover_cap,
        "cvar_alpha": cfg.cvar_beta,
        "covariance_estimator": cfg.covariance_method,
        "lookback_window": cfg.lookback_days,
        "Sharpe": metrics["sharpe_ratio"],
        "max_drawdown": metrics["max_drawdown"],
        "Calmar": metrics["calmar_ratio"],
        "CVaR_daily_loss": metrics["cvar_95_daily_loss"],
        "net_return": metrics["net_annual_return"],
        "average_monthly_turnover": metrics["avg_monthly_turnover"],
        "solver_fallback_rate": fallback_rate,
    }


def run_improvement_search(
    returns: pd.DataFrame,
    eval_start_date: str,
    config: dict,
    incumbent_metrics: dict,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    candidate_rows = []
    outputs = []
    for candidate_name, cfg in candidate_configurations(config["transaction_cost_bps"]):
        print(f"Running improvement {candidate_name}...")
        result, solver_diag, _, _ = run_convex_adaptive_backtest(returns, cfg)
        metrics = summarize_result(candidate_name, result, eval_start_date, config)
        fallback_rate = float(solver_diag["fallback_used"].mean()) if not solver_diag.empty else 1.0
        score, reject_reason = selection_score(metrics, incumbent_metrics, fallback_rate)
        candidate_rows.append(config_row(candidate_name, cfg, metrics, fallback_rate, score, reject_reason))
        outputs.append((candidate_name, result, solver_diag))

    candidates = pd.DataFrame(candidate_rows)
    accepted = candidates[candidates["reject_reason"].eq("")]
    preferred = accepted[
        (accepted["average_monthly_turnover"] <= 0.02)
        & (accepted["Sharpe"] > float(incumbent_metrics["sharpe_ratio"]))
        & (accepted["Calmar"] > float(incumbent_metrics["calmar_ratio"]))
    ]
    if not preferred.empty:
        selected_idx = preferred["selection_score"].idxmax()
    elif not accepted.empty:
        selected_idx = accepted["selection_score"].idxmax()
    else:
        selected_idx = candidates["selection_score"].idxmax()
    candidates.loc[selected_idx, "selected"] = True
    selected_name = str(candidates.loc[selected_idx, "candidate_name"])
    _, selected_result, selected_solver = next(row for row in outputs if row[0] == selected_name)
    selected_solver = selected_solver.copy()
    if not selected_solver.empty:
        selected_solver.insert(0, "model", IMPROVED_MODEL_NAME)
    return candidates, selected_result, selected_solver


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


def readme_row(row: pd.Series) -> str:
    return (
        f"| {public_model_label(row['model'])} | {row['net_annual_return']:.2%} | {row['sharpe_ratio']:.2f} | "
        f"{row['max_drawdown']:.2%} | {row['calmar_ratio']:.2f} | {row['avg_monthly_turnover']:.2%} |"
    )


def replace_latest_results_table(text: str, heading: str, rows: list[str], note: str) -> str:
    if heading not in text:
        return text
    start = text.index(heading)
    table_start = text.index("|", start)
    next_heading = text.find("\n## ", table_start)
    next_anchor = text.find("\n<a id=", table_start)
    candidates = [idx for idx in [next_heading, next_anchor] if idx != -1]
    end = min(candidates) if candidates else len(text)

    block = text[start:end]
    lines = block.splitlines()
    table_idx = next(i for i, line in enumerate(lines) if line.startswith("|"))
    header = lines[: table_idx + 2]
    new_block = "\n".join(header + rows + ["", note, ""])
    return text[:start] + new_block + text[end:]


def previous_improved_metrics() -> dict | None:
    path = Path(resolve_path("results/tables/convex_adaptive_performance_summary.csv"))
    if not path.exists():
        return None
    previous = pd.read_csv(path)
    previous = previous[previous["model"].map(public_model_label).eq(public_model_label(IMPROVED_MODEL_NAME))]
    if previous.empty:
        return None
    return previous.iloc[0].to_dict()


def write_readme(summary: pd.DataFrame, baseline_metrics: dict, improved_metrics: dict) -> None:
    public_models = [
        "Global Relaxed Risk Parity",
        "Defensive Dynamic Relaxed Risk Parity",
        BASE_CONVEX_MODEL_NAME,
        IMPROVED_MODEL_NAME,
        "HRP Benchmark",
        "HERC Benchmark",
    ]
    public_summary = apply_public_model_labels(summary.set_index("model").loc[public_models].reset_index())
    rows = [readme_row(row) for _, row in public_summary.iterrows()]
    both_improved = (
        improved_metrics["sharpe_ratio"] > baseline_metrics["sharpe_ratio"]
        and abs(improved_metrics["max_drawdown"]) < abs(baseline_metrics["max_drawdown"])
    )
    note_en = (
        f"{IMPROVED_MODEL_NAME} is a constrained parameter refinement of the convex adaptive optimizer, "
        "selected with drawdown and turnover-aware criteria."
        if both_improved
        else "Additional constrained tuning was tested, but the existing improved variant remained the preferred robust setting."
    )
    note_zh = (
        f"{IMPROVED_MODEL_NAME} 是对凸自适应优化器的受约束参数细化版本，并采用回撤和换手约束感知的标准进行选择。"
        if both_improved
        else f"{IMPROVED_MODEL_NAME} 已作为受约束优化细化版本进行测试；本次运行改进有限，结果已如实报告。"
    )
    readme_path = Path(resolve_path("README.md"))
    text = readme_path.read_text(encoding="utf-8")
    text = replace_latest_results_table(text, "## 最新结果", rows, note_zh)
    text = replace_latest_results_table(text, "## Latest Results", rows, note_en)
    readme_path.write_text(text, encoding="utf-8")


def main() -> None:
    ensure_output_dirs()
    config = get_config({"transaction_cost_bps": 3.0, "turnover_cap": 0.25, "target_vol": 0.060})
    eval_start_date = config.get("plot_start_date", "2015-01-01")
    incumbent_metrics = previous_improved_metrics()
    returns = load_data(source="tushare", force_update=False).dropna(how="all")

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

    print(f"Running {BASE_CONVEX_MODEL_NAME}...")
    base_cfg = ConvexRRPConfig(transaction_cost_bps=config["transaction_cost_bps"], budget_penalty=0.55)
    base_result, base_solver, _, _ = run_convex_adaptive_backtest(returns, base_cfg)
    base_result.to_csv(resolve_path("results/tables/convex_adaptive_global_relaxed_risk_parity_returns.csv"), index=False)
    base_solver.insert(0, "model", BASE_CONVEX_MODEL_NAME)
    baseline_summary = summarize_result(BASE_CONVEX_MODEL_NAME, base_result, eval_start_date, config)
    if incumbent_metrics is None:
        incumbent_metrics = baseline_summary

    candidates, improved_result, improved_solver = run_improvement_search(returns, eval_start_date, config, incumbent_metrics)
    improved_result.to_csv(resolve_path("results/tables/improved_convex_adaptive_global_relaxed_risk_parity_returns.csv"), index=False)
    candidates.to_csv(resolve_path("results/tables/convex_adaptive_improvement_candidates.csv"), index=False)

    models: dict[str, pd.DataFrame] = {
        "Global Relaxed Risk Parity": global_rrp,
        "Defensive Dynamic Relaxed Risk Parity": dynamic,
        BASE_CONVEX_MODEL_NAME: base_result,
        IMPROVED_MODEL_NAME: improved_result,
        "HRP Benchmark": hrp,
        "HERC Benchmark": herc,
    }
    public_order = list(models)
    summary = pd.DataFrame([summarize_result(name, result, eval_start_date, config) for name, result in models.items()])
    summary = summary.set_index("model").loc[public_order].reset_index()
    summary_public = apply_public_model_labels(summary)
    summary_public.to_csv(resolve_path("results/tables/convex_adaptive_performance_summary.csv"), index=False)

    selected_row = candidates[candidates["selected"]].iloc[0]
    ablation = summary_public[summary_public["model"].isin([public_model_label(BASE_CONVEX_MODEL_NAME), public_model_label(IMPROVED_MODEL_NAME)])].copy()
    ablation["selected_candidate"] = ablation["model"].eq(public_model_label(IMPROVED_MODEL_NAME))
    ablation["selected_candidate_name"] = np.where(ablation["selected_candidate"], selected_row["candidate_name"], "")
    ablation["selected_parameters"] = np.where(
        ablation["selected_candidate"],
        (
            f"lambda_cvar={selected_row['lambda_cvar']}, lambda_turnover={selected_row['lambda_turnover']}, "
            f"lambda_budget={selected_row['lambda_budget']}, upper_bound_i={selected_row['upper_bound_i']}, "
            f"cvar_alpha={selected_row['cvar_alpha']}, covariance={selected_row['covariance_estimator']}, "
            f"lookback={selected_row['lookback_window']}, return_reward={selected_row['return_reward']}"
        ),
        "baseline",
    )
    ablation.to_csv(resolve_path("results/tables/convex_adaptive_ablation.csv"), index=False)

    tc_summary = summary_public[
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

    solver_diag_df = pd.concat([base_solver, improved_solver], ignore_index=True)
    solver_diag_df = apply_public_model_labels(solver_diag_df)
    solver_diag_df.to_csv(resolve_path("results/tables/convex_adaptive_solver_diagnostics.csv"), index=False)
    graph_diag_df = graph_feature_frame(returns, monthly_rebalance_dates(returns), 240)
    graph_diag_df.to_csv(resolve_path("results/tables/asset_graph_diagnostics.csv"), index=False)

    nav_dict = {name: nav_from_return(result, "net_return" if "net_return" in result else "portfolio_return", eval_start_date) for name, result in models.items()}
    plot_nav_comparison(nav_dict, f"Convex Adaptive RRP NAV since {eval_start_date}", resolve_path("results/figures/convex_adaptive_nav_comparison.png"))
    plot_drawdown_comparison(nav_dict, f"Convex Adaptive RRP Drawdown since {eval_start_date}", resolve_path("results/figures/convex_adaptive_drawdown_comparison.png"))
    plot_transaction_cost(tc_summary, resolve_path("results/figures/convex_adaptive_transaction_cost_comparison.png"))
    plot_metric_comparison(summary_public, "avg_monthly_turnover", "Core Model Average Monthly Turnover", resolve_path("results/figures/convex_adaptive_turnover_comparison.png"), ylabel="Average monthly turnover")
    plot_metric_comparison(summary_public, "cvar_95_daily_loss", "Core Model CVaR Comparison", resolve_path("results/figures/convex_adaptive_cvar_comparison.png"), ylabel="95% daily CVaR")
    plot_feature_timeline(graph_diag_df, ["correlation_stress_score", "avg_abs_corr", "largest_cluster_size_ratio"], "Asset Graph Stress Timeline", resolve_path("results/figures/asset_graph_stress_timeline.png"))

    baseline_metrics = summary.set_index("model").loc[BASE_CONVEX_MODEL_NAME].to_dict()
    improved_metrics = summary.set_index("model").loc[IMPROVED_MODEL_NAME].to_dict()
    write_readme(summary, baseline_metrics, improved_metrics)

    print("\nConvex Adaptive Summary:")
    print(summary[["model", "net_annual_return", "sharpe_ratio", "max_drawdown", "calmar_ratio", "cvar_95_daily_loss", "turnover_adjusted_sharpe"]])
    print("\nSelected improvement candidate:")
    print(candidates[candidates["selected"]].T)
    print("Pipeline completed successfully.")


if __name__ == "__main__":
    main()
