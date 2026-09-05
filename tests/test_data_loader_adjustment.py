from __future__ import annotations

import pandas as pd


def test_adjustment_factor_extends_back_to_daily_history_start() -> None:
    from src.data_loader import adjusted_fund_close

    dates = pd.to_datetime(["2007-01-18", "2015-11-19", "2015-11-20"])
    close = pd.Series([10.0, 11.0, 12.0], index=dates)
    factor = pd.Series([2.0, 2.2], index=dates[1:])

    adjusted = adjusted_fund_close(close, factor)

    assert adjusted.notna().all()
    assert adjusted.loc[dates[0]] == 10.0 * 2.0 / 2.2
    assert adjusted.loc[dates[-1]] == 12.0


def test_incremental_adjusted_history_merge_preserves_return_continuity() -> None:
    from scripts.update_etf_data import merge_adjusted_history

    existing = pd.DataFrame(
        {"ETF A": [100.0, 102.0], "ETF B": [50.0, 51.0]},
        index=pd.to_datetime(["2026-08-27", "2026-08-28"]),
    )
    refreshed = pd.DataFrame(
        {"ETF A": [51.0, 52.0], "ETF B": [102.0, 104.0]},
        index=pd.to_datetime(["2026-08-28", "2026-08-31"]),
    )

    merged = merge_adjusted_history(existing, refreshed)

    assert list(merged.index) == list(
        pd.to_datetime(["2026-08-27", "2026-08-28", "2026-08-31"])
    )
    assert merged.loc[pd.Timestamp("2026-08-27"), "ETF A"] == 50.0
    assert merged.loc[pd.Timestamp("2026-08-27"), "ETF B"] == 100.0
    assert merged.loc[pd.Timestamp("2026-08-31"), "ETF A"] == 52.0
    assert merged.loc[pd.Timestamp("2026-08-31"), "ETF B"] == 104.0
