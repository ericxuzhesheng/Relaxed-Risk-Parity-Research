from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.run_frozen_oos_validation import selected_candidate
from src.convex_adaptive_rrp import ConvexRRPConfig, run_convex_adaptive_backtest
from src.data_loader import load_data
from src.utils import get_config, resolve_path
from src.validation import candidate_params_json, ensure_datetime_index, result_window_metrics


def build_variants(base: ConvexRRPConfig) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = [
        {
            "variant_id": "baseline_selected_candidate",
            "cvar_beta": base.cvar_beta,
            "lookback_days": base.lookback_days,
            "cfg": base,
            "is_baseline": True,
        }
    ]
    betas = [0.90, 0.95, 0.975, 0.99]
    lookbacks = [126, 252, 504]
    baseline_key = (float(base.cvar_beta), int(base.lookback_days))
    for beta in betas:
        for lookback in lookbacks:
            if (beta, lookback) == baseline_key:
                continue
            params = {
                **base.__dict__,
                "cvar_beta": beta,
                "lookback_days": lookback,
            }
            cfg = ConvexRRPConfig(**params)
            rows.append(
                {
                    "variant_id": f"beta_{str(beta).replace('.', '_')}_lb_{lookback}",
                    "cvar_beta": beta,
                    "lookback_days": lookback,
                    "cfg": cfg,
                    "is_baseline": False,
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CVaR sensitivity diagnostics for the convex adaptive candidate.")
    parser.add_argument("--output-dir", default="results/tables")
    parser.add_argument("--eval-start", default="2021-01-01")
    parser.add_argument("--sample-start", default="2018-01-02")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    config = get_config({"transaction_cost_bps": 3.0})
    returns = ensure_datetime_index(load_data(source="tushare", force_update=False))
    returns = returns[(returns.index >= pd.Timestamp(args.sample_start)) & (returns.index <= pd.Timestamp("2026-04-30"))]
    if returns.empty:
        raise ValueError("CVaR sensitivity returns are empty.")

    candidate_id, base_cfg = selected_candidate(config["transaction_cost_bps"])
    variants = build_variants(base_cfg)
    if args.smoke:
        variants = variants[:4]

    detail_rows: list[dict] = []
    for i, variant in enumerate(variants, start=1):
        cfg = variant["cfg"]
        print(f"Running CVaR sensitivity variant {i}/{len(variants)}: {variant['variant_id']}")
        result, solver_diag, _, _ = run_convex_adaptive_backtest(returns, cfg)
        metrics = result_window_metrics(result, pd.Timestamp(args.eval_start), returns.index.max(), config)
        detail_rows.append(
            {
                "variant_id": variant["variant_id"],
                "base_candidate_id": candidate_id,
                "cvar_beta": variant["cvar_beta"],
                "lookback_days": variant["lookback_days"],
                "is_baseline": bool(variant["is_baseline"]),
                "params_json": candidate_params_json(cfg),
                "solver_fallback_rate": float(solver_diag["fallback_used"].mean()) if not solver_diag.empty else 1.0,
                **metrics,
            }
        )

    detail = pd.DataFrame(detail_rows)
    base_row = detail.loc[detail["is_baseline"]].iloc[0].copy()
    for col in ["net_annual_return", "annual_volatility", "sharpe", "calmar", "max_drawdown", "cvar", "annual_turnover", "avg_monthly_turnover", "total_return"]:
        detail[f"delta_{col}"] = detail[col] - float(base_row[col])

    summary_rows = []
    for beta in sorted(detail["cvar_beta"].unique()):
        group = detail[detail["cvar_beta"].eq(beta)]
        summary_rows.append(
            {
                "row_type": "beta_summary",
                "cvar_beta": beta,
                "lookback_days": None,
                "net_annual_return_mean": float(group["net_annual_return"].mean()),
                "sharpe_mean": float(group["sharpe"].mean()),
                "max_drawdown_mean": float(group["max_drawdown"].mean()),
                "cvar_mean": float(group["cvar"].mean()),
                "avg_monthly_turnover_mean": float(group["avg_monthly_turnover"].mean()),
                "validation_status": "cvar_sensitivity",
            }
        )
    for lookback in sorted(detail["lookback_days"].unique()):
        group = detail[detail["lookback_days"].eq(lookback)]
        summary_rows.append(
            {
                "row_type": "lookback_summary",
                "cvar_beta": None,
                "lookback_days": lookback,
                "net_annual_return_mean": float(group["net_annual_return"].mean()),
                "sharpe_mean": float(group["sharpe"].mean()),
                "max_drawdown_mean": float(group["max_drawdown"].mean()),
                "cvar_mean": float(group["cvar"].mean()),
                "avg_monthly_turnover_mean": float(group["avg_monthly_turnover"].mean()),
                "validation_status": "cvar_sensitivity",
            }
        )
    summary_rows.append(
        {
            "row_type": "overall",
            "cvar_beta": None,
            "lookback_days": None,
            "net_annual_return_mean": float(detail["net_annual_return"].mean()),
            "sharpe_mean": float(detail["sharpe"].mean()),
            "max_drawdown_mean": float(detail["max_drawdown"].mean()),
            "cvar_mean": float(detail["cvar"].mean()),
            "avg_monthly_turnover_mean": float(detail["avg_monthly_turnover"].mean()),
            "validation_status": "cvar_sensitivity",
        }
    )
    summary = pd.DataFrame(summary_rows)
    summary["base_candidate_id"] = candidate_id
    summary["sample_start"] = pd.Timestamp(args.sample_start).date().isoformat()
    summary["sample_end"] = pd.Timestamp(returns.index.max()).date().isoformat()
    summary["eval_start"] = pd.Timestamp(args.eval_start).date().isoformat()
    summary["eval_end"] = pd.Timestamp(returns.index.max()).date().isoformat()
    summary["candidate_count"] = len(variants)
    summary["notes"] = (
        "Parameter sensitivity over CVaR confidence levels 90%, 95%, 97.5% and 99% "
        "with lookbacks 126/252/504."
    )

    output_dir = Path(resolve_path(args.output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)
    detail.to_csv(output_dir / "cvar_sensitivity.csv", index=False)
    summary.to_csv(output_dir / "cvar_sensitivity_summary.csv", index=False)
    print(f"Saved CVaR sensitivity summary to {output_dir}")


if __name__ == "__main__":
    main()
