import numpy as np
import pandas as pd
import pytest
from src.backtest import _rrp_parameter_schedule, run_static_backtest


@pytest.mark.parametrize('covariance_method,mean_halflife', [('ewma',60.),('ledoit_wolf',20.)])
def test_ewma_uses_only_history_and_admits_later_assets(covariance_method,mean_halflife):
    rng=np.random.default_rng(123)
    data=pd.DataFrame(rng.normal(.0003,.008,(145,3)),
                      index=pd.bdate_range('2015-01-05',periods=145),columns=['沪深300ETF','黄金ETF','纳指ETF'])
    data.iloc[:65,2]=np.nan
    config={'rebalance_frequency':'W','risk_overlay_enabled':False,'trend_filter_mode':'off',
            'bond_leverage_upper':1.,'rrp_variance_reference':'equal_weight',
            'mean_estimator':'ewma','mean_ewma_halflife':mean_halflife,'covariance_method':covariance_method,
            'ewma_halflife':60.,'lookback_weeks':48}
    diag={}
    first=run_static_backtest(data,'relaxed',config,diag)
    changed=data.copy();changed.iloc[135:]*=-3
    second=run_static_backtest(changed,'relaxed',config)
    pd.testing.assert_frame_equal(first.iloc[:135],second.iloc[:135])
    assert (pd.to_datetime(diag['solver'].information_cutoff)<pd.to_datetime(diag['solver'].date)).all()
    universe=diag['universe']
    eligible=universe.included_assets.str.contains('纳指ETF')
    assert eligible.any()
    assert universe.loc[eligible,'date'].min()>data.index[123]
    assert first.loc[first.date.le(data.index[123]),'weight_纳指ETF'].eq(0).all()


def test_252_day_window_and_penalty_schedule_are_point_in_time():
    rng=np.random.default_rng(42)
    data=pd.DataFrame(rng.normal(.0002,.007,(330,3)),
                      index=pd.bdate_range('2019-01-02',periods=330),columns=['沪深300ETF','黄金ETF','纳指ETF'])
    effective=data.index[280]
    cfg={'rebalance_frequency':'W','risk_overlay_enabled':False,'trend_filter_mode':'off',
         'lookback_days':252,'trading_days_per_year':252,'rrp_return_target_mode':'reference',
         'mean_estimator':'ewma','mean_ewma_halflife':20.,'covariance_method':'ledoit_wolf',
         'rrp_parameter_schedule':[{'effective_date':str(effective.date()),
             'rrp_variance_penalty':.03,'lambda_pen':.7}]}
    diag={}
    run_static_backtest(data,'relaxed',cfg,diag)
    solver=diag['solver'];dates=pd.to_datetime(solver.date)
    before=solver[dates<effective]
    after=solver[dates>=effective]
    assert (before.selected_variance_penalty==.10).all()
    assert (before.selected_shortfall_penalty==1.9).all()
    assert (after.selected_variance_penalty==.03).all()
    assert (after.selected_shortfall_penalty==.7).all()
    assert solver.reference_predicted_annual_return.equals(solver.target_annual_return)
    covariance=diag['covariance']
    assert covariance.covariance_observations.max() <= 252


def test_parameter_schedule_rejects_missing_effective_date():
    with pytest.raises(ValueError, match="effective dates"):
        _rrp_parameter_schedule({"rrp_parameter_schedule": [{
            "effective_date": None,
            "rrp_variance_penalty": .1,
            "lambda_pen": 1.,
        }]})
