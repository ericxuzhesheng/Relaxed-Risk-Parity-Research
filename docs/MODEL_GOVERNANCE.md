# Model Governance

## Published models

Global RRP is the weekly primary model. HRP Benchmark, HERC Benchmark, Equal Weight and 60/40 Benchmark are monthly comparisons. Estimation and frequency variants are experiments, not additional models.

## Primary specification

A convex log risk-budget problem produces the reference. A second convex problem balances reference tracking, normalized variance and expected-return shortfall. The variance scale is the contemporaneous equal-weight portfolio variance. The inherited variance and shortfall coefficients are 0.10 and 1.9; the forecast target is 1.9 times the nonnegative cross-asset mean forecast. These are research conventions.

The 240-observation window uses Ledoit–Wolf covariance shrinkage and EWMA return estimates with a 20-trading-day half-life. Weights are long-only, sum to one, and receive no post-solve risk scaling. There is no active CVaR or turnover constraint. One-way costs of 3 bps multiply the sum of absolute weight trades.

## Data and evidence

Evaluation spans 2018-01-02 through 2026-08-31, with 243-day annualization and rf=0. The 30-ETF pool excludes six candidates. Eligibility requires 60 prior valid observations and positive variance. Returns retain extremes and pre-listing prices are not backfilled. All 30 assets were materially held, without artificial minimum weights.

Rebalance inputs precede the trading date. The daily backtest applies target weights to that day's return and deducts costs; actual execution prices and capacity need separate validation. Full-history verification matches the evaluated daily results exactly.

The historical research target is approximately 10% net annual return and maximum drawdown no greater than 8%. Selection followed structural research and two logged estimation rounds. Prior-only inputs do not remove retrospective selection bias. Freeze the specification for validation on new observations. Archived significance and overfitting results do not validate this configuration.

## Reproduction

Run `scripts/run_primary_publication_pipeline.py` with `TUSHARE_TOKEN` set. The pipeline refreshes ETF data, reruns fixed experiments and comparisons, generates tables and figures, synchronizes prose, compiles both PDFs and cleans temporary files. ChinaBond is not required under rf=0.

Configuration and validation are recorded in `results/tables/primary_model_configuration.json` and `primary_publication_audit.json`. Full weekly holdings remain in repository CSVs. Check code, tables, figures and both PDFs before release.
