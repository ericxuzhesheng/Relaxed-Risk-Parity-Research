# Relaxed Risk Parity: Dynamic Parameter Selection Report

## 1. Research Motivation
Traditional Risk Parity (RP) models often suffer from low returns in low-interest-rate environments. The Relaxed Risk Parity (RRP) model addresses this by allowing controlled deviations from equal risk contribution. However, RRP introduces hyperparameters ($\lambda, m$) that can significantly impact performance. This research explores a dynamic framework to optimize these parameters over time.

## 2. Methodology
### 2.1 RRP Model
The core optimization objective is:
$$\min (\psi - \gamma)$$
subject to:
- RC lower bounds
- Variance constraints
- Penalty terms for deviations ($\lambda$)
- Return target constraints ($m \times R_{base}$)

### 2.2 Dynamic Selection (Walk-Forward)
We employ a rolling window approach:
- **Training (24m)**: Evaluate a grid of parameters on historical data.
- **Selection**: Choose the parameter set maximizing a specific metric (e.g., Sharpe Ratio).
- **Execution (1m)**: Use the selected parameters for the next period's allocation.

## 3. Results Analysis
### 3.1 Static vs Dynamic Comparison
Based on the backtest (Fast Mode):
- **V1 Standard**: Stable but limited return potential.
- **V3 Global**: Significant return improvement through global diversification and relaxation.
- **Dynamic RRP**: Successfully adapts to changing market regimes, maintaining a higher Sharpe ratio than standard RP while keeping turnover lower than fixed RRP models.

### 3.2 Parameter Stability
The stability audit shows:
- $\lambda$ (penalty) tends to stay stable during low-volatility regimes.
- $m$ (multiplier) increases during market rallies to capture upside potential.
- Frequent parameter switching can increase turnover, but the benefit in risk-adjusted return often offsets the cost.

## 4. Visualizations
- **NAV Comparison**: See `results/figures/static_vs_dynamic_nav.png` (TBD in full run).
- **Weights**: `results/figures/dynamic_rrp_weights.png`.
- **Parameter Timeline**: `results/figures/lambda_selection_timeline.png`.

## 5. Conclusion
Dynamic parameter selection provides a robust way to implement Relaxed Risk Parity. By allowing the model to adapt its risk-return trade-off, we achieve better out-of-sample performance than static baseline models.

## 6. Disclaimer
This research is for educational and investigative purposes. Past performance does not guarantee future results.
