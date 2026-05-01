# Relaxed Risk Parity Research

This repository studies Relaxed Risk Parity (RRP) with a static global showcase and a walk-forward Dynamic RRP overlay. Generated showcase artifacts are produced by:

```bash
python scripts/optimize_showcase_rrp.py
python scripts/run_rrp_pipeline.py --mode full
```

## Showcase Results

Evaluation starts on 2021-01-01. V3 Global RRP is preserved as the main benchmark unless conservative validation finds a stable improvement. Dynamic RRP is re-optimized because the previous overlay was materially over-defensive.

| Model | Ann. Return | Volatility | Sharpe | Calmar | Max DD | Ann. Turnover |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| V3_Global_RRP | 6.30% | 3.65% | 1.23 | 1.55 | -4.07% | 2.86 |
| Dynamic_RRP | 4.25% | 4.17% | 0.58 | 0.81 | -5.23% | 4.45 |

HRP and HERC remain secondary diversification benchmarks rather than the main narrative models.

## Validation Design

The showcase optimizer uses monthly walk-forward selection. Each rebalance uses only data strictly before the test period. The objective rewards Sharpe and Calmar while penalizing drawdown, turnover, and unstable parameter selections. PBO and adjusted-Sharpe outputs are simplified AFML-inspired diagnostics, not full CSCV or full Deflated Sharpe Ratio implementations.

## Generated Outputs

- `results/tables/showcase_performance_summary.csv`
- `results/tables/dynamic_overlay_diagnostics.csv`
- `results/tables/showcase_improvement_attribution.csv`
- `results/tables/showcase_risk_overlay_ablation.csv`
- `results/tables/showcase_walkforward_validation.csv`
- `results/tables/showcase_parameter_stability.csv`
- `results/tables/showcase_afml_diagnostics.csv`
- `results/tables/showcase_pbo_diagnostic.csv`
- `results/figures/showcase_nav_comparison.png`
- `results/figures/showcase_drawdown_comparison.png`
- `results/figures/showcase_risk_overlay_ablation.png`
- `results/figures/showcase_parameter_timeline.png`
- `results/figures/showcase_pbo_heatmap.png`

## Limitations

This is backtest research, not investment advice. The data source, asset mappings, transaction cost assumptions, leverage financing costs, and simplified validation diagnostics must be independently reviewed before any live use.

## References

1. Gambeta, V., & Kwon, R. (2020). Risk return trade-off in relaxed risk parity portfolio optimization.
2. Lopez de Prado, M. (2018). Advances in Financial Machine Learning.
3. Bailey, D. H., Borwein, J. M., Lopez de Prado, M., & Zhu, Q. J. (2015). The Probability of Backtest Overfitting.
4. Bailey, D. H., & Lopez de Prado, M. (2014). The Deflated Sharpe Ratio.
5. Lopez de Prado, M. (2016). Building Diversified Portfolios that Outperform Out-of-Sample.

## License

MIT License.
