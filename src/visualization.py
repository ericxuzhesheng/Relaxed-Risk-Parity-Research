import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import os

plt.rcParams["font.sans-serif"] = ["SimHei"]
plt.rcParams["axes.unicode_minus"] = False

def plot_nav_comparison(nav_dict: dict, title: str, save_path: str):
    plt.figure(figsize=(12, 6))
    for name, nav in nav_dict.items():
        plt.plot(nav, label=name)
    plt.title(title)
    plt.legend()
    plt.grid(True)
    plt.savefig(save_path)
    plt.close()

def plot_drawdown_comparison(nav_dict: dict, title: str, save_path: str):
    plt.figure(figsize=(12, 6))
    for name, nav in nav_dict.items():
        drawdown = nav / nav.cummax() - 1
        plt.plot(drawdown, label=name)
    plt.title(title)
    plt.legend()
    plt.grid(True)
    plt.savefig(save_path)
    plt.close()


def plot_metric_comparison(summary: pd.DataFrame, metric_col: str, title: str, save_path: str, ylabel: str | None = None):
    if metric_col not in summary.columns:
        raise ValueError(f"Missing metric column: {metric_col}")
    plot_df = summary.set_index("model")[[metric_col]].copy()
    ax = plot_df.plot(kind="bar", figsize=(12, 6), legend=False)
    ax.set_title(title)
    if ylabel is not None:
        ax.set_ylabel(ylabel)
    ax.grid(axis="y", alpha=0.3)
    plt.xticks(rotation=25, ha="right")
    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()

def plot_weights(weights_df: pd.DataFrame, title: str, save_path: str):
    plt.figure(figsize=(12, 6))
    weights_df.plot.area(stacked=True, ax=plt.gca())
    plt.title(title)
    plt.legend(loc='center left', bbox_to_anchor=(1, 0.5))
    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()

def plot_param_timeline(df: pd.DataFrame, param_col: str, title: str, save_path: str):
    plt.figure(figsize=(12, 4))
    plt.plot(df['date'], df[param_col], drawstyle='steps-post')
    plt.title(title)
    plt.savefig(save_path)
    plt.close()


def plot_dynamic_parameter_timeline(df: pd.DataFrame, save_path: str):
    cols = [
        c
        for c in ["avg_selected_lambda", "avg_selected_m", "avg_selected_bond_leverage_upper"]
        if c in df.columns
    ]
    if not cols:
        return
    plot_df = df.copy()
    plot_df["date"] = pd.to_datetime(plot_df["date"])
    plot_df = plot_df.groupby(plot_df["date"].dt.to_period("M")).head(1)
    fig, axes = plt.subplots(len(cols), 1, figsize=(12, 3 * len(cols)), sharex=True)
    if len(cols) == 1:
        axes = [axes]
    for ax, col in zip(axes, cols):
        ax.plot(plot_df["date"], plot_df[col], drawstyle="steps-post")
        ax.set_title(col)
        ax.grid(True)
    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()


def plot_risk_overlay_ablation(df: pd.DataFrame, save_path: str):
    if df.empty:
        return
    metric = "sharpe_ratio" if "sharpe_ratio" in df.columns else df.columns[-1]
    plt.figure(figsize=(10, 5))
    plt.bar(df["model"], df[metric])
    plt.title(f"Risk Overlay Ablation ({metric})")
    plt.xticks(rotation=25, ha="right")
    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()


def plot_pbo_heatmap(df: pd.DataFrame, save_path: str):
    plt.figure(figsize=(8, 4))
    if df.empty:
        plt.text(0.5, 0.5, "No PBO data", ha="center", va="center")
        plt.axis("off")
    else:
        data = df[["test_rank_percentile"]].T.values
        plt.imshow(data, aspect="auto", cmap="RdYlGn_r", vmin=0, vmax=1)
        plt.yticks([0], ["Test rank percentile"])
        labels = pd.to_datetime(df["split_date"]).dt.strftime("%Y-%m").tolist()
        plt.xticks(range(len(labels)), labels, rotation=45, ha="right")
        plt.colorbar(label="Lower is better")
        plt.title("Simplified PBO Diagnostic")
    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()
