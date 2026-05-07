from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.run_convex_adaptive_rrp import BASE_CONVEX_MODEL_NAME, IMPROVED_MODEL_NAME
from scripts.run_frozen_oos_validation import selected_candidate
from src.backtest import run_static_backtest
from src.convex_adaptive_rrp import ConvexRRPConfig, run_convex_adaptive_backtest
from src.data_loader import load_data
from src.dynamic_selection import run_dynamic_rrp_selection
from src.hierarchical_risk_parity import solve_herc, solve_hrp
from src.investable import expand_weights, investable_columns, portfolio_return_for_available
from src.public_labels import apply_public_model_labels
from src.utils import get_config, resolve_path
from src.validation import ensure_datetime_index


def monthly_rebalance_dates(returns: pd.DataFrame) -> set[pd.Timestamp]:
    return set(returns.groupby(returns.index.to_period("M")).tail(1).index)


def point_in_time_universe_timeline(returns: pd.DataFrame, lookback_days: int = 240) -> pd.DataFrame:
    rebalance_dates = monthly_rebalance_dates(returns)
    rows: list[dict] = []
    for date in returns.index:
        if date not in rebalance_dates:
            continue
        window_full = returns[returns.index < date].iloc[-lookback_days:]
        active_cols = investable_columns(window_full, min_observations=min(60, lookback_days))
        rows.append(
            {
                "rebalance_date": date,
                "available_assets": len(active_cols),
                "total_assets": len(returns.columns),
                "missing_assets": len(returns.columns) - len(active_cols),
                "coverage_ratio": len(active_cols) / max(len(returns.columns), 1),
                "window_start": window_full.index.min() if not window_full.empty else pd.NaT,
                "window_end": window_full.index.max() if not window_full.empty else pd.NaT,
            }
        )
    return pd.DataFrame(rows)


def run_point_in_time_hrp_like(returns: pd.DataFrame, model_type: str, transaction_cost_bps: float) -> pd.DataFrame:
    rebalance_dates = monthly_rebalance_dates(returns)
    weights = pd.Series(0.0, index=returns.columns)
    rows: list[dict] = []
    cost_rate = transaction_cost_bps / 10000.0
    for date in returns.index:
        turnover = 0.0
        if date in rebalance_dates:
            window_full = returns[returns.index < date].iloc[-240:]
            active_cols = investable_columns(window_full, min_observations=60)
            window = window_full[active_cols]
            if len(window) >= 30 and len(active_cols) > 1:
                previous = weights.values.copy()
                active_weights = solve_hrp(window).values if model_type == "hrp" else solve_herc(window).values
                weights = pd.Series(expand_weights(active_weights, active_cols, returns.columns), index=returns.columns)
                turnover = float(abs(weights.values - previous).sum())
        gross = portfolio_return_for_available(returns.loc[date], weights.values)
        cost = cost_rate * turnover
        rows.append(
            {
                "date": date,
                "gross_return": gross,
                "net_return": gross - cost,
                "portfolio_return": gross - cost,
                "turnover": turnover,
            }
        )
    return pd.DataFrame(rows)


