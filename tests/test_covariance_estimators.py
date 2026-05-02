import sys

import numpy as np
import pandas as pd
import pytest

from src.covariance_estimators import estimate_covariance


def sample_returns(n=80, k=4):
    rng = np.random.default_rng(123)
    dates = pd.bdate_range("2022-01-03", periods=n)
    data = rng.normal(0.0002, 0.01, size=(n, k))
    return pd.DataFrame(data, index=dates, columns=[f"asset_{i}" for i in range(k)])


def test_sample_covariance_is_finite_square_and_preserves_order():
    returns = sample_returns(k=5)
    cov = estimate_covariance(returns, method="sample")
    assert cov.shape == (5, 5)
    assert list(cov.index) == list(returns.columns)
    assert list(cov.columns) == list(returns.columns)
    assert np.isfinite(cov.values).all()


def test_covariance_dimension_equals_input_asset_count_with_missing_column():
    returns = sample_returns(k=3)
    returns["asset_missing"] = np.nan
    cov = estimate_covariance(returns, method="sample")
    assert cov.shape == (4, 4)
    assert "asset_missing" in cov.columns


def test_ledoit_wolf_success_when_sklearn_is_installed():
    pytest.importorskip("sklearn")
    returns = sample_returns()
    result = estimate_covariance(returns, method="ledoit_wolf", return_diagnostics=True)
    assert result.covariance.shape == (4, 4)
    assert result.diagnostics["covariance_fallback_used"] is False


def test_ledoit_wolf_explicit_fallback_when_sklearn_fails(monkeypatch):
    class FailingLedoitWolf:
        def fit(self, values):
            raise RuntimeError("patched failure")

    class FakeCovarianceModule:
        LedoitWolf = FailingLedoitWolf

    monkeypatch.setitem(sys.modules, "sklearn.covariance", FakeCovarianceModule)
    result = estimate_covariance(sample_returns(), method="ledoit_wolf", allow_fallback=True, return_diagnostics=True)
    assert result.diagnostics["covariance_fallback_used"] is True
    assert result.diagnostics["covariance_fallback_method"] == "sample"
    assert "patched failure" in result.diagnostics["covariance_failure_note"]


def test_ledoit_wolf_without_explicit_fallback_raises(monkeypatch):
    class FailingLedoitWolf:
        def fit(self, values):
            raise RuntimeError("patched failure")

    class FakeCovarianceModule:
        LedoitWolf = FailingLedoitWolf

    monkeypatch.setitem(sys.modules, "sklearn.covariance", FakeCovarianceModule)
    with pytest.raises(RuntimeError):
        estimate_covariance(sample_returns(), method="ledoit_wolf", allow_fallback=False)


def test_ewma_is_finite_symmetric_output():
    cov = estimate_covariance(sample_returns(), method="ewma_halflife_20")
    assert np.isfinite(cov.values).all()
    assert np.allclose(cov.values, cov.values.T)


def test_ewma_recent_observations_receive_higher_weight():
    returns = pd.DataFrame({"asset": [1.0, 0.0, 0.0, 0.0]}, index=pd.bdate_range("2022-01-03", periods=4))
    older = estimate_covariance(returns, method="ewma", ewma_halflife=2.0).iloc[0, 0]
    returns_recent = pd.DataFrame({"asset": [0.0, 0.0, 0.0, 1.0]}, index=returns.index)
    recent = estimate_covariance(returns_recent, method="ewma", ewma_halflife=2.0).iloc[0, 0]
    assert recent > older


def test_diagnostics_contain_required_fields():
    result = estimate_covariance(sample_returns(), method="sample", annualize=True, trading_days=243, return_diagnostics=True)
    required = {
        "covariance_method",
        "covariance_annualized",
        "covariance_trading_days",
        "covariance_fallback_used",
        "covariance_fallback_method",
        "covariance_min_eigenvalue",
        "covariance_max_eigenvalue",
        "covariance_condition_number",
        "covariance_point_in_time",
        "covariance_psd_notes",
    }
    assert required.issubset(result.diagnostics)


def test_estimator_consumes_only_supplied_returns_window():
    returns = sample_returns(n=50, k=3)
    window = returns.iloc[:30]
    cov_window = estimate_covariance(window, method="sample")
    altered_future = returns.copy()
    altered_future.iloc[30:] = altered_future.iloc[30:] * 1000.0
    cov_after_future_change = estimate_covariance(altered_future.iloc[:30], method="sample")
    pd.testing.assert_frame_equal(cov_window, cov_after_future_change)
