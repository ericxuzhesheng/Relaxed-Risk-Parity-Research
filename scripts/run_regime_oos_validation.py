from __future__ import annotations

"""Out-of-sample validation for the regime-conditional covariance prior.

The state-frequency prior sweep in ``run_regime_covariance_experiment`` showed
that an aggressive prior improves the Improved Convex Adaptive RRP over the full
2019.. evaluation window. That selection inspected the whole period, so the
prior choice could be in-sample overfitting. This script removes that look-ahead:

* **Selection stage** — the regime prior is chosen *only* on a design window
  (default 2019-01-01..2023-12-31) by the repository's ``validation_score``;
  the backtest history is truncated at the design end so selection never sees
  post-design data.
* **Out-of-sample stage** — the design-selected prior, the default prior, the
  aggressive prior, and the standard EWMA baseline are each evaluated on the
  held-out window (default 2024-01-01..end). Metrics are reported on the OOS
  slice only; the rolling backtest remains point-in-time.

A second holdout at 2025-01-01 is reported for robustness. Outputs are written
with the standard validation-status metadata. This is a validation-only
diagnostic; it does not re-select any headline model.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.run_convex_adaptive_rrp import candidate_configurations
from src.convex_adaptive_rrp import ConvexRRPConfig
from src.data_loader import load_data
from src.utils import get_config, resolve_path
from src.validation import (
    VALIDATION_STATUS,
    ensure_datetime_index,
    evaluate_candidate_window,
    next_trading_day,
    validation_score,
)

PRIOR_GRID: list[tuple[float, float]] = [
    (0.40, 0.50),
    (0.50, 0.50),
    (0.50, 0.75),
    (0.60, 0.75),
    (0.67, 1.00),
]


def selected_full_improved_config(transaction_cost_bps: float) -> ConvexRRPConfig:
    """Reconstruct the exact headline Improved config (vol-target preserved)."""
    candidates_path = ROOT_DIR / "results" / "tables" / "convex_adaptive_improvement_candidates.csv"
    candidates = pd.read_csv(candidates_path)
    selected = candidates[candidates["selected"].astype(str).str.lower().eq("true")]
    if selected.empty:
        raise ValueError(f"No selected improved row found in {candidates_path}")
    selected_name = str(selected.iloc[0]["candidate_name"])
    for name, cfg in candidate_configurations(transaction_cost_bps):
        if name == selected_name:
            return cfg
    raise ValueError(f"Selected candidate {selected_name} not found in candidate_configurations")


def with_regime(cfg: ConvexRRPConfig, method: str, crisis_prior: float | None = None, prior_weight: float | None = None) -> ConvexRRPConfig:
    params = {**cfg.__dict__, "covariance_method": method, "covariance_allow_fallback": True}
    if crisis_prior is not None:
        params["regime_crisis_prior"] = crisis_prior
    if prior_weight is not None:
        params["regime_prior_weight"] = prior_weight
    return ConvexRRPConfig(**params)


def main() -> None:
    parser = argparse.ArgumentParser(description="OOS validation of the regime-conditional covariance prior.")
    parser.add_argument("--design-start", default="2019-01-01")
    parser.add_argument("--design-end", default="2023-12-31")
    parser.add_argument("--oos-start", default="2024-01-01")
    parser.add_argument("--secondary-holdout", default="2025-01-01")
    parser.add_argument("--output-dir", default="results/tables")
    args = parser.parse_args()

    config = get_config({"transaction_cost_bps": 3.0})
    returns = ensure_datetime_index(load_data(source="tushare", force_update=False))
    full_start = pd.Timestamp(returns.index.min())
    full_end = pd.Timestamp(returns.index.max())
    base = selected_full_improved_config(config["transaction_cost_bps"])
    print(f"Sample: {full_start.date()} .. {full_end.date()}; design ends {args.design_end}, OOS from {args.oos_start}")

    design_start = pd.Timestamp(args.design_start)
    design_end = pd.Timestamp(args.design_end)

    # --- Selection stage: choose the prior on the design window only. ---
    selection_rows = []
    for crisis_prior, prior_weight in PRIOR_GRID:
        cfg = with_regime(base, "regime_conditional", crisis_prior, prior_weight)
        metrics, fallback, _ = evaluate_candidate_window(returns, cfg, full_start, design_end, design_start, design_end, config)
        score = validation_score(metrics, fallback)
        selection_rows.append({
            "crisis_prior": crisis_prior, "prior_weight": prior_weight,
            "design_sharpe": metrics["sharpe"], "design_max_drawdown": metrics["max_drawdown"],
            "design_calmar": metrics["calmar"], "design_avg_monthly_turnover": metrics["avg_monthly_turnover"],
            "design_selection_score": score, "design_solver_fallback_rate": fallback,
        })
    selection = pd.DataFrame(selection_rows).sort_values("design_selection_score", ascending=False).reset_index(drop=True)
    best = selection.iloc[0]
    sel_prior, sel_weight = float(best["crisis_prior"]), float(best["prior_weight"])
    print(f"\nDesign-window selected prior: crisis_prior={sel_prior}, prior_weight={sel_weight}")
    print(selection.to_string(index=False))

    # --- OOS stage: evaluate fixed configs on each holdout window. ---
    arms = {
        "baseline_ewma": with_regime(base, "ewma"),
        "regime_selected": with_regime(base, "regime_conditional", sel_prior, sel_weight),
        "regime_default": with_regime(base, "regime_conditional", 0.40, 0.50),
        "regime_aggressive": with_regime(base, "regime_conditional", 0.67, 1.00),
    }
    holdouts = {"oos_2024": args.oos_start, "oos_2025": args.secondary_holdout}

    oos_rows = []
    for holdout_name, holdout_start in holdouts.items():
        metric_start = next_trading_day(returns.index, pd.Timestamp(holdout_start), inclusive=True)
        for arm_name, cfg in arms.items():
            metrics, fallback, _ = evaluate_candidate_window(returns, cfg, full_start, full_end, metric_start, full_end, config)
            oos_rows.append({
                "holdout": holdout_name, "metric_start": metric_start.date().isoformat(), "metric_end": full_end.date().isoformat(),
                "arm": arm_name,
                "regime_crisis_prior": cfg.regime_crisis_prior if cfg.covariance_method == "regime_conditional" else None,
                "regime_prior_weight": cfg.regime_prior_weight if cfg.covariance_method == "regime_conditional" else None,
                "net_annual_return": metrics["net_annual_return"], "annual_volatility": metrics["annual_volatility"],
                "sharpe": metrics["sharpe"], "max_drawdown": metrics["max_drawdown"], "calmar": metrics["calmar"],
                "cvar": metrics["cvar"], "avg_monthly_turnover": metrics["avg_monthly_turnover"],
                "solver_fallback_rate": fallback, "validation_status": VALIDATION_STATUS,
                "selection_rule": "regime prior chosen on design window only (2019..design_end)",
            })
    oos = pd.DataFrame(oos_rows)

    out = Path(resolve_path(args.output_dir))
    out.mkdir(parents=True, exist_ok=True)
    selection.to_csv(out / "regime_oos_selection.csv", index=False)
    oos.to_csv(out / "regime_oos_validation.csv", index=False)

    print("\n=== Out-of-sample comparison (metrics on holdout slice only) ===")
    for holdout_name in holdouts:
        sub = oos[oos["holdout"].eq(holdout_name)].set_index("arm")
        base_sharpe = sub.loc["baseline_ewma", "sharpe"]
        base_mdd = sub.loc["baseline_ewma", "max_drawdown"]
        sel_sharpe = sub.loc["regime_selected", "sharpe"]
        sel_mdd = sub.loc["regime_selected", "max_drawdown"]
        print(f"\n[{holdout_name}] start={sub.iloc[0]['metric_start']}")
        print(sub[["sharpe", "max_drawdown", "net_annual_return", "avg_monthly_turnover", "cvar"]].to_string())
        verdict = "PASS" if (sel_sharpe >= base_sharpe and abs(sel_mdd) <= abs(base_mdd)) else ("MIXED" if sel_sharpe >= base_sharpe or abs(sel_mdd) <= abs(base_mdd) else "FAIL")
        print(f"  regime_selected vs baseline: dSharpe={sel_sharpe - base_sharpe:+.3f}, dMaxDD={abs(base_mdd) - abs(sel_mdd):+.4f} (positive=shallower) -> {verdict}")

    print("\nOutputs written to", out)


if __name__ == "__main__":
    main()
