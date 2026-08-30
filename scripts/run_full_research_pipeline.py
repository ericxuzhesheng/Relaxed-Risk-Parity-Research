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
    rrp_cmd = [python, "scripts/run_rrp_pipeline.py", "--mode", "full", "--diagnostics", "full"]
    if quick:
        rrp_cmd.append("--fast-mode")
    quick_root = ROOT_DIR / "results" / "quick"
    return [
        PipelineStep("update_etf_data", [python, "scripts/update_etf_data.py", "--provider", "tushare", "--start-date", "20000101", "--end-date", "20260828"], True),
        PipelineStep("update_risk_free_rate", [python, "scripts/update_risk_free_rate.py", "--start-date", "20000101", "--end-date", "20260828"], True),
        PipelineStep("barra_exposure_correlation", [python, "scripts/run_barra_exposure_correlation.py"], True),
        PipelineStep("rrp_pipeline", rrp_cmd, True, [ROOT_DIR / "results/tables/performance_summary.csv"] if quick else None),
        PipelineStep("showcase_optimization", [python, "scripts/optimize_showcase_rrp.py"], False, [ROOT_DIR / "results/tables/showcase_performance_summary.csv"] if quick else None),
        PipelineStep("hrp_comparison", [python, "scripts/run_hrp_comparison.py"], False, [ROOT_DIR / "results/tables/hrp_comparison.csv"] if quick else None),
        PipelineStep("convex_adaptive_rrp", [python, "scripts/run_convex_adaptive_rrp.py"], True, [ROOT_DIR / "results/tables/convex_adaptive_performance_summary.csv"] if quick else None),
        PipelineStep("export_next_month_holdings", [python, "scripts/export_next_month_holdings.py"], True),
        PipelineStep("walkforward_validation", [python, "scripts/run_walkforward_validation.py", *(["--smoke"] if quick else [])], False, [ROOT_DIR / "results/tables/walkforward_validation_summary.csv"] if quick else None),
        PipelineStep("cscv_pbo", [python, "scripts/run_cscv_pbo.py", *(["--smoke"] if quick else [])], False, [ROOT_DIR / "results/tables/cscv_pbo_summary.csv"] if quick else None),
        PipelineStep("monthly_hs300_comparison", [python, "scripts/run_monthly_hs300_comparison.py"], False, [ROOT_DIR / "results/tables/improved_rrp_vs_hs300_monthly_returns.csv"] if quick else None),
        PipelineStep("rebalance_frequency_sensitivity", [python, "scripts/run_rebalance_frequency_sensitivity.py"], False, [ROOT_DIR / "results/tables/rebalance_frequency_sensitivity.csv"] if quick else None),
        PipelineStep("extended_sample_robustness", [python, "scripts/run_extended_sample_robustness.py", *( ["--smoke"] if quick else [] )], False, [ROOT_DIR / "results/tables/extended_sample_robustness_summary.csv"] if quick else None),
        PipelineStep("cvar_sensitivity", [python, "scripts/run_cvar_sensitivity.py", *( ["--smoke"] if quick else [] )], False, [ROOT_DIR / "results/tables/cvar_sensitivity_summary.csv"] if quick else None),
        PipelineStep("enhanced_cscv_pbo", [python, "scripts/run_enhanced_cscv_pbo.py", *( ["--smoke"] if quick else [] )], False, [ROOT_DIR / "results/tables/cscv_pbo_enhanced_summary.csv"] if quick else None),
        PipelineStep("parameter_sensitivity", [python, "scripts/run_parameter_sensitivity.py", *(["--smoke"] if quick else [])], False, [ROOT_DIR / "results/tables/parameter_sensitivity_summary.csv"] if quick else None),
        PipelineStep("overlay_sensitivity", [python, "scripts/run_overlay_sensitivity.py"], False),
        PipelineStep("regime_covariance_experiment", [python, "scripts/run_regime_covariance_experiment.py"], False),
        PipelineStep("regime_oos_validation", [python, "scripts/run_regime_oos_validation.py"], False),
        PipelineStep("vol_aligned_comparison", [python, "scripts/run_vol_aligned_comparison.py"], False),
        PipelineStep("sharpe_diff_tests", [python, "scripts/run_sharpe_diff_tests.py"], False),
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
        PipelineStep("weight_path_diagnostics", [python, "scripts/run_weight_path_diagnostics.py"], False),
        PipelineStep("plot_weights_timeline", [python, "scripts/plot_weights_timeline.py"], False),
        PipelineStep("augment_supplementary_csvs", [python, "scripts/augment_supplementary_csvs.py"], False),
        PipelineStep("asset_descriptive_statistics", [python, "scripts/run_asset_descriptive_statistics.py"], True),
        PipelineStep("generate_thesis_numbers", [python, "scripts/generate_thesis_numbers.py"], True),
    ]


