# Reference Mapping For Thesis Reinforcement

This file is an internal implementation aid for `report/thesis_latex/main.tex` and `references.bib`.
Only references whose title, date, and author or institution can be verified from the PDF front matter should be promoted into the formal bibliography.

| File | Verified title / front-matter signal | Main topic | Planned thesis use | Bib status |
|---|---|---|---|---|
| `Risk Return Trade-Off in Relaxed Risk Parity.pdf` | Vaughn Gambeta, Roy Kwon, 2020, *Risk Return Trade-Off in Relaxed Risk Parity Portfolio Optimization* | relaxed risk parity with explicit return trade-off | Ch.2 relaxed risk parity; Ch.3 model motivation | formal |
| `Building Diversified Portfolios that Outperform Out-of-Sample.pdf` | Marcos López de Prado, 2016, *Building Diversified Portfolios that Outperform Out-of-Sample* | HRP origin and out-of-sample diversification | Ch.2 HRP/HERC benchmark discussion | already formal |
| `PanAgora-Risk-Parity-Portfolios-Efficient-Portfolios-Through-True-Diversification.pdf` | Edward Qian, 2005, *Risk Parity Portfolios: Efficient Portfolios Through True Diversification* | risk parity intuition and risk contribution | Ch.2 risk parity background | already formal |
| `Asset and Factor Risk Budgeting_ A Balanced Approach.pdf` | Adil Rengim Cetingoz, Olivier Guéant, 2024, *Asset and Factor Risk Budgeting: A Balanced Approach* | asset-level and factor-level risk budgeting | Ch.2 risk budgeting extension; domestic practice bridge | formal |
| `Multi-Asset Portfolios with Active and Passive Funds_A Robust Optimization Framework.pdf` | Mohamed Alaa Mallouli, Romain Perchet, Francois Soupe, Raul Leote de Carvalho, 2025, *Multi-Asset Portfolios with Active and Passive Funds: A Robust Optimization Framework* | multi-asset robust optimization with implementability constraints | optional wording support for robust multi-asset implementation | note only |
| `Hierarchical risk parity using security selection based on peripheral assets of correlation-based minimum spanning.pdf` | title visible but front-matter extraction is incomplete in current pass | HRP variant / security selection | reading note only unless full metadata is re-verified | note only |
| `Deep reinforcement learning for portfolio management.pdf` | front-matter extraction noisy in current pass; topic confirmed | DRL for portfolio management | background only; not central to thesis line | note only |
| `Using Deep Reinforcement Learning with Hierarchical Risk Parity for Portfolio Optimization.pdf` | Adrian Millea, Abbas Edalat, 2023, *Using Deep Reinforcement Learning with Hierarchical Risk Parity for Portfolio Optimization* | DRL + HRP/HERC hybrid | Ch.2 benchmark-related adjacent literature | note only |
| `A machine learning approach to risk based asset allocation in portfolio optimization.pdf` | title extractable but authenticity and publication context should be treated cautiously | ML-based adaptive risk allocation | reading note only; do not rely on it for central claims | note only |
| `An Online and Adaptive Factor Model Based on Hierarchical and.pdf` | Zikai Wei et al., 2023, *HireVAE: An Online and Adaptive Factor Model Based on Hierarchical and Regime-Switch VAE* | online factor model / regime switching | background only; outside main thesis line | note only |
| `20201116-华泰证券-金工研究： 风险平价模型的常见理解误区剖析，“风险”的界定、度量与“平价”、杠杆的实现.pdf` | 华泰研究, 林晓明/黄晓彬/源洁莹, 2020-11-16 | risk parity interpretation, leverage, covariance-aware parity | Ch.2 domestic practice and misunderstandings | formal |
| `20211206-华泰证券-深度研究：风险平价之标的优选与层次化风险估计.pdf` | 华泰研究, 林晓明/黄晓彬/张泽, 2021-12-06 | asset selection and hierarchical risk estimation | Ch.2 domestic HRP discussion | formal |
| `20241120-华泰证券-资产配置方法论系列：风险平价的理念与国内实践.pdf` | 华泰研究, 张继强/陶冶/何颖雯, 2024-11-20 | domestic risk parity practice with ETFs | Ch.2 domestic practice; Ch.7 institutional interpretation | formal |
| `20250103-中信建投-大类资产配置策略系列：大类资产配置方法在中国市场实践.pdf` | 中信建投证券, 陈果/王程畅, 2025-01-03 | China-market asset allocation practice | Ch.2 domestic practice bridge | formal |
| `20250305-华泰证券-固收深度研究：资产配置方法论系列，低利率环境下的绝对收益路径.pdf` | 华泰研究, 张继强/陶冶/何颖雯, 2025-03-05 | low-rate absolute return paths; TIPP + risk parity | Ch.2 domestic practice; Ch.7 institutional implications | formal |
| `20250603-华泰证券-从资产配置走向因子配置：中国版全天候增强策略.pdf` | 华泰研究, 林晓明/徐特, 2025-06-03 | factor risk parity evolution in China | Ch.2 domestic method evolution | note only unless needed |
