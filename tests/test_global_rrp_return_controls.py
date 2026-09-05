import numpy as np
import pytest
from src.risk_parity import solve_relaxed_rp


def solve(**overrides):
    sigma = np.diag([.0001, .02, .04])
    diag = {}
    w = solve_relaxed_rp(sigma, np.array([.02, .08, .12]), sigma, 3, .07,
                         {"asset_weight_bounds": (0., 1.), **overrides}, diag)
    return w, diag, sigma


def test_equal_weight_normalization_is_historical_and_convex():
    w, d, sigma = solve(rrp_variance_reference="equal_weight", rrp_target_annual_return=.05)
    assert d['problem_is_dcp'] and d['solver_success']
    assert d['target_annual_return'] == .05
    np.testing.assert_allclose(d['variance_scale'], np.ones(3) @ sigma @ np.ones(3) / 9)
    np.testing.assert_allclose(w.sum(), 1, atol=1e-6)
    assert w.min() >= 0


def test_legacy_scale_remains_default():
    _, d, _ = solve()
    assert d['variance_reference'] == 'risk_budget'
    assert d['target_annual_return'] == .07


def test_reference_target_is_feasible_and_ignores_legacy_multiplier():
    _, d, _ = solve(rrp_return_target_mode="reference", m=999.)
    assert d['target_annual_return'] == pytest.approx(d['reference_predicted_annual_return'])
    assert d['return_target_mode'] == 'reference'


def test_reference_target_rejects_explicit_target():
    with pytest.raises(ValueError):
        solve(rrp_return_target_mode="reference", rrp_target_annual_return=.05)


@pytest.mark.parametrize('overrides', [{'rrp_variance_reference': 'unknown'}, {'rrp_target_annual_return': -1}, {'rrp_target_annual_return': float('nan')}])
def test_invalid_parameters_fail_closed(overrides):
    with pytest.raises(ValueError):
        solve(**overrides)
