"""Generate monthly portfolio weights stacked bar chart for the Improved model.

Output: results/figures/improved_weights_timeline.png
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# Use system CJK font so Chinese labels render correctly
for _font in ["Microsoft YaHei", "SimHei", "Noto Sans SC", "STSong"]:
    if any(f.name == _font for f in fm.fontManager.ttflist):
        matplotlib.rcParams["font.family"] = _font
        break
matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# ── colour palette per asset class ───────────────────────────────────────────
ASSET_CLASS_COLOR = {
    "government bond":         "#2166ac",   # deep blue
    "convertible bond":        "#4393c3",   # mid blue
    "credit bond":             "#74add1",   # light blue
    "money market":            "#abd9e9",   # very light blue
    "china equity":            "#d73027",   # red
    "china equity dividend":   "#f46d43",   # orange-red
    "china tech equity":       "#fdae61",   # orange
    "china advanced manufacturing": "#fee090",  # pale orange
    "china new energy":        "#ffffbf",   # pale yellow
    "china finance":           "#e0f3f8",   # ice
    "china defense":           "#b2182b",   # dark red
    "china consumer":          "#ef8a62",   # salmon
    "hong kong equity":        "#999999",   # grey
    "global equity":           "#1b7837",   # dark green
    "commodity":               "#d9a82a",   # gold
    "commodity equity":        "#bf812d",   # brown-gold
}

EVAL_START = "2019-01-01"
EVAL_END   = "2026-04-30"


def _load_weights() -> tuple[pd.DataFrame, list[str]]:
    path = ROOT / "results/tables/improved_convex_adaptive_global_relaxed_risk_parity_returns.csv"
    df = pd.read_csv(path, parse_dates=["date"])
    df = df[df["is_rebalance_day"] == True].copy()
    df = df[(df["date"] >= EVAL_START) & (df["date"] <= EVAL_END)].copy()
    df = df.sort_values("date").reset_index(drop=True)

    wcols = [c for c in df.columns if c.startswith("weight_")]
    return df, wcols


def _etf_color(etf_name: str, etf_universe) -> str:
    for e in etf_universe:
        if e.new_name == etf_name:
            return ASSET_CLASS_COLOR.get(e.asset_class, "#cccccc")
    return "#cccccc"


def _asset_class(etf_name: str, etf_universe) -> str:
    for e in etf_universe:
        if e.new_name == etf_name:
            return e.asset_class
    return "other"


def main() -> None:
    from asset_universe import ETF_UNIVERSE

    df, wcols = _load_weights()
    dates = df["date"].dt.strftime("%Y-%m")

    # strip "weight_" prefix
    etf_names = [c[len("weight_"):] for c in wcols]

    weights = df[wcols].values  # shape (n_periods, n_etfs)

    # ── group order: bonds → equity → commodity (for visual clarity) ─────────
    CLASS_ORDER = [
        "government bond", "convertible bond", "credit bond", "money market",
        "china equity", "china equity dividend", "china consumer",
        "china finance", "china defense",
        "china tech equity", "china advanced manufacturing", "china new energy",
        "hong kong equity",
        "global equity",
        "commodity", "commodity equity",
    ]

    def sort_key(name: str) -> int:
        cls = _asset_class(name, ETF_UNIVERSE)
        try:
            return CLASS_ORDER.index(cls)
        except ValueError:
            return 99

    order = sorted(range(len(etf_names)), key=lambda i: sort_key(etf_names[i]))
    etf_names_sorted = [etf_names[i] for i in order]
    weights_sorted = weights[:, order]

    colors = [_etf_color(n, ETF_UNIVERSE) for n in etf_names_sorted]

    # ── plot ─────────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(18, 7))

    x = np.arange(len(dates))
    bar_width = 0.85
    bottoms = np.zeros(len(dates))

    bars = []
    for i, (name, color) in enumerate(zip(etf_names_sorted, colors)):
        vals = weights_sorted[:, i]
        bar = ax.bar(x, vals, bar_width, bottom=bottoms, color=color,
                     linewidth=0, zorder=2)
        bars.append((name, color, bar))
        bottoms += vals

    # ── x-axis: show every 3rd month label ───────────────────────────────────
    step = 3
    tick_positions = x[::step]
    tick_labels = [dates.iloc[i] for i in range(0, len(dates), step)]
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, rotation=45, ha="right", fontsize=8)

    ax.set_xlim(-0.5, len(dates) - 0.5)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("权重占比", fontsize=11)
    ax.set_xlabel("日期", fontsize=11)
    ax.set_title("改进型凸适应性全局RRP — 月末持仓权重变化", fontsize=13, fontweight="bold")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0%}"))
    ax.grid(axis="y", linestyle="--", alpha=0.4, zorder=1)

    # ── legend: one entry per unique (name, color), skip near-zero holdings ──
    shown = set()
    legend_handles = []
    mean_w = weights_sorted.mean(axis=0)
    for i, (name, color) in enumerate(zip(etf_names_sorted, colors)):
        if mean_w[i] < 0.005:   # skip if avg weight < 0.5%
            continue
        if color not in shown:
            shown.add(color)
        legend_handles.append(
            mpatches.Patch(color=color, label=name)
        )

    ax.legend(
        handles=legend_handles,
        loc="upper left",
        bbox_to_anchor=(1.01, 1),
        fontsize=8,
        frameon=True,
        ncol=1,
        title="资产",
        title_fontsize=9,
    )

    plt.tight_layout()
    out = ROOT / "results/figures/improved_weights_timeline.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
