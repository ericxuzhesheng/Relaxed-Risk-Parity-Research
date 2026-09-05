from __future__ import annotations

import pandas as pd
import numpy as np


def test_price_to_returns_preserves_extreme_realized_returns() -> None:
    from src.data_loader import price_to_returns

    changes = np.r_[np.repeat(.001, 90), -.30, .40, np.repeat(.001, 8)]
    dates = pd.bdate_range("2020-01-01", periods=len(changes))
    prices = pd.DataFrame({"asset": 100 * np.cumprod(1 + changes)}, index=dates)
    returns = price_to_returns(prices)
    assert dates[90] in returns.index and dates[91] in returns.index
    np.testing.assert_allclose(returns.loc[dates[90:92], "asset"], [-.30, .40])


def test_future_prices_cannot_change_historical_returns() -> None:
    from src.data_loader import price_to_returns

    changes = np.r_[np.repeat(.001, 90), .15, np.repeat(.001, 9), .8]
    dates = pd.bdate_range("2020-01-01", periods=len(changes))
    prices = pd.DataFrame({"asset": 100 * np.cumprod(1 + changes)}, index=dates)
    before = price_to_returns(prices.iloc[:-1])
    after = price_to_returns(prices).loc[:dates[-2]]
    pd.testing.assert_frame_equal(before, after)


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
