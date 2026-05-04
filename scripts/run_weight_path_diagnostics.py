from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent

MODEL_PATHS = {
    "Improved Convex Adaptive Global RRP": ROOT_DIR / "results" / "tables" / "improved_convex_adaptive_global_relaxed_risk_parity_returns.csv",
    "Global RRP": ROOT_DIR / "results" / "tables" / "v3_global_rrp_weights.csv",
    "HRP Benchmark": ROOT_DIR / "results" / "tables" / "hrp_benchmark_weights.csv",
    "HERC Benchmark": ROOT_DIR / "results" / "tables" / "herc_benchmark_weights.csv",
}

GROUP_ORDER = [
    "Bonds",
    "China Equity",
    "Hong Kong Equity",
    "Global Equity",
    "Commodities",
]

GROUP_DISPLAY = {
    "Bonds": "Bonds",
    "China Equity": "China Equity",
    "Hong Kong Equity": "Hong Kong Equity",
    "Global Equity": "Global Equity",
    "Commodities": "Commodities",
}

KEY_ASSETS = [
    "短融ETF",
    "红利ETF",
    "黄金ETF",
    "恒生ETF",
    "恒生科技ETF",
    "纳指ETF",
    "标普500ETF",
]

PERIODS = [
    ("2021-01-01", "2022-12-31", "2021-2022"),
    ("2023-01-01", "2025-12-31", "2023-2025"),
]


def output_dirs(root: Path) -> tuple[Path, Path]:
    tables = root / "tables"
    figures = root / "figures"
    tables.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    return tables, figures


def load_asset_groups() -> dict[str, str]:
    mapping = pd.read_csv(ROOT_DIR / "data" / "processed" / "etf_asset_mapping.csv")
    grouped: dict[str, str] = {}
    for _, row in mapping.iterrows():
        asset_name = str(row["new_name"])
        asset_class = str(row["asset_class"])
        if asset_class in {"short-duration credit", "convertible bond"}:
            grouped[asset_name] = "Bonds"
        elif asset_class in {"china equity", "china equity dividend"}:
            grouped[asset_name] = "China Equity"
        elif asset_class == "hong kong equity":
            grouped[asset_name] = "Hong Kong Equity"
        elif asset_class == "global equity":
            grouped[asset_name] = "Global Equity"
        elif asset_class in {"commodity", "commodity equity"}:
            grouped[asset_name] = "Commodities"
        else:
            grouped[asset_name] = asset_class
    return grouped


