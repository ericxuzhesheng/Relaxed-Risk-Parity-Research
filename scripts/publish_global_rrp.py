"""Publish the historically selected Global RRP specification and four comparisons."""
from pathlib import Path
import json
import sys
import logging
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_global_rrp_frontier import BASE as COMMON, VARIANTS
from scripts.run_convex_adaptive_rrp import summarize_result, run_hrp_like, slice_and_rebase_result
from src.backtest import run_static_backtest
from src.benchmarks import run_benchmark_backtest
from src.data_loader import load_data
from src.utils import get_config
from src.public_labels import PUBLICATION_MODELS, validate_publication_models
from scripts.generate_thesis_numbers import _etf_pool_table, _asset_stats_table

# Selected after the fixed experiments: meets the requested realized-return
# target without adding a fixed forecast-return target. Selection is retrospective.
PRIMARY_VARIANT = "lw_cov_mean20"


def tex_table(headers, rows, align):
    return '\n'.join([r'\begin{tabular}{'+align+'}', r'\toprule', ' & '.join(headers)+r'\\\midrule',
                      *[' & '.join(row)+r'\\' for row in rows], r'\bottomrule', r'\end{tabular}'])


def pct(v):
    return f'{v*100:.2f}'+r'\%'


def main():
    logging.getLogger().setLevel(logging.ERROR)
    tables, thesis = ROOT/'results/tables', ROOT/'report/thesis_latex'
    folder = ROOT/'results/global_rrp_frontier/round_02'/PRIMARY_VARIANT
    research = pd.read_csv(ROOT/'results/global_rrp_frontier/summary.csv')
    if len(research) != len(VARIANTS) or research.set_index('variant').loc[PRIMARY_VARIANT, 'status'] != 'passed':
        raise ValueError('Selected research specification has not passed')
    verification = json.loads((folder/'verification.json').read_text())
    if verification['status'] != 'passed' or not verification['target_met']:
        raise ValueError('Full-history verification has not passed')
    cfg = get_config({**COMMON, **VARIANTS[PRIMARY_VARIANT]})
    primary = pd.read_csv(folder/'daily_returns.csv', parse_dates=['date'])
    solver = pd.read_csv(folder/'solver.csv', parse_dates=['date'])
    solver = solver[solver.date.ge(cfg['evaluation_start_date'])]
    usage = pd.read_csv(folder/'asset_participation.csv')
    returns = load_data(source='tushare', force_update=False).dropna(how='all')
    models = {'Global RRP': primary}
    for name, key in [('HRP Benchmark','hrp'), ('HERC Benchmark','herc')]:
        print('Running', name, flush=True)
        models[name] = run_hrp_like(returns, key, 3.0)
    for name in ['Equal Weight','60/40 Benchmark']:
        models[name] = run_benchmark_backtest(returns, 'Equal Weight Benchmark' if name == 'Equal Weight' else name, transaction_cost_bps=3.)
    summaries, daily = [], {}
    for name, result in models.items():
        net = result.net_return if 'net_return' in result else result.portfolio_return
        gross = result.gross_return if 'gross_return' in result else net + result.turnover.fillna(0)*.0003
        result = slice_and_rebase_result(result.assign(net_return=net, gross_return=gross), cfg['evaluation_start_date'])
        pd.testing.assert_series_equal(result.date, primary.date, check_names=False)
        if not np.isfinite(result.net_return).all():
            raise ValueError('Nonfinite returns')
        daily[name] = result
        summaries.append(summarize_result(name, result, cfg['evaluation_start_date'], cfg))
    summary = pd.DataFrame(summaries)
    validate_publication_models(summary.model)
    summary['role'] = np.where(summary.model.eq('Global RRP'), 'primary', 'comparison')
    summary['risk_free_rate'] = 0.
    summary['rebalance_frequency'] = np.where(summary.role.eq('primary'), 'W', 'M')
    frequencies = []
    for code, label in [('W','Weekly'),('2W','Biweekly'),('M','Monthly'),('Q','Quarterly')]:
        print('Frequency', code, flush=True)
        result = primary if code == 'W' else slice_and_rebase_result(run_static_backtest(returns, 'relaxed', {**COMMON, **VARIANTS[PRIMARY_VARIANT], 'rebalance_frequency':code}), cfg['evaluation_start_date'])
        frequencies.append({'frequency_code':code,'frequency_label':label,'rebalance_count':int(result.is_rebalance_day.sum()),
                            'solver_fallback_rate':0., **summarize_result('Global RRP',result,cfg['evaluation_start_date'],cfg)})
    # Write only after all paths and fixed comparisons completed successfully.
    for name, result in daily.items():
        slug = name.lower().replace('/','_').replace(' ','_')
        result.to_csv(tables/f'comparison_{slug}_returns.csv',index=False)
    for filename in ['model_performance_summary.csv','convex_adaptive_performance_summary.csv','hrp_comparison.csv']:
        summary.to_csv(tables/filename,index=False)
    pd.DataFrame(frequencies).to_csv(tables/'rebalance_frequency_sensitivity.csv',index=False)
    solver.to_csv(tables/'global_rrp_solver_diagnostics.csv',index=False)
    usage.to_csv(tables/'primary_asset_participation.csv',index=False)
    research.to_csv(tables/'primary_constraint_comparison.csv',index=False)
    annual = pd.DataFrame([{'year':year, **summarize_result('Global RRP',g,str(g.date.min().date()),cfg)} for year,g in primary.groupby(primary.date.dt.year)])
    annual.to_csv(tables/'primary_annual_summary.csv',index=False)
    row = summary.iloc[0]
    audit = {'status':'passed','model':'Global RRP','problem_is_dcp':bool(solver.problem_is_dcp.all()),
             'max_constraint_violation':float(solver.max_constraint_violation.max()),
             'future_information_count':int((pd.to_datetime(solver.information_cutoff)>=solver.date).sum()),
             'target_net_annual_return':.10,'target_max_drawdown':-.08,
             'target_met':bool(row.net_annual_return>=.10 and row.max_drawdown>=-.08),
             'full_history_verification':verification,
             'all_eligible_assets_ever_used':bool(usage.loc[usage.eligible_weeks.gt(0),'ever_used'].all()),
             'daily_observations':len(primary),'rebalance_count':int(primary.is_rebalance_day.sum()),
             'risk_free_rate':0.,'selection_is_exploratory':True}
    (tables/'primary_publication_audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
    clean_cfg = {k:v for k,v in cfg.items() if k != 'tushare_token'}
    (tables/'primary_model_configuration.json').write_text(json.dumps({'model':'Global RRP','configuration':clean_cfg,'selected_variant':PRIMARY_VARIANT,'selection':'Selected after structural research and two logged estimation rounds. Meets historical return, drawdown and participation targets. Retrospective research, not untouched validation.'},indent=2),encoding='utf-8')
    macros = {'evalStartDate':cfg['evaluation_start_date'],'evalEndDate':cfg['evaluation_end_date'],'etfCount':'30','txCostBps':'3',
              'primaryRebalances':str(audit['rebalance_count']),'primaryObservations':str(len(primary)),
              'primaryCashMean':pct(primary['weight_日利ETF'].mean()),'primaryCashMax':pct(primary['weight_日利ETF'].max()),
              'primaryAssetsUsed':str(int(usage.ever_used.sum())), 'primaryTargetStatus':'达到' if audit['target_met'] else '未达到',
              'primaryReturnTargetDef':r'$R_t=1.9\max(\overline{\mu}_t,0)$，其中 $\overline{\mu}_t$ 为合格资产预测收益的均值'}
    for suffix, field in [('NetReturn','net_annual_return'),('Volatility','annualized_volatility'),('MaxDD','max_drawdown'),('MonthlyTurnover','avg_monthly_turnover')]:
        macros['global'+suffix] = pct(row[field])
    for suffix, field in [('Sharpe','sharpe_ratio'),('Sortino','sortino_ratio'),('Calmar','calmar_ratio')]:
        macros['global'+suffix] = f'{row[field]:.3f}'
    (thesis/'generated_numbers.tex').write_text('\n'.join('\\newcommand{\\'+k+'}{'+v+'}' for k,v in macros.items())+'\n',encoding='utf-8')
    perf_rows = [[r.model,pct(r.net_annual_return),pct(r.annualized_volatility),f'{r.sharpe_ratio:.3f}',pct(r.max_drawdown),pct(r.avg_monthly_turnover)] for r in summary.itertuples()]
    (thesis/'generated_global_performance.tex').write_text(tex_table(['模型','净年化收益','年化波动','夏普','最大回撤','月均换手'],perf_rows,'lrrrrr'),encoding='utf-8')
    yr_rows = [[str(r.year),pct(r.net_annual_return),pct(r.annualized_volatility),f'{r.sharpe_ratio:.3f}',pct(r.max_drawdown)] for r in annual.itertuples()]
    (thesis/'generated_primary_annual.tex').write_text(tex_table(['年份','净年化收益','年化波动','夏普','最大回撤'],yr_rows,'lrrrr'),encoding='utf-8')
    labels = {'sample_mean_ewma60':'样本协方差／收益半衰期60日','ewma_cov_mean60':'指数协方差／收益半衰期60日','lw_cov_mean60':'收缩协方差／收益半衰期60日','ewma_cov_mean20':'指数协方差／收益半衰期20日','lw_cov_mean20':'收缩协方差／收益半衰期20日'}
    exp_rows = [[labels[r.variant], pct(r.net_annual_return),f'{r.sharpe_ratio:.3f}',pct(r.max_drawdown),str(int(r.assets_ever_used))] if r.status == 'passed' else [labels[r.variant],'失败','--','--','--'] for r in research.itertuples()]
    (thesis/'generated_primary_constraints.tex').write_text(tex_table(['实验配置','净年化收益','夏普','最大回撤','持有资产数'],exp_rows,'lrrrr'),encoding='utf-8')
    _etf_pool_table(thesis)
    _asset_stats_table(pd.read_csv(tables/'asset_descriptive_statistics.csv'),thesis)
    print(json.dumps(audit),flush=True)


if __name__ == '__main__':
    main()
