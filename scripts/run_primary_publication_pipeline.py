"""Reproduce the designated primary model and its publication artifacts."""
from pathlib import Path
import argparse
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
    diagnostic_audit = json.loads(
        (ROOT / "results/tables/primary_diagnostics_audit.json").read_text(encoding="utf-8")
    )
    if diagnostic_audit["status"] != "passed":
        raise ValueError("Current-specification diagnostics have not passed")
    logs = [
        ROOT / "report/thesis_latex/main.log",
        ROOT / "report/ppt/rrp_defense.log",
    ]
    log_text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in logs)
    overfull = log_text.count("Overfull")
    if overfull or any(note in log_text for note in (
        "There were undefined references", "There were multiply-defined labels",
        "Missing character:",
    )):
        raise ValueError("Publication PDFs require layout, reference or glyph repair")
    font_checks = {}
    for pdf in (thesis_pdf, slides_pdf):
        font_list = subprocess.run(["pdffonts", str(pdf)], capture_output=True, check=True).stdout.decode("utf-8")
        rows = font_list.splitlines()[2:]
        if not rows or any(row.split()[-5] != "yes" for row in rows if row.strip()):
            raise ValueError(f"Unembedded fonts in {pdf}")
        chinese_fonts = sorted({
            row.split()[0] for row in rows
            if any(name in row.lower() for name in ("simsun", "simhei", "yahei", "stzhong", "fangsong"))
        })
        if not chinese_fonts:
            raise ValueError(f"No embedded Chinese font found in {pdf}")
        font_checks[pdf.name] = {"all_fonts_embedded": True, "chinese_fonts": chinese_fonts}
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
        "diagnostic_audit_status": diagnostic_audit["status"],
        "diagnostic_experiment_count": diagnostic_audit["experiment_count"],
        "risk_matching_decisions": diagnostic_audit["risk_matching_decisions"],
        "risk_matching_infeasible_count": diagnostic_audit["risk_matching_infeasible_count"],
        "fonts": font_checks,
        "figures": "high-contrast red-blue PNG and vector PDF",
    }
    (ROOT / "results/tables/publication_build_verification.json").write_text(
        json.dumps(verification, indent=2), encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force-recalibrate", action="store_true",
                        help="Recompute all annual validations instead of reusing matching results")
    parser.add_argument("--force-backtest", action="store_true",
                        help="Recompute all five final backtests from the beginning")
    args = parser.parse_args()
    if not os.environ.get("TUSHARE_TOKEN"):
        raise RuntimeError("Set TUSHARE_TOKEN before running; existing results are untouched.")
    records = []
    python = sys.executable
    commands = [
        [python, "scripts/update_etf_data.py", "--provider", "tushare", "--start-date", "20000101", "--end-date", "20261016"],
        [python, "scripts/run_global_rrp_rolling_calibration.py",
         *(["--force-recalibrate"] if args.force_recalibrate else []),
         *(["--force-backtest"] if args.force_backtest else [])],
        [python, "scripts/verify_global_rrp_rolling_calibration.py"],
        [python, "scripts/run_asset_descriptive_statistics.py"],
        [python, "scripts/publish_global_rrp.py",
         *(["--force-backtest"] if args.force_backtest else [])],
        [python, "scripts/export_primary_weekly_holdings.py"],
        [python, "scripts/export_next_month_holdings.py", "--latest", "--rebalance-date", "2026-10-23"],
        [python, "scripts/render_publication_figures.py"],
        [python, "scripts/run_primary_diagnostics.py"],
        [python, "scripts/analyze_primary_attribution.py"],
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
