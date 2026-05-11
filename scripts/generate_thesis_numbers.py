"""Generate ``report/thesis_latex/generated_numbers.tex`` from the
authoritative CSV outputs in ``results/tables/``.

Eliminates the manual copy-paste risk flagged by the audit: any number in
the thesis that should match a CSV is exposed as a LaTeX ``\\newcommand``
so the main document references the command rather than a literal value.

Sources read:
* ``results/tables/convex_adaptive_performance_summary.csv`` — headline
  performance table for the six models.
* ``data/MANIFEST.json`` — evaluation-window start/end dates.
* ``results/tables/sharpe_difference_tests.csv`` — pairwise statistical
  tests (when present).

Output: ``report/thesis_latex/generated_numbers.tex``. Rerunning the
script is idempotent. The output file declares a sentinel comment with
the generation timestamp so it is easy to confirm which run produced the
current snapshot.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.utils import resolve_path


logger = logging.getLogger("generate_thesis_numbers")


# Map of model name (as it appears in the CSV) -> LaTeX command prefix.
MODEL_SLUGS: dict[str, str] = {
    "Global RRP": "global",
    "Defensive Dynamic RRP": "defensive",
    "Convex Adaptive Global Relaxed Risk Parity": "convex",
    "Improved Convex Adaptive Global Relaxed Risk Parity": "improved",
    "HRP Benchmark": "hrp",
    "HERC Benchmark": "herc",
}

# Map of model name -> LaTeX command prefix for sharpe-difference results.
DIFF_SLUGS: dict[tuple[str, str], str] = {
    ("Improved Convex Adaptive Global RRP", "Global RRP"): "improvedVsGlobal",
    ("Improved Convex Adaptive Global RRP", "Defensive Dynamic RRP"): "improvedVsDefensive",
    ("Improved Convex Adaptive Global RRP", "Equal Weight"): "improvedVsEqual",
    ("Global RRP", "Equal Weight"): "globalVsEqual",
    ("Defensive Dynamic RRP", "Equal Weight"): "defensiveVsEqual",
}


def _pct(x: float, digits: int = 2) -> str:
    return f"{100.0 * x:.{digits}f}\\%"


def _num(x: float, digits: int = 3) -> str:
    return f"{x:.{digits}f}"


def _percent_summary_rows(summary: pd.DataFrame) -> list[str]:
    lines: list[str] = []
    indexed = summary.set_index("model")
    for model_name, slug in MODEL_SLUGS.items():
        if model_name not in indexed.index:
            logger.warning("model %s missing from summary CSV; skipping", model_name)
            continue
        row = indexed.loc[model_name]
        lines.append(f"% --- {model_name} ---")
        lines.append(f"\\newcommand{{\\{slug}NetReturn}}{{{_pct(row['net_annual_return'])}}}")
        lines.append(f"\\newcommand{{\\{slug}Volatility}}{{{_pct(row['annualized_volatility'])}}}")
        lines.append(f"\\newcommand{{\\{slug}Sharpe}}{{{_num(row['sharpe_ratio'])}}}")
        lines.append(f"\\newcommand{{\\{slug}Sortino}}{{{_num(row['sortino_ratio'])}}}")
        lines.append(f"\\newcommand{{\\{slug}MaxDD}}{{{_pct(row['max_drawdown'])}}}")
        lines.append(f"\\newcommand{{\\{slug}Calmar}}{{{_num(row['calmar_ratio'])}}}")
        lines.append(
            f"\\newcommand{{\\{slug}MonthlyTurnover}}"
            f"{{{_pct(row['avg_monthly_turnover'])}}}"
        )
        lines.append("")
    return lines


def _manifest_dates() -> tuple[str | None, str | None]:
    path = resolve_path("data/MANIFEST.json")
    if not Path(path).exists():
        return None, None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("could not read data manifest: %s", exc)
        return None, None
    return data.get("first_date"), data.get("last_date")


def _sharpe_diff_rows() -> list[str]:
    path = resolve_path("results/tables/sharpe_difference_tests.csv")
    if not Path(path).exists():
        logger.info("sharpe_difference_tests.csv missing — skipping diff macros")
        return []
    df = pd.read_csv(path)
    lines = ["% --- Sharpe-difference tests (results/tables/sharpe_difference_tests.csv) ---"]
    for _, row in df.iterrows():
        key = (str(row["model_a"]), str(row["model_b"]))
        slug = DIFF_SLUGS.get(key)
        if slug is None:
            continue
        lines.append(f"\\newcommand{{\\{slug}Diff}}{{{_num(row['observed_difference'])}}}")
        lines.append(f"\\newcommand{{\\{slug}CILow}}{{{_num(row['ci_low'])}}}")
        lines.append(f"\\newcommand{{\\{slug}CIHigh}}{{{_num(row['ci_high'])}}}")
        lines.append(f"\\newcommand{{\\{slug}PValue}}{{{_num(row['p_value_two_sided'])}}}")
        lines.append(
            f"\\newcommand{{\\{slug}Significant}}"
            f"{{{('显著' if bool(row['significant_at_95pct']) else '不显著')}}}"
        )
        lines.append("")
    return lines


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    summary_path = resolve_path("results/tables/convex_adaptive_performance_summary.csv")
    if not Path(summary_path).exists():
        raise FileNotFoundError(
            f"performance summary not found at {summary_path}; run scripts/run_convex_adaptive_rrp.py first"
        )
    summary = pd.read_csv(summary_path)
    first_date, last_date = _manifest_dates()

    header = [
        "% ===========================================================",
        "%  Auto-generated by scripts/generate_thesis_numbers.py",
        f"%  Generated at (UTC):     {datetime.now(tz=timezone.utc).isoformat()}",
        "%  Sources:",
        "%    - results/tables/convex_adaptive_performance_summary.csv",
        "%    - results/tables/sharpe_difference_tests.csv (optional)",
        "%    - data/MANIFEST.json (optional, for evaluation dates)",
        "%  Do not edit by hand. Run the generator script after every",
        "%  pipeline rerun to keep thesis numbers in sync with the CSVs.",
        "% ===========================================================",
        "",
    ]
    if first_date is not None:
        header.append(f"\\newcommand{{\\dataFirstDate}}{{{first_date}}}")
    if last_date is not None:
        header.append(f"\\newcommand{{\\dataLastDate}}{{{last_date}}}")
    header.append("")

    content = header + _percent_summary_rows(summary) + _sharpe_diff_rows()
    out_path = resolve_path("report/thesis_latex/generated_numbers.tex")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text("\n".join(content) + "\n", encoding="utf-8")
    logger.info("wrote %d lines -> %s", len(content), out_path)


if __name__ == "__main__":
    main()
