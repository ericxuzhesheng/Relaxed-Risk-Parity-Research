# Overfitting and OOS Audit

The public Improved Convex Adaptive Global RRP is one continuous rolling out-of-sample path from 2018-01-02 through 2026-08-31. Every quarterly decision uses only completed prior windows. The selector forms a 95% confidence set around the best past Sharpe and resolves statistically tied candidates using the pre-declared low-turnover order. It does not use the current or future OOS window.

The full 36-configuration grid remains exploratory. It is reported for robustness and CSCV/PBO diagnostics and cannot directly overwrite the public path. Candidate-score caches include parameter signatures and fail closed when definitions change.

The authoritative audit files are

- `results/tables/afml_oos_selection.csv`
- `results/tables/afml_oos_candidate_scores.csv`
- `results/tables/cscv_pbo_summary.csv`
- `results/tables/convex_adaptive_solver_diagnostics.csv`

The active universe contains 30 ETFs. The six-candidate universe is excluded from portfolio construction. ETF eligibility is point-in-time and requires 60 valid observations. Sharpe and Sortino use the date-aligned one-year ChinaBond government yield, observed at month-end and applied with a one-month lag.

This remains retrospective historical evidence rather than preregistered live validation. Statistical indistinguishability does not prove economic equivalence, and repeated research decisions before publication can still create researcher degrees of freedom.
