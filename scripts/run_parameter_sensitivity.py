from __future__ import annotations

import argparse
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.public_oos import modal_selected_config, run_public_oos_variant
from src.convex_adaptive_rrp import ConvexRRPConfig
from src.data_loader import load_data
from src.utils import get_config, resolve_path
from src.validation import VALIDATION_STATUS, candidate_params_json, ensure_datetime_index, result_window_metrics


def build_variants(base: ConvexRRPConfig) -> list[tuple[str, str, ConvexRRPConfig]]:
    params = asdict(base)

    def variant(name: str, field: str, value) -> tuple[str, str, ConvexRRPConfig]:
        updated = params.copy()
        updated[field] = value
        return name, field, ConvexRRPConfig(**updated)

    variants = [("base", "base", base)]
    variants.extend(
        [
            variant("lookback_down", "lookback_days", max(60, int(base.lookback_days * 0.75))),
            variant("lookback_up", "lookback_days", int(base.lookback_days * 1.25)),
            variant("covariance_sample", "covariance_method", "sample"),
            variant("max_weight_down", "max_weight", max(0.20, base.max_weight - 0.05)),
            variant("max_weight_up", "max_weight", min(0.60, base.max_weight + 0.05)),
            variant("turnover_cap_down", "turnover_cap", None if base.turnover_cap is None else max(0.05, base.turnover_cap * 0.75)),
            variant("turnover_cap_up", "turnover_cap", None if base.turnover_cap is None else base.turnover_cap * 1.25),
            variant("turnover_penalty_down", "turnover_penalty", max(0.0, base.turnover_penalty * 0.5)),
            variant("turnover_penalty_up", "turnover_penalty", base.turnover_penalty * 1.5 + 0.001),
            variant("cvar_penalty_down", "cvar_penalty", max(0.0, base.cvar_penalty * 0.5)),
            variant("cvar_penalty_up", "cvar_penalty", base.cvar_penalty * 1.5 + 0.001),
            variant("budget_penalty_down", "budget_penalty", max(0.0, base.budget_penalty * 0.5)),
            variant("budget_penalty_up", "budget_penalty", base.budget_penalty * 1.5 + 0.001),
            variant("ewma_halflife_down", "ewma_halflife", max(20.0, base.ewma_halflife * 0.67)),
            variant("ewma_halflife_up", "ewma_halflife", base.ewma_halflife * 1.50),
            variant("transaction_cost_bps_down", "transaction_cost_bps", max(0.0, base.transaction_cost_bps - 2.0)),
            variant("transaction_cost_bps_up", "transaction_cost_bps", base.transaction_cost_bps + 2.0),
        ]
    )
    return variants


def interpretation(delta_sharpe: float, delta_drawdown: float, delta_turnover: float) -> str:
    if abs(delta_sharpe) < 0.10 and abs(delta_drawdown) < 0.01 and abs(delta_turnover) < 0.01:
        return "robust"
    if delta_sharpe < -0.25 or delta_drawdown < -0.02:
        return "fragile"
    return "moderate"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one-at-a-time parameter sensitivity around the selected improved candidate.")
    parser.add_argument("--output-dir", default="results/tables")
    parser.add_argument("--max-candidates", type=int, default=None, help="Accepted for CLI consistency; ignored.")
    parser.add_argument("--eval-start", default="2018-01-02")
    parser.add_argument("--smoke", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()

    config = get_config({"transaction_cost_bps": 3.0})
    returns = ensure_datetime_index(load_data(source="tushare", force_update=False))
    metric_start = pd.Timestamp(args.eval_start)
    returns = returns[returns.index <= returns.index.max()]
    _modal_candidate_id, base_cfg = modal_selected_config(config["transaction_cost_bps"])
    base_id = "afml_rolling_oos_schedule"
    variants = build_variants(base_cfg)
    if args.smoke:
        variants = variants[:4]

    rows = []
    for i, (variant_id, parameter, cfg) in enumerate(variants, start=1):
        print(f"Running sensitivity variant {i}/{len(variants)}: {variant_id}")
        transform = (
            (lambda original: original)
            if parameter == "base"
            else (lambda original, field=parameter, value=getattr(cfg, parameter): replace(original, **{field: value}))
        )
        result, solver = run_public_oos_variant(
            returns,
            transaction_cost_bps=config["transaction_cost_bps"],
            transform=transform,
        )
        metrics = result_window_metrics(result, metric_start, returns.index.max(), config)
        fallback_rate = float(solver["fallback_used"].mean()) if not solver.empty else 1.0
        rows.append(
            {
                "variant_id": variant_id,
                "base_candidate_id": base_id,
                "perturbed_parameter": parameter,
                "params_json": candidate_params_json(cfg),
                "solver_fallback_rate": fallback_rate,
                **metrics,
                "validation_status": VALIDATION_STATUS,
                "diagnostic_scope": "published_afml_oos_selection_schedule_held_constant",
                "candidate_reselection": False,
            }
        )
    detail = pd.DataFrame(rows)
    base = detail[detail["variant_id"].eq("base")].iloc[0]
    for col in ["net_annual_return", "annual_volatility", "sharpe", "calmar", "max_drawdown", "cvar", "annual_turnover", "avg_monthly_turnover", "total_return"]:
        detail[f"delta_{col}"] = detail[col] - float(base[col])
    detail["interpretation"] = detail.apply(
        lambda row: interpretation(row["delta_sharpe"], row["delta_max_drawdown"], row["delta_avg_monthly_turnover"]),
        axis=1,
    )
    summary = (
        detail[detail["variant_id"].ne("base")]
        .groupby("perturbed_parameter")
        .agg(
            max_abs_delta_sharpe=("delta_sharpe", lambda x: float(x.abs().max())),
            max_abs_delta_drawdown=("delta_max_drawdown", lambda x: float(x.abs().max())),
            max_abs_delta_turnover=("delta_avg_monthly_turnover", lambda x: float(x.abs().max())),
            worst_interpretation=("interpretation", lambda x: "fragile" if "fragile" in set(x) else ("moderate" if "moderate" in set(x) else "robust")),
        )
        .reset_index()
    )
    summary["validation_status"] = VALIDATION_STATUS
    summary["diagnostic_scope"] = "published_afml_oos_selection_schedule_held_constant"

    output_dir = Path(resolve_path(args.output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)
    detail.to_csv(output_dir / "parameter_sensitivity.csv", index=False)
    summary.to_csv(output_dir / "parameter_sensitivity_summary.csv", index=False)
    print(f"Saved {len(detail)} parameter sensitivity rows to {output_dir}")


if __name__ == "__main__":
    main()
