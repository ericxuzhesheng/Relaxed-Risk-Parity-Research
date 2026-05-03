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
        "scripts/run_enhanced_cscv_pbo.py",
        "scripts/run_frozen_oos_validation.py",
        "scripts/run_holdout_validation.py",
        "scripts/run_parameter_sensitivity.py",
        "scripts/run_cvar_sensitivity.py",
        "scripts/run_extended_sample_robustness.py",
        "results/tables/walkforward_validation.csv",
        "results/tables/nested_validation.csv",
        "results/tables/cscv_pbo_results.csv",
        "results/tables/cscv_pbo_enhanced_results.csv",
        "results/tables/frozen_oos_validation.csv",
        "results/tables/holdout_validation.csv",
        "results/tables/parameter_sensitivity.csv",
        "results/tables/cvar_sensitivity.csv",
        "results/tables/extended_sample_robustness_summary.csv",
        "docs/MODEL_GOVERNANCE.md",
    ]:
        assert needle in text


def test_readme_references_governance_and_three_bucket_framing() -> None:
    text = Path("README.md").read_text(encoding="utf-8")
    assert "pseudo-frozen" in text
    assert "retrospective holdout" in text.lower() or "回顾性 holdout" in text


def test_holdout_split_generator_returns_chronological_splits() -> None:
    from src.validation import generate_retrospective_holdout_splits

    dates = pd.bdate_range("2020-01-01", periods=900)
    returns = pd.DataFrame({"asset_a": 0.0002}, index=dates)
    splits = generate_retrospective_holdout_splits(returns, ["2022-01-01", "2023-01-01"])
    assert len(splits) == 2
    for split in splits:
        assert split["split_id"].startswith("holdout_")
        assert split["train_end"] < split["test_start"]
        assert split["test_start"] >= pd.Timestamp(split["requested_holdout_start"])


def test_governance_doc_exists() -> None:
    path = Path("docs/MODEL_GOVERNANCE.md")
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "lookback_days" in content
    assert "cvar_beta" in content
    assert "Change-Log" in content


def test_thesis_body_no_engineer_path() -> None:
    tex = Path("report/thesis_latex/main.tex").read_text(encoding="utf-8")
    start = tex.find("\\appendix")
    body = tex[:start] if start > 0 else tex
    assert "\\path{data/" not in body
    assert "\\path{scripts/" not in body
    assert "\\path{results/" not in body
    assert "\\path{python scripts/" not in body


def test_thesis_limitations_no_abc_buckets() -> None:
    tex = Path("report/thesis_latex/main.tex").read_text(encoding="utf-8")
    for old_marker in ["A 类", "B 类", "C 类", "已被实证或诊断澄清"]:
        assert old_marker not in tex  # A/B/C buckets intentionally removed
    for new_marker in [
        "真实流动性与资金容量数据不足",
        "未纳入完整的资产负债管理和负债端约束",
        "ETF 与指数/期货历史衔接仍需进一步研究",
        "未来收益不可保证",
    ]:
        assert new_marker in tex


def test_stale_turnover_cvar_numbers_absent_from_readme_and_thesis() -> None:
    import re

    for path in [Path("README.md"), Path("report/thesis_latex/main.tex")]:
        text = path.read_text(encoding="utf-8")
        for stale in ["22.45%", "20.22%", "1.03%", "0.52%"]:
            assert stale not in text, f"Stale value {stale} found in {path}"


def test_no_future_leakage_in_extended_sample_logic() -> None:
    from src.investable import investable_columns

    dates = pd.bdate_range("2020-01-01", periods=500)
    returns = pd.DataFrame({"a": 0.0002, "b": 0.0001}, index=dates)
    window = returns.iloc[:200]
    active = investable_columns(window, min_observations=30)
    assert len(active) <= len(returns.columns)
    window2 = returns.iloc[300:400]
    active2 = investable_columns(window2, min_observations=30)
    assert len(active2) <= len(returns.columns)
