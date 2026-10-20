import numpy as np

from scripts.analyze_primary_attribution import brinson_fachler


def test_brinson_cash_overweight_in_falling_market():
    wp = np.array([[0.5, 0.5]])
    wb = np.array([[0.1, 0.9]])
    returns = np.array([[0.001, -0.10]])
    allocation, selection, interaction = brinson_fachler(wp, wb, returns, returns)
    np.testing.assert_allclose(allocation, [[0.03636, 0.00404]])
    np.testing.assert_allclose(selection, 0)
    np.testing.assert_allclose(interaction, 0)
    np.testing.assert_allclose(allocation.sum(), (wp * returns).sum() - (wb * returns).sum())


def test_brinson_selection_interaction_and_zero_category():
    wp = np.array([[0.7, 0.3], [0.0, 1.0]])
    wb = np.array([[0.4, 0.6], [0.2, 0.8]])
    rp = np.array([[0.03, -0.02], [0.01, 0.05]])
    rb = np.array([[0.01, -0.01], [0.01, 0.04]])
    allocation, selection, interaction = brinson_fachler(wp, wb, rp, rb)
    np.testing.assert_allclose(selection[0], [0.008, -0.006])
    np.testing.assert_allclose(interaction[0], [0.006, 0.003])
    np.testing.assert_allclose(
        (allocation + selection + interaction).sum(axis=1),
        (wp * rp).sum(axis=1) - (wb * rb).sum(axis=1), atol=1e-15)
