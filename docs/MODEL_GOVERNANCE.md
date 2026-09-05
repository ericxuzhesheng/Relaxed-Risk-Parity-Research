# Model Governance

## Published models

| Role | Model |
|---|---|
| Primary | Improved Convex Adaptive Global RRP |
| Comparison | Global RRP |
| Comparison | Convex Adaptive Global RRP |
| Comparison | HRP Benchmark |
| Comparison | HERC Benchmark |
| Comparison | Equal Weight |
| Comparison | 60/40 Benchmark |

Use these names in text, tables and figures. Constraint and frequency variants are experiment settings within this study.

## Primary specification

The primary model rebalances weekly. It uses a 252-observation EWMA window with half-life 60, a 0.25 reference-tracking coefficient, a 0.02 turnover penalty and an 80% turnover limit. One-way costs are 3 bps.

The portfolio is long-only and unlevered. Cash has no group cap, and individual assets are limited by the unit budget. Bond, defensive, commodity/gold and equity group caps remain 70%, 25%, 40% and 70%. The variance, expected-return and CVaR penalties are zero. These inherited settings are research conventions.

## Data and evidence

The evaluation window is 2018-01-02 through 2026-08-31. The active pool has 30 ETFs and excludes 6 candidates. An asset needs 60 prior valid observations. Realized extreme returns are retained and pre-listing prices are not backfilled.

Rebalance inputs precede the trading date. The daily backtest applies target weights to that day's return and deducts costs. Actual execution prices require separate validation.

Headline metrics use zero risk-free return. Lagged one-year ChinaBond yields provide a separate opportunity-cost comparison. Cash concentration must accompany the Sharpe interpretation.

The specification was chosen after historical experiments. Prior-only inputs do not remove retrospective selection bias. Archived significance and overfitting results do not validate the current specification.

## Reproduction

Run `scripts/run_primary_publication_pipeline.py` with `TUSHARE_TOKEN` set. It refreshes data, runs the comparisons, produces figures and numbers, compiles both PDFs and cleans temporary files.

The configuration and audit are recorded in `results/tables/primary_model_configuration.json` and `results/tables/primary_publication_audit.json`. Failures stop publication. Check that code, tables and documents agree before release.
