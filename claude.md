# Agent Documentation Policy

## Core Principle: Write What Is, Not What Changed

Every time any agent (human or AI) updates documentation in this repository — README, thesis text, inline comments, or any other narrative section — the update **must describe the current state of the project factually and in full detail**, as if the reader has never seen a previous version.

### What This Means in Practice

- **No revision history in prose.** Do not write "this version now adds X", "the second-round rewrite includes Y", "previously we had Z, now we have W". That language belongs in a git commit message, not in the document itself.
- **No meta-commentary about the update process.** Phrases like "补强", "返工", "rewrite", "polish", "second-round" describe the editing process, not the project. Remove them.
- **State the current numbers, not the delta.** Instead of "performance improved from 5.10% to 5.62%", write "net annualized return is 5.62%".
- **Describe what exists now.** Every section should read as a complete, accurate description of the current state: what models are included, what results they produce, what validation was run.

### Thesis Title

The official thesis title is: **宽松风险平价在全球 ETF 资产配置中的改进与实证研究**
English: *Improvements and Empirical Study of Relaxed Risk Parity in Global ETF Asset Allocation*

This title is set in `report/thesis_latex/main.tex` via `\covertitle{}` and `pdftitle`. Any documentation referencing the thesis must use this exact title.

### Documentation Sections That Need This Treatment

| Section | What to Include |
|---|---|
| README 本科论文初稿 / Thesis Draft | Thesis title, chapter structure, asset universe, current performance table, robustness coverage |
| README 绩效看板 / Performance Dashboard | Latest numbers from `results/tables/convex_adaptive_performance_summary.csv` |
| README ETF 资产池 / ETF Pool | Current 30-ETF list with tickers, categories, full names |
| Thesis abstract (Chinese & English) | Current model results, current ETF count, current evaluation window |
| Thesis Chapter 4 tab:etf_pool | Current 30 rows, 8 categories |
| Thesis Chapter 5 performance tables | Numbers from the latest run |

### Authoritative Result Files

Always read these files before writing any performance numbers — never copy from memory or a previous document version:

- `results/tables/convex_adaptive_performance_summary.csv` — primary model metrics (net_annual_return, annualized_volatility, sharpe_ratio, sortino_ratio, max_drawdown, calmar_ratio, avg_monthly_turnover)
- `results/tables/hrp_comparison.csv` — full model comparison including Equal Weight
- `results/tables/asset_descriptive_statistics.csv` — per-ETF statistics for the thesis data chapter

### Checklist Before Committing Documentation Changes

- [ ] All performance numbers match the latest CSV files exactly
- [ ] No sentences describe the update process ("这次修改了…", "this version adds…")
- [ ] The ETF pool description matches the current `src/asset_universe.py`
- [ ] Data range matches `data/processed/etf_prices_updated.csv` (first and last valid dates)
- [ ] Evaluation window matches the pipeline start date (currently `2021-01-01`)

---

## If the Updating Agent Is Claude

When Claude (claude.ai/code or any Claude API) is making documentation updates, it must:

1. Follow all rules above.
2. Copy this file (`agent.md`) to `claude.md` in the same directory, overwriting any previous version — so `claude.md` always reflects the current policy as Claude understands it.
3. Do not add commentary to `claude.md`; it should be an exact copy of `agent.md`.

This ensures the project always has a record of the policy as understood by the AI agent that last touched the documentation.
