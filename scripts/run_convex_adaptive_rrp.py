from __future__ import annotations

import argparse
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
from src.afml_oos import (
    generate_quarterly_oos_windows,
    score_oos_candidates,
    select_public_low_turnover_oos_candidates,
)
from src.backtest import run_static_backtest
from src.benchmarks import run_benchmark_backtest
from src.convex_adaptive_rrp import (
    ConvexRRPConfig,
    drift_weights,
    run_convex_adaptive_backtest,
    run_convex_adaptive_schedule_backtest,
)
from src.data_loader import load_data
from src.hierarchical_risk_parity import solve_herc, solve_hrp
from src.metrics import calculate_metrics
from src.public_labels import apply_public_model_labels, public_model_label
from src.utils import get_config, resolve_path
from src.validation import config_fields, result_window_metrics
from src.visualization import plot_drawdown_comparison, plot_metric_comparison, plot_nav_comparison


BASE_CONVEX_MODEL_NAME = "Convex Adaptive Global Relaxed Risk Parity"
IMPROVED_MODEL_NAME = "Improved Convex Adaptive Global Relaxed Risk Parity"
PUBLIC_SELECTION_METHOD = "afml_rolling_oos"
EXPLORATORY_REFERENCE_CANDIDATE_ID = "candidate_03"
PUBLIC_LOW_TURNOVER_CANDIDATE_IDS = ("candidate_03", "candidate_04", "candidate_05")
PUBLIC_EXECUTION_WARMUP_MONTHS = 36
PUBLIC_CASH_CONCENTRATION_CAP = 0.30
PUBLIC_GROUP_BOUNDS = {
    "cash": (0.0, PUBLIC_CASH_CONCENTRATION_CAP),
    "bond": (0.0, 0.70),
    "defensive": (0.0, 0.25),
    "commodity_gold": (0.0, 0.40),
    "equity": (0.0, 0.70),
}
PUBLIC_VALIDATION_TURNOVER_LIMIT = 0.04
PUBLIC_REALIZED_TURNOVER_LIMIT = 0.02


def ensure_output_dirs() -> None:
    for path in ["results/tables", "results/figures"]:
        os.makedirs(resolve_path(path), exist_ok=True)


def monthly_rebalance_dates(returns: pd.DataFrame) -> set[pd.Timestamp]:
    return set(returns.groupby(returns.index.to_period("M")).tail(1).index)


def public_execution_warmup_start(returns: pd.DataFrame, evaluation_start: str) -> pd.Timestamp:
    requested = pd.Timestamp(evaluation_start) - pd.DateOffset(months=PUBLIC_EXECUTION_WARMUP_MONTHS)
    available = pd.DatetimeIndex(returns.index)[pd.DatetimeIndex(returns.index) >= requested]
    if available.empty or available[0] >= pd.Timestamp(evaluation_start):
        raise ValueError("Insufficient pre-evaluation history for public execution warm-up")
    return pd.Timestamp(available[0])