def expected_outputs() -> list[Path]:
    return [
        ROOT_DIR / "results/tables/performance_summary.csv",
        ROOT_DIR / "results/tables/convex_adaptive_performance_summary.csv",
        ROOT_DIR / "results/tables/next_month_holdings.csv",
        ROOT_DIR / "results/tables/benchmark_performance_summary.csv",
        ROOT_DIR / "results/tables/benchmark_turnover_summary.csv",
        ROOT_DIR / "results/tables/benchmark_drawdown_summary.csv",
        ROOT_DIR / "results/tables/robustness_overall_summary.csv",
        ROOT_DIR / "results/tables/robustness_block_bootstrap_summary.csv",
        ROOT_DIR / "results/tables/robustness_overfitting_diagnostic.csv",
        ROOT_DIR / "results/tables/asset_pricing_factor_exposure_summary.csv",
        ROOT_DIR / "results/tables/regime_covariance_experiment_summary.csv",
        ROOT_DIR / "results/tables/regime_oos_selection.csv",
        ROOT_DIR / "results/tables/regime_oos_validation.csv",
        ROOT_DIR / "results/tables/extended_sample_robustness_summary.csv",
        ROOT_DIR / "results/tables/rebalance_frequency_sensitivity.csv",
        ROOT_DIR / "results/tables/cvar_sensitivity_summary.csv",
        ROOT_DIR / "results/tables/cscv_pbo_enhanced_summary.csv",
        ROOT_DIR / "results/tables/walkforward_validation_summary.csv",
        ROOT_DIR / "results/tables/afml_oos_selection.csv",
        ROOT_DIR / "results/tables/asset_descriptive_statistics.csv",
        ROOT_DIR / "data/processed/risk_free_rate_monthly.csv",
        ROOT_DIR / "data/processed/barra_style_exposure_correlation.csv",
        ROOT_DIR / "docs/MODEL_GOVERNANCE.md",
        ROOT_DIR / "report/thesis_latex/main.tex",
        ROOT_DIR / "report/thesis_latex/main.pdf",
        ROOT_DIR / "report/ppt/rrp_defense.tex",
        ROOT_DIR / "report/ppt/rrp_defense.pdf",
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


def write_checklist(rows: list[dict], output_path: Path | None = None) -> Path:
    output = output_path if output_path is not None else ROOT_DIR / "results/tables/full_pipeline_checklist.csv"
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


def compile_pdf() -> None:
    documents = [
        (ROOT_DIR / "report" / "thesis_latex", "main.tex", "Thesis"),
        (ROOT_DIR / "report" / "ppt", "rrp_defense.tex", "Defense slides"),
    ]
    for tex_dir, filename, label in documents:
        if not (tex_dir / filename).exists():
            continue
        print(f"\nCompiling {label} PDF with three XeLaTeX passes...")
        try:
            result = subprocess.run(
                ["xelatex", "-interaction=nonstopmode", "-halt-on-error", filename],
                cwd=tex_dir,
            )
            return_code = result.returncode
            if return_code == 0 and filename == "main.tex":
                return_code = subprocess.run(["bibtex", "main"], cwd=tex_dir).returncode
            for _ in range(2):
                if return_code != 0:
                    break
                return_code = subprocess.run(
                    ["xelatex", "-interaction=nonstopmode", "-halt-on-error", filename],
                    cwd=tex_dir,
                ).returncode
            if return_code == 0:
                print(f"{label} PDF compiled successfully.")
            else:
                print(f"Warning: {label} PDF compilation failed.", file=sys.stderr)
        except FileNotFoundError:
            print("Warning: xelatex not found on PATH; PDFs were not compiled.", file=sys.stderr)
            return


def selected_steps(quick: bool, skip_data: bool) -> list[PipelineStep]:
    pipeline_steps = steps(quick)
    if skip_data:
        return [step for step in pipeline_steps if step.name not in {"update_etf_data", "update_risk_free_rate"}]
    return pipeline_steps


def cleanup() -> None:
    cleanup_script = ROOT_DIR / "scripts" / "cleanup_temp.py"
    if cleanup_script.exists():
        print("\nCleaning temporary files...")
        subprocess.run([sys.executable, str(cleanup_script)], cwd=ROOT_DIR)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full thesis research reproduction pipeline.")
    parser.add_argument("--quick", action="store_true", help="Use smoke/fast modes for diagnostics where supported.")
    parser.add_argument("--skip-data", action="store_true", help="Reuse ETF and risk-free data refreshed immediately before this run.")
    args = parser.parse_args()
    rows = []
    failed_critical = False
    try:
        for step in selected_steps(args.quick, args.skip_data):
            row = run_step(step, args.quick)
            rows.append(row)
            if row["status"] == "critical_failed":
                failed_critical = True
                break
        checklist = write_checklist(rows)
        print(f"Full pipeline checklist written to {checklist}")
    finally:
        compile_pdf()  # compile before cleanup so intermediates (.aux etc.) are present
        cleanup()      # then remove intermediates; .pdf is not in cleanup list and is preserved
    if failed_critical:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