def load_weights(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"])
    keep = ["date"] + [col for col in df.columns if col.startswith("weight_")]
    return df.loc[:, keep].copy()


def to_group_weights(df: pd.DataFrame, asset_groups: dict[str, str]) -> pd.DataFrame:
    out = pd.DataFrame({"date": df["date"]})
    for group in GROUP_ORDER:
        out[group] = 0.0
    for col in [col for col in df.columns if col.startswith("weight_")]:
        asset_name = col.replace("weight_", "", 1)
        group = asset_groups.get(asset_name)
        if group in out.columns:
            out[group] = out[group] + df[col].fillna(0.0)
    return out


def monthly_group_weights(models: dict[str, pd.DataFrame], asset_groups: dict[str, str]) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for model, df in models.items():
        grouped = to_group_weights(df, asset_groups).set_index("date").resample("ME").last()
        grouped = grouped[grouped.index >= pd.Timestamp("2021-01-31")]
        grouped = grouped.reset_index()
        grouped.insert(1, "model", model)
        rows.append(grouped)
    return pd.concat(rows, ignore_index=True)


def stage_summary(models: dict[str, pd.DataFrame], asset_groups: dict[str, str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    group_rows: list[dict[str, object]] = []
    key_rows: list[dict[str, object]] = []
    for model, df in models.items():
        grouped = to_group_weights(df, asset_groups)
        for start, end, label in PERIODS:
            sub = df[(df["date"] >= start) & (df["date"] <= end)].copy()
            sub_grouped = grouped[(grouped["date"] >= start) & (grouped["date"] <= end)].copy()
            group_row: dict[str, object] = {"model": model, "stage": label}
            for group in GROUP_ORDER:
                group_row[group.lower().replace(" ", "_")] = float(sub_grouped[group].mean())
            group_rows.append(group_row)

            key_row: dict[str, object] = {"model": model, "stage": label}
            for asset in KEY_ASSETS:
                key_row[asset] = float(sub[f"weight_{asset}"].mean()) if f"weight_{asset}" in sub.columns else 0.0
            key_rows.append(key_row)
    return pd.DataFrame(group_rows), pd.DataFrame(key_rows)


def change_summary(group_summary: pd.DataFrame, key_summary: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for model in group_summary["model"].unique():
        g = group_summary[group_summary["model"].eq(model)].set_index("stage")
        k = key_summary[key_summary["model"].eq(model)].set_index("stage")
        row: dict[str, object] = {"model": model}
        for col in [c for c in g.columns if c != "model"]:
            row[f"{col}_change_2023_2025_vs_2021_2022"] = float(g.loc["2023-2025", col] - g.loc["2021-2022", col])
        for col in [c for c in k.columns if c != "model"]:
            row[f"{col}_change_2023_2025_vs_2021_2022"] = float(k.loc["2023-2025", col] - k.loc["2021-2022", col])
        rows.append(row)
    return pd.DataFrame(rows)


def plot_group_weights(monthly: pd.DataFrame, path: Path) -> None:
    colors = {
        "Bonds": "#1f4e79",
        "China Equity": "#c44e52",
        "Hong Kong Equity": "#dd8452",
        "Global Equity": "#55a868",
        "Commodities": "#8172b2",
    }
    fig, axes = plt.subplots(2, 2, figsize=(14, 9), sharex=True, sharey=True)
    axes_flat = axes.flatten()
    for ax, model in zip(axes_flat, MODEL_PATHS):
        data = monthly[monthly["model"].eq(model)].copy()
        for group in GROUP_ORDER:
            ax.plot(data["date"], data[group], linewidth=1.8, color=colors[group], label=GROUP_DISPLAY[group])
        ax.set_title(model, fontsize=10)
        ax.grid(True, alpha=0.25)
        ax.set_ylim(0, 1.02)
    for ax in axes[:, 0]:
        ax.set_ylabel("Weight")
    for ax in axes[-1, :]:
        ax.set_xlabel("Date")
    handles, labels = axes_flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=5, frameon=False)
    fig.suptitle("Asset-Group Weight Paths (Monthly, 2021-2025)", y=0.98)
    fig.tight_layout(rect=(0, 0.06, 1, 0.96))
    fig.savefig(path, dpi=200)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate weight-path diagnostics from existing portfolio weight outputs.")
    parser.add_argument("--output-root", type=Path, default=ROOT_DIR / "results", help="Directory that will receive tables/ and figures/.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tables, figures = output_dirs(args.output_root)
    asset_groups = load_asset_groups()
    models = {model: load_weights(path) for model, path in MODEL_PATHS.items()}
    monthly = monthly_group_weights(models, asset_groups)
    group_summary, key_summary = stage_summary(models, asset_groups)
    changes = change_summary(group_summary, key_summary)

    monthly.to_csv(tables / "weight_path_monthly_group_weights.csv", index=False)
    group_summary.to_csv(tables / "weight_path_stage_summary.csv", index=False)
    key_summary.to_csv(tables / "weight_path_key_asset_stage_summary.csv", index=False)
    changes.to_csv(tables / "weight_path_change_summary.csv", index=False)
    plot_group_weights(monthly, figures / "weight_path_asset_group_comparison.png")
    print(f"Weight-path diagnostics written to {args.output_root}")


if __name__ == "__main__":
    main()
