# Model Governance

## Published models

Global RRP is the weekly primary model. HRP Benchmark, HERC Benchmark, Equal Weight and 60/40 Benchmark are weekly comparisons. Parameter and frequency variants remain research experiments.

## Primary specification

A convex log risk-budget problem produces the reference portfolio. A second convex problem balances reference tracking, normalized variance and expected-return shortfall. The return target equals the predicted return of the contemporaneous feasible reference portfolio.

The lookback and annualization conventions both use 252 trading days. Covariance uses Ledoit-Wolf shrinkage, and expected returns use a 20-trading-day half-life. Weights are long-only, sum to one and receive no post-solve risk scaling. The model has no active CVaR or turnover constraint. One-way costs of 3 bps multiply the sum of absolute weight trades.

Variance and shortfall penalties update once a year. An earlier 252-day block supplies objective-term ratios for three data-derived candidates per penalty. The following 252-day block evaluates the nine combinations after costs. Selection uses the one-standard-error Sharpe set, an adjacent qualifying grid point when available, lower turnover and quarterly stability. The selected values remain fixed for the next year.

All nine candidates enter the one-standard-error set in every annual validation. The procedure therefore limits arbitrary fixed coefficients but does not identify a unique pair. This uncertainty must accompany any discussion of the parameter schedule.

## Data and evidence

Evaluation spans 2018-01-02 through 2026-08-31 with rf=0. The 30-ETF pool excludes six candidates. Eligibility requires 60 prior valid observations and positive variance. Returns retain extremes, and pre-listing prices are not backfilled.

The historical path records 6.13% net annual return, 3.59% annual volatility, a 1.674 Sharpe ratio and -6.80% maximum drawdown. All 30 ETFs receive material allocations during eligible periods.

Rebalance inputs precede the trading date. Saved daily returns reconcile target weights, drifted weights, turnover and costs. The backtest does not establish actual execution prices, market impact or capacity. Historical design choices also prevent an untouched model-selection claim.

## Reproduction

Run `scripts/run_primary_publication_pipeline.py` with `TUSHARE_TOKEN` set. The pipeline refreshes ETF data, reruns annual calibration and four comparisons, generates current tables and figures, synchronizes prose, compiles both PDFs and removes temporary files. The rf=0 convention does not require ChinaBond data.

Configuration and validation live in `results/tables/primary_model_configuration.json` and `primary_publication_audit.json`. The annual schedule and all candidate results are stored beside them. Complete weekly holdings remain in repository CSV files.
