# Model Governance

## Primary model

Improved Convex Adaptive Global RRP is the weekly primary specification. It applies the approved no-concentration-caps transform to the frozen research schedule. Global RRP and all other model families are comparisons. The public label remains stable; `results/tables/primary_model_configuration.json` is the actual configuration record.

The primary path uses candidate_03: 252-observation EWMA window, half-life 60, risk-budget tracking coefficient 0.25, turnover penalty 0.02, 80% one-period turnover limit, one-way cost 3 bps and no leverage. Cash has no group cap and each asset is constrained only by the long-only unit budget. Bond, defensive, commodity/gold and equity upper bounds remain 70%, 25%, 40% and 70%. CVaR, expected-return reward and variance penalties are zero. These inherited numerical settings are research conventions, not empirically calibrated optimal constants.

## Evidence boundaries

The specification was chosen after reviewing historical weekly constraint experiments. Its retrospective selection prevents interpretation as untouched OOS model-selection evidence. The frozen quarterly schedule is retained for reproduction and chooses candidate_03 throughout the public period. The earlier candidate-family confidence and turnover selection gates govern that archived schedule, not promotion of the current primary specification.

Headline Sharpe and Sortino use rf=0. The same return path is also evaluated using lagged one-year ChinaBond yields. Zero risk-free is a reporting convention, not a return improvement. Money-market concentration, actual return, volatility, drawdown, turnover and costs must accompany the primary Sharpe. Primary designation does not imply superiority over every comparison.

## Data and execution

Evaluation is 2018-01-02 through 2026-08-31. The 30 active ETFs and 6 excluded candidates are defined by src/asset_universe.py. An asset requires 60 prior valid observations. Extreme realized returns are retained. Pre-listing prices are not backfilled. Weekly rebalancing uses the last observed trading day in each week, and optimization inputs strictly precede that day. Existing same-day return accounting is retained as a backtest convention, not an intraday execution simulation.

The optimizer computes a convex log-barrier risk-budget reference, followed by a DCP tracking and turnover problem. Non-cash group bounds are subject to the existing point-in-time feasibility policy. Diagnostic outputs expose any relaxation, constraint slack, dual values, solver status and violations. CVaR epigraph tests use the exact empirical fractional-tail definition at 95%.

## Reproduction and release

Run scripts/run_primary_publication_pipeline.py with TUSHARE_TOKEN set. It refreshes ETF and risk-free data, reruns all core paths and the primary frequency experiment, verifies the approved path, generates numbers and figures, compiles both PDFs with three XeLaTeX passes, and cleans temporary artifacts. Failures stop publication. The primary audit requires common dates, finite values, valid accounting, prior-only inputs and reproduction within the existing solver tolerance.

Historical diagnostics outside this entrypoint are archival. Their metrics, PBO scores and significance claims must not be reused as validation of the current primary model. The primary-model data tables, README, AGENTS, thesis and slides must agree before a release. Reference textbooks remain local and are excluded from the release commit.
