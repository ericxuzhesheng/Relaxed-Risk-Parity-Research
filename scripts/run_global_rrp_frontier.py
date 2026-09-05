"""Independent, logged return/drawdown research; never updates publication files."""
from pathlib import Path
import argparse
import json
import logging
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_global_rrp_research import COMMON, participation
from scripts.run_convex_adaptive_rrp import summarize_result, slice_and_rebase_result
from src.backtest import run_static_backtest
from src.data_loader import load_data
from src.utils import get_config

BASE = {**COMMON, 'risk_overlay_enabled':False, 'trend_filter_mode':'off', 'rrp_variance_reference':'equal_weight'}
VARIANTS = {
    'sample_mean_ewma60': {'mean_estimator':'ewma','mean_ewma_halflife':60.},
    'ewma_cov_mean60': {'mean_estimator':'ewma','mean_ewma_halflife':60.,'covariance_method':'ewma','ewma_halflife':60.},
    'lw_cov_mean60': {'mean_estimator':'ewma','mean_ewma_halflife':60.,'covariance_method':'ledoit_wolf'},
    'ewma_cov_mean20': {'mean_estimator':'ewma','mean_ewma_halflife':20.,'covariance_method':'ewma','ewma_halflife':60.},
    'lw_cov_mean20': {'mean_estimator':'ewma','mean_ewma_halflife':20.,'covariance_method':'ledoit_wolf'},
}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--variant',choices=VARIANTS,required=True)
    parser.add_argument('--round',default='round_01',choices=['round_01','round_02'])
    parser.add_argument('--full-history',action='store_true',help='Verify with all cached history in a separate output directory.')
    args=parser.parse_args()
    logging.getLogger().setLevel(logging.ERROR)
    folder=ROOT/'results/global_rrp_frontier'/args.round/args.variant
    if args.full_history:
        folder=folder/'full_history_verification'
    folder.mkdir(parents=True,exist_ok=True)
    overrides={**BASE,**VARIANTS[args.variant]}
    (folder/'configuration.json').write_text(json.dumps({'variant':args.variant,'configuration':overrides,
        'target_net_annual_return':.10,'target_max_drawdown':-.08,'full_history':args.full_history,
        'hypothesis':'Faster historical mean and covariance updates reduce persistence of stale exposures. Half-lives 20/60 reuse existing project horizons.',
        'selection':'Exploratory research; no public promotion','risk_free_rate':0.},indent=2),encoding='utf-8')
    try:
        cfg=get_config(overrides)
        returns=load_data(source='tushare',force_update=False).dropna(how='all')
        # No overlays or persistent signals: only the bounded estimation window
        # and preceding portfolio matter. Keep two complete lookbacks for warm-up.
        start=max(0,returns.index.searchsorted(cfg['evaluation_start_date'])-2*cfg['lookback_weeks']*5)
        if not args.full_history:
            returns=returns.iloc[start:]
        diagnostics={}
        result=run_static_backtest(returns,'relaxed',overrides,diagnostics)
        result=slice_and_rebase_result(result,cfg['evaluation_start_date'])
        solver=diagnostics['solver'];solver=solver[pd.to_datetime(solver.date).ge(cfg['evaluation_start_date'])]
        assert solver.problem_is_dcp.all() and solver.solver_success.all()
        assert (pd.to_datetime(solver.information_cutoff)<pd.to_datetime(solver.date)).all()
        weights=result.filter(regex='^weight_').to_numpy();before=result.filter(regex='^previous_weight_').to_numpy()
        np.testing.assert_allclose(weights.sum(axis=1),1,atol=1e-6)
        np.testing.assert_allclose(np.abs(weights-before)[result.is_rebalance_day].sum(axis=1),result.loc[result.is_rebalance_day,'turnover'],atol=1e-6)
        np.testing.assert_allclose(result.gross_return-result.net_return,result.transaction_cost,atol=1e-12)
        assert np.isfinite(result.net_return).all() and weights.min()>=-1e-6
        usage=participation(result,diagnostics['universe'])
        result.to_csv(folder/'daily_returns.csv',index=False)
        usage.to_csv(folder/'asset_participation.csv',index=False)
        for key,frame in diagnostics.items():frame.to_csv(folder/f'{key}.csv',index=False)
        row=summarize_result('Global RRP',result,cfg['evaluation_start_date'],cfg)
        row.update(variant=args.variant,status='passed',assets_ever_used=int(usage.ever_used.sum()),
                   target_met=bool(row['net_annual_return']>=.10 and row['max_drawdown']>=-.08 and usage.ever_used.all()))
        (folder/'summary.json').write_text(json.dumps(row,indent=2),encoding='utf-8')
        print(json.dumps(row),flush=True)
    except Exception as exc:
        (folder/'summary.json').write_text(json.dumps({'variant':args.variant,'status':'failed','error':str(exc)},indent=2),encoding='utf-8')
        raise


if __name__=='__main__':main()
