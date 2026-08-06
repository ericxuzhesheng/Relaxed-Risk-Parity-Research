import pandas as pd
import pytest


def test_merge_futures_refresh_preserves_missing_cached_assets_and_extends_overlap():
    from src.futures_data import merge_futures_price_refresh

    existing = pd.DataFrame(
        {
            "asset_a": [100.0, 101.0, 102.0],
            "asset_b": [200.0, 202.0, 204.0],
        },
        index=pd.to_datetime(["2026-05-20", "2026-05-21", "2026-05-22"]),
    )
    refreshed = pd.DataFrame(
        {"asset_a": [50.0, 51.0, 52.0]},
        index=pd.to_datetime(["2026-05-21", "2026-05-22", "2026-05-25"]),
    )

    merged = merge_futures_price_refresh(existing, refreshed)

    assert list(merged.columns) == ["asset_a", "asset_b"]
    pd.testing.assert_series_equal(
        merged.loc[existing.index, "asset_b"],
        existing["asset_b"],
        check_names=False,
    )
    assert merged.loc[pd.Timestamp("2026-05-22"), "asset_a"] == pytest.approx(102.0)
    assert merged.loc[pd.Timestamp("2026-05-25"), "asset_a"] == pytest.approx(104.0)


def test_merge_futures_refresh_keeps_cached_tail_when_refresh_is_stale():
    from src.futures_data import merge_futures_price_refresh

    existing = pd.DataFrame(
        {"asset_a": [100.0, 101.0, 102.0]},
        index=pd.to_datetime(["2026-05-20", "2026-05-21", "2026-05-22"]),
    )
    stale_refresh = pd.DataFrame(
        {"asset_a": [50.0, 51.0]},
        index=pd.to_datetime(["2026-05-20", "2026-05-21"]),
    )

    merged = merge_futures_price_refresh(existing, stale_refresh)

    pd.testing.assert_series_equal(merged["asset_a"].dropna(), existing["asset_a"])


def test_tushare_contract_fetch_retries_transient_failure(monkeypatch):
    from src import futures_data

    class FlakyClient:
        def __init__(self):
            self.calls = 0

        def fut_daily(self, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary throttle")
            return pd.DataFrame(
                {
                    "trade_date": ["20260805"],
                    "close": [123.4],
                    "vol": [10],
                }
            )

    client = FlakyClient()
    monkeypatch.setattr(futures_data.time, "sleep", lambda _seconds: None)

    result = futures_data._fetch_contract_tushare(
        client,
        "AU2610.SHF",
        "20260801",
        "20260806",
    )

    assert client.calls == 2
    assert result is not None
    assert result.iloc[0] == pytest.approx(123.4)


def test_futures_benchmark_is_capped_at_etf_evaluation_end():
    from scripts.run_futures_extension import cap_evaluation_end

    futures_returns = pd.DataFrame(
        {"asset": [0.01, 0.02]},
        index=pd.to_datetime(["2026-08-05", "2026-08-06"]),
    )

    capped = cap_evaluation_end(futures_returns, pd.Timestamp("2026-08-05"))

    assert capped.index.max() == pd.Timestamp("2026-08-05")


def test_average_rebalance_turnover_excludes_non_rebalance_days():
    from scripts.run_futures_extension import average_rebalance_turnover

    turnover = pd.Series([0.0, 0.02, 0.0, 0.04])

    assert average_rebalance_turnover(turnover) == pytest.approx(0.03)


def test_futures_transaction_cost_scales_with_notional():
    from scripts.run_futures_extension import futures_transaction_cost

    assert futures_transaction_cost(turnover=0.25, gross_notional=2.0, cost_bps=5.0) == pytest.approx(0.00025)
