"""Verify the saved 252-day rolling Global RRP experiment."""
from __future__ import annotations

from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results/global_rrp_rolling_252"
ANNUALIZATION = 252
ESTIMATION_WINDOW = 252
COST_RATE = 3.0 / 10_000.0


def _latest_schedule(schedule: pd.DataFrame, dates: pd.Series) -> pd.DataFrame:
    left = pd.DataFrame({"date": pd.to_datetime(dates)}).sort_values("date")
    right = schedule.sort_values("effective_date")
    return pd.merge_asof(
        left,
        right,
        left_on="date",
        right_on="effective_date",
        direction="backward",
    )


def _metrics(nav: pd.Series) -> dict[str, float]:
    nav = pd.Series(nav, dtype=float)
    returns = nav.pct_change().dropna()
    total_return = float(nav.iloc[-1] / nav.iloc[0] - 1.0)
    annual_return = float((1.0 + total_return) ** (ANNUALIZATION / len(nav)) - 1.0)
    volatility = float(returns.std() * np.sqrt(ANNUALIZATION))
    sharpe = float(returns.mean() / returns.std() * np.sqrt(ANNUALIZATION))
    drawdown = float((nav / nav.cummax() - 1.0).min())
    return {
        "annual_return": annual_return,
        "volatility": volatility,
        "sharpe": sharpe,
        "max_drawdown": drawdown,
        "total_return": total_return,
    }


