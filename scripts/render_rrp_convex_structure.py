"""Render the Global RRP constraint/objective diagram from its mathematical form.

References: Convex Optimization, chapters 2, 3 and 5; Introduction to Risk
Parity and Budgeting. The triangle is schematic, not an observed allocation.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BLUE, RED = "#194F7D", "#B53B4A"


def render():
    plt.rcParams.update({"font.family": "sans-serif",
        "font.sans-serif": ["Microsoft YaHei", "Arial"], "font.size": 12,
        "mathtext.fontset": "stix", "axes.unicode_minus": False, "pdf.fonttype": 42})
    fig = plt.figure(figsize=(8, 4.65), facecolor="white")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set(xlim=(0, 1), ylim=(0, 1)); ax.axis("off")

    def card(x, y, width, height, color):
        ax.add_patch(FancyBboxPatch((x, y), width, height,
            boxstyle="round,pad=0.009,rounding_size=0.012",
            facecolor="#F1F5F8" if color == BLUE else "#FBF1F3",
            edgecolor=color, linewidth=1))

    ax.text(.235, .95, "多头、满仓的可行权重", ha="center", color=BLUE, weight="bold")
    tri = np.array([[.055, .25], [.44, .25], [.055, .81]])
    ax.add_patch(Polygon(tri, facecolor="#EAF1F7", edgecolor=BLUE, lw=1.7))
    q = np.array([.17, .44])
    w = .57*tri[1] + .43*tri[2]
    ax.scatter(*q, s=38, color=BLUE, zorder=4)
    ax.text(q[0]-.005, q[1]+.055, r"参考 $q_t$", ha="center", color=BLUE)
    ax.scatter(*w, s=40, color=RED, zorder=4)
    ax.annotate("", xy=w, xytext=q,
        arrowprops={"arrowstyle":"->", "lw":1.4, "color":RED,
                    "connectionstyle":"arc3,rad=-.15"})
    ax.text(.27, .62, r"最优权重 $w_t$", color=RED)
    ax.text(.27, .56, "可位于边界", color=RED, fontsize=10)
    ax.text(.245, .17, r"$\Delta_t=\{w\geq0:\ \mathbf{1}^{T}w=1\}$",
            ha="center", fontsize=13, color=BLUE)
    ax.text(.245, .105, "三资产几何示意，非实际持仓", ha="center", fontsize=9, color="#666666")

    ax.text(.742, .95, "固定当期输入后的目标函数", ha="center", color=RED, weight="bold")
    card(.49, .70, .49, .13, RED)
    ax.text(.51, .777, r"参考跟踪  $\|w-q_t\|_2^2$", va="center", fontsize=13)
    ax.text(.96, .722, "严格凸", ha="right", color=RED, fontsize=10)
    card(.49, .49, .49, .13, BLUE)
    ax.text(.51, .568, r"组合方差  $\lambda_{v,t}\,w^T\Sigma_t w/v_t$", va="center", fontsize=13)
    ax.text(.96, .512, "凸", ha="right", color=BLUE, fontsize=10)
    card(.49, .28, .49, .13, BLUE)
    ax.text(.51, .366, r"收益短缺  $\lambda_{r,t}[\max(0,z_t)]^2$", va="center", fontsize=12)
    ax.text(.51, .301, r"$z_t=(R_t-\mu_t^T w)/s_t$", va="center", fontsize=11)
    ax.text(.96, .30, "凸", ha="right", color=BLUE, fontsize=10)
    for y in [.66, .45]:
        ax.text(.73, y, "+", ha="center", va="center", color=RED, fontsize=17)
    ax.text(.742, .17, r"$R_t=\mu_t^T q_t$，收益目标由可行参考给出", ha="center", fontsize=10)
    ax.text(.742, .105, "收益目标采用软惩罚，可行域保持不变", ha="center", fontsize=9, color="#666666")
    ax.text(.5, .025, "凸可行域  +  严格凸目标    →    唯一最优权重", ha="center",
            fontsize=12, color=RED, weight="bold")
    out = ROOT / "results" / "figures"
    for ext in ["pdf", "png"]:
        fig.savefig(out/f"rrp_convex_structure.{ext}", dpi=300, bbox_inches="tight", pad_inches=.06)
    plt.close(fig)
    # The illustrative endpoint is on the triangle boundary; the reference is internal.
    assert np.isclose((w[0]-.055)/.385+(w[1]-.25)/.56, 1)
    assert (q[0]-.055)/.385+(q[1]-.25)/.56 < 1
    print("Rendered one model-specific diagram as vector PDF and 300-dpi PNG.")


if __name__ == "__main__":
    render()
