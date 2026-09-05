# Model Governance

## Public model

Improved Convex Adaptive Global RRP is one stitched rolling out-of-sample path beginning on 2018-01-02. Each quarterly decision uses completed prior observations, followed by a one-trading-day embargo. A 95% confidence set retains candidates that cannot be distinguished from the best historical Sharpe estimate. Statistical ties follow the declared low-turnover order. A challenger replaces the incumbent only when past-only evidence clears the switching threshold.

The governed public family contains `candidate_03`, `candidate_04`, and `candidate_05`. All three use a 252-day EWMA window, a 40% asset cap, an 80% one-period turnover cap, a 0.02 turnover penalty, a 0.25 risk-budget reference penalty, a 30% cash-group cap, and the same remaining group limits. Their soft CVaR penalties are 0.00, 0.02, and 0.05. They do not use an absolute volatility cap.

The validation-window turnover gate is 4% per month. The stitched public path must remain at or below 2% average monthly turnover. Transaction costs are 3 bps one way.

The current historical path selects `candidate_03` throughout. Its CVaR penalty is zero. Reported drawdown and tail-loss outcomes therefore cannot be attributed to a CVaR penalty. Positive-CVaR candidates and the separate CVaR sensitivity grid remain diagnostic evidence.

## Convex formulation

The optimizer first computes a risk-budget reference with the convex log-barrier formulation. The implementation stage is a disciplined convex program that tracks this reference while applying long-only, full-investment, asset, group, and turnover limits. Optional variance and CVaR terms enter only in convex form.

Leverage-sensitive legacy paths use an exposure variable so the optimization does not contain a bilinear product between weights and leverage. Expected return enters through a convex shortfall penalty when enabled. The solver accepts only an `optimal` status and records feasibility diagnostics after every rebalance.

Covariance estimation uses one common complete sample for the active universe. The estimate is symmetrized, projected onto the positive-semidefinite cone, and given a scale-relative eigenvalue floor. Materially invalid inputs fail closed. The code never relies on an explicit covariance inverse for portfolio optimization.

## Research grid

The 36-configuration grid is exploratory. It supports sensitivity analysis and CSCV/PBO diagnostics, but it cannot overwrite the public rolling path. Cached scores are reusable only when their serialized parameter signatures match the current candidate definitions.

## Data and timing

- The evaluation window runs from 2018-01-02 through 2026-08-31.
- The ETF request window runs from 2000-01-01 through 2026-08-31, while each ETF retains its longest valid history.
- The active universe contains 30 ETFs and the isolated candidate universe contains 6 ETFs.
- An ETF enters the point-in-time universe after 60 valid observations.
- Sharpe and Sortino use the final valid monthly one-year ChinaBond government yield, lagged one month and compounded over 243 trading days.

## Release checks

Publication stops when the active and candidate universes overlap, a required risk-free month is missing, future data enters a decision, a cache signature is stale, the public turnover gate fails, a solver returns anything other than `optimal`, or generated CSV and public documents disagree.

The authoritative selection history is `results/tables/afml_oos_selection.csv`. A governance change must update implementation, tests, generated outputs, and this document in the same release.