def main() -> None:
    schedule = pd.read_csv(OUTPUT / "selected_schedule.csv")
    candidates = pd.read_csv(OUTPUT / "validation_candidates.csv")
    daily = pd.read_csv(OUTPUT / "daily_returns.csv", parse_dates=["date"])
    weekly = pd.read_csv(OUTPUT / "weekly_rebalances.csv", parse_dates=["date"])
    annual = pd.read_csv(OUTPUT / "annual_performance.csv")
    solver = pd.read_csv(OUTPUT / "solver.csv", parse_dates=["date", "information_cutoff"])
    covariance = pd.read_csv(OUTPUT / "covariance.csv", parse_dates=["date"])
    usage = pd.read_csv(OUTPUT / "asset_participation.csv")
    summary = json.loads((OUTPUT / "summary.json").read_text(encoding="utf-8"))
    config = json.loads((OUTPUT / "configuration.json").read_text(encoding="utf-8"))

    checks: dict[str, bool] = {}
    schedule["effective_date"] = pd.to_datetime(schedule.effective_date)
    schedule["information_end"] = pd.to_datetime(schedule.information_end)
    checks["ten_annual_schedule_entries"] = (
        schedule.effective_date.dt.year.tolist() == list(range(2017, 2027))
    )
    checks["schedule_uses_only_prior_information"] = bool(
        (schedule.information_end < schedule.effective_date).all()
    )

    candidate_selection_ok = True
    candidate_timing_ok = True
    stable_selection_ok = True
    for year, frame in candidates.groupby("schedule_year"):
        selected = frame[frame.selected]
        if len(selected) != 1 or not bool(selected.within_one_standard_error.iloc[0]):
            candidate_selection_ok = False
            continue
        effective = pd.Timestamp(f"{int(year)}-01-01")
        timing = (
            pd.to_datetime(frame.calibration_end) < pd.to_datetime(frame.validation_start)
        ) & (pd.to_datetime(frame.validation_end) < effective)
        candidate_timing_ok &= bool(timing.all() and frame.future_information_count.eq(0).all())
        eligible = frame[frame.within_one_standard_error]
        cells = set(zip(eligible.variance_rank.astype(int), eligible.shortfall_rank.astype(int)))
        neighbor_cells = {
            (i, j)
            for i, j in cells
            if any((i + di, j + dj) in cells for di, dj in ((-1, 0), (1, 0), (0, -1), (0, 1)))
        }
        selected_cell = (
            int(selected.variance_rank.iloc[0]),
            int(selected.shortfall_rank.iloc[0]),
        )
        stable_selection_ok &= not neighbor_cells or selected_cell in neighbor_cells
        scheduled = schedule[schedule.effective_date.dt.year == int(year)].iloc[0]
        candidate_selection_ok &= bool(
            np.isclose(selected.variance_penalty.iloc[0], scheduled.rrp_variance_penalty)
            and np.isclose(selected.shortfall_penalty.iloc[0], scheduled.lambda_pen)
        )
    checks["one_candidate_selected_per_year"] = candidate_selection_ok
    checks["candidate_windows_are_strictly_prior"] = candidate_timing_ok
    checks["selected_candidate_has_stable_neighbor_when_available"] = stable_selection_ok
    informative_years = int(
        (schedule.within_one_standard_error_count < schedule.candidate_count).sum()
    )
    checks["parameter_selection_uncertainty_is_recorded"] = bool(
        summary["parameter_selection_informative_years"] == informative_years
        and summary["parameter_selection_years"] == len(schedule)
    )

    start = pd.Timestamp(config["evaluation_start_date"])
    end = pd.Timestamp(config["evaluation_end_date"])
    solver = solver[solver.date.between(start, end)].reset_index(drop=True)
    covariance = covariance[covariance.date.between(start, end)].reset_index(drop=True)
    checks["configured_252_day_conventions"] = bool(
        config["trading_days_per_year"] == ANNUALIZATION
        and config["lookback_days"] == ESTIMATION_WINDOW
        and config["rrp_return_target_mode"] == "reference"
        and "m" not in config
    )
    checks["complete_convex_solver_path"] = bool(
        len(solver) > 0
        and solver.solver_success.all()
        and solver.problem_is_dcp.all()
        and not solver.fallback_used.any()
    )
    checks["solver_information_is_strictly_prior"] = bool(
        (solver.information_cutoff < solver.date).all()
    )
    checks["reference_return_target_is_exact"] = bool(
        solver.return_target_mode.eq("reference").all()
        and np.allclose(
            solver.target_annual_return,
            solver.reference_predicted_annual_return,
            rtol=0.0,
            atol=1e-12,
        )
    )
    expected = _latest_schedule(schedule, solver.date)
    checks["annual_parameters_are_frozen_and_match_schedule"] = bool(
        pd.to_datetime(solver.parameter_effective_date).reset_index(drop=True).equals(
            expected.effective_date.reset_index(drop=True)
        )
        and np.allclose(solver.selected_variance_penalty, expected.rrp_variance_penalty)
        and np.allclose(solver.selected_shortfall_penalty, expected.lambda_pen)
    )
    checks["constraints_satisfied"] = bool(
        np.isfinite(solver.max_constraint_violation).all()
        and solver.max_constraint_violation.max() <= 1e-6
    )

    checks["point_in_time_252_day_covariance"] = bool(
        len(covariance) == len(solver)
        and covariance.covariance_method.eq("ledoit_wolf").all()
        and covariance.covariance_annualized.all()
        and covariance.covariance_trading_days.eq(ANNUALIZATION).all()
        and covariance.covariance_point_in_time.all()
        and covariance.covariance_observations.le(ESTIMATION_WINDOW).all()
        and covariance.covariance_observations.ge(60).all()
        and not covariance.covariance_fallback_used.any()
    )

    weight_cols = [column for column in daily if column.startswith("weight_")]
    previous_weight_cols = [column for column in daily if column.startswith("previous_weight_")]
    required_numeric_cols = [
        "portfolio_return", "net_return", "gross_return", "transaction_cost",
        "turnover", "gross_exposure", "risky_exposure",
        "defensive_cash_proxy_exposure", "nav_gross", "nav_net",
        *weight_cols, *previous_weight_cols,
    ]
    checks["finite_daily_output"] = bool(
        np.isfinite(daily[required_numeric_cols].to_numpy()).all()
    )
    checks["long_only_unlevered_weights"] = bool(
        len(weight_cols) == 30
        and np.allclose(daily[weight_cols].sum(axis=1), 1.0, atol=1e-6)
        and daily[weight_cols].min().min() >= -1e-8
        and daily[weight_cols].max().max() <= 1.0 + 1e-8
    )
    checks["three_basis_point_cost_identity"] = bool(
        np.allclose(daily.transaction_cost, daily.turnover * COST_RATE, atol=1e-12)
        and np.allclose(daily.gross_return - daily.transaction_cost, daily.net_return, atol=1e-12)
    )
    expected_net_nav = (1.0 + daily.net_return).cumprod()
    expected_gross_nav = (1.0 + daily.gross_return).cumprod()
    checks["nav_matches_saved_returns"] = bool(
        np.allclose(daily.nav_net, expected_net_nav, atol=1e-12)
        and np.allclose(daily.nav_gross, expected_gross_nav, atol=1e-12)
    )
    checks["all_eligible_assets_participate"] = bool(
        len(usage) == 30
        and usage.ever_used.all()
        and usage.held_eligible_weeks.le(usage.eligible_weeks).all()
    )
    checks["weekly_and_annual_exports_are_complete"] = bool(
        len(weekly) == daily.is_rebalance_day.sum()
        and weekly.date.reset_index(drop=True).equals(
            daily.loc[daily.is_rebalance_day, "date"].reset_index(drop=True)
        )
        and annual.year.tolist() == list(range(2018, 2027))
        and annual.observations.sum() == len(daily)
    )

    net = _metrics(daily.nav_net)
    gross = _metrics(daily.nav_gross)
    summary_pairs = {
        "net_annual_return": net["annual_return"],
        "gross_annual_return": gross["annual_return"],
        "annualized_volatility": net["volatility"],
        "sharpe_ratio": net["sharpe"],
        "max_drawdown": net["max_drawdown"],
        "total_return": net["total_return"],
    }
    checks["summary_metrics_recomputed"] = all(
        np.isclose(summary[key], value, rtol=0.0, atol=1e-12)
        for key, value in summary_pairs.items()
    )

    audit = {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "evaluation_start": str(daily.date.min().date()),
        "evaluation_end": str(daily.date.max().date()),
        "daily_observations": int(len(daily)),
        "rebalance_count": int(daily.is_rebalance_day.sum()),
        "solver_count": int(len(solver)),
        "covariance_observations_min": int(covariance.covariance_observations.min()),
        "covariance_observations_max": int(covariance.covariance_observations.max()),
        "maximum_constraint_violation": float(solver.max_constraint_violation.max()),
        "minimum_weight": float(daily[weight_cols].min().min()),
        "maximum_weight": float(daily[weight_cols].max().max()),
        "parameter_selection_informative_years": informative_years,
        "recomputed_metrics": summary_pairs,
    }
    (OUTPUT / "audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(json.dumps(audit, indent=2))
    if audit["status"] != "passed":
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(f"rolling calibration audit failed: {failed}")


if __name__ == "__main__":
    main()
