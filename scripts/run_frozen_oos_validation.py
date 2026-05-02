from __future__ import annotations

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
    config_fields,
    ensure_datetime_index,
    evaluate_candidate_window,
    generate_frozen_oos_split,
)


def selected_candidate(transaction_cost_bps: float) -> tuple[str, ConvexRRPConfig]:
    candidates = dict(candidate_configurations(transaction_cost_bps))
    path = Path(resolve_path("results/tables/convex_adaptive_improvement_candidates.csv"))
    if path.exists():
        table = pd.read_csv(path)
        selected = table[table["selected"].astype(bool)] if "selected" in table else pd.DataFrame()
        if not selected.empty:
            row = selected.iloc[0]
            candidate_id = str(row.get("candidate_id", row.get("candidate_name", "")))
            if candidate_id in candidates:
                return candidate_id, candidates[candidate_id]
            params = {
                "lookback_days": int(row.get("lookback_window", row.get("lookback_days", 252))),
                "covariance_method": str(row.get("covariance_estimator", row.get("covariance_method", "ewma"))),
                "max_weight": float(row.get("upper_bound_i", row.get("max_weight", 0.45))),
                "turnover_cap": row.get("turnover_cap", 0.80),
                "turnover_penalty": float(row.get("lambda_turnover", row.get("turnover_penalty", 0.01))),
                "budget_penalty": float(row.get("lambda_budget", row.get("budget_penalty", 0.10))),
                "cvar_penalty": float(row.get("lambda_cvar", row.get("cvar_penalty", 0.08))),
                "cvar_beta": float(row.get("cvar_alpha", row.get("cvar_beta", 0.95))),
                "return_reward": float(row.get("return_reward", 0.05)),
                "transaction_cost_bps": transaction_cost_bps,
            }
            if pd.isna(params["turnover_cap"]):
                params["turnover_cap"] = None
            else:
                params["turnover_cap"] = float(params["turnover_cap"])
            return candidate_id or "selected_candidate_from_csv", ConvexRRPConfig(**params)
    if "candidate_02" in candidates:
        return "candidate_02", candidates["candidate_02"]
    first_id = next(iter(candidates))
    return first_id, candidates[first_id]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run frozen OOS validation for the pre-declared improved candidate.")
    parser.add_argument("--output-dir", default="results/tables")
    parser.add_argument("--max-candidates", type=int, default=None, help="Accepted for CLI consistency; ignored.")
    parser.add_argument("--eval-start", default=None, help="Accepted for CLI consistency; frozen-start controls the split.")
    parser.add_argument("--frozen-start", default="2025-01-01")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    config = get_config({"transaction_cost_bps": 3.0})
    returns = ensure_datetime_index(load_data(source="tushare", force_update=False))
    split = generate_frozen_oos_split(returns, args.frozen_start)
    candidate_id, cfg = selected_candidate(config["transaction_cost_bps"])
    metrics, fallback_rate, _ = evaluate_candidate_window(
        returns,
        cfg,
        split["train_start"],
        split["test_end"],
        split["test_start"],
        split["test_end"],
        config,
    )
    row = {
        "split_id": split["split_id"],
        "validation_status": VALIDATION_STATUS,
        "requested_frozen_start": split["requested_frozen_start"].date().isoformat(),
        "train_start": split["train_start"].date().isoformat(),
        "train_end": split["train_end"].date().isoformat(),
        "test_start": split["test_start"].date().isoformat(),
        "test_end": split["test_end"].date().isoformat(),
        **config_fields(candidate_id, cfg),
        "test_solver_fallback_rate": fallback_rate,
        **{f"test_{key}": value for key, value in metrics.items()},
        "notes": "Pseudo-frozen if 2025+ data was already observed during prior candidate development.",
    }
    notes = pd.DataFrame(
        [
            {
                "item": "interpretation",
                "note": "Frozen OOS reports the pre-declared selected Improved Convex Adaptive Global RRP candidate on the frozen period only.",
            },
            {
                "item": "limitation",
                "note": "This should be treated as pseudo-frozen if the 2025+ period was already visible during earlier research iterations.",
            },
        ]
    )
    output_dir = Path(resolve_path(args.output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([row]).to_csv(output_dir / "frozen_oos_validation.csv", index=False)
    notes.to_csv(output_dir / "frozen_oos_validation_notes.csv", index=False)
    print(f"Saved frozen OOS validation for {candidate_id} to {output_dir}")


if __name__ == "__main__":
    main()
