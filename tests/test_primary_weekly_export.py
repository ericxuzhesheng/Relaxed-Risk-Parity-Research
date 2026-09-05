import numpy as np
import pandas as pd
import pytest

from scripts.export_primary_weekly_holdings import build_weekly_tables
from src.asset_universe import ETF_UNIVERSE


def sample():
    # Qingming closes April 4-5; April 3 is the actual week-end trading day.
    dates = pd.to_datetime(['2024-04-01', '2024-04-03', '2024-04-08', '2024-04-12', '2024-04-15'])
    daily = pd.DataFrame({'date': dates, 'is_rebalance_day': [False, True, False, True, True],
                          'gross_return': .001, 'turnover': [0, .2, 0, .2, .2]})
    daily['transaction_cost'] = daily.turnover * .0003
    daily['net_return'] = daily.gross_return - daily.transaction_cost
    for i, asset in enumerate(ETF_UNIVERSE):
        daily['weight_' + asset.new_name] = .6 if i == 0 else .4 if i == 1 else 0.
        daily['previous_weight_' + asset.new_name] = .5 if i < 2 else 0.
    solver = pd.DataFrame({'date': dates[[1, 3, 4]],
                           'information_cutoff': dates[[0, 2, 3]]})
    return daily, solver


def test_full_records_and_distinct_weekly_periods():
    daily, solver = sample()
    weekly, holdings = build_weekly_tables(daily, solver)
    assert len(holdings) == 90
    assert holdings.groupby('rebalance_date').size().eq(30).all()
    assert weekly.trading_days.tolist() == [2, 2, 1]
    assert weekly.holding_period_days.tolist() == [2, 1, 1]
    assert weekly.holding_period_truncated.tolist() == [False, False, True]
    assert weekly.calendar_week_at_sample_end.tolist() == [False, False, True]
    np.testing.assert_allclose((1 + weekly.calendar_week_net_return).prod(), (1 + daily.net_return).prod())
    np.testing.assert_allclose(holdings.groupby('rebalance_date').transaction_cost.sum(), weekly.transaction_cost)
    assert holdings.target_weight.eq(0).sum() == 84


@pytest.mark.parametrize('issue', ['future', 'cost', 'calendar', 'drift'])
def test_reject_inconsistent_source(issue):
    daily, solver = sample()
    if issue == 'future':
        solver.loc[0, 'information_cutoff'] = solver.loc[0, 'date']
    elif issue == 'cost':
        daily.loc[1, 'transaction_cost'] = 0.
    elif issue == 'calendar':
        daily.loc[0, 'is_rebalance_day'] = True
    else:
        daily.loc[1, 'previous_weight_' + ETF_UNIVERSE[0].new_name] = .1
    with pytest.raises((ValueError, AssertionError)):
        build_weekly_tables(daily, solver)
