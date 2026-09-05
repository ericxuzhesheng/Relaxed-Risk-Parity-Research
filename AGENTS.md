# AGENTS.md

## Repository Purpose

This repository is a thesis-oriented quantitative asset allocation research project.

Main research line:

```
Relaxed Risk Parity
-> Global Multi-Asset Extension (30-ETF universe, 8 asset categories)
-> Convex Adaptive Global RRP
-> CVaR / Turnover / Group Constraints
-> Robustness Validation
-> Long-Term Institutional / Insurance Allocation Interpretation
```

This is a portfolio optimization and risk-budgeting research project, not a short-term trading strategy repository.

---

## Core Models and Public Labels

Use exactly these seven model names in publication prose, tables and figures. Parameter and frequency variants are experiments, not additional models.

| Public label | Role |
|---|---|
| Improved Convex Adaptive Global RRP | Primary weekly model |
| Global RRP | Comparison |
| Convex Adaptive Global RRP | Comparison |
| HRP Benchmark | Comparison |
| HERC Benchmark | Comparison |
| Equal Weight | Comparison |
| 60/40 Benchmark | Comparison |

---

## Main Positioning

Current model positioning:

- **Improved Convex Adaptive Global RRP** is the primary model: weekly, no cash-group or individual-asset concentration caps, long-only and unlevered. Non-cash group bounds and turnover controls remain.
- **Global RRP**, Convex Adaptive Global RRP, HRP Benchmark, HERC Benchmark, Equal Weight and 60/40 Benchmark are comparisons.
- Headline Sharpe and Sortino use rf=0. Report the lagged ChinaBond opportunity-cost Sharpe separately.
- Selection of the weekly unconcentrated specification followed historical research. Do not claim untouched OOS model-selection evidence or future guarantees.
- The frozen schedule uses candidate_03, whose CVaR penalty is zero. Do not attribute performance to an active CVaR constraint.
- Low volatility must be interpreted with actual money-market ETF concentration. Primary status does not imply the highest Sharpe among comparisons.

---

## Latest Core Results

**Always read from CSV before writing any numbers.** Authoritative source files:

| Purpose | File |
|---|---|
| Primary model metrics | `results/tables/convex_adaptive_performance_summary.csv` |
| Full model comparison | `results/tables/hrp_comparison.csv` |
| Per-ETF statistics | `results/tables/asset_descriptive_statistics.csv` |
| Overfitting diagnostic | `results/tables/cscv_pbo_summary.csv` |
| Rebalance-frequency sensitivity | `results/tables/rebalance_frequency_sensitivity.csv` |

Current results: 2018-01-02 to 2026-08-31, unfiltered realized returns, rf=0, 243-day annualization, 3-bp one-way cost. Primary model weekly; core comparisons monthly. Cache 2007-01-18 to 2026-08-31; 60-observation point-in-time filter.

| Model | Net annual return | Annual vol | Sharpe | Sortino | Max drawdown | Calmar | Avg monthly turnover |
|---|---:|---:|---:|---:|---:|---:|---:|
| Improved Convex Adaptive Global RRP | 2.92% | 1.56% | 1.859 | 2.648 | -2.63% | 1.110 | 4.36% |
| Global RRP | 2.40% | 0.58% | 4.103 | 6.496 | -1.01% | 2.384 | 12.89% |
| Convex Adaptive Global RRP | 5.87% | 6.02% | 0.979 | 1.382 | -8.18% | 0.718 | 2.59% |
| HRP Benchmark | 2.03% | 0.26% | 7.674 | 17.069 | -0.19% | 10.758 | 1.95% |
| HERC Benchmark | 2.44% | 0.82% | 2.958 | 4.432 | -1.53% | 1.597 | 7.17% |
| Equal Weight | 9.21% | 12.92% | 0.747 | 1.057 | -18.25% | 0.505 | 4.73% |
| 60/40 Benchmark | 6.98% | 11.84% | 0.629 | 0.905 | -20.04% | 0.348 | 4.21% |

Primary average money-market ETF weight is 70.23%, maximum 86.61%. The same primary path has ChinaBond opportunity-cost Sharpe 0.529. Configuration and validation: `primary_model_configuration.json` and `primary_publication_audit.json` under `results/tables/`. Historical tables outside the primary publication pipeline are archival, not current-model validation.

---

## ETF Asset Pool

Current universe: **30 ETFs** across **8 categories**. Longest valid data range: `2007-01-18` to `2026-08-31`. Source: `src/asset_universe.py` (single source of truth).

| ETF | Ticker | Category |
|---|---|---|
| 可转债ETF | 511380.SH | convertible bond |
| 5年国债ETF | 511010.SH | government bond |
| 10年国债ETF | 511260.SH | government bond |
| 信用债ETF | 511030.SH | credit bond |
| 日利ETF | 511880.SH | money market |
| 沪深300ETF | 510300.SH | china equity |
| 中证500ETF | 510500.SH | china equity |
| 中证1000ETF | 512100.SH | china equity |
| 中证2000ETF | 563300.SH | china equity |
| 创业板ETF | 159915.SZ | china equity |
| 红利ETF | 510880.SH | china equity dividend |
| 半导体ETF | 512480.SH | china tech equity |
| 人工智能ETF | 159819.SZ | china tech equity |
| 新能源ETF | 516160.SH | china new energy |
| 科创50ETF | 588000.SH | china tech equity |
| 证券ETF | 512880.SH | china finance |
| 军工ETF | 512660.SH | china defense |
| 消费ETF | 159928.SZ | china consumer |
| 恒生ETF | 159920.SZ | hong kong equity |
| 白银LOF | 161226.SZ | commodity |
| 纳指ETF | 159941.SZ | global equity |
| 标普500ETF | 513500.SH | global equity |
| 日经225ETF | 513880.SH | global equity |
| 欧洲ETF | 513030.SH | global equity |
| 黄金ETF | 518880.SH | commodity |
| 有色金属期货ETF | 159980.SZ | commodity |
| 能源化工期货ETF | 159981.SZ | commodity |
| 豆粕ETF | 159985.SZ | commodity |
| 煤炭ETF | 515220.SH | commodity |
| 原油ETF | 162411.SZ | commodity |

