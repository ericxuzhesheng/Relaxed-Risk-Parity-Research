import numpy as np
import pandas as pd
import pytest

from scripts.export_next_month_holdings import build_next_month_holdings
from scripts.run_global_rrp_rolling_calibration import BASE
from src.asset_universe import ETF_UNIVERSE
from src.utils import get_config


def sample():
    rng = np.random.default_rng(41)
    names = [asset.new_name for asset in ETF_UNIVERSE]
    returns = pd.DataFrame(
        rng.normal(0.0002, 0.006, (260, len(names))),
        index=pd.bdate_range(end="2026-09-30", periods=260), columns=names,
    )
    config = get_config({
        **BASE,
        "rrp_parameter_schedule": [{
            "effective_date": "2026-01-01",
            "rrp_variance_penalty": 0.15, "lambda_pen": 3.8,
        }],
    })
    return returns, config


def test_forecast_uses_month_end_information_and_frozen_annual_parameters():
    returns, config = sample()
    holdings, audit = build_next_month_holdings(returns, config, "2026-10-09")
    assert len(holdings) == 30
    assert set(holdings.ticker) == {asset.ticker for asset in ETF_UNIVERSE}
    assert holdings.model.eq("Global RRP").all()
    assert holdings.as_of_date.eq("2026-09-30").all()
    assert holdings.holding_month.eq("2026-10").all()
    assert holdings.weight.ge(0).all()
    assert holdings.weight.sum() == pytest.approx(1.0)
    assert audit["information_cutoff"] == "2026-09-30"
    assert audit["estimation_observations"] == 252
    assert audit["selected_variance_penalty"] == 0.15
    assert audit["selected_shortfall_penalty"] == 3.8
    assert audit["future_realized_returns_used"] is False
    # An unobserved later October decision must not change the same forecast.
    later, _ = build_next_month_holdings(returns, config, "2026-10-16")
    np.testing.assert_allclose(holdings.weight, later.weight, atol=1e-10)
    # The final observed day's return must enter the next-month forecast.
    changed = returns.copy()
    changed.iloc[-1, 5] = 0.20
    revised, _ = build_next_month_holdings(changed, config, "2026-10-09")
    original = holdings.set_index("ticker").weight.sort_index()
    updated = revised.set_index("ticker").weight.sort_index()
    assert not np.allclose(original, updated, atol=1e-5)


@pytest.mark.parametrize("decision", ["2026-09-30", "2026-11-06"])
def test_reject_forecast_outside_next_month(decision):
    returns, config = sample()
    with pytest.raises(ValueError, match="month after"):
        build_next_month_holdings(returns, config, decision)


def test_reject_incomplete_estimation_window():
    returns, config = sample()
    with pytest.raises(ValueError, match="Insufficient history"):
        build_next_month_holdings(returns.tail(251), config, "2026-10-09")
