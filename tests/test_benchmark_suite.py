import subprocess
import sys

import pandas as pd


def test_benchmark_suite_smoke_outputs(tmp_path):
    subprocess.run(
        [sys.executable, "scripts/run_benchmark_suite.py", "--smoke", "--output-root", str(tmp_path)],
        check=True,
    )
    required = [
        "benchmark_performance_summary.csv",
        "benchmark_turnover_summary.csv",
        "benchmark_drawdown_summary.csv",
    ]
    for name in required:
        path = tmp_path / "tables" / name
        assert path.exists(), name
        assert not pd.read_csv(path).empty, name
    assert (tmp_path / "figures/benchmark_nav_comparison.png").exists()
    assert (tmp_path / "figures/benchmark_drawdown_comparison.png").exists()

    summary = pd.read_csv(tmp_path / "tables/benchmark_performance_summary.csv")
    assert "Equal Weight Benchmark" in set(summary["model"])
    assert "Global RRP" in set(summary["model"])
