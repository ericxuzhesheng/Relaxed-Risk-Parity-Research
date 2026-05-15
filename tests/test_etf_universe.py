import pandas as pd
import pytest

from src.asset_universe import asset_mapping_frame, etf_names
from src.data_loader import load_data, price_to_returns
from src.investable import investable_columns


def test_asset_mapping_is_etf_only_and_complete():
    mapping = asset_mapping_frame()
    assert set(mapping["old_name"]) >= {"中证转债", "豆粕连续"}
    assert mapping["new_name"].tolist() == etf_names()
    assert mapping["ticker"].str.len().gt(0).all()
    assert mapping["ticker"].str.endswith((".SH", ".SZ")).all()
    assert not {"0-5中高信用票", "中证转债", "豆粕连续"}.intersection(mapping["new_name"])
    assert len(mapping) == 30


def test_price_to_returns_preserves_pre_listing_nan():
    dates = pd.bdate_range("2024-01-01", periods=6)
    prices = pd.DataFrame(
        {
            "old_etf": [1.0, 1.1, 1.2, 1.3, 1.4, 1.5],
            "new_etf": [None, None, None, 2.0, 2.1, 2.2],
        },
        index=dates,
    )
    returns = price_to_returns(prices)
    assert returns.loc[dates[1], "old_etf"] == pytest.approx(0.1)
    assert pd.isna(returns.loc[dates[2], "new_etf"])
    assert pd.isna(returns.loc[dates[3], "new_etf"])
    assert returns.loc[dates[4], "new_etf"] > 0


def test_investable_columns_require_real_observations():
    dates = pd.bdate_range("2024-01-01", periods=8)
    returns = pd.DataFrame(
        {
            "seasoned": [0.01, 0.02, -0.01, 0.03, 0.01, 0.02, -0.02, 0.01],
            "unlisted": [None, None, None, None, 0.01, 0.02, 0.01, 0.02],
        },
        index=dates,
    )
    assert investable_columns(returns, min_observations=5) == ["seasoned"]
