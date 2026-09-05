"""Reconcile the research finalist with full history and source returns."""
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_loader import load_data
from src.utils import get_config
from scripts.run_global_rrp_frontier import BASE, VARIANTS
from scripts.run_convex_adaptive_rrp import summarize_result


def main():
    root = ROOT / 'results/global_rrp_frontier'
    folder = root / 'round_02/lw_cov_mean20'
    full = folder / 'full_history_verification'
    result = pd.read_csv(folder / 'daily_returns.csv', parse_dates=['date'])
    verified = pd.read_csv(full / 'daily_returns.csv', parse_dates=['date'])
    assert result.date.equals(verified.date)
    columns = ['net_return', 'gross_return', 'turnover', 'transaction_cost'] + list(result.filter(regex='^(weight_|previous_weight_)'))
    difference = float(np.abs(result[columns].to_numpy() - verified[columns].to_numpy()).max())
    np.testing.assert_allclose(result[columns], verified[columns], atol=1e-6, rtol=0)
    weights = result.filter(regex='^weight_').copy()
    weights.columns = weights.columns.str.removeprefix('weight_')
    source = load_data(source='tushare', force_update=False).reindex(index=result.date, columns=weights.columns)
    gross = (source.fillna(0).to_numpy() * weights.to_numpy()).sum(axis=1)
    np.testing.assert_allclose(gross, result.gross_return, atol=1e-12)
    np.testing.assert_allclose(result.transaction_cost, result.turnover * .0003, atol=1e-12)
    np.testing.assert_allclose(gross - result.transaction_cost, result.net_return, atol=1e-12)
    np.testing.assert_allclose(weights.sum(axis=1), 1., atol=1e-6)
    assert weights.to_numpy().min() >= -1e-6
    universe = pd.read_csv(full / 'universe.csv', parse_dates=['date']).set_index('date')
    ineligible_max = 0.
    for i in result.index[result.is_rebalance_day]:
        eligible = set(str(universe.loc[result.loc[i, 'date'], 'included_assets']).split('|'))
        excluded = weights.columns.difference(list(eligible))
        if len(excluded):
            ineligible_max = max(ineligible_max, float(weights.loc[i, excluded].abs().max()))
    assert ineligible_max < 1e-6
    usage = pd.read_csv(full / 'asset_participation.csv')
    assert len(usage) == 30 and usage.ever_used.all()
    cfg = get_config({**BASE, **VARIANTS['lw_cov_mean20']})
    metrics = summarize_result('Global RRP', verified, cfg['evaluation_start_date'], cfg)
    saved = json.loads((folder / 'summary.json').read_text())
    for key in metrics:
        if key != 'model':
            np.testing.assert_allclose(metrics[key], saved[key], atol=1e-6, rtol=0)
    audit = {'status': 'passed', 'start_date': str(result.date.min().date()),
             'end_date': str(result.date.max().date()), 'observations': len(result),
             'weekly_decisions': int(result.is_rebalance_day.sum()),
             'full_history_max_absolute_difference': difference,
             'ineligible_weight_max': ineligible_max,
             'assets_ever_used': int(usage.ever_used.sum()),
             'smallest_asset_peak_weight': float(usage.max_eligible_weight.min()),
             'held_missing_return_observations': int(((source.isna().to_numpy()) & (weights.to_numpy() > 5e-5)).sum()),
             'missing_return_accounting': 'Existing convention: missing asset returns contribute zero; no weight renormalization.',
             'target_met': bool(metrics['net_annual_return'] >= .10 and metrics['max_drawdown'] >= -.08),
             'selection': 'Historical exploratory selection after round 01; not untouched model-selection OOS evidence.',
             'publication_updated': False, 'metrics': metrics}
    (folder / 'verification.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
    summaries = [json.loads(p.read_text()) for p in sorted(root.glob('round_*/*/summary.json'))]
    pd.DataFrame(summaries).to_csv(root / 'summary.csv', index=False)
    annual = []
    for year, frame in verified.groupby(verified.date.dt.year):
        r = frame.net_return.to_numpy()
        nav = np.r_[1., np.cumprod(1 + r)]
        annual.append({'year': int(year), 'observations': len(r), 'net_period_return': nav[-1]-1,
                       'max_drawdown': float((nav / np.maximum.accumulate(nav)-1).min()),
                       'turnover': frame.turnover.sum(), 'transaction_cost_sum': frame.transaction_cost.sum()})
    pd.DataFrame(annual).to_csv(folder / 'annual_results.csv', index=False)
    print(json.dumps(audit, indent=2))


if __name__ == '__main__':
    main()
