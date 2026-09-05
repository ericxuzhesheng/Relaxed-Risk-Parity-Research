# Weekly constraint research

This independent experiment uses the public candidate schedule and execution warm-up. The schedule is frozen, not reselected for any experiment. The current frozen schedule uses candidate_03 throughout. Results are exploratory and do not replace the public model.

## Run

```powershell
$env:MPLBACKEND = 'Agg'
$env:PYTHONIOENCODING = 'utf-8'
.venv\Scripts\python.exe scripts/run_weekly_constraint_research.py
```

TUSHARE_TOKEN must exist in the environment. A fresh run refreshes ETF and risk-free data through the configured evaluation end before running experiments. Refresh logs are stored with the experiment. The entrypoint invokes the repository cleanup script on exit. It neither commits nor pushes.

For an interrupted run:

```powershell
.venv\Scripts\python.exe scripts/run_weekly_constraint_research.py --resume
```

Resume checks serialized configurations and input snapshots before reusing completed experiments. Failed experiments are retried; a changed configuration or input after successful work requires a separate run directory (archive the previous output deliberately before a fresh invocation). Failure files and the append-only event log preserve prior attempts; `summary.csv` represents the latest attempt.

## Input and information timing

The archived legacy loader masks observations outside three full-sample standard deviations and the backtest accounts for masked returns as zero. This leaks future distribution information into historical inputs and can remove tail losses. Its results are reproduced only in `legacy_weekly_reproduction`, and explicitly are not valid OOS evidence.

All main experiments, including the monthly control, use adjusted-price percentage changes without outlier masking. Prices are forward-filled from already observed prices only; no prices are backfilled before listing. Extreme returns remain in both optimization history and realized P&L. The production loader also retains extreme returns. The historical research results remain isolated from the current primary tables. Historical adjusted-price data can still be subject to provider revisions; this is not a vintage-data reconstruction.

Optimization uses dates strictly before the execution date. Monthly or weekly execution occurs on the final observed trading day in that period; the warm-up begins with the inherited initial allocation. The inherited accounting deploys the new weights for the execution day's close-to-close return and charges L1 turnover at 3 bps. This is a discrete daily-bar execution convention, not evidence of attainable execution prices. The original research directory uses 243-day annualization and lagged ChinaBond yields. The --risk-free-zero option writes a separate rf=0 replay to results/weekly_constraint_research_rf0/. The current primary publication uses rf=0, with ChinaBond shown separately. In particular the existing NAV metric excludes the first NAV-to-NAV return; this convention remains identical across experiments.

## Fixed experiments

Monthly control, weekly baseline, no cash-group cap, no individual-asset cap, neither concentration cap, no turnover hard cap, Ledoit-Wolf covariance, relative CVaR, and Ledoit-Wolf plus relative CVaR are the complete declared set. No automated search expands it. Removing the cash cap alone still leaves the individual-asset cap. Covariance changes retain the historical window and disable covariance fallback for Ledoit-Wolf.

The relative CVaR constraint uses the current feasible solution under the same covariance, previous holdings, and objective as its upper bound. Empirical expected shortfall includes fractional probability mass at the VaR atom, matching the scenario epigraph. Consequently the baseline is feasible and optimal for the unchanged objective; numerical differences and constraint redundancy are measured, not interpreted as a new source of return.

Optional optimizer diagnostics expose each explicit constraint's left and right sides, slack and dual. `binding` uses the existing 5e-5 feasibility tolerance; vector components are recorded separately. Nonnegativity of the auxiliary CVaR slack is a variable domain rather than an investment constraint. Effective group caps and the existing point-in-time capacity relaxation are reported; constraints are checked at rebalance time, since subsequent price drift can move exposures outside target caps.

## Outputs and interpretation

`results/weekly_constraint_research/` contains input snapshots, complete per-candidate configurations, data audit, published-baseline reproduction differences, refresh/cleanup logs and timestamped run events. Each experiment exports daily returns (including pre-trade holdings), weights, trades, solver diagnostics, explicit constraints and a completion receipt or failure traceback.

`summary.csv` and `annual_summary.csv` report net performance, turnover, cash/group exposure and HHI concentration. `scenario_cvar_95_daily_loss` is the consistent empirical expected shortfall; the legacy quantile-tail CVaR metric is retained separately for reproduction. `paired_daily_differences.csv` and metric deltas compare common dates against the unfiltered weekly baseline. They are descriptive paired differences, not confidence intervals or significance tests. Partial first/last calendar years disclose their actual date spans.

`target_met` means only that point-estimate net Sharpe is at least 1.0. It does not establish significance, future performance or eligibility to replace the official model. Failures remain in the summary, and invalid controls block downstream runs. A cash-dominated result must be interpreted as such. Current production figures and thesis numbers use the weekly primary publication tables. The no-concentration-caps specification was explicitly designated primary after review; the research runner never promotes a winner automatically.
