from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.run_convex_adaptive_rrp import candidate_configurations
from src.data_loader import load_data
from src.utils import get_config, resolve_path
from src.validation import (
    VALIDATION_NOTE,
    VALIDATION_STATUS,
    config_fields,
    ensure_datetime_index,
    evaluate_candidate_window,
    generate_walkforward_splits,
    select_candidate,
    summarize_validation_rows,
    validation_run_metadata,
)


def split_windows(
    returns: pd.DataFrame,
    train_months: int,
    validation_months: int,
    test_months: int,
    step_months: int,
    max_splits: int | None,
) -> list[dict[str, pd.Timestamp]]:
    return generate_walkforward_splits(
        returns,
        train_months=train_months,
        validation_months=validation_months,
        test_months=test_months,
        step_months=step_months,
        max_splits=max_splits,
    )


def metric_columns(prefix: str, metrics: dict) -> dict:
    return {f"{prefix}_{key}": value for key, value in metrics.items()}


def run_split(
    returns: pd.DataFrame,
    split: dict,
    candidates: list[tuple[str, object]],
    config: dict,
    run_metadata: dict,
) -> dict:
    (selected_id, selected_cfg), validation_metrics, validation_fallback, selection_score, _ = select_candidate(
        returns,
        candidates,
        split["train_start"],
        split["validation_end"],
        split["validation_start"],
        split["validation_end"],
        config,
    )
    test_metrics, test_fallback, _ = evaluate_candidate_window(
        returns,
        selected_cfg,
        split["train_start"],
        split["test_end"],
        split["test_start"],
        split["test_end"],
        config,
    )
    return {
        **run_metadata,
        "split_id": split["split_id"],
        "validation_status": VALIDATION_STATUS,
        "uses_future_data": False,
        "train_start": split["train_start"].date().isoformat(),
        "train_end": split["train_end"].date().isoformat(),
        "validation_start": split["validation_start"].date().isoformat(),
        "validation_end": split["validation_end"].date().isoformat(),
        "test_start": split["test_start"].date().isoformat(),
        "test_end": split["test_end"].date().isoformat(),
        **config_fields(selected_id, selected_cfg),
        "selection_score": selection_score,
        "validation_solver_fallback_rate": validation_fallback,
        "test_solver_fallback_rate": test_fallback,
        **metric_columns("validation", validation_metrics),
        **metric_columns("test", test_metrics),
        "notes": VALIDATION_NOTE,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run walk-forward validation for Convex Adaptive Global RRP candidates.")
    parser.add_argument("--output-dir", default="results/tables")
    parser.add_argument("--max-candidates", type=int, default=None)
    parser.add_argument("--eval-start", default=None)
    parser.add_argument("--train-years", type=float, default=2.0)
    parser.add_argument("--validation-years", type=float, default=0.5)
    parser.add_argument("--test-years", type=float, default=0.25)
    parser.add_argument("--step-months", type=int, default=3)
    parser.add_argument("--max-splits", type=int, default=None)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    validation_kind = "formal"
    if args.smoke:
        validation_kind = "smoke"
        args.max_candidates = args.max_candidates or 2
        args.max_splits = args.max_splits or 1
    elif args.max_candidates is not None or args.max_splits is not None or args.eval_start or args.train_years != 2.0 or args.validation_years != 0.5 or args.test_years != 0.25 or args.step_months != 3:
        validation_kind = "intermediate"

    requested_eval_start = args.eval_start
    requested_frozen_start = None

    config = get_config({"transaction_cost_bps": 3.0})
    base_candidate_count = len(candidate_configurations(config["transaction_cost_bps"]))
    returns = ensure_datetime_index(load_data(source="tushare", force_update=False))
    if args.eval_start:
        returns = returns[returns.index >= pd.Timestamp(args.eval_start)]
    run_metadata = validation_run_metadata(
        validation_method="walkforward",
        validation_kind=validation_kind,
        eval_start=args.eval_start or returns.index.min(),
        eval_end=returns.index.max(),
        selection_rule="highest validation-window score within each split",
        limitations="Validation-window selection is followed by test reporting; bounded runs are intermediate validation evidence.",
        candidate_count=len(candidate_configurations(config["transaction_cost_bps"])),
        num_splits=None,
        num_blocks=None,
        num_combinations=None,
        requested_eval_start=requested_eval_start,
        requested_frozen_start=requested_frozen_start,
        train_years=args.train_years,
        validation_years=args.validation_years,
        test_years=args.test_years,
        step_months=args.step_months,
        base_candidate_count=base_candidate_count,
    )
    if args.eval_start:
        run_metadata["eval_start"] = pd.Timestamp(args.eval_start).date().isoformat()
    run_metadata["candidate_count"] = len(candidate_configurations(config["transaction_cost_bps"]))
    run_metadata["base_candidate_count"] = base_candidate_count
    run_metadata["validation_method"] = "walkforward"
    run_metadata["validation_kind"] = validation_kind
    run_metadata["selection_rule"] = "highest validation-window score within each split"
    run_metadata["limitations"] = "Validation-window selection is followed by test reporting; bounded runs are intermediate validation evidence."

    candidates = candidate_configurations(config["transaction_cost_bps"])
    if args.eval_start:
        returns = returns[returns.index >= pd.Timestamp(args.eval_start)]
    candidates = candidate_configurations(config["transaction_cost_bps"])
    if args.max_candidates is not None:
        candidates = candidates[: args.max_candidates]
    if not candidates:
        raise ValueError("Candidate configurations are unavailable.")

    splits = generate_walkforward_splits(
        returns,
        train_months=int(round(args.train_years * 12)),
        validation_months=int(round(args.validation_years * 12)),
        test_months=int(round(args.test_years * 12)),
        step_months=args.step_months,
        max_splits=args.max_splits,
    )
    rows = []
    for i, split in enumerate(splits, start=1):
        print(f"Running walk-forward split {i}/{len(splits)}: {split['test_start'].date()} to {split['test_end'].date()}")
        rows.append(run_split(returns, split, candidates, config, run_metadata))

    output_dir = Path(resolve_path(args.output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)
    detail = pd.DataFrame(rows)
    summary = summarize_validation_rows(detail, "test")
    detail.to_csv(output_dir / "walkforward_validation.csv", index=False)
    summary.to_csv(output_dir / "walkforward_validation_summary.csv", index=False)
    print(f"Saved {len(detail)} walk-forward rows and {len(summary)} summary rows to {output_dir}")


if __name__ == "__main__":
    main()
