from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.run_convex_adaptive_rrp import candidate_configurations, cvar
from src.convex_adaptive_rrp import ConvexRRPConfig, run_convex_adaptive_backtest
from src.data_loader import load_data
from src.metrics import calculate_metrics
from src.utils import get_config, resolve_path


VALIDATION_STATUS = "preliminary_walk_forward_scaffold"
VALIDATION_NOTE = "Candidate selected on train/validation history and evaluated on the next unseen test window."


def monthly_window_ends(returns: pd.DataFrame) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(returns.groupby(returns.index.to_period("M")).tail(1).index)


def next_trading_day(index: pd.DatetimeIndex, after: pd.Timestamp) -> pd.Timestamp:
    later = index[index > after]
    if later.empty:
        raise ValueError(f"No trading day exists after {after.date()}")
    return pd.Timestamp(later[0])


def split_windows(
    returns: pd.DataFrame,
    train_months: int,
    validation_months: int,
    test_months: int,
    step_months: int,
    max_splits: int | None,
) -> list[dict[str, pd.Timestamp]]:
    month_ends = monthly_window_ends(returns)
    total = train_months + validation_months + test_months
    if len(month_ends) < total:
        raise ValueError(
            f"Not enough monthly data for walk-forward validation: need {total} months, found {len(month_ends)}."
        )

    splits = []
    for start_idx in range(0, len(month_ends) - total + 1, step_months):
        train_start = pd.Timestamp(returns.index[0]) if start_idx == 0 else next_trading_day(returns.index, month_ends[start_idx - 1])
        train_end = pd.Timestamp(month_ends[start_idx + train_months - 1])
        validation_start = next_trading_day(returns.index, train_end)
        validation_end = pd.Timestamp(month_ends[start_idx + train_months + validation_months - 1])
        test_start = next_trading_day(returns.index, validation_end)
        test_end = pd.Timestamp(month_ends[start_idx + total - 1])
        splits.append(
            {
                "train_start": train_start,
                "train_end": train_end,
                "validation_start": validation_start,
                "validation_end": validation_end,
                "test_start": test_start,
                "test_end": test_end,
            }
        )
        if max_splits is not None and len(splits) >= max_splits:
            break
    return splits


def window_metrics(result: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, config: dict) -> dict:
    data = result.copy()
    data["date"] = pd.to_datetime(data["date"])
    data = data[(data["date"] >= start) & (data["date"] <= end)].copy()
    if data.empty:
        raise ValueError(f"No backtest rows found between {start.date()} and {end.date()}.")

    net_returns = data["net_return"] if "net_return" in data else data["portfolio_return"]
    nav = (1.0 + net_returns.fillna(0.0)).cumprod()
    metrics = calculate_metrics(nav, config.get("risk_free_rate", 0.0), config["trading_days_per_year"])
    years = max((data["date"].max() - data["date"].min()).days / 365.25, 1.0 / 12.0)
    months = max(len(data["date"].dt.to_period("M").unique()), 1)
    turnover = data["turnover"].fillna(0.0) if "turnover" in data else pd.Series(0.0, index=data.index)
    return {
        "net_annual_return": metrics["annualized_return"],
        "sharpe": metrics["sharpe_ratio"],
        "max_drawdown": metrics["max_drawdown"],
        "calmar": metrics["calmar_ratio"],
        "cvar": cvar(net_returns, 0.95),
        "annual_turnover": float(turnover.sum() / years),
        "avg_monthly_turnover": float(turnover.sum() / months),
    }


def validation_score(metrics: dict) -> float:
    drawdown_penalty = abs(min(float(metrics["max_drawdown"]), 0.0))
    turnover_penalty = float(metrics["avg_monthly_turnover"])
    cvar_penalty = float(metrics["cvar"])
    return (
        float(metrics["sharpe"])
        + 0.35 * float(metrics["calmar"])
        - 2.0 * drawdown_penalty
        - 0.25 * turnover_penalty
        - 10.0 * cvar_penalty
    )


def config_fields(candidate_id: str, cfg: ConvexRRPConfig) -> dict:
    return {
        "selected_candidate_id": candidate_id,
        "selected_candidate_name": candidate_id,
        "lookback_days": cfg.lookback_days,
        "covariance_method": cfg.covariance_method,
        "max_weight": cfg.max_weight,
        "turnover_cap": cfg.turnover_cap,
        "turnover_penalty": cfg.turnover_penalty,
        "cvar_penalty": cfg.cvar_penalty,
        "budget_penalty": cfg.budget_penalty,
        "cvar_beta": cfg.cvar_beta,
        "return_reward": cfg.return_reward,
    }