def slice_and_rebase_result(result: pd.DataFrame, evaluation_start: str) -> pd.DataFrame:
    public = result[pd.to_datetime(result["date"]) >= pd.Timestamp(evaluation_start)].copy()
    if public.empty:
        raise ValueError("Public OOS result is empty after the evaluation start")
    public["nav_gross"] = (1.0 + public["gross_return"].fillna(0.0)).cumprod()
    public["nav_net"] = (1.0 + public["net_return"].fillna(0.0)).cumprod()
    return public.reset_index(drop=True)


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
        weights = drift_weights(weights, returns.loc[date])
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
        "cvar_penalty": 0.0,
        "cvar_beta": 0.95,
        "return_reward": 0.0,
        "use_transaction_cost_objective": True,
    }
    probe_winner = {
        "lookback_days": 252,
        "covariance_method": "ewma",
        "max_weight": 0.45,
        "turnover_cap": 0.80,
        "turnover_penalty": 0.01,
        "budget_penalty": 0.10,
        "cvar_penalty": 0.0,
        "cvar_beta": 0.95,
        "return_reward": 0.0,
        "use_transaction_cost_objective": True,
    }

    add(incumbent)
    add(probe_winner)

    public_base = {
        "lookback_days": 252,
        "covariance_method": "ewma",
        "max_weight": 0.40,
        "turnover_cap": 0.80,
        "turnover_penalty": 0.02,
        "budget_penalty": 0.25,
        "cvar_beta": 0.95,
        "return_reward": 0.0,
        "use_transaction_cost_objective": True,
    }
    for cvar_penalty in [0.00, 0.02, 0.05]:
        add({**public_base, "cvar_penalty": cvar_penalty})

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

    for turnover_cap in [0.35, 0.60, 0.80, 1.00, None]:
        add({**probe_winner, "turnover_cap": turnover_cap})

    for cvar_penalty in [0.00, 0.02, 0.05, 0.08, 0.12, 0.20]:
        add({**probe_winner, "cvar_penalty": cvar_penalty})

    # Scale-normalized variance penalties give an always-feasible convex
    # risk trade-off across the staggered point-in-time universe. Absolute
    # volatility caps were removed because the early, narrow universe made
    # 4%-6% caps infeasible while a universally feasible cap was nonbinding.
    for variance_penalty in [0.02, 0.05, 0.10]:
        add({**probe_winner, "variance_penalty": variance_penalty})

    for params in [
        {**probe_winner, "max_weight": 0.30},
        {**probe_winner, "max_weight": 0.35},
        {**probe_winner, "max_weight": 0.40},
        {**probe_winner, "max_weight": 0.50},
        {**probe_winner, "covariance_method": "sample"},
        {**probe_winner, "cvar_beta": 0.90},
        {**probe_winner, "cvar_beta": 0.975},
        {**probe_winner, "ewma_halflife": 42},
        {**probe_winner, "ewma_halflife": 126},
        {**probe_winner, "turnover_cap": 0.20},
        {**probe_winner, "budget_penalty": 0.20},
    ]:
        add(params)
    if len(rows) != 36:
        raise RuntimeError(f"Candidate grid must contain 36 unique specifications, got {len(rows)}")
    configurations = []
    for name, params in rows:
        governed = dict(params)
        if name in PUBLIC_LOW_TURNOVER_CANDIDATE_IDS:
            governed["group_bounds"] = PUBLIC_GROUP_BOUNDS.copy()
        configurations.append(
            (name, ConvexRRPConfig(transaction_cost_bps=transaction_cost_bps, **governed))
        )
    return configurations


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
    if cvar_loss > cvar_base * 1.15:
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
    audit_note = (
        "The public model uses AFML-inspired rolling OOS selection. Full-sample candidate metrics "
        "are exploratory diagnostics and never select the public historical path."
    )
    return {
        "candidate_id": name,
        "candidate_name": name,
        "selected": False,
        "primary_selected": False,
        "exploratory_selected": False,
        "selection_score": score,
        "sharpe": metrics["sharpe_ratio"],
        "calmar": metrics["calmar_ratio"],
        "max_drawdown": metrics["max_drawdown"],
        "cvar": metrics["cvar_95_daily_loss"],
        "annual_turnover": metrics["annualized_turnover"],
        "avg_monthly_turnover": metrics["avg_monthly_turnover"],
        "turnover_penalty": cfg.turnover_penalty,
        "cvar_penalty": cfg.cvar_penalty,
        "cvar_limit": cfg.cvar_limit,
        "cvar_limit_multiplier": cfg.cvar_limit_multiplier,
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
        "portfolio_vol_cap": cfg.portfolio_vol_cap,
        "cvar_alpha": cfg.cvar_beta,
        "covariance_estimator": cfg.covariance_method,
        "lookback_window": cfg.lookback_days,
        "Sharpe": metrics["sharpe_ratio"],
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
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    evaluated: list[tuple[str, ConvexRRPConfig, pd.DataFrame, pd.DataFrame, dict, float]] = []
    for candidate_name, cfg in candidate_configurations(config["transaction_cost_bps"]):
        print(f"Running improvement {candidate_name}...")
        result, solver_diag, _, _ = run_convex_adaptive_backtest(returns, cfg)
        metrics = summarize_result(candidate_name, result, eval_start_date, config)
        fallback_rate = float(solver_diag["fallback_used"].mean()) if not solver_diag.empty else 1.0
        evaluated.append((candidate_name, cfg, result, solver_diag, metrics, fallback_rate))

    reference = next(row for row in evaluated if row[0] == EXPLORATORY_REFERENCE_CANDIDATE_ID)
    reference_metrics = reference[4]
    candidate_rows = []
    for candidate_name, cfg, _result, _solver, metrics, fallback_rate in evaluated:
        score, reject_reason = selection_score(metrics, reference_metrics, fallback_rate)
        candidate_rows.append(config_row(candidate_name, cfg, metrics, fallback_rate, score, reject_reason))

    candidates = pd.DataFrame(candidate_rows)
    accepted = candidates[candidates["reject_reason"].eq("")]
    preferred = accepted[
        (accepted["average_monthly_turnover"] <= 0.02)
        & (accepted["Sharpe"] > float(reference_metrics["sharpe_ratio"]))
        & (accepted["Calmar"] > float(reference_metrics["calmar_ratio"]))
    ]
    if not preferred.empty:
        selected_idx = preferred["selection_score"].idxmax()
    elif not accepted.empty:
        selected_idx = accepted["selection_score"].idxmax()
    else:
        selected_idx = candidates["selection_score"].idxmax()
    candidates.loc[selected_idx, "exploratory_selected"] = True

    candidate_results = {candidate_id: result for candidate_id, _cfg, result, _solver, _metrics, _fallback in evaluated}
    candidate_solvers = {candidate_id: solver for candidate_id, _cfg, _result, solver, _metrics, _fallback in evaluated}
    candidate_configs = {candidate_id: cfg for candidate_id, cfg, _result, _solver, _metrics, _fallback in evaluated}
    warmup_start = public_execution_warmup_start(returns, eval_start_date)
    windows = generate_quarterly_oos_windows(
        returns,
        evaluation_start=warmup_start,
        evaluation_end=config["evaluation_end_date"],
        train_months=24,
        validation_months=6,
        embargo_trading_days=1,
    )
    oos_scores = score_oos_candidates(
        windows,
        candidate_results,
        candidate_solvers,
        risk_free_returns=config.get("risk_free_rate"),
        trading_days_per_year=config["trading_days_per_year"],
    )
    parameter_json = {
        candidate_id: config_fields(candidate_id, cfg)["selected_params_json"]
        for candidate_id, cfg in candidate_configs.items()
    }
    oos_scores["candidate_params_json"] = oos_scores["candidate_id"].map(parameter_json)
    return build_public_oos_from_scores(returns, eval_start_date, config, candidates, oos_scores)


def build_public_oos_from_scores(
    returns: pd.DataFrame,
    eval_start_date: str,
    config: dict,
    candidates: pd.DataFrame,
    oos_scores: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build the public schedule from an already-audited complete score table."""
    candidate_configs = dict(candidate_configurations(config["transaction_cost_bps"]))
    expected_ids = set(candidate_configs)
    actual_ids = set(oos_scores["candidate_id"].astype(str))
    if actual_ids != expected_ids:
        raise ValueError("Cached OOS scores do not match the complete current candidate grid")
    if "candidate_params_json" not in oos_scores:
        raise ValueError("Cached OOS scores lack candidate parameter signatures")
    expected_params = {
        candidate_id: config_fields(candidate_id, cfg)["selected_params_json"]
        for candidate_id, cfg in candidate_configs.items()
    }
    observed_params = oos_scores.groupby("candidate_id")["candidate_params_json"].agg(
        lambda values: set(values.dropna().astype(str))
    )
    for candidate_id, expected_json in expected_params.items():
        if observed_params.get(candidate_id, set()) != {expected_json}:
            raise ValueError(
                f"Cached OOS scores use stale parameters for {candidate_id}"
            )
    split_counts = oos_scores.groupby("split_id")["candidate_id"].nunique()
    if split_counts.empty or not split_counts.eq(len(expected_ids)).all():
        raise ValueError("Cached OOS scores are incomplete for one or more splits")
    warmup_start = public_execution_warmup_start(returns, eval_start_date)
    if pd.Timestamp(oos_scores["test_start"].min()) != warmup_start:
        raise ValueError("Cached OOS scores do not start at the configured execution warm-up")
    if pd.Timestamp(oos_scores["test_end"].max()) != pd.Timestamp(config["evaluation_end_date"]):
        raise ValueError("Cached OOS scores do not end at the configured evaluation date")

    candidates = candidates.copy()
    oos_scores = oos_scores.copy()
    evaluation_start = pd.Timestamp(eval_start_date)
    oos_scores["phase"] = np.where(
        pd.to_datetime(oos_scores["test_start"]) < evaluation_start,
        "execution_warmup",
        "public_oos",
    )
    selection_parts = []
    for phase in ("execution_warmup", "public_oos"):
        phase_scores = oos_scores[oos_scores["phase"].eq(phase)]
        if phase_scores.empty:
            raise ValueError(f"Missing {phase} candidate scores")
        phase_selection = select_public_low_turnover_oos_candidates(
            phase_scores,
            eligible_candidate_ids=PUBLIC_LOW_TURNOVER_CANDIDATE_IDS,
            turnover_limit=PUBLIC_VALIDATION_TURNOVER_LIMIT,
            switch_confidence=0.95,
            trading_days_per_year=config["trading_days_per_year"],
        )
        phase_selection["phase"] = phase
        selection_parts.append(phase_selection)
    oos_selection = pd.concat(selection_parts, ignore_index=True).sort_values(
        "test_start", kind="mergesort"
    ).reset_index(drop=True)
    parameter_rows = {
        candidate_id: config_fields(candidate_id, cfg)
        for candidate_id, cfg in candidate_configs.items()
    }
    for key in next(iter(parameter_rows.values())):
        if key != "selected_candidate_id":
            oos_selection[key] = oos_selection["selected_candidate_id"].map(
                {candidate_id: fields[key] for candidate_id, fields in parameter_rows.items()}
            )

    scheduled_result, scheduled_solver, _, _ = run_convex_adaptive_schedule_backtest(
        returns,
        oos_selection[["test_start", "test_end", "selected_candidate_id"]],
        candidate_configs,
    )
    test_metric_rows = []
    for row in oos_selection.itertuples(index=False):
        metrics = result_window_metrics(
            scheduled_result,
            pd.Timestamp(row.test_start),
            pd.Timestamp(row.test_end),
            config,
        )
        test_metric_rows.append({f"test_{key}": value for key, value in metrics.items()})
    oos_selection = pd.concat([oos_selection.reset_index(drop=True), pd.DataFrame(test_metric_rows)], axis=1)
    public_result = slice_and_rebase_result(scheduled_result, eval_start_date)
    public_months = max(
        pd.to_datetime(public_result["date"]).dt.to_period("M").nunique(), 1
    )
    realized_monthly_turnover = float(
        public_result["turnover"].fillna(0.0).sum() / public_months
    )
    if realized_monthly_turnover > PUBLIC_REALIZED_TURNOVER_LIMIT + 1e-12:
        raise ValueError(
            "Public OOS path violates the realized monthly turnover release gate: "
            f"{realized_monthly_turnover:.4%} > {PUBLIC_REALIZED_TURNOVER_LIMIT:.4%}"
        )
    public_solver = scheduled_solver[
        pd.to_datetime(scheduled_solver["date"]) >= evaluation_start
    ].copy()
    selection_counts = oos_selection.loc[
        oos_selection["phase"].eq("public_oos"), "selected_candidate_id"
    ].value_counts()
    candidates["oos_selection_count"] = candidates["candidate_id"].map(selection_counts).fillna(0).astype(int)
    candidates["selected"] = candidates["oos_selection_count"].gt(0)
    if not public_solver.empty:
        public_solver.insert(0, "model", IMPROVED_MODEL_NAME)
    return candidates, public_result, public_solver, oos_selection, oos_scores


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
        f"| {public_model_label(row['model'])} | {row['net_annual_return']:.2%} | {row['annualized_volatility']:.2%} | "
        f"{row['sharpe_ratio']:.2f} | {row['sortino_ratio']:.2f} | "
        f"{row['max_drawdown']:.2%} | {row['calmar_ratio']:.2f} | "
        f"{row['avg_monthly_turnover']:.2%} |"
    )


def replace_latest_results_table(text: str, heading: str, rows: list[str], note: str) -> str:
    if heading not in text:
        return text
    start = text.index(heading)
    table_start = text.index("|", start)
    next_h2 = text.find("\n## ", table_start)
    next_h3 = text.find("\n### ", table_start)
    next_anchor = text.find("\n<a id=", table_start)
    candidates = [idx for idx in [next_h2, next_h3, next_anchor] if idx != -1]
    end = min(candidates) if candidates else len(text)

    block = text[start:end]
    lines = block.splitlines()
    table_idx = next(i for i, line in enumerate(lines) if line.startswith("|"))
    header = lines[: table_idx + 2]
    new_block = "\n".join(header + rows + ["", note, ""])
    return text[:start] + new_block + text[end:]


def main() -> None:
    ensure_output_dirs()
    config = get_config({"transaction_cost_bps": 3.0, "turnover_cap": 0.25, "target_vol": 0.060})
    eval_start_date = config["evaluation_start_date"]
    returns = load_data(source="tushare", force_update=False).dropna(how="all")

    print("Running baseline Global Relaxed Risk Parity...")
    static_diagnostics: dict = {}
    global_rrp = run_static_backtest(
        returns,
        model_type="relaxed",
        config_overrides=config,
        diagnostics_out=static_diagnostics,
    )
    # Reliability layer: write the per-rebalance solver / covariance / universe
    # diagnostics for the Global RRP path. These artifacts are additive — they
    # do not affect any model parameters or the headline performance table.
    static_diagnostics["solver"].to_csv(
        resolve_path("results/tables/static_backtest_solver_diagnostics.csv"), index=False
    )
    static_diagnostics["covariance"].to_csv(
        resolve_path("results/tables/static_backtest_covariance_diagnostics.csv"), index=False
    )
    static_diagnostics["universe"].to_csv(
        resolve_path("results/tables/static_backtest_universe_diagnostics.csv"), index=False
    )
    print("Running HRP and HERC benchmarks...")
    hrp = run_hrp_like(returns, "hrp", config["transaction_cost_bps"])
    herc = run_hrp_like(returns, "herc", config["transaction_cost_bps"])

    print("Running Equal Weight and 60/40 baselines...")
    equal_weight_result = run_benchmark_backtest(
        returns, "Equal Weight Benchmark", transaction_cost_bps=config["transaction_cost_bps"]
    )
    sixty_forty_result = run_benchmark_backtest(
        returns, "60/40 Benchmark", transaction_cost_bps=config["transaction_cost_bps"]
    )

    print(f"Running {BASE_CONVEX_MODEL_NAME}...")
    base_cfg = ConvexRRPConfig(transaction_cost_bps=config["transaction_cost_bps"], budget_penalty=0.55)
    base_result, base_solver, _, _ = run_convex_adaptive_backtest(returns, base_cfg)
    base_result.to_csv(resolve_path("results/tables/convex_adaptive_global_relaxed_risk_parity_returns.csv"), index=False)
    base_solver.insert(0, "model", BASE_CONVEX_MODEL_NAME)
    baseline_summary = summarize_result(BASE_CONVEX_MODEL_NAME, base_result, eval_start_date, config)
    from scripts.public_oos import run_public_oos_variant, load_public_oos_selection, primary_model_config, public_candidate_configs
    from dataclasses import asdict
    import json
    print("Running weekly primary model with frozen research schedule...")
    improved_result, improved_solver = run_public_oos_variant(returns, collect_constraint_diagnostics=True)
    improved_result.to_csv(resolve_path("results/tables/improved_convex_adaptive_global_relaxed_risk_parity_returns.csv"), index=False)
    improved_solver.insert(0, "model", IMPROVED_MODEL_NAME)
    oos_selection = load_public_oos_selection()
    manifest = {
        "model": public_model_label(IMPROVED_MODEL_NAME),
        "role": "primary", "risk_free_rate": 0.0,
        "selection_status": "Chosen after historical constraint research; not an untouched out-of-sample model selection test.",
        "schedule": "Frozen afml_oos_selection.csv; candidate_03 throughout the public period.",
        "configurations": {cid: asdict(primary_model_config(cfg)) for cid, cfg in public_candidate_configs(3.0).items() if cid in oos_selection.selected_candidate_id.unique()},
    }
    Path(resolve_path("results/tables/primary_model_configuration.json")).write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    models: dict[str, pd.DataFrame] = {
        "Global Relaxed Risk Parity": global_rrp,
        BASE_CONVEX_MODEL_NAME: base_result,
        IMPROVED_MODEL_NAME: improved_result,
        "HRP Benchmark": hrp,
        "HERC Benchmark": herc,
        "Equal Weight Benchmark": equal_weight_result,
        "60/40 Benchmark": sixty_forty_result,
    }
    public_order = [IMPROVED_MODEL_NAME, *[name for name in models if name != IMPROVED_MODEL_NAME]]
    for name, result in models.items():
        label = public_model_label(name).lower().replace("/", "_").replace(" ", "_")
        net = result["net_return"] if "net_return" in result else result["portfolio_return"]
        gross = result["gross_return"] if "gross_return" in result else net + result["turnover"].fillna(0.0) * config["transaction_cost_bps"] / 10000.0
        slice_and_rebase_result(result.assign(gross_return=gross, net_return=net), eval_start_date).to_csv(resolve_path(f"results/tables/comparison_{label}_returns.csv"), index=False)
    summary = pd.DataFrame([summarize_result(name, result, eval_start_date, config) for name, result in models.items()])
    summary = summary.set_index("model").loc[public_order].reset_index()
    summary_public = apply_public_model_labels(summary)
    summary_public["role"] = np.where(summary_public.model.eq(public_model_label(IMPROVED_MODEL_NAME)), "primary", "comparison")
    summary_public["risk_free_rate"] = 0.0
    summary_public["rebalance_frequency"] = np.where(summary_public.role.eq("primary"), "W", "M")
    summary_public.to_csv(resolve_path("results/tables/convex_adaptive_performance_summary.csv"), index=False)
    summary_public.to_csv(resolve_path("results/tables/hrp_comparison.csv"), index=False)

    ablation = summary_public[summary_public["model"].isin([public_model_label(BASE_CONVEX_MODEL_NAME), public_model_label(IMPROVED_MODEL_NAME)])].copy()
    ablation["selected_candidate"] = ablation["model"].eq(public_model_label(IMPROVED_MODEL_NAME))
    ablation["selected_candidate_name"] = np.where(
        ablation["selected_candidate"],
        "Weekly primary specification",
        "",
    )
    ablation["selected_parameters"] = np.where(
        ablation["selected_candidate"],
        "weekly; no cash or asset concentration caps; frozen research schedule; rf=0; see primary_model_configuration.json",
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
    # Narrative publication is synchronized after all diagnostic artifacts complete.

    print("\nConvex Adaptive Summary:")
    print(summary[["model", "net_annual_return", "sharpe_ratio", "max_drawdown", "calmar_ratio", "cvar_95_daily_loss", "turnover_adjusted_sharpe"]])
    print("\nFrozen research schedule candidate counts:")
    print(oos_selection["selected_candidate_id"].value_counts())
    print("Pipeline completed successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the convex adaptive RRP research pipeline")
    parser.parse_args()
    main()
