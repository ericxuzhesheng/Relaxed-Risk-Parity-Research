import numpy as np
import pandas as pd
import pytest
from src.backtest import run_static_backtest


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
