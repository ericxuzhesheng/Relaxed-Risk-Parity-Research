import numpy as np
import pandas as pd

from scripts.run_primary_diagnostics import (
    experiment_config, replay_targets, risk_matched_weights,
)


def test_risk_matching_uses_cash_covariance_and_detects_infeasibility():
    sigma = np.array([[.04, .001], [.001, .0004]])
    base, cash = np.array([1., 0.]), np.array([0., 1.])
    weights, fraction, feasible = risk_matched_weights(base, cash, sigma, .0025)
    assert 0 < fraction < 1 and feasible
    np.testing.assert_allclose(weights @ sigma @ weights, .0025, atol=1e-12)
    np.testing.assert_allclose(weights.sum(), 1)
    weights, _, feasible = risk_matched_weights(base, cash, sigma, .0001)
    assert not feasible
    np.testing.assert_allclose(weights, cash)
    weights, fraction, feasible = risk_matched_weights(base, cash, sigma, .05)
    assert fraction == 1 and feasible
    np.testing.assert_allclose(weights, base)


def test_delayed_execution_retains_old_holdings_and_charges_actual_trade():
    dates = pd.bdate_range("2020-01-01", periods=5)
    returns = pd.DataFrame({"a": [0, .1, -.2, .1, 0], "b": [0]*5}, index=dates)
    targets = pd.DataFrame([[1., 0.], [0., 1.]], index=dates[[0, 2]], columns=returns.columns)
    immediate = replay_targets(returns, targets)
    delayed = replay_targets(returns, targets, delay=1)
    assert immediate.loc[2, "gross_return"] == 0
    assert delayed.loc[2, "gross_return"] == -.2
    assert delayed.loc[3, "turnover"] == 2
    assert delayed.loc[3, "transaction_cost"] == .0006
    assert delayed.loc[0, "turnover"] == 0


def test_ablations_and_freezing_preserve_prior_schedule_and_input():
    config = {
        "evaluation_start_date": "2018-01-02", "lambda_pen": 1.,
        "rrp_parameter_schedule": [
            {"effective_date": f"{y}-01-01", "information_end": f"{y-1}-12-29",
             "rrp_variance_penalty": v, "lambda_pen": v*10}
            for y, v in [(2017, .1), (2018, .2), (2019, .3)]
        ],
    }
    frozen = experiment_config(config, "frozen")["rrp_parameter_schedule"]
    assert [r["rrp_variance_penalty"] for r in frozen] == [.1, .2, .2]
    ablation = experiment_config(config, "no_shortfall")
    assert all(r["lambda_pen"] == 0 for r in ablation["rrp_parameter_schedule"])
    assert config["rrp_parameter_schedule"][-1]["lambda_pen"] == 3.
