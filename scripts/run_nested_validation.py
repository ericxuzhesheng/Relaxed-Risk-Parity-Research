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
    generate_nested_splits,
    select_candidate,
    summarize_validation_rows,
)


def _metrics(prefix: str, metrics: dict) -> dict:
    return {f"{prefix}_{key}": value for key, value in metrics.items()}


def run_split(returns: pd.DataFrame, split: dict, candidates: list[tuple[str, object]], config: dict) -> dict:
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
        "sharpe_decay_validation_to_test": validation_metrics["sharpe"] - test_metrics["sharpe"],
        "calmar_decay_validation_to_test": validation_metrics["calmar"] - test_metrics["calmar"],
        **_metrics("validation", validation_metrics),
        **_metrics("test", test_metrics),
        "notes": VALIDATION_NOTE,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run nested train/validation/test validation.")
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

    if args.smoke:
        args.max_candidates = args.max_candidates or 2
        args.max_splits = args.max_splits or 1

    config = get_config({"transaction_cost_bps": 3.0})
    returns = ensure_datetime_index(load_data(source="tushare", force_update=False))
    if args.eval_start:
        returns = returns[returns.index >= pd.Timestamp(args.eval_start)]
    candidates = candidate_configurations(config["transaction_cost_bps"])
    if args.max_candidates is not None:
        candidates = candidates[: args.max_candidates]

    splits = generate_nested_splits(
        returns,
        train_months=int(round(args.train_years * 12)),
        validation_months=int(round(args.validation_years * 12)),
        test_months=int(round(args.test_years * 12)),
        step_months=args.step_months,
        max_splits=args.max_splits,
    )
    rows = []
    for i, split in enumerate(splits, start=1):
        print(f"Running nested split {i}/{len(splits)}: test starts {split['test_start'].date()}")
        rows.append(run_split(returns, split, candidates, config))

    output_dir = Path(resolve_path(args.output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)
    detail = pd.DataFrame(rows)
    summary = summarize_validation_rows(detail, "test")
    decay_summary = summarize_validation_rows(
        detail.rename(
            columns={
                "sharpe_decay_validation_to_test": "test_sharpe_decay_validation_to_test",
                "calmar_decay_validation_to_test": "test_calmar_decay_validation_to_test",
            }
        ),
        "test",
    )
    summary = pd.concat([summary, decay_summary[decay_summary["metric"].str.contains("decay")]], ignore_index=True)
    summary.to_csv(output_dir / "nested_validation_summary.csv", index=False)
    detail.to_csv(output_dir / "nested_validation.csv", index=False)
    print(f"Saved {len(detail)} nested validation rows to {output_dir}")


if __name__ == "__main__":
    main()
