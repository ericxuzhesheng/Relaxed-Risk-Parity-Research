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
