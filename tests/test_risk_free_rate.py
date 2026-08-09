from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _daily(rows: list[tuple[str, float, str]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["trade_date", "yield_pct", "provider"])


def test_monthly_rates_use_last_observation_and_apply_next_month() -> None:
    from src.risk_free import build_monthly_rates

    daily = _daily(
        [
            ("2017-11-29", 3.80, "tushare_yc_cb"),
            ("2017-11-30", 3.81, "tushare_yc_cb"),
            ("2017-12-28", 3.82, "tushare_yc_cb"),
            ("2017-12-29", 3.83, "tushare_yc_cb"),
            ("2018-01-31", 3.84, "tushare_yc_cb"),
        ]
    )

    monthly = build_monthly_rates(daily)

    assert monthly["observation_date"].dt.strftime("%Y-%m-%d").tolist() == [
        "2017-11-30",
        "2017-12-29",
        "2018-01-31",
    ]
    assert monthly["effective_month"].astype(str).tolist() == [
        "2017-12",
        "2018-01",
        "2018-02",
    ]
    assert monthly["annual_yield"].tolist() == pytest.approx([0.0381, 0.0383, 0.0384])


def test_daily_risk_free_returns_use_prior_month_and_effective_compounding() -> None:
    from src.risk_free import build_daily_risk_free_returns, build_monthly_rates

    monthly = build_monthly_rates(
        _daily(
            [
                ("2017-12-29", 3.65, "tushare_yc_cb"),
                ("2018-01-31", 3.70, "tushare_yc_cb"),
            ]
        )
    )
    trading_days = pd.DatetimeIndex(["2018-01-02", "2018-01-31", "2018-02-01"])

    result = build_daily_risk_free_returns(trading_days, monthly, trading_days_per_year=243)

    assert result.loc["2018-01-02"] == pytest.approx((1.0 + 0.0365) ** (1.0 / 243.0) - 1.0)
    assert result.loc["2018-01-31"] == pytest.approx(result.loc["2018-01-02"])
    assert result.loc["2018-02-01"] == pytest.approx((1.0 + 0.0370) ** (1.0 / 243.0) - 1.0)


def test_daily_risk_free_returns_fail_when_effective_month_is_missing() -> None:
    from src.risk_free import build_daily_risk_free_returns, build_monthly_rates

    monthly = build_monthly_rates(_daily([("2017-12-29", 3.65, "tushare_yc_cb")]))

    with pytest.raises(ValueError, match="missing monthly risk-free rates.*2018-02"):
        build_daily_risk_free_returns(
            pd.DatetimeIndex(["2018-01-02", "2018-02-01"]),
            monthly,
            trading_days_per_year=243,
        )


def test_provider_merge_fills_missing_dates_and_rejects_conflicts() -> None:
    from src.risk_free import merge_provider_yields

    primary = _daily([("2017-12-29", 3.83, "tushare_yc_cb")])
    fallback = _daily(
        [
            ("2017-11-30", 3.81, "chinabond_official"),
            ("2017-12-29", 3.83, "chinabond_official"),
        ]
    )

    combined = merge_provider_yields(primary, fallback)
    assert combined["trade_date"].dt.strftime("%Y-%m-%d").tolist() == ["2017-11-30", "2017-12-29"]
    assert combined["provider"].tolist() == ["chinabond_official", "tushare_yc_cb"]

    conflicting = fallback.copy()
    conflicting.loc[conflicting["trade_date"].eq("2017-12-29"), "yield_pct"] = 3.90
    with pytest.raises(ValueError, match="provider conflict"):
        merge_provider_yields(primary, conflicting)


def test_collect_history_uses_fallback_for_missing_months_and_fails_closed() -> None:
    from src.risk_free import collect_risk_free_history

    calls: list[tuple[str, str]] = []

    def primary(start_date: str, end_date: str) -> pd.DataFrame:
        calls.append(("primary", start_date))
        return _daily([("2017-12-29", 3.83, "tushare_yc_cb")])

    def fallback(start_date: str, end_date: str) -> pd.DataFrame:
        calls.append(("fallback", start_date))
        return _daily([("2018-01-31", 3.84, "chinabond_official")])

    combined = collect_risk_free_history(
        "2017-12-01",
        "2018-01-31",
        primary_fetcher=primary,
        fallback_fetcher=fallback,
    )
    assert calls == [("primary", "2017-12-01"), ("fallback", "2017-12-01")]
    assert combined["trade_date"].dt.strftime("%Y-%m-%d").tolist() == ["2017-12-29", "2018-01-31"]

    with pytest.raises(ValueError, match="missing monthly risk-free observations.*2018-01"):
        collect_risk_free_history(
            "2017-12-01",
            "2018-01-31",
            primary_fetcher=primary,
            fallback_fetcher=lambda _start, _end: _daily([]),
        )


def test_incremental_refresh_reuses_history_and_refetches_last_month(tmp_path) -> None:
    from scripts.update_risk_free_rate import incremental_refresh_start, merge_incremental_history

    cached = _daily(
        [
            ("2026-05-29", 1.42, "chinabond_official"),
            ("2026-06-30", 1.36, "chinabond_official"),
        ]
    )
    raw_path = tmp_path / "risk_free_daily.csv"
    cached.to_csv(raw_path, index=False)

    assert incremental_refresh_start("2000-01-01", raw_path) == "2026-06-01"

    fetched = _daily(
        [
            ("2026-06-30", 1.36, "tushare_yc_cb"),
            ("2026-07-31", 1.35, "tushare_yc_cb"),
        ]
    )
    combined = merge_incremental_history(cached, fetched)
    assert combined["trade_date"].dt.strftime("%Y-%m-%d").tolist() == [
        "2026-05-29",
        "2026-06-30",
        "2026-07-31",
    ]

    conflicting = fetched.copy()
    conflicting.loc[conflicting["trade_date"].eq("2026-06-30"), "yield_pct"] = 1.37
    with pytest.raises(ValueError, match="provider conflict"):
        merge_incremental_history(cached, conflicting)


def test_metrics_use_aligned_daily_excess_returns() -> None:
    from src.metrics import calculate_metrics

    dates = pd.bdate_range("2018-01-02", periods=5)
    portfolio_returns = pd.Series([0.0, 0.010, -0.004, 0.006, -0.002], index=dates)
    nav = (1.0 + portfolio_returns).cumprod()
    risk_free = pd.Series(0.0001, index=dates)

    metrics = calculate_metrics(nav, risk_free_returns=risk_free, trading_days=243)
    aligned_returns = nav.pct_change().dropna()
    excess = aligned_returns - risk_free.reindex(aligned_returns.index)
    expected_sharpe = excess.mean() / aligned_returns.std() * np.sqrt(243)
    downside = excess.clip(upper=0.0)
    expected_sortino = excess.mean() / np.sqrt((downside.pow(2)).mean()) * np.sqrt(243)

    assert metrics["sharpe_ratio"] == pytest.approx(expected_sharpe)
    assert metrics["sortino_ratio"] == pytest.approx(expected_sortino)


def test_metrics_reject_nonzero_scalar_risk_free_rate() -> None:
    from src.metrics import calculate_metrics

    nav = pd.Series([1.0, 1.01, 1.02], index=pd.bdate_range("2018-01-02", periods=3))
    with pytest.raises(TypeError, match="daily risk-free return Series"):
        calculate_metrics(nav, risk_free_returns=0.0182)


def test_public_improved_model_is_frozen_to_candidate_03() -> None:
    from scripts.run_convex_adaptive_rrp import PRIMARY_CANDIDATE_ID, candidate_configurations

    candidates = dict(candidate_configurations(transaction_cost_bps=3.0))
    primary = candidates[PRIMARY_CANDIDATE_ID]

    assert PRIMARY_CANDIDATE_ID == "candidate_03"
    assert primary.lookback_days == 252
    assert primary.covariance_method == "ewma"
    assert primary.max_weight == pytest.approx(0.40)
    assert primary.turnover_cap == pytest.approx(0.60)
    assert primary.turnover_penalty == pytest.approx(0.02)
    assert primary.budget_penalty == pytest.approx(0.25)
    assert primary.cvar_penalty == pytest.approx(0.15)
    assert primary.return_reward == pytest.approx(0.06)
    assert primary.portfolio_vol_cap == pytest.approx(0.025)
