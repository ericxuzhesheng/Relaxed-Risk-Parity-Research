import numpy as np
import pytest

from scripts.audit_defense_consistency import reconcile_tracking_distance


def test_original_tracking_is_preserved_across_reference_solver_residuals():
    weights = np.array([0.55, 0.45])
    reference = np.array([0.5, 0.5])
    replay = reference + np.array([3e-6, -3e-6])
    objective = float(np.sum((weights - reference)**2))
    recorded, reconstructed = reconcile_tracking_distance(weights, replay, objective)
    assert recorded == np.sqrt(objective)
    assert reconstructed == np.linalg.norm(weights - replay)
    assert abs(recorded - reconstructed) < 1e-5


def test_material_reference_mismatch_still_fails():
    with pytest.raises(AssertionError):
        reconcile_tracking_distance(np.array([0.55, 0.45]), np.array([0.51, 0.49]), .005)
