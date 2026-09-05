"""Fixed, exploratory weekly constraint ablations; never promotes a winner.

Run with the repository Python. A fresh run refreshes both data sources first.
--resume reuses successful variants only after checking configurations and inputs.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.public_oos import load_public_oos_result, load_public_oos_selection, public_candidate_configs, run_public_oos_variant
from scripts.run_convex_adaptive_rrp import summarize_result
from src.convex_adaptive_rrp import rebalance_dates_for_frequency, scenario_cvar
from src.data_loader import load_price_data, price_to_returns
from src.risk_free import load_daily_risk_free_returns
from src.utils import get_config, infer_asset_class

VARIANTS = (
    "monthly_control", "weekly_baseline", "no_cash_cap", "no_asset_cap",
    "no_concentration_caps", "no_turnover_cap", "ledoit_wolf",
    "relative_cvar", "ledoit_wolf_relative_cvar",
)
SOLVER_TOL = 5e-5  # Existing optimizer post-solve feasibility acceptance.
METRICS = ("net_annual_return", "annualized_volatility", "sharpe_ratio", "sortino_ratio", "max_drawdown", "avg_monthly_turnover")


def log_event(output, event, **details):
    with (output / "run_events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"time_utc": datetime.now(timezone.utc).isoformat(), "event": event, **details}, ensure_ascii=False) + "\n")


def unfiltered_returns(prices):
    """Keep realized extreme moves; forward-fill only already-observed prices.

    Never use future distribution statistics or backfill a not-yet-listed ETF.
    The first observation has no return and is excluded, as in the public loader.
    """
    clean = prices.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan).sort_index()
    if (clean <= 0).any().any():
        raise ValueError("nonpositive adjusted prices")
    return price_to_returns(clean)


def legacy_reproduction_returns(prices):
    """Audit-only reproduction of the obsolete, future-dependent input masking.

    Never use this series for the main experiments or production backtests.
    """
    returns = price_to_returns(prices)

    def mask_full_sample_outliers(series):
        clean = series.dropna()
        if clean.empty:
            return series
        mean, std = clean.mean(), clean.std()
        if not np.isfinite(std) or std <= 0:
            return series
        return series.mask((series - mean).abs() > 3 * std)

    return returns.apply(mask_full_sample_outliers).dropna(how="all")


def variant_config(config, variant):
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant: {variant}")
    cfg = replace(config, rebalance_frequency="M" if variant == "monthly_control" else "W", group_bounds=dict(config.group_bounds))
    if variant in {"no_cash_cap", "no_concentration_caps"}:
        cfg.group_bounds.pop("cash", None)
    if variant in {"no_asset_cap", "no_concentration_caps"}:
        cfg.max_weight = 1.0
    if variant == "no_turnover_cap":
        cfg.turnover_cap = None
    if variant.startswith("ledoit_wolf"):
        cfg.covariance_method = "ledoit_wolf"
        cfg.covariance_allow_fallback = False
    return cfg


def check_result(result, solver, returns, *, monthly=False):
    dates = pd.DatetimeIndex(result.date)
    if not dates.equals(returns.index) or dates.has_duplicates:
        raise ValueError("result does not cover the common evaluation dates exactly")
    cols = [f"weight_{c}" for c in returns.columns]
    weights = result[cols].to_numpy(float)
    numeric = result[["gross_return", "net_return", "turnover", "transaction_cost"]].to_numpy(float)
    if not np.isfinite(weights).all() or not np.isfinite(numeric).all():
        raise ValueError("non-finite weights or returns")
    if weights.min() < -SOLVER_TOL or not np.allclose(weights.sum(axis=1), 1, atol=SOLVER_TOL, rtol=0):
        raise ValueError("long-only unlevered budget violated")
    if not np.allclose(result.transaction_cost, result.turnover * 0.0003, atol=1e-10, rtol=0):
        raise ValueError("cost does not equal 3 bps times L1 turnover")
    if not np.allclose(result.net_return, result.gross_return - result.transaction_cost, atol=1e-10, rtol=0):
        raise ValueError("net return accounting mismatch")
    if not np.allclose((returns.fillna(0).to_numpy() * weights).sum(axis=1), result.gross_return, atol=1e-10, rtol=0):
        raise ValueError("gross return does not match deployed weights")
    missing_weight = np.where(returns.isna().to_numpy(), weights, 0).sum(axis=1)
    if missing_weight.max() > SOLVER_TOL:
        raise ValueError("material exposure has missing execution-day returns")
    previous = result[[f"previous_weight_{c}" for c in returns.columns]].to_numpy(float)
    if not np.isfinite(previous).all() or not np.allclose(np.abs(weights - previous).sum(axis=1), result.turnover, atol=1e-8, rtol=0):
        raise ValueError("pre-trade weights disagree with turnover")
    expected_prior = weights[:-1] * (1 + returns.fillna(0).to_numpy()[:-1]) / (1 + result.gross_return.to_numpy()[:-1, None])
    if not np.allclose(previous[1:], expected_prior, atol=1e-8, rtol=0):
        raise ValueError("pre-trade weights do not reflect previous-day drift")
    expected = rebalance_dates_for_frequency(returns, "M" if monthly else "W")
    if set(dates[result.is_rebalance_day.astype(bool)]) != expected:
        raise ValueError("weekly rebalance calendar mismatch")
    if set(pd.to_datetime(solver.date)) != expected:
        raise ValueError("a weekly rebalance lacks a solver result")
    if not (pd.to_datetime(solver.information_cutoff) < pd.to_datetime(solver.date)).all():
        raise ValueError("future information at a rebalance")
    if solver.max_constraint_violation.max() > SOLVER_TOL or solver.fallback_used.any():
        raise ValueError("solver acceptance failed")


def result_summary(variant, result, config):
    summary = summarize_result(variant, result, str(result.date.min().date()), config)
    weights = result.filter(regex="^weight_")
    summary.update({
        "variant": variant, "status": "passed", "target_met": bool(summary["sharpe_ratio"] >= 1.0),
        "observations": len(result), "sample_start": str(result.date.min().date()),
        "sample_end": str(result.date.max().date()),
        "scenario_cvar_95_daily_loss": scenario_cvar(-result.net_return.to_numpy()),
        "mean_hhi": float(weights.pow(2).sum(axis=1).mean()),
        "max_single_asset_weight": float(weights.max().max()),
        "total_transaction_cost": float(result.transaction_cost.sum()),
        "rebalance_count": int(result.is_rebalance_day.sum()),
    })
    for group in ("cash", "bond", "defensive", "commodity_gold", "equity"):
        columns = [c for c in weights if infer_asset_class(c.removeprefix("weight_")) == group]
        exposure = weights[columns].sum(axis=1)
        summary[f"mean_{group}_weight"] = float(exposure.mean())
        summary[f"max_{group}_weight"] = float(exposure.max())
    return summary


def save_variant(folder, result, solver):
    folder.mkdir(parents=True, exist_ok=True)
    result.to_csv(folder / "daily_returns.csv", index=False)
    result[["date", *result.filter(regex="^weight_").columns]].to_csv(folder / "weights.csv", index=False)
    trade_cols = ["date", "turnover", "transaction_cost", *result.filter(regex="^(previous_weight_|weight_)").columns]
    result.loc[result.is_rebalance_day.astype(bool), trade_cols].to_csv(folder / "trades.csv", index=False)
    records = []
    for _, row in solver.iterrows():
        for constraint in json.loads(row.get("constraints_json", "[]")):
            records.append({"date": row.date, **constraint})
    pd.DataFrame(records, columns=["date", "constraint", "component", "lhs", "rhs", "slack", "dual", "binding"]).to_csv(folder / "constraints.csv", index=False)
    solver.drop(columns="constraints_json", errors="ignore").to_csv(folder / "solver_diagnostics.csv", index=False)


def refresh_data(output):
    if not os.environ.get("TUSHARE_TOKEN"):
        raise RuntimeError("Set TUSHARE_TOKEN before refreshing data; no backtests were run")
    commands = [
        [sys.executable, "scripts/update_etf_data.py", "--provider", "tushare", "--start-date", "20000101", "--end-date", "20260831"],
        [sys.executable, "scripts/update_risk_free_rate.py", "--start-date", "20000101", "--end-date", "20260831"],
    ]
    for number, command in enumerate(commands):
        print(f"Refreshing {Path(command[1]).name}", flush=True)
        log_event(output, "refresh_started", command=command)
        with (output / f"refresh_{number}.log").open("w", encoding="utf-8") as log:
            subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
        log_event(output, "refresh_passed", command=command)
    (output / "refresh_complete.json").write_text(json.dumps({"commands": commands, "completed_utc": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")


def run(output, resume=False, *, risk_free_zero=False, selected_variant=None):
    if selected_variant is not None and selected_variant not in VARIANTS:
        raise ValueError(f"unknown variant: {selected_variant}")
    variants = VARIANTS if selected_variant is None else tuple(
        v for v in VARIANTS if v in {"monthly_control", "weekly_baseline", selected_variant}
    )
    if not os.environ.get("TUSHARE_TOKEN"):
        raise RuntimeError("TUSHARE_TOKEN missing; refusing to run or overwrite results")
    if output.exists() and not resume:
        raise ValueError("output already exists; use --resume to verify inputs and reuse successful experiments")
    output.mkdir(parents=True, exist_ok=True)
    if not (resume and (output / "refresh_complete.json").exists()):
        refresh_data(output)
    config = get_config({"transaction_cost_bps": 3.0, "trading_days_per_year": 243})
    config["risk_free_rate"] = None
    published_config = config.copy()
    if risk_free_zero:
        config["risk_free_rate"] = 0.0
    prices = load_price_data("tushare").loc[:config["evaluation_end_date"]]
    legacy_returns = legacy_reproduction_returns(prices)
    returns = unfiltered_returns(prices)
    evaluation = returns.loc[config["evaluation_start_date"]:]
    monthly = load_public_oos_result(ROOT / "results/legacy_monthly_reference/improved_convex_adaptive_global_relaxed_risk_parity_returns.csv")
    selection = load_public_oos_selection()
    if not (selection.validation_end < selection.test_start).all():
        raise ValueError("public selection includes future validation information")
    rf = pd.Series(0.0, index=evaluation.index, name="risk_free_return") if risk_free_zero else load_daily_risk_free_returns(evaluation.index)
    configurations = {
        variant: {cid: asdict(variant_config(cfg, variant)) for cid, cfg in public_candidate_configs(3.0).items()}
        for variant in variants
    }
    manifest = {"variants": configurations, "relative_cvar_variants": [v for v in VARIANTS if "relative_cvar" in v],
                "evaluation_start": config["evaluation_start_date"], "evaluation_end": config["evaluation_end_date"],
                "target_sharpe": 1.0, "constraint_tolerance": SOLVER_TOL,
                "return_input": "Unfiltered adjusted-close percentage changes; no full-sample outlier masking. Monthly control rerun on identical inputs. Published weekly metrics reproduced separately with the legacy loader.",
                "interpretation": "Exploratory fixed-grid ablation; no candidate reselection or public promotion. Existing return accounting and warm-up retained. Scenario CVaR uses fractional tail mass; legacy CVaR also reported for comparability. Paired differences are descriptive, not significance tests."}
    if risk_free_zero:
        manifest["risk_free_rate"] = 0.0
        manifest["risk_free_convention"] = "User-specified zero rate; a reporting assumption, not a portfolio return improvement. Public schedule remains frozen. Legacy reproduction retains the published ChinaBond convention."
    manifest_text = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2)
    manifest_path = output / "configurations.json"
    has_success = any((output / v / "success.json").exists() for v in (*VARIANTS, "legacy_weekly_reproduction"))
    if resume and has_success and manifest_path.exists() and manifest_path.read_text(encoding="utf-8") != manifest_text:
        raise ValueError("resume configuration mismatch")
    manifest_path.write_text(manifest_text, encoding="utf-8")
    for name, frame in {"input_returns": legacy_returns, "unfiltered_input_returns": returns, "risk_free_returns": rf.to_frame(), "public_selection": selection, "monthly_input": monthly}.items():
        path = output / f"{name}.csv"
        # Compare serialized inputs before reuse; no hashes or cached-score guessing.
        serialized = frame.to_csv(index=True, lineterminator="\n")
        if resume and has_success and path.exists() and path.read_text(encoding="utf-8") != serialized:
            raise ValueError(f"resume input mismatch: {name}")
        path.write_text(serialized, encoding="utf-8")
    frequency = pd.read_csv(ROOT / "results/legacy_monthly_reference/rebalance_frequency_sensitivity.csv")
    historical_weekly = frequency.loc[frequency.frequency_code.eq("W")].iloc[0]
    if not (resume and (output / "legacy_weekly_reproduction/success.json").exists()):
        print("Reproducing published weekly metrics with legacy inputs (not OOS evidence)", flush=True)
        log_event(output, "legacy_reproduction_started")
        legacy_folder = output / "legacy_weekly_reproduction"
        legacy_cached = resume and (legacy_folder / "daily_returns.csv").exists() and (legacy_folder / "solver_diagnostics.csv").exists()
        if legacy_cached:
            legacy_result = pd.read_csv(legacy_folder / "daily_returns.csv", parse_dates=["date"])
            legacy_solver = pd.read_csv(legacy_folder / "solver_diagnostics.csv")
        else:
            legacy_result, legacy_solver = run_public_oos_variant(legacy_returns, primary_model=False, selection=selection, transform=lambda cfg: variant_config(cfg, "weekly_baseline"), collect_constraint_diagnostics=True)
        summary = result_summary("legacy_weekly_reproduction", legacy_result, published_config)
        differences = {key: summary[key] - float(historical_weekly[key]) for key in METRICS}
        (output / "baseline_reproduction.json").write_text(json.dumps(differences, indent=2), encoding="utf-8")
        if max(abs(value) for value in differences.values()) > SOLVER_TOL:
            raise ValueError(f"legacy weekly baseline does not reproduce published metrics: {differences}")
        folder = output / "legacy_weekly_reproduction"
        if not legacy_cached:
            save_variant(folder, legacy_result, legacy_solver)
        (folder / "success.json").write_text(json.dumps(summary), encoding="utf-8")
        mask = legacy_returns.reindex(evaluation.index).isna() & evaluation.notna()
        weights = monthly.filter(regex="^weight_").copy()
        weights.columns = weights.columns.str.removeprefix("weight_")
        weights.index = pd.DatetimeIndex(monthly.date)
        audit = {"legacy_full_sample_mask_count": int(mask.sum().sum()),
                 "max_published_monthly_weight_on_masked_return": float(weights.where(mask, 0).sum(axis=1).max()),
                 "legacy_reproduction_is_valid_oos_evidence": False,
                 "research_uses_unfiltered_returns": True,
                 "published_schedule_is_fixed_not_reestimated": True,
                 "selected_ids": selection.selected_candidate_id.unique().tolist()}
        (output / "data_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
        log_event(output, "legacy_reproduction_passed", **differences)
    rows, annual, paired = [], [], []
    baseline_result = None
    baseline_metrics = None
    for variant in variants:
        started = time.monotonic()
        folder = output / variant
        print(f"Running {variant}", flush=True)
        log_event(output, "variant_started", variant=variant)
        try:
            receipt = folder / "success.json"
            if resume and receipt.exists():
                result = pd.read_csv(folder / "daily_returns.csv", parse_dates=["date"])
                solver_path = folder / "solver_diagnostics.csv"
                solver = pd.read_csv(solver_path) if solver_path.stat().st_size > 3 else pd.DataFrame()
            else:
                result, solver = run_public_oos_variant(
                    returns, selection=selection, primary_model=False, transform=lambda cfg: variant_config(cfg, variant),
                    collect_constraint_diagnostics=True, relative_cvar_to_baseline="relative_cvar" in variant,
                )
            check_result(result, solver, evaluation, monthly=variant == "monthly_control")
            summary = result_summary(variant, result, config)
            if risk_free_zero:
                summary["risk_free_rate"] = 0.0
                summary["sharpe_with_published_risk_free"] = result_summary(variant, result, published_config)["sharpe_ratio"]
            if variant == "weekly_baseline":
                baseline_result, baseline_metrics = result, summary
            if variant == "monthly_control":
                monthly = result
            if baseline_result is not None:
                paired.append(pd.DataFrame({"date": result.date, "variant": variant, "net_return_difference": result.net_return - baseline_result.net_return}))
                weight_difference = result.filter(regex="^weight_") - baseline_result.filter(regex="^weight_")
                summary["max_weight_difference_vs_weekly"] = float(weight_difference.abs().max().max())
                summary["mean_l1_weight_difference_vs_weekly"] = float(weight_difference.abs().sum(axis=1).mean())
                for key in METRICS:
                    summary[f"delta_vs_weekly_{key}"] = summary[key] - baseline_metrics[key]
            if not solver.empty:
                summary["group_bounds_relaxed_count"] = int(solver.group_bounds_point_in_time_relaxed.sum())
                summary["max_constraint_violation"] = float(solver.max_constraint_violation.max())
                summary["relative_cvar_max_weight_difference"] = float(solver.relative_cvar_weight_difference.max())
                summary["relative_cvar_numerically_redundant"] = bool(solver.relative_cvar_weight_difference.max() <= SOLVER_TOL) if "relative_cvar" in variant else None
            for year, subset in result.groupby(result.date.dt.year):
                annual.append({"year": int(year), **result_summary(variant, subset, config)})
            if not (resume and receipt.exists()):
                save_variant(folder, result, solver)
                receipt.write_text(json.dumps({"completed_utc": datetime.now(timezone.utc).isoformat()}), encoding="utf-8")
            rows.append({**summary, "elapsed_seconds": time.monotonic() - started})
            log_event(output, "variant_passed", variant=variant, sharpe=summary["sharpe_ratio"], elapsed_seconds=rows[-1]["elapsed_seconds"])
        except Exception as exc:
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
            rows.append({"variant": variant, "status": "failed", "target_met": False, "error": str(exc), "elapsed_seconds": time.monotonic() - started})
            log_event(output, "variant_failed", variant=variant, error=str(exc))
            if variant in {"monthly_control", "weekly_baseline"}:
                rows.extend({"variant": v, "status": "blocked", "target_met": False, "error": f"control validation failed: {variant}"} for v in variants[len(rows):])
                break
        pd.DataFrame(rows).to_csv(output / "summary.csv", index=False)
        print(f"{variant}: {rows[-1]['status']} Sharpe={rows[-1].get('sharpe_ratio', 'unavailable')}", flush=True)
    table = pd.DataFrame(rows)
    if baseline_metrics is not None:
        for key in METRICS:
            table[f"delta_vs_weekly_{key}"] = table[key] - baseline_metrics[key]
        paired.insert(0, pd.DataFrame({"date": monthly.date, "variant": "monthly_control", "net_return_difference": monthly.net_return - baseline_result.net_return}))
        monthly_difference = monthly.filter(regex="^weight_") - baseline_result.filter(regex="^weight_")
        table.loc[table.variant.eq("monthly_control"), "max_weight_difference_vs_weekly"] = float(monthly_difference.abs().max().max())
        table.loc[table.variant.eq("monthly_control"), "mean_l1_weight_difference_vs_weekly"] = float(monthly_difference.abs().sum(axis=1).mean())
    table.to_csv(output / "summary.csv", index=False)
    pd.DataFrame(annual).to_csv(output / "annual_summary.csv", index=False)
    if paired:
        pd.concat(paired, ignore_index=True).to_csv(output / "paired_daily_differences.csv", index=False)
    print(table[["variant", "status", "target_met", *(["sharpe_ratio"] if "sharpe_ratio" in table else [])]].to_string(index=False), flush=True)
    return 0 if table.status.eq("passed").all() else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--risk-free-zero", action="store_true", help="Use the user-specified zero risk-free rate and a separate output directory.")
    parser.add_argument("--variant", choices=VARIANTS, help="Run a selected experiment together with monthly and weekly controls.")
    args = parser.parse_args()
    output = ROOT / ("results/weekly_constraint_research_rf0" if args.risk_free_zero else "results/weekly_constraint_research")
    if not os.environ.get("TUSHARE_TOKEN"):
        parser.error("TUSHARE_TOKEN missing; existing results are untouched")
    if output.exists() and not args.resume:
        parser.error("output already exists; use --resume to verify inputs and reuse successful experiments")
    try:
        code = run(output, args.resume, risk_free_zero=args.risk_free_zero, selected_variant=args.variant)
    except Exception:
        if output.exists():
            (output / "run_failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise
    finally:
        # Run the repository's mandated cleanup only after research execution.
        if output.exists():
            with (output / "cleanup.log").open("w", encoding="utf-8") as cleanup_log:
                subprocess.run([sys.executable, "scripts/cleanup_temp.py"], cwd=ROOT, stdout=cleanup_log, stderr=subprocess.STDOUT, check=True)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
