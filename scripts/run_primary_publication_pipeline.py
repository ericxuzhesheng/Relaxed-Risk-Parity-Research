"""Reproduce the designated primary model and its publication artifacts."""
from pathlib import Path
import csv
import os
import re
import subprocess
import sys
import json

ROOT = Path(__file__).resolve().parents[1]


def _pdf_page_count(path: Path) -> int:
    completed = subprocess.run(["pdfinfo", str(path)], capture_output=True, check=True)
    match = re.search(rb"^Pages:\s+(\d+)\r?$", completed.stdout, flags=re.MULTILINE)
    if not match:
        raise RuntimeError(f"Could not read page count from {path}")
    return int(match.group(1))


def _write_build_verification() -> None:
    thesis_pdf = ROOT / "report/thesis_latex/main.pdf"
    slides_pdf = ROOT / "report/ppt/rrp_defense.pdf"
    with (ROOT / "results/tables/hrp_comparison.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        models = [row["model"] for row in csv.DictReader(handle)]
    expected = [
        "Global RRP",
        "HRP Benchmark",
        "HERC Benchmark",
        "Equal Weight",
        "60/40 Benchmark",
    ]
    if models != expected:
        raise ValueError(f"Unexpected publication model order: {models}")
    audit = json.loads(
        (ROOT / "results/tables/primary_publication_audit.json").read_text(
            encoding="utf-8"
        )
    )
    logs = [
        ROOT / "report/thesis_latex/main.log",
        ROOT / "report/ppt/rrp_defense.log",
    ]
    overfull = sum(
        path.read_text(encoding="utf-8", errors="replace").count("Overfull")
        for path in logs
        if path.exists()
    )
    verification = {
        "primary_model": "Global RRP",
        "publication_models": models,
        "model_count": len(models),
        "thesis_pages": _pdf_page_count(thesis_pdf),
        "slides_pages": _pdf_page_count(slides_pdf),
        "compile_passes": 3,
        "overfull_boxes": overfull,
        "annualization_days": audit["annualization_days"],
        "estimation_window_days": audit["estimation_window_days"],
        "primary_audit_status": audit["status"],
        "figures": "high-contrast red-blue PNG and vector PDF",
    }
    (ROOT / "results/tables/publication_build_verification.json").write_text(
        json.dumps(verification, indent=2), encoding="utf-8"
    )


def main():
    if not os.environ.get("TUSHARE_TOKEN"):
        raise RuntimeError("Set TUSHARE_TOKEN before running; existing results are untouched.")
    records = []
    python = sys.executable
    commands = [
        [python, "scripts/update_etf_data.py", "--provider", "tushare", "--start-date", "20000101", "--end-date", "20260831"],
        [python, "scripts/run_global_rrp_rolling_calibration.py"],
        [python, "scripts/verify_global_rrp_rolling_calibration.py"],
        [python, "scripts/run_asset_descriptive_statistics.py"],
        [python, "scripts/publish_global_rrp.py"],
        [python, "scripts/export_primary_weekly_holdings.py"],
        [python, "scripts/render_publication_figures.py"],
        [python, "scripts/sync_global_rrp_docs.py"],
    ]
    try:
        for command in commands:
            print("Running", command[1], flush=True)
            completed = subprocess.run(command, cwd=ROOT)
            records.append({"step": command[1], "returncode": completed.returncode})
            completed.check_returncode()
        for folder, stem in [("thesis_latex", "main"), ("ppt", "rrp_defense")]:
            cwd = ROOT / "report" / folder
            for pass_index in range(3):
                subprocess.run(["xelatex", "-interaction=nonstopmode", "-halt-on-error", f"{stem}.tex"], cwd=cwd, check=True)
                if pass_index == 0 and stem == "main":
                    subprocess.run(["bibtex", stem], cwd=cwd, check=True)
            records.append({"step": f"{folder}/{stem}.pdf", "returncode": 0})
        _write_build_verification()
    finally:
        (ROOT / "results/tables/primary_pipeline_checklist.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
        subprocess.run([python, "scripts/cleanup_temp.py"], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
