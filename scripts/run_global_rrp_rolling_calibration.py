"""Walk-forward calibration for the two Global RRP penalty coefficients.

The public evaluation is untouched while each calendar year's coefficients are
chosen from data ending before that year.  Candidate ranges are determined by
the scale of the three objective terms, not by a hand-written numeric grid.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import itertools
import json
import logging
import os
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_convex_adaptive_rrp import slice_and_rebase_result, summarize_result
from scripts.run_global_rrp_research import participation
from src.backtest import run_static_backtest
from src.data_loader import load_data
from src.utils import get_config


OUTPUT = ROOT / "results/global_rrp_rolling_252"
FIRST_SCHEDULE_YEAR = 2017
LAST_SCHEDULE_YEAR = 2026
CALIBRATION_DAYS = 252
VALIDATION_DAYS = 252
WARMUP_DAYS = 504
QUANTILES = (0.25, 0.50, 0.75)

BASE = {
    "rebalance_frequency": "W",
    "risk_overlay_enabled": False,
    "trend_filter_mode": "off",
    "bond_leverage_upper": 1.0,
    "gross_exposure_cap": 1.0,
    "risk_free_rate": 0.0,
    "transaction_cost_bps": 3.0,
    "trading_days_per_year": 252,
    "lookback_days": 252,
    "rrp_variance_reference": "equal_weight",
    "rrp_return_target_mode": "reference",
    "mean_estimator": "ewma",
    "mean_ewma_halflife": 20.0,
    "covariance_method": "ledoit_wolf",
}


def _window_result(returns: pd.DataFrame, config: dict, start: pd.Timestamp, end: pd.Timestamp):
    start_pos = returns.index.searchsorted(start)
    subset = returns.iloc[max(0, start_pos - WARMUP_DAYS):]
    subset = subset[subset.index <= end]
    diagnostics = {}
    result = run_static_backtest(subset, "relaxed", config, diagnostics)
    result = result[(result.date >= start) & (result.date <= end)].reset_index(drop=True)
    solver = diagnostics["solver"]
    solver = solver[(pd.to_datetime(solver.date) >= start) & (pd.to_datetime(solver.date) <= end)]
    if result.empty or solver.empty or not solver.solver_success.all() or not solver.problem_is_dcp.all():
        raise RuntimeError("candidate validation did not produce a complete convex path")
    return result, solver


def _quarterly_stability(result: pd.DataFrame) -> tuple[float, float]:
    values = []
    for _, frame in result.groupby(pd.to_datetime(result.date).dt.to_period("Q")):
        r = frame.net_return.astype(float)
        if len(r) >= 20 and r.std() > 0:
            values.append(float(r.mean() / r.std() * np.sqrt(252)))
    if not values:
        return float("nan"), float("nan")
    return float(np.median(values)), float(np.min(values))


def _candidate_job(args):
    returns, start, end, variance_penalty, shortfall_penalty = args
    logging.getLogger().setLevel(logging.ERROR)
    cfg = {**BASE, "rrp_variance_penalty": variance_penalty,
           "lambda_pen": shortfall_penalty}
    result, solver = _window_result(returns, cfg, start, end)
    metrics = summarize_result("Global RRP", result, str(start.date()), get_config(cfg))
    quarter_median, quarter_min = _quarterly_stability(result)
    n = max(len(result.net_return) - 1, 1)
    sharpe_se = float(np.sqrt((252.0 + 0.5 * metrics["sharpe_ratio"] ** 2) / n))
    return {
        "variance_penalty": variance_penalty,
        "shortfall_penalty": shortfall_penalty,
        **metrics,
        "sharpe_standard_error": sharpe_se,
        "quarterly_sharpe_median": quarter_median,
        "quarterly_sharpe_min": quarter_min,
        "solver_count": len(solver),
        "future_information_count": int(
            (pd.to_datetime(solver.information_cutoff) >= pd.to_datetime(solver.date)).sum()
        ),
    }


def _term_scale_candidates(calibration: pd.DataFrame) -> tuple[list[float], list[float]]:
    tracking = calibration.objective_tracking.astype(float)
    variance = calibration.objective_variance_normalized.astype(float)
    shortfall = calibration.objective_shortfall_normalized.astype(float)
    variance_ratio = (tracking / variance).where((tracking > 1e-12) & (variance > 1e-12)).dropna()
    shortfall_ratio = (tracking / shortfall).where((tracking > 1e-12) & (shortfall > 1e-12)).dropna()
    if len(variance_ratio) < 4 or len(shortfall_ratio) < 4:
        raise RuntimeError("insufficient positive objective terms for data-derived penalty ranges")
    v = sorted(set(float(x) for x in variance_ratio.quantile(QUANTILES)))
    r = sorted(set(float(x) for x in shortfall_ratio.quantile(QUANTILES)))
    return v, r


def _select_candidate(frame: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame]:
    best = frame.loc[frame.sharpe_ratio.idxmax()]
    cutoff = float(best.sharpe_ratio - best.sharpe_standard_error)
    eligible = frame[frame.sharpe_ratio >= cutoff].copy()
    good = set(zip(eligible.variance_rank, eligible.shortfall_rank))
    eligible["has_eligible_neighbor"] = [
        any((i + di, j + dj) in good for di, dj in ((-1, 0), (1, 0), (0, -1), (0, 1)))
        for i, j in zip(eligible.variance_rank, eligible.shortfall_rank)
    ]
    stable = eligible[eligible.has_eligible_neighbor]
    if stable.empty:
        stable = eligible
    stable = stable.sort_values(
        ["annualized_turnover", "quarterly_sharpe_median", "variance_penalty", "shortfall_penalty"],
        ascending=[True, False, True, True],
    )
    return stable.iloc[0], eligible


def main():
    logging.getLogger().setLevel(logging.ERROR)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    protocol = {
        "status": "declared_before_execution",
        "annualization_days": 252,
        "estimation_window_days": 252,
        "calibration_days": CALIBRATION_DAYS,
        "validation_days": VALIDATION_DAYS,
        "parameter_update": "first calendar-year rebalance; frozen within year",
        "return_target": "predicted return of the contemporaneous feasible risk-budget reference",
        "candidate_construction": "25th, 50th and 75th percentiles of tracking/variance and tracking/shortfall objective-term ratios from the earlier calibration block under unit penalties",
        "selection": "one-standard-error net Sharpe set; require an adjacent qualifying grid point when available; then lowest turnover, then higher median quarterly Sharpe",
        "cost": "3 bps per unit absolute trade weight",
        "adaptive_grid_expansion": False,
        "public_evaluation_start": "2018-01-02",
        "public_evaluation_end": "2026-08-31",
    }
    (OUTPUT / "protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")

    returns = load_data(source="tushare", force_update=False).dropna(how="all")
    neutral_diag = {}
    neutral_cfg = {**BASE, "rrp_variance_penalty": 1.0, "lambda_pen": 1.0}
    run_static_backtest(returns, "relaxed", neutral_cfg, neutral_diag)
    neutral_solver = neutral_diag["solver"].copy()
    neutral_solver["date"] = pd.to_datetime(neutral_solver.date)
    neutral_solver.to_csv(OUTPUT / "unit_penalty_diagnostics.csv", index=False)

    schedules, validation_rows = [], []
    for year in range(FIRST_SCHEDULE_YEAR, LAST_SCHEDULE_YEAR + 1):
        effective = pd.Timestamp(f"{year}-01-01")
        prior = returns.index[returns.index < effective]
        if len(prior) < CALIBRATION_DAYS + VALIDATION_DAYS:
            raise RuntimeError(f"insufficient pre-{year} history")
        calibration_dates = prior[-(CALIBRATION_DAYS + VALIDATION_DAYS):-VALIDATION_DAYS]
        validation_dates = prior[-VALIDATION_DAYS:]
        calibration = neutral_solver[
            neutral_solver.date.between(calibration_dates[0], calibration_dates[-1])
        ]
        variance_candidates, shortfall_candidates = _term_scale_candidates(calibration)
        jobs = [
            (returns, validation_dates[0], validation_dates[-1], v, r)
            for v, r in itertools.product(variance_candidates, shortfall_candidates)
        ]
        with ProcessPoolExecutor(max_workers=min(4, os.cpu_count() or 1)) as executor:
            rows = list(executor.map(_candidate_job, jobs))
        frame = pd.DataFrame(rows)
        v_order = {v: i for i, v in enumerate(variance_candidates)}
        r_order = {r: i for i, r in enumerate(shortfall_candidates)}
        frame["variance_rank"] = frame.variance_penalty.map(v_order)
        frame["shortfall_rank"] = frame.shortfall_penalty.map(r_order)
        selected, eligible = _select_candidate(frame)
        frame["within_one_standard_error"] = frame.index.isin(eligible.index)
        frame["selected"] = frame.index == selected.name
        frame.insert(0, "schedule_year", year)
        frame.insert(1, "calibration_start", calibration_dates[0])
        frame.insert(2, "calibration_end", calibration_dates[-1])
        frame.insert(3, "validation_start", validation_dates[0])
        frame.insert(4, "validation_end", validation_dates[-1])
        validation_rows.append(frame)
        schedules.append({
            "effective_date": str(effective.date()),
            "information_end": str(validation_dates[-1].date()),
            "rrp_variance_penalty": float(selected.variance_penalty),
            "lambda_pen": float(selected.shortfall_penalty),
            "validation_net_sharpe": float(selected.sharpe_ratio),
            "validation_annualized_turnover": float(selected.annualized_turnover),
            "candidate_count": int(len(frame)),
            "within_one_standard_error_count": int(len(eligible)),
            "selected_has_eligible_neighbor": bool(selected.has_eligible_neighbor),
        })
        print(year, schedules[-1], flush=True)

    candidates = pd.concat(validation_rows, ignore_index=True)
    candidates.to_csv(OUTPUT / "validation_candidates.csv", index=False)
    pd.DataFrame(schedules).to_csv(OUTPUT / "selected_schedule.csv", index=False)
    (OUTPUT / "selected_schedule.json").write_text(json.dumps(schedules, indent=2), encoding="utf-8")

    final_cfg = {**BASE, "rrp_variance_penalty": 1.0, "lambda_pen": 1.0,
                 "rrp_parameter_schedule": schedules}
    diagnostics = {}
    result = run_static_backtest(returns, "relaxed", final_cfg, diagnostics)
    cfg = get_config(final_cfg)
    result = slice_and_rebase_result(result, cfg["evaluation_start_date"])
    result = result[pd.to_datetime(result.date) <= pd.Timestamp(cfg["evaluation_end_date"])].reset_index(drop=True)
    solver = diagnostics["solver"].copy()
    solver = solver[pd.to_datetime(solver.date).between(cfg["evaluation_start_date"], cfg["evaluation_end_date"])]
    covariance = diagnostics["covariance"].copy()
    covariance = covariance[
        pd.to_datetime(covariance.date).between(cfg["evaluation_start_date"], cfg["evaluation_end_date"])
    ]
    if (pd.to_datetime(solver.information_cutoff) >= pd.to_datetime(solver.date)).any():
        raise RuntimeError("future information detected in final schedule")
    if not solver.solver_success.all() or not solver.problem_is_dcp.all() or solver.fallback_used.any():
        raise RuntimeError("final schedule did not produce a complete convex solver path")
    if covariance.covariance_fallback_used.any():
        raise RuntimeError("covariance fallback detected")
    weights = result.filter(regex="^weight_").to_numpy()
    np.testing.assert_allclose(weights.sum(axis=1), 1.0, atol=1e-6)
    np.testing.assert_allclose(result.gross_return - result.transaction_cost, result.net_return, atol=1e-12)
    usage = participation(result, diagnostics["universe"])
    decisions = result[result.is_rebalance_day]
    usage["mean_rebalance_weight"] = [
        float(decisions[f"weight_{asset}"].mean()) for asset in usage.asset
    ]
    usage["median_rebalance_weight"] = [
        float(decisions[f"weight_{asset}"].median()) for asset in usage.asset
    ]
    usage["final_weight"] = [
        float(result[f"weight_{asset}"].iloc[-1]) for asset in usage.asset
    ]
    metrics = summarize_result("Global RRP", result, cfg["evaluation_start_date"], cfg)
    summary = {
        **metrics,
        "status": "passed",
        "annualization_days": 252,
        "estimation_window_days": 252,
        "assets_ever_used": int(usage.ever_used.sum()),
        "sharpe_target": 1.0,
        "sharpe_target_met": bool(metrics["sharpe_ratio"] >= 1.0),
        "preferred_net_return_target": .10,
        "preferred_net_return_target_met": bool(metrics["net_annual_return"] >= .10),
        "acceptable_net_return_floor": .08,
        "acceptable_net_return_floor_met": bool(metrics["net_annual_return"] >= .08),
        "max_drawdown_guardrail": -.08,
        "max_drawdown_guardrail_met": bool(metrics["max_drawdown"] >= -.08),
        "target_met": bool(
            metrics["sharpe_ratio"] >= 1.0
            and metrics["net_annual_return"] >= .08
            and metrics["max_drawdown"] >= -.08
        ),
        "selection_is_strictly_prior": True,
        "specification_selection_is_exploratory": True,
        "parameter_selection_informative_years": int(sum(
            row["within_one_standard_error_count"] < row["candidate_count"]
            for row in schedules
        )),
        "parameter_selection_years": int(len(schedules)),
    }
    annual_rows = []
    for year, frame in result.groupby(pd.to_datetime(result.date).dt.year):
        period_start = str(pd.to_datetime(frame.date).min().date())
        row = summarize_result("Global RRP", frame, period_start, cfg)
        row = {
            "year": int(year),
            "period_start": period_start,
            "period_end": str(pd.to_datetime(frame.date).max().date()),
            "observations": int(len(frame)),
            **row,
        }
        annual_rows.append(row)
    result.to_csv(OUTPUT / "daily_returns.csv", index=False)
    result[result.is_rebalance_day].to_csv(OUTPUT / "weekly_rebalances.csv", index=False)
    pd.DataFrame(annual_rows).to_csv(OUTPUT / "annual_performance.csv", index=False)
    usage.to_csv(OUTPUT / "asset_participation.csv", index=False)
    for key, frame in diagnostics.items():
        frame.to_csv(OUTPUT / f"{key}.csv", index=False)
    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    clean_cfg = {k: v for k, v in cfg.items() if k != "tushare_token"}
    if "lookback_days" in clean_cfg:
        clean_cfg.pop("lookback_weeks", None)
    if clean_cfg.get("rrp_return_target_mode") == "reference":
        clean_cfg.pop("m", None)
        clean_cfg.pop("rrp_target_annual_return", None)
    (OUTPUT / "configuration.json").write_text(json.dumps(clean_cfg, indent=2), encoding="utf-8")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
