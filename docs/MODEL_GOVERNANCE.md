# Model Governance

## Public model

The public Improved Convex Adaptive Global RRP is the stitched rolling OOS path beginning on 2018-01-02. It is not a full-sample best candidate. At each quarterly selection date, only completed prior observations are eligible. A 95% confidence set retains candidates statistically indistinguishable from the best historical Sharpe, after which the pre-declared low-turnover order is used. A challenger replaces the incumbent only when the past-only evidence is statistically decisive.

The public candidate family preserves the original low-turnover design, uses portfolio-volatility caps of 2.5%, 3.0%, and 3.5%, and imposes a structural 30% cash-group ceiling. The realized public release gate requires average monthly turnover no greater than 2%. Transaction costs remain 3 bps one way.

Common candidate fields are `lookback_days=252`, `covariance_method=ewma`, `max_weight=0.40`, `turnover_cap=0.60`, `turnover_penalty=0.02`, `cvar_penalty=0.15`, `budget_penalty=0.25`, `cvar_beta=0.95`, and `return_reward=0.06`. The three public candidates differ only in their predeclared portfolio-volatility caps; changing these definitions invalidates cached selection scores.

## Research grid

The 36-configuration grid is exploratory. It supports sensitivity, CSCV/PBO, and robustness analysis but cannot overwrite the public OOS path. Cached scores are reusable only when their serialized parameter signatures match the current candidate definitions.

## Data and timing

- Evaluation window: 2018-01-02 to 2026-08-28.
- ETF request window: 2000-01-01 to 2026-08-28; each ETF keeps its longest available history.
- Active universe: 30 ETFs; candidate universe: 6 ETFs; no overlap.
- Point-in-time entry: at least 60 valid observations.
- Risk-free rate: monthly one-year ChinaBond government yield, lagged one month and converted with 243 trading days.

## Release checks

Publication fails if the universe overlaps, a required risk-free month is missing, future data enters a decision, the candidate cache signature is stale, realized turnover exceeds the release gate, or generated CSV, README, thesis, and presentation numbers disagree.

## Change-Log

The authoritative selection history is `results/tables/afml_oos_selection.csv`. Governance changes must update the implementation, tests, generated outputs, and this document in the same release; narrative-only edits do not alter historical selections.
