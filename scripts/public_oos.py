"""Shared loaders and variants for the published AFML rolling OOS path."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pandas as pd

from scripts.run_convex_adaptive_rrp import candidate_configurations, slice_and_rebase_result
from src.convex_adaptive_rrp import (
    ConvexRRPConfig,
    run_convex_adaptive_schedule_backtest,
)
from src.utils import get_config, resolve_path


SELECTION_PATH = Path(resolve_path("results/tables/afml_oos_selection.csv"))
PUBLIC_RESULT_PATH = Path(
    resolve_path("results/tables/improved_convex_adaptive_global_relaxed_risk_parity_returns.csv")
)


def load_public_oos_selection(path: str | Path = SELECTION_PATH) -> pd.DataFrame:
    selection = pd.read_csv(path, parse_dates=["test_start", "test_end", "validation_end"])
    required = {"test_start", "test_end", "selected_candidate_id"}
    missing = required.difference(selection.columns)
    if missing:
        raise ValueError(f"public OOS selection table missing columns: {sorted(missing)}")
    if selection.empty:
        raise ValueError("public OOS selection table is empty")
    return selection.sort_values("test_start").reset_index(drop=True)


def load_public_oos_result(path: str | Path = PUBLIC_RESULT_PATH) -> pd.DataFrame:
    result = pd.read_csv(path, parse_dates=["date"])
    required = {"date", "gross_return", "net_return", "turnover"}
    missing = required.difference(result.columns)
    if missing:
        raise ValueError(f"public OOS result missing columns: {sorted(missing)}")
    if result.empty:
        raise ValueError("public OOS result is empty")
    return result.sort_values("date").reset_index(drop=True)


def public_candidate_configs(transaction_cost_bps: float) -> dict[str, ConvexRRPConfig]:
    return dict(candidate_configurations(transaction_cost_bps))


def run_public_oos_variant(
    returns: pd.DataFrame,
    *,
    transaction_cost_bps: float = 3.0,
    transform: Callable[[ConvexRRPConfig], ConvexRRPConfig] | None = None,
    selection: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Re-run the audited warm-up and public OOS schedule after a uniform perturbation."""
    planned = load_public_oos_selection() if selection is None else selection.copy()
    configs = public_candidate_configs(transaction_cost_bps)
    if transform is not None:
        configs = {candidate_id: transform(cfg) for candidate_id, cfg in configs.items()}
    scheduled_result, scheduled_solver, _, _ = run_convex_adaptive_schedule_backtest(
        returns,
        planned[["test_start", "test_end", "selected_candidate_id"]],
        configs,
    )
    evaluation_start = get_config()["evaluation_start_date"]
    result = slice_and_rebase_result(scheduled_result, evaluation_start)
    if scheduled_solver.empty:
        solver = scheduled_solver.copy()
    else:
        solver = scheduled_solver[
            pd.to_datetime(scheduled_solver["date"]) >= pd.Timestamp(evaluation_start)
        ].copy()
    return result, solver


def reprice_public_result(result: pd.DataFrame, transaction_cost_bps: float) -> pd.DataFrame:
    """Hold the OOS decisions fixed and apply an alternative per-turnover cost."""
    data = result.copy()
    data["transaction_cost"] = data["turnover"].fillna(0.0) * float(transaction_cost_bps) / 10000.0
    data["net_return"] = data["gross_return"].fillna(0.0) - data["transaction_cost"]
    data["portfolio_return"] = data["net_return"]
    data["nav_gross"] = (1.0 + data["gross_return"].fillna(0.0)).cumprod()
    data["nav_net"] = (1.0 + data["net_return"].fillna(0.0)).cumprod()
    return data


def modal_selected_config(transaction_cost_bps: float = 3.0) -> tuple[str, ConvexRRPConfig]:
    """Return the most frequently selected candidate for local diagnostics only."""
    selection = load_public_oos_selection()
    if "phase" in selection:
        selection = selection[selection["phase"].eq("public_oos")]
    counts = selection["selected_candidate_id"].value_counts()
    candidate_id = sorted(counts[counts.eq(counts.max())].index)[0]
    return candidate_id, public_candidate_configs(transaction_cost_bps)[candidate_id]