def summarize_result(name: str, result: pd.DataFrame, eval_start_date: str, config: dict, universe_stats: dict) -> dict:
    data = result.copy()
    if "net_return" not in data:
        data["net_return"] = data["portfolio_return"]
    if "gross_return" not in data:
        data["gross_return"] = data["portfolio_return"]
    eval_result = data[pd.to_datetime(data["date"]) >= pd.Timestamp(eval_start_date)].copy()
    nav = (1.0 + eval_result["net_return"].fillna(0.0)).cumprod()
    nav.index = pd.to_datetime(eval_result["date"])

    from src.metrics import calculate_metrics

    metrics = calculate_metrics(nav, config.get("risk_free_rate", 0.0), config["trading_days_per_year"])
    dates = pd.to_datetime(eval_result["date"])
    years = max((dates.max() - dates.min()).days / 365.25, 1.0 / 12.0)
    return {
        "model": name,
        "net_annual_return": metrics["annualized_return"],
        "annualized_volatility": metrics["annualized_volatility"],
        "sharpe_ratio": metrics["sharpe_ratio"],
        "max_drawdown": metrics["max_drawdown"],
        "calmar_ratio": metrics["calmar_ratio"],
        "avg_monthly_turnover": float(eval_result["turnover"].fillna(0.0).sum() / max(len(dates.dt.to_period("M").unique()), 1)),
        "annualized_turnover": float(eval_result["turnover"].fillna(0.0).sum() / years),
        "cvar_95_daily_loss": float((-eval_result["net_return"].fillna(0.0)).quantile(0.95)),
        "eval_start": pd.Timestamp(eval_start_date).date().isoformat(),
        "eval_end": pd.Timestamp(eval_result["date"].max()).date().isoformat(),
        "sample_start": pd.Timestamp(data["date"].min()).date().isoformat(),
        "sample_end": pd.Timestamp(data["date"].max()).date().isoformat(),
        "observations": int(len(eval_result)),
        "avg_available_assets": universe_stats["avg_available_assets"],
        "min_available_assets": universe_stats["min_available_assets"],
        "max_available_assets": universe_stats["max_available_assets"],
        "avg_coverage_ratio": universe_stats["avg_coverage_ratio"],
        "rebalance_points": universe_stats["rebalance_points"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run extended-sample robustness diagnostics for the thesis models.")
    parser.add_argument("--output-dir", default="results/tables")
    parser.add_argument("--eval-start", default="2018-01-01")
    parser.add_argument("--sample-start", default="2018-01-02")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    config = get_config({"transaction_cost_bps": 3.0, "turnover_cap": 0.25, "target_vol": 0.060})
    returns = ensure_datetime_index(load_data(source="tushare", force_update=False))
    returns = returns[(returns.index >= pd.Timestamp(args.sample_start)) & (returns.index <= pd.Timestamp("2026-04-30"))]
    if returns.empty:
        raise ValueError("Extended sample returns are empty.")
    if args.smoke:
        returns = returns.iloc[:260].copy()

    base_candidate_id, base_cfg = selected_candidate(config["transaction_cost_bps"])
    timeline = point_in_time_universe_timeline(returns)
    universe_stats = {
        "avg_available_assets": float(timeline["available_assets"].mean()) if not timeline.empty else 0.0,
        "min_available_assets": int(timeline["available_assets"].min()) if not timeline.empty else 0,
        "max_available_assets": int(timeline["available_assets"].max()) if not timeline.empty else 0,
        "avg_coverage_ratio": float(timeline["coverage_ratio"].mean()) if not timeline.empty else 0.0,
        "rebalance_points": int(len(timeline)),
    }

    models: dict[str, pd.DataFrame] = {
        "Global Relaxed Risk Parity": run_static_backtest(returns, model_type="relaxed", config_overrides=config),
        "Defensive Dynamic Relaxed Risk Parity": run_dynamic_rrp_selection(
            returns,
            [{"lambda_pen": 0.10, "m": 1.9, "bond_leverage_upper": 1.4}, {"lambda_pen": 1.90, "m": 3.0, "bond_leverage_upper": 1.8}],
            train_window_months=24,
            selection_metric="utility",
            top_k=2,
            config_base=config,
        ),
        BASE_CONVEX_MODEL_NAME: run_convex_adaptive_backtest(
            returns,
            ConvexRRPConfig(transaction_cost_bps=config["transaction_cost_bps"], budget_penalty=0.55),
        )[0],
        IMPROVED_MODEL_NAME: run_convex_adaptive_backtest(returns, base_cfg)[0],
        "HRP Benchmark": run_point_in_time_hrp_like(returns, "hrp", config["transaction_cost_bps"]),
        "HERC Benchmark": run_point_in_time_hrp_like(returns, "herc", config["transaction_cost_bps"]),
    }

    summary_rows = [summarize_result(name, result, args.eval_start, config, universe_stats) for name, result in models.items()]
    summary = apply_public_model_labels(pd.DataFrame(summary_rows))
    summary["base_candidate_id"] = base_candidate_id
    summary["validation_status"] = "extended_sample_robustness"
    summary["notes"] = (
        "Point-in-time extended sample robustness over 2018-01-02 to 2026-04-30; "
        "early-listed ETFs are filtered through trailing availability checks."
    )

    output_dir = Path(resolve_path(args.output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)
    summary.to_csv(output_dir / "extended_sample_robustness_summary.csv", index=False)
    timeline.to_csv(output_dir / "extended_sample_robustness_universe_timeline.csv", index=False)
    print(f"Saved extended sample robustness summary to {output_dir}")


if __name__ == "__main__":
    main()
