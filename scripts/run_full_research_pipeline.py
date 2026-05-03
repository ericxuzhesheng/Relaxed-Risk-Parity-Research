from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent


@dataclass
class PipelineStep:
    name: str
    command: list[str]
    critical: bool = True
    quick_cache_outputs: list[Path] | None = None


def steps(quick: bool) -> list[PipelineStep]:
    python = sys.executable
    rrp_cmd = [python, "scripts/run_rrp_pipeline.py", "--mode", "full"]
    if quick:
        rrp_cmd.append("--fast-mode")
    quick_root = ROOT_DIR / "results" / "quick"
    return [
        PipelineStep("rrp_pipeline", rrp_cmd, True, [ROOT_DIR / "results/tables/performance_summary.csv"] if quick else None),
        PipelineStep("showcase_optimization", [python, "scripts/optimize_showcase_rrp.py"], False, [ROOT_DIR / "results/tables/showcase_performance_summary.csv"] if quick else None),
        PipelineStep("hrp_comparison", [python, "scripts/run_hrp_comparison.py"], False, [ROOT_DIR / "results/tables/hrp_comparison.csv"] if quick else None),
        PipelineStep("convex_adaptive_rrp", [python, "scripts/run_convex_adaptive_rrp.py"], True, [ROOT_DIR / "results/tables/convex_adaptive_performance_summary.csv"] if quick else None),
        PipelineStep("extended_sample_robustness", [python, "scripts/run_extended_sample_robustness.py", *( ["--smoke"] if quick else [] )], False, [ROOT_DIR / "results/tables/extended_sample_robustness_summary.csv"] if quick else None),
        PipelineStep("cvar_sensitivity", [python, "scripts/run_cvar_sensitivity.py", *( ["--smoke"] if quick else [] )], False, [ROOT_DIR / "results/tables/cvar_sensitivity_summary.csv"] if quick else None),
        PipelineStep("enhanced_cscv_pbo", [python, "scripts/run_enhanced_cscv_pbo.py", *( ["--smoke"] if quick else [] )], False, [ROOT_DIR / "results/tables/cscv_pbo_enhanced_summary.csv"] if quick else None),
        PipelineStep("holdout_validation", [python, "scripts/run_holdout_validation.py", *( ["--smoke"] if quick else [] )], False, [ROOT_DIR / "results/tables/holdout_validation_summary.csv"] if quick else None),
        PipelineStep(
            "benchmark_suite",
            [python, "scripts/run_benchmark_suite.py", *(["--smoke", "--output-root", str(quick_root / "benchmark")] if quick else [])],
            True,
        ),
        PipelineStep(
            "robustness_tests",
            [python, "scripts/run_robustness_tests.py", *(["--smoke", "--output-root", str(quick_root / "robustness")] if quick else [])],
            False,
        ),
        PipelineStep(
            "asset_pricing_diagnostics",
            [python, "scripts/run_asset_pricing_diagnostics.py", *(["--smoke", "--output-root", str(quick_root / "asset_pricing")] if quick else [])],
            False,
        ),
    ]


def expected_outputs() -> list[Path]:
    return [
        ROOT_DIR / "results/tables/performance_summary.csv",
        ROOT_DIR / "results/tables/convex_adaptive_performance_summary.csv",
        ROOT_DIR / "results/tables/benchmark_performance_summary.csv",
        ROOT_DIR / "results/tables/benchmark_turnover_summary.csv",
        ROOT_DIR / "results/tables/benchmark_drawdown_summary.csv",
        ROOT_DIR / "results/tables/robustness_overall_summary.csv",
        ROOT_DIR / "results/tables/robustness_block_bootstrap_summary.csv",
        ROOT_DIR / "results/tables/robustness_overfitting_diagnostic.csv",
        ROOT_DIR / "results/tables/asset_pricing_factor_exposure_summary.csv",
        ROOT_DIR / "results/tables/extended_sample_robustness_summary.csv",
        ROOT_DIR / "results/tables/cvar_sensitivity_summary.csv",
        ROOT_DIR / "results/tables/cscv_pbo_enhanced_summary.csv",
        ROOT_DIR / "results/tables/holdout_validation_summary.csv",
        ROOT_DIR / "report/methodology_notes.md",
        ROOT_DIR / "docs/MODEL_GOVERNANCE.md",
        ROOT_DIR / "report/asset_pricing_interpretation.md",
        ROOT_DIR / "report/insurance_allocation_perspective.md",
        ROOT_DIR / "report/thesis_figures_and_tables.md",
    ]


def quick_cache_available(step: PipelineStep) -> bool:
    if not step.quick_cache_outputs:
        return False
    return all(path.exists() and path.stat().st_size > 0 for path in step.quick_cache_outputs)


def display_command(command: list[str]) -> str:
    parts = []
    for part in command:
        path = Path(part)
        if path.is_absolute():
            try:
                parts.append(str(path.relative_to(ROOT_DIR)))
            except ValueError:
                parts.append(path.name)
        elif part == sys.executable:
            parts.append("python")
        else:
            parts.append(part)
    return " ".join(parts)


def run_step(step: PipelineStep, quick: bool = False) -> dict:
    if quick and quick_cache_available(step):
        outputs = ";".join(str(path.relative_to(ROOT_DIR)) for path in step.quick_cache_outputs or [])
        print(f"Using cached quick output for {step.name}: {outputs}")
        return {
            "step": step.name,
            "critical": step.critical,
            "return_code": 0,
            "status": "quick_cached",
            "command": display_command(step.command),
        }
    if quick and step.quick_cache_outputs and not step.critical:
        print(f"Skipping non-critical quick step without cache: {step.name}")
        return {
            "step": step.name,
            "critical": step.critical,
            "return_code": 0,
            "status": "quick_skipped_no_cache",
            "command": display_command(step.command),
        }
    print(f"Running {step.name}: {display_command(step.command)}")
    completed = subprocess.run(step.command, cwd=ROOT_DIR, text=True, capture_output=True)
    if completed.stdout:
        print(completed.stdout)
    if completed.stderr:
        print(completed.stderr, file=sys.stderr)
    status = "passed" if completed.returncode == 0 else "failed"
    if completed.returncode != 0 and step.critical:
        status = "critical_failed"
    return {
        "step": step.name,
        "critical": step.critical,
        "return_code": completed.returncode,
        "status": status,
        "command": display_command(step.command),
    }


def write_checklist(rows: list[dict]) -> Path:
    output = ROOT_DIR / "results/tables/full_pipeline_checklist.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    file_rows = []
    for path in expected_outputs():
        file_rows.append(
            {
                "step": "expected_output",
                "critical": True,
                "return_code": 0 if path.exists() and path.stat().st_size > 0 else 1,
                "status": "present" if path.exists() and path.stat().st_size > 0 else "missing",
                "command": str(path.relative_to(ROOT_DIR)),
            }
        )
    pd.DataFrame([*rows, *file_rows]).to_csv(output, index=False)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full thesis research reproduction pipeline.")
    parser.add_argument("--quick", action="store_true", help="Use smoke/fast modes for diagnostics where supported.")
    args = parser.parse_args()
    rows = []
    failed_critical = False
    for step in steps(args.quick):
        row = run_step(step, args.quick)
        rows.append(row)
        if row["status"] == "critical_failed":
            failed_critical = True
            break
    checklist = write_checklist(rows)
    print(f"Full pipeline checklist written to {checklist}")
    if failed_critical:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
