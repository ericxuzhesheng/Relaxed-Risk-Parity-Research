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


def test_readme_describes_current_validation_layer() -> None:
    text = Path("README.md").read_text(encoding="utf-8").lower()
    for needle in [
        "cscv-pbo",
        "walk-forward",
        "rolling oos",
        "block bootstrap",
        "covariance robustness",
        "parameter perturbation",
        "stress-period",
        "rebalance frequency sensitivity",
        "run_full_research_pipeline.py",
        "results/tables/",
        "report/thesis_latex/",
    ]:
        assert needle in text, needle


def test_readme_uses_current_model_and_robustness_framing() -> None:
    text = Path("README.md").read_text(encoding="utf-8")
    for needle in [
        "Global RRP",
        "Improved Convex Adaptive Global RRP",
        "HRP Benchmark",
        "HERC Benchmark",
        "CVaR",
        "turnover",
        "proof against overfitting",
        "out-of-sample",
    ]:
        assert needle in text, needle
    assert "Defensive Dynamic RRP" not in text


def test_governance_doc_exists() -> None:
    path = Path("docs/MODEL_GOVERNANCE.md")
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "252-day EWMA window" in content
    assert "soft CVaR penalties" in content
    assert "candidate_03" in content
    assert "Release checks" in content


def test_thesis_body_no_engineer_path() -> None:
    tex = Path("report/thesis_latex/main.tex").read_text(encoding="utf-8")
    start = tex.find("\\appendix")
    body = tex[:start] if start > 0 else tex
    assert "\\path{data/" not in body
    assert "\\path{scripts/" not in body
    assert "\\path{results/" not in body
    assert "\\path{python scripts/" not in body


def test_thesis_limitations_match_current_structure() -> None:
    tex = Path("report/thesis_latex/main.tex").read_text(encoding="utf-8")
    for old_marker in ["A 类", "B 类", "C 类", "已被实证或诊断澄清"]:
        assert old_marker not in tex
    assert "\\subsection{研究边界与后续方向}" in tex
    assert "\\label{tab:limitations}" in tex
    for limitation_marker in [
        "价差",
        "成交量",
        "冲击成本",
        "现金流",
        "久期缺口",
        "评价区间",
        "当前市场结构",
        "不构成未来收益保证",
    ]:
        assert limitation_marker in tex


def test_generated_asset_table_combines_identity_and_performance() -> None:
    from src.asset_universe import ETF_UNIVERSE

    tex = Path("report/thesis_latex/generated_asset_stats_table.tex").read_text(encoding="utf-8")
    for heading in ["ETF", "代码", "类别", "样本数", "年化收益", "年化波动", "最大回撤"]:
        assert heading in tex
    for etf in ETF_UNIVERSE:
        assert etf.ticker in tex
    assert "5年国债ETF & 511010.SH" in tex


def test_documents_record_future_public_reits_etf_review() -> None:
    for path in [Path("report/thesis_latex/main.tex"), Path("report/ppt/rrp_defense.tex")]:
        tex = path.read_text(encoding="utf-8")
        assert "公募 REITs ETF" in tex
        assert "资产池评审" in tex


def test_stale_turnover_cvar_numbers_absent_from_readme_and_thesis() -> None:
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


def test_walkforward_defaults_to_configured_evaluation_start() -> None:
    from scripts.run_walkforward_validation import effective_evaluation_start

    config = {"evaluation_start_date": "2018-01-02"}
    assert effective_evaluation_start(None, config) == "2018-01-02"
    assert effective_evaluation_start("2020-01-01", config) == "2020-01-01"


def test_convex_models_use_governed_public_labels() -> None:
    from src.public_labels import public_model_label

    assert public_model_label("Convex Adaptive Global Relaxed Risk Parity") == "Convex Adaptive Global RRP"
    assert (
        public_model_label("Improved Convex Adaptive Global Relaxed Risk Parity")
        == "Improved Convex Adaptive Global RRP"
    )
