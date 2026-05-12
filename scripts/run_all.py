"""End-to-end pipeline orchestrator.

Runs the research pipeline in dependency order so the thesis numbers stay
consistent across CSV outputs. Each step is a regular Python ``-m`` /
script invocation, so any step can also be rerun individually for
debugging.

Usage::

    python scripts/run_all.py                # full pipeline
    python scripts/run_all.py --skip-data    # reuse cached ETF prices
    python scripts/run_all.py --smoke        # fast diagnostic (where supported)

The script intentionally avoids re-implementing logic — it delegates to the
existing per-stage scripts so that maintainers always have one canonical
entry point for each stage.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
logger = logging.getLogger("run_all")


PIPELINE: list[tuple[str, list[str]]] = [
    ("update_etf_data", ["python", "scripts/update_etf_data.py"]),
    ("convex_adaptive_rrp", ["python", "scripts/run_convex_adaptive_rrp.py"]),
    ("hrp_comparison", ["python", "scripts/run_hrp_comparison.py"]),
    ("benchmark_suite", ["python", "scripts/run_benchmark_suite.py"]),
    ("walkforward_validation", ["python", "scripts/run_walkforward_validation.py"]),
    ("cscv_pbo", ["python", "scripts/run_cscv_pbo.py"]),
    ("frozen_oos_validation", ["python", "scripts/run_frozen_oos_validation.py"]),
    ("robustness_tests", ["python", "scripts/run_robustness_tests.py"]),
    ("vol_aligned_comparison", ["python", "scripts/run_vol_aligned_comparison.py"]),
    ("sharpe_diff_tests", ["python", "scripts/run_sharpe_diff_tests.py"]),
    ("generate_thesis_numbers", ["python", "scripts/generate_thesis_numbers.py"]),
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-data",
        action="store_true",
        help="Skip update_etf_data.py (reuse cached prices in data/processed/).",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Pass --smoke to stages that support it (cscv_pbo, robustness_tests).",
    )
    parser.add_argument(
        "--only",
        nargs="*",
        default=None,
        help="Run only the named stages, in declared order.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue running subsequent stages even if one fails.",
    )
    return parser.parse_args()


def _stage_command(name: str, base: list[str], smoke: bool) -> list[str]:
    if smoke and name in {"cscv_pbo", "robustness_tests"}:
        return base + ["--smoke"]
    return base


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = _parse_args()
    selected = set(args.only) if args.only else None
    overall_start = time.time()
    failures: list[str] = []

    for name, base_command in PIPELINE:
        if args.skip_data and name == "update_etf_data":
            logger.info("[%s] skipped (--skip-data)", name)
            continue
        if selected is not None and name not in selected:
            continue
        command = _stage_command(name, base_command, args.smoke)
        logger.info("[%s] running: %s", name, " ".join(command))
        stage_start = time.time()
        try:
            subprocess.run(command, cwd=ROOT_DIR, check=True)
        except subprocess.CalledProcessError as exc:
            elapsed = time.time() - stage_start
            logger.error("[%s] failed after %.1fs: exit code %d", name, elapsed, exc.returncode)
            failures.append(name)
            if not args.continue_on_error:
                logger.error("aborting pipeline; rerun with --continue-on-error to keep going")
                return exc.returncode
        else:
            logger.info("[%s] completed in %.1fs", name, time.time() - stage_start)

    total = time.time() - overall_start
    if failures:
        logger.error("pipeline finished in %.1fs with failures: %s", total, ", ".join(failures))
        return 1
    logger.info("pipeline completed in %.1fs", total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
