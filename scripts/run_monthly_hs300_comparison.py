from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.data_loader import load_data


STRATEGY_RETURNS = ROOT_DIR / "results/tables/improved_convex_adaptive_global_relaxed_risk_parity_returns.csv"
MONTHLY_OUTPUT = ROOT_DIR / "results/tables/improved_rrp_vs_hs300_monthly_returns.csv"
SUMMARY_OUTPUT = ROOT_DIR / "results/tables/improved_rrp_vs_hs300_monthly_summary.csv"
FIGURE_OUTPUT = ROOT_DIR / "results/figures/improved_rrp_vs_hs300_monthly_comparison.png"
THESIS_OUTPUT = ROOT_DIR / "report/thesis_latex/generated_hs300_monthly_comparison.tex"
README_PATH = ROOT_DIR / "README.md"

README_CN_BEGIN = "<!-- BEGIN MONTHLY_HS300_COMPARISON_CN -->"
README_CN_END = "<!-- END MONTHLY_HS300_COMPARISON_CN -->"
README_EN_BEGIN = "<!-- BEGIN MONTHLY_HS300_COMPARISON_EN -->"
README_EN_END = "<!-- END MONTHLY_HS300_COMPARISON_EN -->"
THESIS_BEGIN = "% BEGIN MONTHLY_HS300_COMPARISON"
THESIS_END = "% END MONTHLY_HS300_COMPARISON"


def _pct(value: float, digits: int = 2) -> str:
    return f"{value * 100:.{digits}f}%"


def _tex_pct(value: float, digits: int = 2) -> str:
    return f"{value * 100:.{digits}f}\\%"


def _annualized(monthly_returns: pd.Series) -> float:
    if monthly_returns.empty:
        return 0.0
    return float((1.0 + monthly_returns).prod() ** (12.0 / len(monthly_returns)) - 1.0)


def _max_drawdown(daily_returns: pd.Series) -> tuple[float, pd.Timestamp]:
    nav = (1.0 + daily_returns.fillna(0.0)).cumprod()
    drawdown = nav / nav.cummax() - 1.0
    idx = drawdown.idxmin()
    return float(drawdown.loc[idx]), pd.Timestamp(idx)


def _load_strategy_returns(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"strategy return file not found: {path}")
    df = pd.read_csv(path, parse_dates=["date"])
    ret_col = "net_return" if "net_return" in df.columns else "portfolio_return"
    if ret_col not in df.columns:
        raise ValueError(f"{path} must contain net_return or portfolio_return")
    return df[["date", ret_col]].rename(columns={ret_col: "strategy_return"})


def _find_hs300_column(returns: pd.DataFrame) -> str:
    exact = [col for col in returns.columns if col == "沪深300ETF"]
    if exact:
        return exact[0]
    matches = [col for col in returns.columns if "300" in str(col)]
    if not matches:
        raise ValueError("could not find HS300 proxy column in return data")
    return matches[0]


