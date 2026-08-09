from pathlib import Path

import pandas as pd


def test_thesis_report_files_exist_and_non_empty():
    for path in [
        Path("report/thesis_latex/main.tex"),
        Path("report/thesis_latex/generated_numbers.tex"),
        Path("docs/MODEL_GOVERNANCE.md"),
    ]:
        assert path.exists()
        assert path.stat().st_size > 0


def test_full_pipeline_script_exists():
    path = Path("scripts/run_full_research_pipeline.py")
    assert path.exists()
    assert "--quick" in path.read_text(encoding="utf-8")


def test_full_pipeline_checklist_generation(tmp_path):
    from scripts.run_full_research_pipeline import write_checklist

    checklist = write_checklist(
        [{"step": "unit_smoke", "critical": True, "return_code": 0, "status": "passed", "command": "pytest"}],
        output_path=tmp_path / "full_pipeline_checklist.csv",
    )
    assert checklist.exists()
    assert checklist.stat().st_size > 0


def test_new_validation_scripts_exist():
    for path in [
        Path("scripts/run_cvar_sensitivity.py"),
        Path("scripts/run_enhanced_cscv_pbo.py"),
        Path("scripts/run_extended_sample_robustness.py"),
    ]:
        assert path.exists()
        assert path.stat().st_size > 0


def test_pipeline_includes_new_diagnostics():
    pipeline = Path("scripts/run_full_research_pipeline.py").read_text(encoding="utf-8")
    for step in [
        "convex_adaptive_rrp",
        "extended_sample_robustness",
        "cvar_sensitivity",
        "enhanced_cscv_pbo",
    ]:
        assert step in pipeline


def test_governance_doc_listed_in_pipeline():
    pipeline = Path("scripts/run_full_research_pipeline.py").read_text(encoding="utf-8")
    assert "MODEL_GOVERNANCE.md" in pipeline


def test_pipeline_expected_outputs_includes_new_tables():
    from scripts.run_full_research_pipeline import expected_outputs

    outputs = [str(p.relative_to(p.parents[1])) if p.is_absolute() else str(p) for p in expected_outputs()]
    for table in [
        "extended_sample_robustness_summary.csv",
        "cvar_sensitivity_summary.csv",
        "cscv_pbo_enhanced_summary.csv",
        "afml_oos_selection.csv",
    ]:
        assert any(table in o for o in outputs), f"{table} missing from expected_outputs()"


def test_cvar_sensitivity_uses_latest_available_date_without_cutoff():
    from scripts.run_cvar_sensitivity import apply_sample_window

    returns = pd.DataFrame(
        {"asset": [0.01, 0.02, 0.03]},
        index=pd.to_datetime(["2026-05-29", "2026-07-01", "2026-08-05"]),
    )

    actual = apply_sample_window(returns, sample_start="2026-05-29", sample_end=None)

    assert actual.index.max() == pd.Timestamp("2026-08-05")


def test_cvar_sensitivity_honors_explicit_cutoff():
    from scripts.run_cvar_sensitivity import apply_sample_window

    returns = pd.DataFrame(
        {"asset": [0.01, 0.02, 0.03]},
        index=pd.to_datetime(["2026-05-29", "2026-07-01", "2026-08-05"]),
    )

    actual = apply_sample_window(returns, sample_start="2026-05-29", sample_end="2026-07-01")

    assert actual.index.max() == pd.Timestamp("2026-07-01")


def test_parameter_sensitivity_default_matches_primary_evaluation_start():
    from scripts.run_parameter_sensitivity import build_parser

    assert build_parser().parse_args([]).eval_start == "2018-01-02"
