# Model Governance

## Purpose

This document records the parameter groups, allowed ranges, selection rules, and validation evidence for the convex adaptive relaxed risk parity models. It is a governance reference, not a replacement for preregistration or formal frozen OOS validation.

## Models

| Model | Public Label | Role |
|---|---|---|
| `BASE_CONVEX_MODEL_NAME` | Convex Adaptive Global RRP | Baseline convex adaptive relaxed risk-budgeting approximation |
| `IMPROVED_MODEL_NAME` | Improved Convex Adaptive Global RRP | Constrained parameter refinement — low turnover, CVaR-aware, implementable |

The base model uses a single configuration (`budget_penalty=0.55`). The improved model is the highest-scoring candidate selected from a grid search using historical evaluation metrics.

## Parameter Groups

### Covariance and Lookback

| Parameter | Allowed Range (Search) | Selected Value |
|---|---|---|
| `lookback_days` | 120, 180, 252 | 252 |
| `covariance_method` | ewma, sample | ewma |

### Weight and Turnover Constraints

| Parameter | Allowed Range (Search) | Selected Value |
|---|---|---|
| `max_weight` | 0.40, 0.45 | 0.45 |
| `turnover_cap` | 0.35, 0.80, 1.00, unbounded | 0.80 |
| `turnover_penalty` | 0.00, 0.01, 0.02, 0.03 | 0.02 |

### Risk Budget and Tail Risk

| Parameter | Allowed Range (Search) | Selected Value |
|---|---|---|
| `budget_penalty` | 0.05, 0.10, 0.35 | 0.10 |
| `cvar_penalty` | 0.05, 0.08, 0.10, 0.20 | 0.08 |
| `cvar_beta` | 0.90, 0.95 | 0.95 |

### Return Input

| Parameter | Allowed Range (Search) | Selected Value |
|---|---|---|
| `return_reward` | 0.05, 0.06 | 0.05 |

### Fixed / Operational

| Parameter | Value |
|---|---|
| `transaction_cost_bps` | 3.0 |
| Rebalance frequency | Monthly |
| Evaluation start | 2021-01-01 |
| Extended sample start | 2018-01-02 |

## Selection Rule

The improved model is selected by ranking all candidates on a composite score:

```
score = sharpe + 0.35 × calmar − 2.0 × |max_drawdown| − 0.25 × avg_monthly_turnover − 10.0 × cvar − 0.5 × fallback_rate
```

Candidates are rejected when:
- `avg_monthly_turnover` exceeds a gate threshold relative to the incumbent,
- or `net_annual_return` falls below the incumbent by more than a threshold.

The selected candidate (`candidate_09`) passed all gates and had the highest selection score among the full candidate set.

## Validation Evidence

| Layer | Status | Interpretation |
|---|---|---|
| Walk-Forward | Implemented | 23 test slices; selection restricted to validation window |
| Nested Validation | Implemented | train/validation/test decay reported per split |
| CSCV/PBO (baseline) | Intermediate | 4 candidates, 6 blocks, 6 combos; PBO ≈ 0.33 |
| CSCV/PBO (enhanced) | Added | 10 blocks, 12 combos; larger but still bounded |
| Frozen OOS | Pseudo-frozen | 2025-01-01 frozen start; may have been observed during development |
| Retrospective holdout | Added | Two slices (2024-01-01, 2025-01-01); retrospective evidence |
| CVaR sensitivity | Added | β ∈ {0.90, 0.95, 0.975, 0.99}, lookback ∈ {126, 252, 504} |
| Extended sample | Added | Point-in-time filtering from 2018-01-02 |
| Parameter sensitivity | Implemented | One-at-a-time perturbation diagnostics |
| Covariance robustness | Implemented | Sample, Ledoit-Wolf, EWMA (h=20,60,120) |
| Block Bootstrap | Implemented | Time-block resampling for distribution uncertainty |
| No-lookahead audit | Implemented | All backtest paths verified for temporal integrity |

None of these layers constitute proof of future out-of-sample performance.

## Change-Log Template

When parameters, selection rules, or data sources change, record:

```
[YYYY-MM-DD] <description>
  - What changed:
  - Why:
  - Affected outputs:
  - Validation re-run: yes / no
  - Reviewer:
```

## Limitations

- Pre-registration has not been performed; the candidate was selected with knowledge of the full sample before 2025.
- The grid search is bounded and does not cover all plausible parameter combinations.
- No ALM, capacity, or full liquidity modeling is included.
- All validation diagnostics are conditional on the current sample, cost assumptions, and ETF universe.
