from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.run_convex_adaptive_rrp import candidate_configurations
from src.data_loader import load_data
from src.utils import get_config, resolve_path
from src.validation import (
    VALIDATION_STATUS,
    ensure_datetime_index,
    generate_cscv_splits,
    pbo_from_cscv,
    result_window_metrics,
    validation_run_metadata,
    validation_score,
)
from src.convex_adaptive_rrp import run_convex_adaptive_backtest


def block_score(metrics_by_block: dict[int, dict], block_ids: tuple[int, ...]) -> float:
    if not block_ids:
        return np.nan
    scores = [validation_score(metrics_by_block[i]) for i in block_ids if i in metrics_by_block]
    return float(np.mean(scores)) if scores else np.nan


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CSCV/PBO diagnostics for convex adaptive candidates.")
    parser.add_argument("--output-dir", default="results/tables")
    parser.add_argument("--max-candidates", type=int, default=None)
    parser.add_argument("--eval-start", default="2015-01-01")
    parser.add_argument("--num-blocks", type=int, default=8)
    parser.add_argument("--max-combinations", type=int, default=None)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    validation_kind = "formal"
    if args.smoke:
        validation_kind = "smoke"
        args.max_candidates = args.max_candidates or 2
        args.max_combinations = args.max_combinations or 2
    elif args.max_candidates is not None or args.max_combinations is not None or args.num_blocks != 8 or args.eval_start != "2015-01-01":
        validation_kind = "intermediate"

    requested_eval_start = args.eval_start
    requested_frozen_start = None

    config = get_config({"transaction_cost_bps": 3.0})
    returns = ensure_datetime_index(load_data(source="tushare", force_update=False))
    returns = returns[returns.index >= pd.Timestamp(args.eval_start)]
    candidates = candidate_configurations(config["transaction_cost_bps"])
    if args.max_candidates is not None:
        candidates = candidates[: args.max_candidates]
    if len(candidates) < 2:
        raise ValueError("CSCV/PBO requires at least two candidates.")

    blocks, combos = generate_cscv_splits(returns, args.num_blocks, args.max_combinations)
    validation_kind = "formal"
    if args.smoke:
        validation_kind = "smoke"
    elif args.max_candidates is not None or args.max_combinations is not None or args.num_blocks != 8 or args.eval_start != "2015-01-01":
        validation_kind = "intermediate"
    elif len(candidates) < len(candidate_configurations(config["transaction_cost_bps"])):
        validation_kind = "intermediate"

    metadata = validation_run_metadata(
        validation_method="cscv_pbo",
        validation_kind=validation_kind,
        eval_start=args.eval_start,
        eval_end=returns.index.max(),
        selection_rule="candidate with highest IS score under the current block split",
        limitations="PBO is a diagnostic, not proof; reduced candidates or combinations make this intermediate validation evidence.",
        candidate_count=len(candidates),
        num_splits=len(combos),
        num_blocks=len(blocks),
        num_combinations=len(combos),
        requested_eval_start=requested_eval_start,
        requested_frozen_start=requested_frozen_start,
    )
    candidate_block_metrics: dict[str, dict[int, dict]] = {}
    for i, (candidate_id, cfg) in enumerate(candidates, start=1):
        print(f"Running candidate {i}/{len(candidates)} for CSCV/PBO: {candidate_id}")
        result, _, _, _ = run_convex_adaptive_backtest(returns, cfg)
        block_metrics = {}
        for block in blocks:
            block_metrics[int(block["block_id"])] = result_window_metrics(result, block["start"], block["end"], config)
        candidate_block_metrics[candidate_id] = block_metrics

    score_rows = []
    for combo in combos:
        for candidate_id, _ in candidates:
            metrics_by_block = candidate_block_metrics[candidate_id]
            score_rows.append(
                {
                    "split_id": combo["split_id"],
                    "candidate_id": candidate_id,
                    "in_sample_blocks": json_tuple(combo["in_sample_blocks"]),
                    "out_of_sample_blocks": json_tuple(combo["out_of_sample_blocks"]),
                    "is_score": block_score(metrics_by_block, combo["in_sample_blocks"]),
                    "oos_score": block_score(metrics_by_block, combo["out_of_sample_blocks"]),
                    "validation_status": VALIDATION_STATUS,
                }
            )
    score_table = pd.DataFrame(score_rows)
    detail, summary = pbo_from_cscv(score_table)
    detail = score_table.copy()
    detail = detail.assign(**metadata)
    summary = summary.assign(**metadata)

    output_dir = Path(resolve_path(args.output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)
    detail.to_csv(output_dir / "cscv_pbo_results.csv", index=False)
    summary.to_csv(output_dir / "cscv_pbo_summary.csv", index=False)
    print(f"Saved CSCV/PBO diagnostics for {len(combos)} splits to {output_dir}")
    print(f"Validation kind: {validation_kind}")


def json_tuple(values: tuple[int, ...]) -> str:
    return "[" + ",".join(str(v) for v in values) + "]"


if __name__ == "__main__":
    main()
