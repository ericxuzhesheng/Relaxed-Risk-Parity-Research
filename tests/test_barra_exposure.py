import numpy as np
import pandas as pd


def _anchor_returns(n: int = 8) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=n)
    base = np.arange(1, n + 1, dtype=float) / 10_000.0
    return pd.DataFrame(
        {
            "510300.SH": base + 0.0010,
            "511880.SH": base,
            "512100.SH": base + 0.0015,
            "510880.SH": base + 0.0007,
            "511260.SH": base + 0.0004,
            "511030.SH": base + 0.0003,
            "511010.SH": base + 0.0001,
            "159980.SZ": base + 0.0010,
            "159981.SZ": base + 0.0012,
            "159985.SZ": base + 0.0008,
            "518880.SH": base + 0.0006,
            "162411.SZ": base + 0.0014,
            "159920.SZ": base + 0.0010,
            "159941.SZ": base + 0.0012,
            "513500.SH": base + 0.0014,
            "513880.SH": base + 0.0016,
            "513030.SH": base + 0.0018,
        },
        index=dates,
    )


def test_barra_style_factor_proxies_follow_declared_spreads():
    from src.barra_exposure import build_barra_style_factors

    returns = _anchor_returns()
    factors = build_barra_style_factors(returns)

    assert list(factors.columns) == [
        "china_market",
        "china_size",
        "china_value",
        "duration",
        "credit",
        "commodity",
        "global_equity",
    ]
    assert np.allclose(factors["china_market"], returns["510300.SH"] - returns["511880.SH"])
    assert np.allclose(factors["china_size"], returns["512100.SH"] - returns["510300.SH"])
    assert np.allclose(factors["duration"], returns["511260.SH"] - returns["511880.SH"])


def test_standardized_exposures_detect_positive_and_negative_factor_loading():
    from src.barra_exposure import estimate_standardized_exposures

    rng = np.random.default_rng(19)
    dates = pd.bdate_range("2022-01-03", periods=180)
    factors = pd.DataFrame(
        rng.normal(size=(len(dates), 3)),
        index=dates,
        columns=["china_market", "duration", "commodity"],
    )
    returns = pd.DataFrame(
        {
            "positive": factors["china_market"] + rng.normal(0.0, 0.05, len(dates)),
            "negative": -factors["china_market"] + rng.normal(0.0, 0.05, len(dates)),
        },
        index=dates,
    )

    exposures = estimate_standardized_exposures(returns, factors, min_observations=120).set_index("ts_code")

    assert exposures.loc["positive", "exposure_china_market"] > 0.95
    assert exposures.loc["negative", "exposure_china_market"] < -0.95
    assert (exposures["min_factor_observations"] >= 120).all()


def test_exposure_correlation_matrix_is_symmetric_with_unit_diagonal():
    from src.barra_exposure import exposure_correlation_matrix

    exposures = pd.DataFrame(
        {
            "ts_code": ["A", "B", "C"],
            "exposure_one": [1.0, 2.0, -1.0],
            "exposure_two": [0.0, 0.0, 0.0],
            "exposure_three": [-1.0, -2.0, 1.0],
        }
    )

    corr = exposure_correlation_matrix(exposures)

    assert corr.index.tolist() == ["A", "B", "C"]
    assert corr.columns.tolist() == ["A", "B", "C"]
    assert np.allclose(corr, corr.T)
    assert np.allclose(np.diag(corr), 1.0)
    assert corr.loc["A", "B"] == 1.0
    assert corr.loc["A", "C"] == -1.0
