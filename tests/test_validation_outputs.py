from __future__ import annotations

from pathlib import Path

import pandas as pd


def synthetic_returns() -> pd.DataFrame:
    dates = pd.bdate_range("2020-01-01", periods=900)
    return pd.DataFrame(
        {
            "asset_a": 0.0002,
            "asset_b": 0.0001,
            "asset_c": -0.00005,
        },
        index=dates,
    )


def test_validation_imports() -> None:
    import src.validation as validation

    assert validation.VALIDATION_STATUS


def test_walkforward_and_nested_splits_are_chronological() -> None:
    from src.validation import generate_nested_splits, generate_walkforward_splits

    returns = synthetic_returns()
    wf = generate_walkforward_splits(returns, train_months=12, validation_months=3, test_months=2, step_months=2, max_splits=2)
    nested = generate_nested_splits(returns, train_months=12, validation_months=3, test_months=2, step_months=2, max_splits=2)
    for split in wf + nested:
        assert split["train_start"] <= split["train_end"] < split["validation_start"] <= split["validation_end"]
        assert split["validation_end"] < split["test_start"] <= split["test_end"]


def test_frozen_oos_split_starts_at_or_after_requested_date() -> None:
    from src.validation import generate_frozen_oos_split

    split = generate_frozen_oos_split(synthetic_returns(), "2022-01-01")
    assert split["test_start"] >= pd.Timestamp("2022-01-01")
    assert split["train_end"] < split["test_start"]


def test_cscv_splits_are_complementary() -> None:
    from src.validation import generate_cscv_splits

    blocks, combos = generate_cscv_splits(synthetic_returns(), num_blocks=8, max_combinations=3)
    block_ids = {block["block_id"] for block in blocks}
    assert len(blocks) == 8
    for combo in combos:
        ins = set(combo["in_sample_blocks"])
        oos = set(combo["out_of_sample_blocks"])
        assert ins.isdisjoint(oos)
        assert ins | oos == block_ids


def test_pbo_summary_handles_small_score_table() -> None:
    from src.validation import pbo_from_cscv

    scores = pd.DataFrame(
        [
            {"split_id": "a", "candidate_id": "c1", "is_score": 2.0, "oos_score": 1.0},
            {"split_id": "a", "candidate_id": "c2", "is_score": 1.0, "oos_score": 2.0},
            {"split_id": "b", "candidate_id": "c1", "is_score": 1.0, "oos_score": 1.5},
            {"split_id": "b", "candidate_id": "c2", "is_score": 2.0, "oos_score": 1.0},
        ]
    )
    detail, summary = pbo_from_cscv(scores)
    assert len(detail) == 2
    assert 0.0 <= float(summary.loc[0, "pbo"]) <= 1.0


def test_readme_references_validation_scripts_and_outputs() -> None:
    text = Path("README.md").read_text(encoding="utf-8")
    for needle in [
        "scripts/run_walkforward_validation.py",
        "scripts/run_nested_validation.py",
        "scripts/run_cscv_pbo.py",
        "scripts/run_frozen_oos_validation.py",
        "scripts/run_parameter_sensitivity.py",
        "results/tables/walkforward_validation.csv",
        "results/tables/nested_validation.csv",
        "results/tables/cscv_pbo_results.csv",
        "results/tables/frozen_oos_validation.csv",
        "results/tables/parameter_sensitivity.csv",
    ]:
        assert needle in text