def build_monthly_comparison(start_date: str = "2019-01-01") -> tuple[pd.DataFrame, pd.DataFrame]:
    strategy = _load_strategy_returns(STRATEGY_RETURNS)
    strategy = strategy[strategy["date"] >= pd.Timestamp(start_date)].copy()
    strategy["month"] = strategy["date"].dt.to_period("M")
    strategy_monthly = strategy.groupby("month")["strategy_return"].apply(lambda s: (1.0 + s.fillna(0.0)).prod() - 1.0)

    returns = load_data(source="tushare", force_update=False).dropna(how="all")
    hs300_col = _find_hs300_column(returns)
    hs300_daily = returns[returns.index >= pd.Timestamp(start_date)][hs300_col].copy()
    hs300_monthly = hs300_daily.groupby(hs300_daily.index.to_period("M")).apply(
        lambda s: (1.0 + s.fillna(0.0)).prod() - 1.0
    )

    monthly = pd.DataFrame(
        {
            "improved_rrp_monthly_return": strategy_monthly,
            "hs300_etf_monthly_return": hs300_monthly,
        }
    ).dropna()
    monthly["excess_return"] = monthly["improved_rrp_monthly_return"] - monthly["hs300_etf_monthly_return"]
    monthly["strategy_outperformed"] = monthly["excess_return"] > 0
    monthly["strategy_positive_hs300_negative"] = (
        (monthly["improved_rrp_monthly_return"] > 0) & (monthly["hs300_etf_monthly_return"] < 0)
    )
    monthly["strategy_negative_hs300_positive"] = (
        (monthly["improved_rrp_monthly_return"] < 0) & (monthly["hs300_etf_monthly_return"] > 0)
    )

    common_daily = strategy.set_index("date")["strategy_return"].to_frame().join(
        hs300_daily.rename("hs300_etf_return"),
        how="inner",
    )
    strategy_mdd, strategy_mdd_date = _max_drawdown(common_daily["strategy_return"])
    hs300_mdd, hs300_mdd_date = _max_drawdown(common_daily["hs300_etf_return"])

    summary = pd.DataFrame(
        [
            {
                "start_month": str(monthly.index.min()),
                "end_month": str(monthly.index.max()),
                "month_count": int(len(monthly)),
                "strategy_cumulative_return": float((1.0 + monthly["improved_rrp_monthly_return"]).prod() - 1.0),
                "hs300_cumulative_return": float((1.0 + monthly["hs300_etf_monthly_return"]).prod() - 1.0),
                "strategy_annualized_return": _annualized(monthly["improved_rrp_monthly_return"]),
                "hs300_annualized_return": _annualized(monthly["hs300_etf_monthly_return"]),
                "strategy_monthly_volatility": float(monthly["improved_rrp_monthly_return"].std()),
                "hs300_monthly_volatility": float(monthly["hs300_etf_monthly_return"].std()),
                "strategy_max_drawdown": strategy_mdd,
                "strategy_max_drawdown_date": strategy_mdd_date.date().isoformat(),
                "hs300_max_drawdown": hs300_mdd,
                "hs300_max_drawdown_date": hs300_mdd_date.date().isoformat(),
                "outperform_months": int(monthly["strategy_outperformed"].sum()),
                "outperform_rate": float(monthly["strategy_outperformed"].mean()),
                "strategy_positive_months": int((monthly["improved_rrp_monthly_return"] > 0).sum()),
                "strategy_positive_rate": float((monthly["improved_rrp_monthly_return"] > 0).mean()),
                "hs300_positive_months": int((monthly["hs300_etf_monthly_return"] > 0).sum()),
                "hs300_positive_rate": float((monthly["hs300_etf_monthly_return"] > 0).mean()),
                "monthly_correlation": float(monthly[["improved_rrp_monthly_return", "hs300_etf_monthly_return"]].corr().iloc[0, 1]),
                "avg_monthly_excess_return": float(monthly["excess_return"].mean()),
                "median_monthly_excess_return": float(monthly["excess_return"].median()),
                "strategy_negative_hs300_positive_months": int(monthly["strategy_negative_hs300_positive"].sum()),
                "strategy_positive_hs300_negative_months": int(monthly["strategy_positive_hs300_negative"].sum()),
            }
        ]
    )
    return monthly, summary


def write_csv_outputs(monthly: pd.DataFrame, summary: pd.DataFrame) -> None:
    MONTHLY_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    monthly_out = monthly.copy()
    monthly_out.index = monthly_out.index.astype(str)
    monthly_out.to_csv(MONTHLY_OUTPUT, index_label="month")
    summary.to_csv(SUMMARY_OUTPUT, index=False)


