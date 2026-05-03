from __future__ import annotations

import pandas as pd

from scripts.run_asset_descriptive_statistics import OUTPUT_COLUMNS, compute_asset_statistics


def test_compute_asset_statistics_schema_and_values() -> None:
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    prices = pd.DataFrame(
        {
            "Asset A": [100.0, 101.0, 102.0, 101.0, 103.0],
            "Asset B": [None, 50.0, 50.5, 51.0, 50.0],
        },
        index=dates,
    )
    mapping = pd.DataFrame(
        {
            "new_name": ["Asset A", "Asset B"],
            "ticker": ["A.TEST", "B.TEST"],
            "asset_class": ["equity", "bond"],
        }
    )

    stats = compute_asset_statistics(prices, mapping)

    assert list(stats.columns) == OUTPUT_COLUMNS
    assert len(stats) == 2
    assert set(stats["etf"]) == {"Asset A", "Asset B"}
    assert stats.loc[stats["etf"].eq("Asset B"), "missing_ratio"].iloc[0] > 0
    assert stats["available_observations"].min() >= 4
    assert stats["max_drawdown"].le(0).all()