def run_split(
    returns: pd.DataFrame,
    split: dict[str, pd.Timestamp],
    candidates: list[tuple[str, ConvexRRPConfig]],
    config: dict,
) -> dict:
    history_end = split["validation_end"]
    validation_rows = []
    for candidate_id, cfg in candidates:
        history = returns[(returns.index >= split["train_start"]) & (returns.index <= history_end)]
        result, _, _, _ = run_convex_adaptive_backtest(history, cfg)
        metrics = window_metrics(result, split["validation_start"], split["validation_end"], config)
        validation_rows.append((validation_score(metrics), candidate_id, cfg, metrics))

    if not validation_rows:
        raise ValueError("No candidate configurations were available for walk-forward validation.")
    validation_rows.sort(key=lambda row: row[0], reverse=True)
    selected_score, selected_id, selected_cfg, validation_metrics = validation_rows[0]

    test_history = returns[(returns.index >= split["train_start"]) & (returns.index <= split["test_end"])]
    test_result, test_solver, _, _ = run_convex_adaptive_backtest(test_history, selected_cfg)
    test_metrics = window_metrics(test_result, split["test_start"], split["test_end"], config)
    fallback_rate = float(test_solver["fallback_used"].mean()) if not test_solver.empty else np.nan

    return {
        "validation_status": VALIDATION_STATUS,
        "uses_future_data": False,
        "train_start": split["train_start"].date().isoformat(),
        "train_end": split["train_end"].date().isoformat(),
        "validation_start": split["validation_start"].date().isoformat(),
        "validation_end": split["validation_end"].date().isoformat(),
        "test_start": split["test_start"].date().isoformat(),
        "test_end": split["test_end"].date().isoformat(),
        **config_fields(selected_id, selected_cfg),
        "selection_score": selected_score,
        "validation_sharpe": validation_metrics["sharpe"],
        "validation_calmar": validation_metrics["calmar"],
        "validation_max_drawdown": validation_metrics["max_drawdown"],
        "validation_avg_monthly_turnover": validation_metrics["avg_monthly_turnover"],
        "test_net_annual_return": test_metrics["net_annual_return"],
        "test_sharpe": test_metrics["sharpe"],
        "test_calmar": test_metrics["calmar"],
        "test_max_drawdown": test_metrics["max_drawdown"],
        "test_cvar": test_metrics["cvar"],
        "test_annual_turnover": test_metrics["annual_turnover"],
        "test_avg_monthly_turnover": test_metrics["avg_monthly_turnover"],
        "test_solver_fallback_rate": fallback_rate,
        "notes": VALIDATION_NOTE,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run preliminary walk-forward validation for improved convex adaptive RRP candidates.")
    parser.add_argument("--train-months", type=int, default=24)
    parser.add_argument("--validation-months", type=int, default=6)
    parser.add_argument("--test-months", type=int, default=3)
    parser.add_argument("--step-months", type=int, default=3)
    parser.add_argument("--max-splits", type=int, default=3)
    parser.add_argument("--max-candidates", type=int, default=None)
    parser.add_argument("--output", default="results/tables/walkforward_validation.csv")
    args = parser.parse_args()

    config = get_config({"transaction_cost_bps": 3.0})
    returns = load_data(source="tushare", force_update=False).dropna(how="all")
    if returns.empty:
        raise ValueError("Cached ETF return data is unavailable or empty; cannot run walk-forward validation.")

    candidates = candidate_configurations(config["transaction_cost_bps"])
    if args.max_candidates is not None:
        candidates = candidates[: args.max_candidates]
    if not candidates:
        raise ValueError("Candidate configurations are unavailable; cannot run walk-forward validation.")

    splits = split_windows(
        returns,
        args.train_months,
        args.validation_months,
        args.test_months,
        args.step_months,
        args.max_splits,
    )
    rows = []
    for i, split in enumerate(splits, start=1):
        print(f"Running walk-forward split {i}/{len(splits)}: test starts {split['test_start'].date()}")
        rows.append(run_split(returns, split, candidates, config))

    output = Path(resolve_path(args.output))
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output, index=False)
    print(f"Saved {len(rows)} preliminary walk-forward validation rows to {output}")


if __name__ == "__main__":
    main()
