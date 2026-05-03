from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.run_frozen_oos_validation import selected_candidate
from src.data_loader import load_data
from src.utils import get_config, resolve_path
from src.validation import (
    VALIDATION_STATUS,
    config_fields,
    ensure_datetime_index,
    evaluate_candidate_window,
    generate_retrospective_holdout_splits,
    summarize_validation_rows,
    validation_run_metadata,
)

DEFAULT_HOLDOUT_STARTS = ("2024-01-01", "2025-01-01")


def metric_columns(prefix: str, metrics: dict) -> dict:
    return {f"{prefix}_{key}": value for key, value in metrics.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run retrospective holdout validation for the pre-declared improved candidate.")
    parser.add_argument("--output-dir", default="results/tables")
    parser.add_argument("--holdout-starts", nargs="+", default=list(DEFAULT_HOLDOUT_STARTS))
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    validation_kind = "retrospective"
    if args.smoke:
        validation_kind = "smoke"
        args.holdout_starts = args.holdout_starts[:1]

    config = get_config({"transaction_cost_bps": 3.0})
    returns = ensure_datetime_index(load_data(source="tushare", force_update=False))
    candidate_id, cfg = selected_candidate(config["transaction_cost_bps"])
    splits = generate_retrospective_holdout_splits(returns, args.holdout_starts)
    metadata = validation_run_metadata(
        validation_method="holdout_validation",
        validation_kind=validation_kind,
        eval_start=splits[0]["test_start"],
        eval_end=splits[-1]["test_end"],
        selection_rule="pre-declared candidate only",
        limitations=(
            "Retrospective holdout slices improve time-slice transparency but are not untouched out-of-sample proof; "
            "they reuse a candidate selected before these holdout reports were generated."
        ),
        candidate_count=1,
        num_splits=len(splits),
        requested_holdout_starts=";".join(pd.Timestamp(value).date().isoformat() for value in args.holdout_starts),
    )

    rows = []
    for i, split in enumerate(splits, start=1):
        print(
            f"Running retrospective holdout split {i}/{len(splits)}: "
            f"{split['test_start'].date()} to {split['test_end'].date()}"
        )
        test_metrics, test_fallback, _ = evaluate_candidate_window(
            returns,
            cfg,
            split["train_start"],
            split["test_end"],
            split["test_start"],
            split["test_end"],
            config,
        )
        rows.append(
            {
                **metadata,
                "split_id": split["split_id"],
                "validation_status": VALIDATION_STATUS,
                "requested_holdout_start": split["requested_holdout_start"].date().isoformat(),
                "train_start": split["train_start"].date().isoformat(),
                "train_end": split["train_end"].date().isoformat(),
                "test_start": split["test_start"].date().isoformat(),
                "test_end": split["test_end"].date().isoformat(),
                **config_fields(candidate_id, cfg),
                "test_solver_fallback_rate": test_fallback,
                **metric_columns("test", test_metrics),
                "notes": (
                    "Retrospective holdout evidence for a pre-declared candidate; interpret as conditional evidence, "
                    "not as a strict untouched frozen OOS test."
                ),
            }
        )

    detail = pd.DataFrame(rows)
    summary = summarize_validation_rows(detail, "test")
    summary = summary.assign(**metadata)
    summary["base_candidate_id"] = candidate_id
    summary["notes"] = (
        "Retrospective holdout slices complement frozen-OOS reporting but do not replace preregistered untouched out-of-sample validation."
    )

    output_dir = Path(resolve_path(args.output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)
    detail.to_csv(output_dir / "holdout_validation.csv", index=False)
    summary.to_csv(output_dir / "holdout_validation_summary.csv", index=False)
    print(f"Saved retrospective holdout validation for {candidate_id} to {output_dir}")


if __name__ == "__main__":
    main()
