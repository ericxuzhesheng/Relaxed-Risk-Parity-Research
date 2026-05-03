from pathlib import Path


def test_thesis_report_files_exist_and_non_empty():
    for path in [
        Path("report/methodology_notes.md"),
        Path("report/insurance_allocation_perspective.md"),
        Path("report/thesis_figures_and_tables.md"),
    ]:
        assert path.exists()
        assert path.stat().st_size > 0


def test_full_pipeline_script_exists():
    path = Path("scripts/run_full_research_pipeline.py")
    assert path.exists()
    assert "--quick" in path.read_text(encoding="utf-8")


def test_full_pipeline_checklist_generation():
    from scripts.run_full_research_pipeline import write_checklist

    checklist = write_checklist(
        [{"step": "unit_smoke", "critical": True, "return_code": 0, "status": "passed", "command": "pytest"}]
    )
    assert checklist.exists()
    assert checklist.stat().st_size > 0


def test_new_validation_scripts_exist():
    for path in [
        Path("scripts/run_holdout_validation.py"),
        Path("scripts/run_cvar_sensitivity.py"),
        Path("scripts/run_enhanced_cscv_pbo.py"),
        Path("scripts/run_extended_sample_robustness.py"),
    ]:
        assert path.exists()
        assert path.stat().st_size > 0


def test_pipeline_includes_new_diagnostics():
    pipeline = Path("scripts/run_full_research_pipeline.py").read_text(encoding="utf-8")
    for step in [
        "extended_sample_robustness",
        "cvar_sensitivity",
        "enhanced_cscv_pbo",
        "holdout_validation",
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
        "holdout_validation_summary.csv",
    ]:
        assert any(table in o for o in outputs), f"{table} missing from expected_outputs()"
