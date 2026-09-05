# AGENTS.md

## Repository Purpose

This repository is a thesis-oriented quantitative asset allocation research project.

Main research line follows convex risk-budget references, a feasible expected-return target and annual prior-only penalty calibration for a 30-ETF universe.

## Core Models and Public Labels

Use exactly these five model names in current publication prose, tables and figures. Parameter and frequency variants are experiments.

| Public label | Role |
|---|---|
| Global RRP | Primary weekly model |
| HRP Benchmark | Monthly comparison |
| HERC Benchmark | Monthly comparison |
| Equal Weight | Monthly comparison |
| 60/40 Benchmark | Monthly comparison |

## Main Positioning

- Global RRP is the weekly primary model. It is long-only, fully invested and unlevered.
- The lookback and annualization conventions both use 252 trading days. Inputs use Ledoit-Wolf covariance shrinkage and 20-day half-life EWMA means.
- The return target equals the predicted return of the contemporaneous feasible risk-budget reference. There is no fixed target multiplier.
- Variance and shortfall penalties update annually from two strictly earlier 252-day blocks. The first block determines candidate scales and the second evaluates candidates after costs. Selected values remain fixed for the following year.
- Every annual validation admits all nine candidates to the one-standard-error set. Report this weak identification and do not describe the selected coefficients as unique estimates.
- All eligible ETFs may participate, including zero weights on a date. There is no artificial minimum allocation.
- rf=0 is the current rate convention. ChinaBond refresh is not required.
- Primary status records the designated research specification. Historical results do not imply performance dominance or future guarantees.

## Latest Core Results

Always read CSV before writing numbers. Authoritative metrics are `results/tables/model_performance_summary.csv` and `hrp_comparison.csv`. The annual parameter path is `primary_parameter_schedule.csv`, and asset statistics are in `asset_descriptive_statistics.csv` under the same directory.

Current results use 2018-01-02 to 2026-08-31, unfiltered realized returns, rf=0, 252-day annualization and 3-bp one-way cost. Global RRP is weekly; comparisons are monthly. Cache starts 2007-01-18. Eligibility requires 60 prior valid observations and positive variance.

| Model | Net annual return | Volatility | Sharpe | Sortino | Max drawdown | Monthly turnover |
|---|---:|---:|---:|---:|---:|---:|
| Global RRP | 6.13% | 3.59% | 1.674 | 2.392 | -6.80% | 17.53% |
| HRP Benchmark | 2.11% | 0.27% | 7.815 | 17.382 | -0.19% | 1.95% |
| HERC Benchmark | 2.53% | 0.83% | 3.013 | 4.514 | -1.53% | 7.17% |
| Equal Weight | 9.56% | 13.16% | 0.761 | 1.076 | -18.25% | 4.73% |
| 60/40 Benchmark | 7.25% | 12.06% | 0.641 | 0.921 | -20.04% | 4.21% |

Primary average money-market weight is 18.02%, with a maximum of 26.43%. The average combined money-market and three-bond weight is 66.27%. All 30 ETFs receive material allocations during eligible periods. The annual calibration has 0 informative years out of 10 under the one-standard-error rule.

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

- `results/figures/global_rrp_nav_comparison.png`
- `results/figures/global_rrp_drawdown_comparison.png`
- `results/figures/global_rrp_turnover_comparison.png`
- `results/figures/global_rrp_cvar_comparison.png`

Figures must use the current primary publication outputs. Explain NAV, drawdown, turnover and CVaR together with the money-market weight. Only the designated weekly specification is published; other experiment results remain archival. Use `scripts/run_primary_publication_pipeline.py` to reproduce the current publication.

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
