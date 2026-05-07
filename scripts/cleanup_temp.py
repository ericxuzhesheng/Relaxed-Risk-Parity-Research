"""Remove temporary and cache files generated during pipeline runs.

Safe to run at any time. Does not touch results/, data/, src/, or report/ content files.
Called automatically by run_full_research_pipeline.py at exit.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _rm(path: Path) -> None:
    if not path.exists():
        return
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        print(f"  removed  {path.relative_to(ROOT)}")
    except PermissionError:
        print(f"  skipped  {path.relative_to(ROOT)}  (permission denied — delete manually as admin)", file=sys.stderr)


def clean_pycache(root: Path) -> None:
    for p in root.rglob("__pycache__"):
        if ".claude/worktrees" not in str(p):
            _rm(p)


def clean_pytest_cache(root: Path) -> None:
    for p in root.rglob(".pytest_cache"):
        if ".claude/worktrees" not in str(p):
            _rm(p)


def clean_tool_caches(root: Path) -> None:
    for name in (".mypy_cache", ".ruff_cache"):
        _rm(root / name)


def clean_latex_artifacts(root: Path) -> None:
    tex_dir = root / "report" / "thesis_latex"
    if not tex_dir.exists():
        return
    for ext in ("aux", "bbl", "blg", "fdb_latexmk", "fls", "log", "out", "xdv"):
        for f in tex_dir.glob(f"*.{ext}"):
            _rm(f)


def clean_pytest_tmp(root: Path) -> None:
    for pattern in ("tmp_pytest*", "tmp_pytest_run*"):
        for p in root.glob(pattern):
            _rm(p)


def clean_empty_dirs(root: Path) -> None:
    for name in ("notebooks", "results/quick"):
        p = root / name
        if p.exists() and p.is_dir() and not any(p.iterdir()):
            _rm(p)


def main() -> None:
    print("Cleaning temporary files...")
    clean_pycache(ROOT)
    clean_pytest_cache(ROOT)
    clean_tool_caches(ROOT)
    clean_latex_artifacts(ROOT)
    clean_pytest_tmp(ROOT)
    clean_empty_dirs(ROOT)
    print("Done.")


if __name__ == "__main__":
    main()
