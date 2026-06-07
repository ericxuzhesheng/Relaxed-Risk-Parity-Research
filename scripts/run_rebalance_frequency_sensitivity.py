from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.run_convex_adaptive_rrp import candidate_configurations, summarize_result
from src.convex_adaptive_rrp import ConvexRRPConfig, run_convex_adaptive_backtest
from src.data_loader import load_data
from src.utils import get_config, resolve_path


FREQUENCIES = [
    ("W", "Weekly"),
    ("2W", "Biweekly"),
    ("M", "Monthly"),
    ("Q", "Quarterly"),
]


def selected_improved_config(transaction_cost_bps: float) -> tuple[str, ConvexRRPConfig]:
    """Return the currently selected Improved model config from the candidate table."""
    candidates_path = Path(resolve_path("results/tables/convex_adaptive_improvement_candidates.csv"))
    selected_id = ""
    if candidates_path.exists():
        candidates = pd.read_csv(candidates_path)
        if "selected" in candidates.columns and "candidate_id" in candidates.columns:
            selected = candidates[candidates["selected"].astype(str).str.lower().eq("true")]
            if not selected.empty:
                selected_id = str(selected.iloc[0]["candidate_id"])
    configs = dict(candidate_configurations(transaction_cost_bps))
    if selected_id and selected_id in configs:
        return selected_id, configs[selected_id]
    if "candidate_23" in configs:
        return "candidate_23", configs["candidate_23"]
    raise RuntimeError(
        "Could not infer the selected Improved Convex Adaptive Global RRP configuration."
    )


def run_frequency_sensitivity(
    returns: pd.DataFrame,
    eval_start_date: str,
    config: dict,
) -> pd.DataFrame:
    rows = []
    selected_id, base_cfg = selected_improved_config(config["transaction_cost_bps"])
    for code, label in FREQUENCIES:
        cfg = replace(base_cfg, rebalance_frequency=code)
        result, solver, _, _ = run_convex_adaptive_backtest(returns, cfg)
        metrics = summarize_result(
            f"Improved Convex Adaptive Global RRP - {label}",
            result,
            eval_start_date,
            {**config, "transaction_cost_bps": cfg.transaction_cost_bps},
        )
        eval_result = result[pd.to_datetime(result["date"]) >= pd.Timestamp(eval_start_date)]
        rebalance_count = int(eval_result["is_rebalance_day"].sum())
        active_rebalance_count = int((eval_result["turnover"].fillna(0.0) > 0.0).sum())
        fallback_rate = float(solver["fallback_used"].mean()) if "fallback_used" in solver and not solver.empty else 0.0
        rows.append(
            {
                "frequency_code": code,
                "frequency_label": label,
                "selected_candidate_id": selected_id,
                "rebalance_count": rebalance_count,
                "active_rebalance_count": active_rebalance_count,
                "solver_fallback_rate": fallback_rate,
                **metrics,
            }
        )
    table = pd.DataFrame(rows)
    monthly = table.loc[table["frequency_code"].eq("M")].iloc[0]
    for col in [
        "net_annual_return",
        "annualized_volatility",
        "sharpe_ratio",
        "sortino_ratio",
        "max_drawdown",
        "calmar_ratio",
        "avg_monthly_turnover",
        "annualized_turnover",
        "cvar_95_daily_loss",
    ]:
        table[f"delta_vs_monthly_{col}"] = table[col] - float(monthly[col])
    table["same_parameters_except_frequency"] = True
    table["interpretation_note"] = (
        "Frequency-only robustness check for the current Improved model; "
        "parameters are not re-selected by frequency."
    )
    return table


def plot_frequency_sensitivity(table: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ordered = table.set_index("frequency_label").loc[[label for _, label in FREQUENCIES]].reset_index()
    fig, axes = plt.subplots(2, 2, figsize=(12, 7))
    metrics = [
        ("net_annual_return", "Net annual return", "{:.1%}"),
        ("sharpe_ratio", "Sharpe ratio", "{:.2f}"),
        ("max_drawdown", "Maximum drawdown", "{:.1%}"),
        ("avg_monthly_turnover", "Average monthly turnover", "{:.1%}"),
    ]
    colors = ["#4267B2" if code == "M" else "#7A869A" for code in ordered["frequency_code"]]
    for ax, (col, title, fmt) in zip(axes.ravel(), metrics):
        bars = ax.bar(ordered["frequency_label"], ordered[col], color=colors)
        ax.set_title(title, pad=10)
        ax.tick_params(axis="x", rotation=20)
        ax.grid(axis="y", alpha=0.25)
        values = ordered[col].astype(float)
        ymin = min(0.0, float(values.min()))
        ymax = max(0.0, float(values.max()))
        span = max(ymax - ymin, 0.01)
        ax.set_ylim(ymin - span * 0.22, ymax + span * 0.22)
        for bar, value in zip(bars, ordered[col]):
            y = bar.get_height()
            offset = span * 0.04 if y >= 0 else -span * 0.04
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                y + offset,
                fmt.format(value),
                ha="center",
                va="bottom" if y >= 0 else "top",
                fontsize=9,
            )
    fig.suptitle("Rebalance Frequency Sensitivity: Improved Convex Adaptive Global RRP")
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run frequency-only rebalance sensitivity for the Improved Convex Adaptive Global RRP."
    )
    parser.add_argument("--eval-start-date", default="2019-01-01")
    parser.add_argument("--source", default="tushare")
    parser.add_argument("--output-dir", default="results/tables")
    parser.add_argument("--figure-dir", default="results/figures")
    args = parser.parse_args()

    config = get_config({"transaction_cost_bps": 3.0, "turnover_cap": 0.25, "target_vol": 0.060})
    returns = load_data(source=args.source)
    table = run_frequency_sensitivity(returns, args.eval_start_date, config)

    output_path = Path(resolve_path(args.output_dir)) / "rebalance_frequency_sensitivity.csv"
    figure_path = Path(resolve_path(args.figure_dir)) / "rebalance_frequency_sensitivity.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(output_path, index=False)
    plot_frequency_sensitivity(table, figure_path)

    print(f"Wrote {output_path}")
    print(f"Wrote {figure_path}")
    print(table[["frequency_label", "net_annual_return", "sharpe_ratio", "max_drawdown", "avg_monthly_turnover"]])


if __name__ == "__main__":
    main()
