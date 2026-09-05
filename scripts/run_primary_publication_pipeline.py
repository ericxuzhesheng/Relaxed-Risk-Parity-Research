"""Reproduce the designated primary model and its publication artifacts."""
from pathlib import Path
import os
import subprocess
import sys
import json

ROOT = Path(__file__).resolve().parents[1]


def main():
    if not os.environ.get("TUSHARE_TOKEN"):
        raise RuntimeError("Set TUSHARE_TOKEN before running; existing results are untouched.")
    records = []
    python = sys.executable
    commands = [
        [python, "scripts/update_etf_data.py", "--provider", "tushare", "--start-date", "20000101", "--end-date", "20260831"],
        *[[python, "scripts/run_global_rrp_frontier.py", "--variant", variant, "--round", "round_01"] for variant in ["sample_mean_ewma60", "ewma_cov_mean60", "lw_cov_mean60", "ewma_cov_mean20"]],
        [python, "scripts/run_global_rrp_frontier.py", "--variant", "lw_cov_mean20", "--round", "round_02"],
        [python, "scripts/run_global_rrp_frontier.py", "--variant", "lw_cov_mean20", "--round", "round_02", "--full-history"],
        [python, "scripts/verify_global_rrp_frontier.py"],
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
    finally:
        (ROOT / "results/tables/primary_pipeline_checklist.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
        subprocess.run([python, "scripts/cleanup_temp.py"], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
