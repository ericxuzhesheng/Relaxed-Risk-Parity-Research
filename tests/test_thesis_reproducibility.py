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