def write_figure(monthly: pd.DataFrame, summary: pd.DataFrame) -> None:
    """Write a compact monthly visual for README and thesis."""
    FIGURE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    plot_df = monthly.copy()
    x = plot_df.index.astype(str)
    strategy_nav = (1.0 + plot_df["improved_rrp_monthly_return"]).cumprod()
    hs300_nav = (1.0 + plot_df["hs300_etf_monthly_return"]).cumprod()
    excess = plot_df["excess_return"] * 100.0

    fig, (ax_nav, ax_excess) = plt.subplots(
        2,
        1,
        figsize=(12, 7),
        sharex=True,
        gridspec_kw={"height_ratios": [2.2, 1.0]},
    )

    ax_nav.plot(x, strategy_nav, label="Improved Convex Adaptive Global RRP")
    ax_nav.plot(x, hs300_nav, label="CSI 300 ETF")
    ax_nav.set_title("Monthly Performance vs CSI 300 ETF")
    ax_nav.set_ylabel("Cumulative NAV")
    ax_nav.grid(True)
    ax_nav.legend()

    colors = ["C2" if value >= 0 else "C3" for value in excess]
    ax_excess.bar(x, excess, color=colors, width=0.82)
    ax_excess.axhline(0, color="black", linewidth=0.8)
    ax_excess.set_ylabel("Monthly Excess Return (pp)")
    ax_excess.grid(True)

    tick_step = max(1, len(x) // 12)
    ax_excess.set_xticks(range(0, len(x), tick_step))
    ax_excess.set_xticklabels([x[i] for i in range(0, len(x), tick_step)], rotation=35, ha="right")

    plt.tight_layout()
    fig.savefig(FIGURE_OUTPUT, bbox_inches="tight")
    plt.close(fig)


def _format_recent_month_table(monthly: pd.DataFrame, n: int = 12) -> str:
    rows = monthly.tail(n)
    lines = [
        "| Month | Improved RRP | CSI 300 ETF | Excess |",
        "|---|---:|---:|---:|",
    ]
    for month, row in rows.iterrows():
        lines.append(
            f"| {month} | {_pct(row['improved_rrp_monthly_return'])} | "
            f"{_pct(row['hs300_etf_monthly_return'])} | {_pct(row['excess_return'])} |"
        )
    return "\n".join(lines)


def build_readme_blocks(monthly: pd.DataFrame, summary: pd.DataFrame) -> tuple[str, str]:
    row = summary.iloc[0]
    latest = monthly.iloc[-1]
    latest_month = str(monthly.index[-1])

    cn = f"""### 与沪深300ETF的月度收益对比

截至 `{row['end_month']}`，Improved Convex Adaptive Global RRP 与沪深300ETF的月度对比显示：策略累计收益为 **{_pct(row['strategy_cumulative_return'])}**，沪深300ETF为 **{_pct(row['hs300_cumulative_return'])}**；策略月度波动率 **{_pct(row['strategy_monthly_volatility'])}**，显著低于沪深300ETF的 **{_pct(row['hs300_monthly_volatility'])}**；日频最大回撤分别为 **{_pct(row['strategy_max_drawdown'])}** 与 **{_pct(row['hs300_max_drawdown'])}**。策略在 {int(row['outperform_months'])}/{int(row['month_count'])} 个月跑赢沪深300ETF，最近一个月（{latest_month}）策略收益 **{_pct(latest['improved_rrp_monthly_return'])}**，沪深300ETF **{_pct(latest['hs300_etf_monthly_return'])}**。

![Improved RRP vs CSI 300 ETF monthly comparison](results/figures/improved_rrp_vs_hs300_monthly_comparison.png)"""

    en = f"""### Monthly Return Comparison vs CSI 300 ETF

Through `{row['end_month']}`, the Improved Convex Adaptive Global RRP delivered **{_pct(row['strategy_cumulative_return'])}** cumulative return versus **{_pct(row['hs300_cumulative_return'])}** for the CSI 300 ETF proxy. Its monthly volatility was **{_pct(row['strategy_monthly_volatility'])}**, far below the CSI 300 ETF's **{_pct(row['hs300_monthly_volatility'])}**; daily maximum drawdowns were **{_pct(row['strategy_max_drawdown'])}** and **{_pct(row['hs300_max_drawdown'])}**, respectively. The strategy outperformed in {int(row['outperform_months'])}/{int(row['month_count'])} months. In the latest month ({latest_month}), the strategy returned **{_pct(latest['improved_rrp_monthly_return'])}** versus **{_pct(latest['hs300_etf_monthly_return'])}** for the CSI 300 ETF.

![Improved RRP vs CSI 300 ETF monthly comparison](results/figures/improved_rrp_vs_hs300_monthly_comparison.png)"""
    return cn, en


def _replace_block(text: str, begin: str, end: str, content: str) -> str:
    block = f"{begin}\n{content}\n{end}"
    if begin in text and end in text:
        before, rest = text.split(begin, 1)
        _, after = rest.split(end, 1)
        return before + block + after
    return text


def _insert_after_performance_section(text: str, block: str, occurrence: int) -> str:
    source_marker = "results/tables/convex_adaptive_performance_summary.csv"
    pos = -1
    search_from = 0
    for _ in range(occurrence):
        pos = text.find(source_marker, search_from)
        if pos < 0:
            return text
        search_from = pos + len(source_marker)
    next_section = text.find("\n---\n\n### ", pos)
    if next_section < 0:
        return text
    return text[:next_section] + "\n\n" + block + "\n" + text[next_section:]


def update_readme(monthly: pd.DataFrame, summary: pd.DataFrame) -> None:
    text = README_PATH.read_text(encoding="utf-8")
    cn, en = build_readme_blocks(monthly, summary)
    cn_block = f"{README_CN_BEGIN}\n{cn}\n{README_CN_END}"
    en_block = f"{README_EN_BEGIN}\n{en}\n{README_EN_END}"
    if README_CN_BEGIN in text and README_CN_END in text:
        text = _replace_block(text, README_CN_BEGIN, README_CN_END, cn)
    else:
        text = _insert_after_performance_section(text, cn_block, occurrence=1)
    if README_EN_BEGIN in text and README_EN_END in text:
        text = _replace_block(text, README_EN_BEGIN, README_EN_END, en)
    else:
        text = _insert_after_performance_section(text, en_block, occurrence=2)
    README_PATH.write_text(text, encoding="utf-8")


def update_thesis_body() -> None:
    main_path = ROOT_DIR / "report/thesis_latex/main.tex"
    text = main_path.read_text(encoding="utf-8")
    block = (
        f"{THESIS_BEGIN}\n"
        r"\subsection{与沪深300ETF的月度收益对比}" "\n"
        r"\IfFileExists{generated_hs300_monthly_comparison.tex}{\input{generated_hs300_monthly_comparison.tex}}{"
        r"\textbf{[HS300 monthly comparison not found --- run scripts/run_monthly_hs300_comparison.py]}}"
        "\n"
        f"{THESIS_END}"
    )

    if THESIS_BEGIN in text and THESIS_END in text:
        before, rest = text.split(THESIS_BEGIN, 1)
        _, after = rest.split(THESIS_END, 1)
        text = before.rstrip() + "\n\n" + after.lstrip()

    core_table = text.find(r"\label{tab:core_perf}")
    if core_table < 0:
        raise ValueError("could not find core performance table anchor in thesis main.tex")
    anchor = text.find(r"\subsection{HRP", core_table)
    if anchor < 0:
        raise ValueError("could not find post-performance HRP subsection anchor in thesis main.tex")
    text = text[:anchor] + block + "\n\n" + text[anchor:]
    main_path.write_text(text, encoding="utf-8")


def write_thesis_snippet(monthly: pd.DataFrame, summary: pd.DataFrame) -> None:
    row = summary.iloc[0]
    lines = [
        "% Auto-generated by scripts/run_monthly_hs300_comparison.py",
        "% Source: monthly comparison generator output",
        "% Do not edit by hand.",
        r"\begin{figure}[H]",
        r"\centering",
        r"\includegraphics[width=\textwidth]{../figures/improved_rrp_vs_hs300_monthly_comparison.png}",
        r"\caption{Improved Convex Adaptive Global RRP 与沪深300ETF的月度表现对比}",
        r"\label{fig:monthly_hs300_comparison}",
        r"\end{figure}",
        "",
        (
            f"图~\\ref{{fig:monthly_hs300_comparison}}展示了 {row['start_month']} 至 {row['end_month']} "
            f"期间 Improved Convex Adaptive Global RRP 与沪深300ETF的月度净值和月度超额收益。"
            f"Improved Convex Adaptive Global RRP 累计收益为 {_tex_pct(row['strategy_cumulative_return'])}，"
            f"沪深300ETF为 {_tex_pct(row['hs300_cumulative_return'])}；但策略月度波动率仅 "
            f"{_tex_pct(row['strategy_monthly_volatility'])}，低于沪深300ETF的 "
            f"{_tex_pct(row['hs300_monthly_volatility'])}。日频最大回撤分别为 "
            f"{_tex_pct(row['strategy_max_drawdown'])}（{row['strategy_max_drawdown_date']}）和 "
            f"{_tex_pct(row['hs300_max_drawdown'])}（{row['hs300_max_drawdown_date']}）。"
        ),
        (
            f"策略在 {int(row['outperform_months'])}/{int(row['month_count'])} 个月跑赢沪深300ETF，"
            f"月度相关系数为 {row['monthly_correlation']:.3f}。该结果说明，本文模型并非"
            "以捕捉A股权益贝塔为目标；其优势主要体现为显著压低波动和回撤，在权益强上涨月份往往牺牲一定进攻弹性。"
        ),
        "",
    ]
    THESIS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    THESIS_OUTPUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Monthly comparison between Improved RRP and CSI 300 ETF proxy.")
    parser.add_argument("--start-date", default="2019-01-01")
    parser.add_argument("--skip-readme", action="store_true")
    args = parser.parse_args()

    monthly, summary = build_monthly_comparison(args.start_date)
    write_csv_outputs(monthly, summary)
    write_figure(monthly, summary)
    write_thesis_snippet(monthly, summary)
    update_thesis_body()
    if not args.skip_readme:
        update_readme(monthly, summary)

    row = summary.iloc[0]
    print(f"Monthly comparison written: {MONTHLY_OUTPUT}")
    print(f"Summary written: {SUMMARY_OUTPUT}")
    print(f"Figure written: {FIGURE_OUTPUT}")
    print(f"Thesis snippet written: {THESIS_OUTPUT}")
    print(
        "Improved RRP vs HS300: "
        f"{_pct(row['strategy_cumulative_return'])} vs {_pct(row['hs300_cumulative_return'])}, "
        f"max drawdown {_pct(row['strategy_max_drawdown'])} vs {_pct(row['hs300_max_drawdown'])}."
    )


if __name__ == "__main__":
    main()
