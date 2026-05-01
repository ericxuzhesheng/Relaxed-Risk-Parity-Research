import subprocess
import sys

import pandas as pd


REQUIRED_TABLES = [
    "robustness_subperiod_summary.csv",
    "robustness_covariance_summary.csv",
    "robustness_transaction_cost_summary.csv",
    "robustness_stress_period_summary.csv",
    "robustness_parameter_perturbation.csv",
    "robustness_no_lookahead_audit.csv",
    "robustness_solver_stability.csv",
    "robustness_overall_summary.csv",
]


def test_robustness_smoke_outputs_required_tables(tmp_path):
    subprocess.run(
        [sys.executable, "scripts/run_robustness_tests.py", "--smoke", "--output-root", str(tmp_path)],
        check=True,
    )

    for name in REQUIRED_TABLES:
        path = tmp_path / "tables" / name
        assert path.exists(), name
        assert not pd.read_csv(path).empty, name

    costs = pd.read_csv(tmp_path / "tables" / "robustness_transaction_cost_summary.csv")
    assert set(costs["transaction_cost_bps"].astype(int)) == {0, 5, 10, 20, 50}

    audit = pd.read_csv(tmp_path / "tables" / "robustness_no_lookahead_audit.csv")
    assert {
        "return_universe_loading",
        "monthly_rebalance_schedule",
        "global_rrp_covariance",
        "convex_adaptive_covariance",
        "adaptive_budget_target",
        "transaction_cost_scenarios",
        "parameter_perturbation",
        "stress_period_identification",
        "solver_diagnostics",
    }.issubset(set(audit["component"]))

    perturb = pd.read_csv(tmp_path / "tables" / "robustness_parameter_perturbation.csv")
    assert "selected_baseline" in set(perturb["case"])
    assert perturb["case"].nunique() > 5


def test_readme_uses_public_model_labels_only():
    text = open("README.md", encoding="utf-8").read()
    forbidden = ["V1", "V2", "V3", "V3_Global_RRP", "Dynamic_RRP_before"]
    assert not any(token in text for token in forbidden)