Candidate universe: **6 ETFs**, excluded from the active 30 and from backtests until the next scheduled universe review.

| ETF | Ticker | Category |
|---|---|---|
| 30年国债ETF | 511090.SH | government bond |
| 中韩半导体ETF | 513310.SH | china tech equity |
| 证券公司先锋策略ETF | 516980.SH | china finance |
| 沙特ETF | 520830.SH | global equity |
| 巴西ETF | 520870.SH | global equity |
| 机器人ETF | 562500.SH | china advanced manufacturing |

`516980.SH` was previously mislabeled as 云计算ETF in the project. Tushare `fund_basic` identifies it as 华富中证证券公司先锋策略ETF, so the candidate label and category use the official identity.

---

## Pipeline Run Protocol (mandatory)

The publication pipeline stores complete weekly holdings in repository CSV files. Do not embed detailed weekly holdings tables in thesis or presentation appendices. Keep all 30 ETFs at each decision and sample-boundary flags. Do not generate a standalone weekly workbook or annual holdings PDF. Publication charts use a red–blue palette with matching vector PDF and 300-dpi PNG output.

**Every pipeline run must follow this sequence:**

### Before running:
```powershell
if (-not $env:TUSHARE_TOKEN) { throw "Set TUSHARE_TOKEN in the local environment before refreshing Tushare data." }
python scripts/update_etf_data.py --provider tushare --start-date 20000101 --end-date 20260831
python scripts/update_risk_free_rate.py --start-date 20000101 --end-date 20260831
```

### After running — refresh artifacts in this order before any commit:
1. **Regenerate thesis numbers and figure assets** — rerun the scripts that create `report/thesis_latex/generated_numbers.tex`, generated thesis tables, and all result figures used by README, thesis, and PPT. Treat generated files as the source for presentation/report numbers rather than manually copying stale values.
2. **`AGENTS.md`** — update performance table, ETF universe, data window, and key interpretation (read CSV first).
3. **`README.md`** — update both Chinese and English performance dashboards and figure explanations (read CSV first).
4. **`report/thesis_latex/main.tex`** — update all tables and narrative numbers in abstracts, Chapter 5, robustness summary table, and appendices (read CSV/generated files first), then recompile PDF with xelatex × 3 passes.
5. **`report/ppt/rrp_defense.tex`** — sync presentation numbers, figures, ETF universe, candidate ID, and explanatory text with the regenerated thesis numbers/figures and current CSV outputs, then recompile the PPT PDF.

Do not commit until AGENTS.md + README.md + main.tex + main.pdf + rrp_defense.tex + rrp_defense.pdf are all updated and mutually consistent.

---

## Documentation Update Policy

Every documentation update must describe the **current state** of the project — not what changed, not what was added in this round.

- No phrases like "补强", "返工", "this version adds", "second-round rewrite".
- All performance numbers must be read from the authoritative CSV files above before writing.
- ETF pool must match `src/asset_universe.py`.
- Data range and evaluation window must match the actual pipeline config.
- Thesis writing must use rigorous formal academic Chinese — no casual expressions.

See `agent.md` and `claude.md` for the full policy.

---

## Automatic Cleanup After Runs

After any pipeline run, execute `scripts/cleanup_temp.py` to remove temporary files:

```powershell
python scripts/cleanup_temp.py
```

This removes: `__pycache__` directories, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, LaTeX build artifacts (`.aux .bbl .blg .fls .fdb_latexmk .log .out .xdv`), `tmp_pytest*/`, `tmp_pytest_run*/`, `results/quick/`, `notebooks/`.

`run_full_research_pipeline.py` calls cleanup automatically at exit (both success and failure).

---

## README Figure Section

Use these figure embeds when files exist:

- `results/figures/convex_adaptive_nav_comparison.png`
- `results/figures/convex_adaptive_drawdown_comparison.png`
- `results/figures/convex_adaptive_turnover_comparison.png`
- `results/figures/convex_adaptive_cvar_comparison.png`
- `results/figures/rebalance_frequency_sensitivity.png`

Figures must use the current primary publication outputs. Explain NAV, drawdown, turnover and CVaR together with the money-market weight. Weekly is the designated main frequency; frequency rankings are descriptive, not proof of optimality. Use `scripts/run_primary_publication_pipeline.py` to reproduce the current publication.

---

## README Style Requirements

README.md is the public-facing GitHub landing page. It must be:

- bilingual (Chinese first, then English);
- polished and concise;
- easy to scan with clear Markdown structure;
- not a raw result dump or implementation log.

README title must be:

```markdown
# 宽松风险平价全球资产配置框架 | Relaxed Risk Parity Framework for Global Asset Allocation
```

---

## README Math Rendering

- Use `$$ ... $$` for display equations.
- Avoid restricted LaTeX macros: `\operatorname`, `\text`, `\begin`, `\end`, `\lVert`, `\rVert`.
- Prefer macro-free math: `Σ_t`, `λ_var`, `CVaR_α`, `wᵀΣ_t w`, `||w-b_t||₂²`.
- Split long optimization problems into multiple display equations rather than using alignment macros.
