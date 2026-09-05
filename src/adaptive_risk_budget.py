from __future__ import annotations

import numpy as np
import pandas as pd

from src.asset_graph_features import rolling_correlation_graph_features


REGIME_LABELS = ("low_risk", "medium_risk", "high_risk")


def economic_risk_group(asset_name: str) -> str:
    """Map an ETF to one of the eight economic risk-budget groups."""
    from src.asset_universe import CANDIDATE_UNIVERSE, ETF_UNIVERSE

    declared = {}
    for asset in (*ETF_UNIVERSE, *CANDIDATE_UNIVERSE):
        declared[asset.new_name] = asset.asset_class
        declared[asset.old_name] = asset.asset_class
    name = str(asset_name)
    category = declared.get(name, "")
    if "bond" in category or category == "money market":
        return "bonds"
    if category in {"china equity", "china equity dividend"}:
        return "china_broad_equity"
    if category in {"china tech equity", "china new energy"}:
        return "china_technology"
    if category in {"china finance", "china defense", "china consumer"}:
        return "china_sector_consumption"
    if category == "hong kong equity":
        return "hong_kong_equity"
    if category == "global equity":
        return "global_equity"
    if category == "commodity" and name in {"黄金ETF", "白银LOF"}:
        return "precious_metals"
    if category == "commodity":
        return "commodities"
    return "other"


def group_neutral_risk_budgets(columns: pd.Index) -> np.ndarray:
    """Allocate equally across active economic groups and then within group."""
    groups = [economic_risk_group(str(column)) for column in columns]
    counts = {group: groups.count(group) for group in set(groups)}
    group_budget = 1.0 / len(counts)
    return np.asarray([group_budget / counts[group] for group in groups], dtype=float)


def _normalize(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    values = np.clip(values, 0.0, None)
    total = float(values.sum())
    if total <= 0.0:
        return np.ones_like(values) / len(values)
    return values / total


def adaptive_budget_target(
    returns_window: pd.DataFrame,
    graph_features: dict | None = None,
    regime_label: str = "medium_risk",
    min_budget: float = 0.01,
) -> pd.Series:
    """Return positive risk-budget shares derived from point-in-time inputs.

    The returned values are *risk budgets*, not portfolio weights.  With graph
    and regime features disabled, active economic groups receive equal budgets
    and ETFs split their group's budget equally.  Under measured stress the
    target tilts gradually toward lower-volatility assets; the convex
    risk-budgeting stage converts the shares into portfolio weights.
    """
    data = returns_window.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    data = data.dropna(how="any")
    if data.empty:
        data = returns_window.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)
    vol = data.std().replace(0.0, np.nan)
    inv_vol = (1.0 / vol).replace([np.inf, -np.inf], np.nan).fillna(0.0).values
    defensive_budget = _normalize(inv_vol)

    stress = float((graph_features or {}).get("correlation_stress_score", 0.0))
    stress = float(np.clip(stress, 0.0, 1.0))
    regime_multiplier = {"low_risk": 0.75, "medium_risk": 1.0, "high_risk": 1.35}.get(regime_label, 1.0)

    group_neutral = group_neutral_risk_budgets(returns_window.columns)
    defensive_tilt = np.clip(stress * regime_multiplier, 0.0, 0.85)
    target = (
        (1.0 - defensive_tilt) * group_neutral
        + defensive_tilt * defensive_budget
    )
    target = np.maximum(target, min_budget)
    target = _normalize(target)
    return pd.Series(target, index=returns_window.columns)


def online_regime_state(
    returns_window: pd.DataFrame,
    previous_state: dict | None = None,
    graph_features: dict | None = None,
    trading_days: int = 243,
    smoothing: float = 0.80,
    persistence: int = 2,
) -> dict:
    """Stable ordered online regime labels from lagged data only."""
    previous_state = previous_state or {}
    data = returns_window.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    data = data.dropna(how="any")
    if data.empty:
        raw_stress = 0.0
    else:
        equal_port = data.mean(axis=1)
        realized_vol = float(equal_port.std() * np.sqrt(trading_days)) if len(equal_port) > 2 else 0.0
        trailing_loss = float(max(0.0, -equal_port.tail(min(len(equal_port), 21)).sum()))
        graph_stress = float((graph_features or rolling_correlation_graph_features(data)).get("correlation_stress_score", 0.0))
        vol_stress = np.clip(realized_vol / 0.18, 0.0, 1.0)
        loss_stress = np.clip(trailing_loss / 0.08, 0.0, 1.0)
        raw_stress = float(np.clip(0.45 * vol_stress + 0.30 * loss_stress + 0.25 * graph_stress, 0.0, 1.0))

    previous_smoothed = float(previous_state.get("smoothed_stress_score", raw_stress))
    smoothing = float(np.clip(smoothing, 0.0, 0.98))
    smoothed = smoothing * previous_smoothed + (1.0 - smoothing) * raw_stress
    candidate = "low_risk" if smoothed < 0.33 else "medium_risk" if smoothed < 0.66 else "high_risk"

    previous_label = str(previous_state.get("regime_label", candidate))
    pending_label = str(previous_state.get("pending_label", candidate))
    pending_count = int(previous_state.get("pending_count", 0))
    if candidate == previous_label:
        label = previous_label
        pending_label = candidate
        pending_count = 0
    elif candidate == pending_label:
        pending_count += 1
        label = candidate if pending_count >= max(int(persistence), 1) else previous_label
    else:
        pending_label = candidate
        pending_count = 1
        label = previous_label

    return {
        "raw_stress_score": raw_stress,
        "smoothed_stress_score": float(smoothed),
        "regime_label": label,
        "candidate_regime_label": candidate,
        "pending_label": pending_label,
        "pending_count": pending_count,
    }
