from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from src.adaptive_risk_budget import adaptive_budget_target, online_regime_state
from src.asset_graph_features import rolling_correlation_graph_features
from src.covariance_estimators import estimate_covariance
from src.investable import expand_weights, investable_columns, portfolio_return_for_available
from src.utils import infer_asset_class

try:
    import cvxpy as cp
except Exception:  # pragma: no cover - exercised when dependency is absent
    cp = None


@dataclass
class ConvexRRPConfig:
    trading_days_per_year: int = 243
    lookback_days: int = 240
    covariance_method: str = "ewma"
    covariance_allow_fallback: bool = True
    ewma_halflife: float = 60.0
    max_weight: float = 0.35
    turnover_cap: float | None = 0.35
    turnover_penalty: float = 0.02
    transaction_cost_bps: float = 3.0
    transaction_cost_penalty: float = 1.0
    variance_penalty: float = 1.0
    budget_penalty: float = 0.35
    return_reward: float = 0.05
    cvar_penalty: float = 0.0
    cvar_beta: float = 0.95
    use_graph_features: bool = False
    use_transaction_cost_objective: bool = False
    use_online_regime: bool = False
    group_bounds: dict[str, tuple[float, float]] = field(default_factory=dict)
    solver: str | None = None


def _clean_weights(weights: np.ndarray) -> np.ndarray:
    w = np.nan_to_num(np.asarray(weights, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
    w = np.clip(w, 0.0, None)
    total = float(w.sum())
    if total <= 0.0:
        return np.ones_like(w) / len(w)
    return w / total


def _group_constraints(columns: pd.Index, group_bounds: dict[str, tuple[float, float]]):
    groups: dict[str, list[int]] = {}
    for i, col in enumerate(columns):
        groups.setdefault(infer_asset_class(str(col)), []).append(i)
    return [(idxs, bounds) for group, bounds in group_bounds.items() if (idxs := groups.get(group))]


def solve_convex_rrp(
    returns_window: pd.DataFrame,
    previous_weights: np.ndarray | None = None,
    config: ConvexRRPConfig | None = None,
    budget_target: pd.Series | np.ndarray | None = None,
    graph_features: dict | None = None,
    regime_label: str = "medium_risk",
) -> tuple[np.ndarray, dict]:
    cfg = config or ConvexRRPConfig()
    n_assets = len(returns_window.columns)
    previous = _clean_weights(previous_weights) if previous_weights is not None else np.ones(n_assets) / n_assets
    graph_features = graph_features or {}
    cov_result = estimate_covariance(
        returns_window,
        cfg.covariance_method,
        trading_days=cfg.trading_days_per_year,
        ewma_halflife=cfg.ewma_halflife,
        annualize=True,
        allow_fallback=cfg.covariance_allow_fallback,
        return_diagnostics=True,
        point_in_time=True,
    )
    cov = cov_result.covariance
    sigma = cov.values
    # mu_t is estimated only from the historical window available before rebalance.
    # It is an annualized sample mean of returns_window rather than a forward-looking forecast.
    # The signal enters the objective only through the small return_reward coefficient.
    # This keeps the convex program anchored on risk budgeting and implementability terms.
    mu = returns_window.mean().fillna(0.0).values * cfg.trading_days_per_year
    if budget_target is None:
        target = adaptive_budget_target(returns_window, graph_features, regime_label).values
    else:
        target = np.asarray(budget_target, dtype=float)
        target = _clean_weights(target)

    diagnostics = {
        "solver_name": None,
        "solver_status": None,
        "objective_value": np.nan,
        "failure_reason": "",
        "fallback_used": False,
        "inaccurate_solution": False,
        **cov_result.diagnostics,
    }

    if cp is not None:
        w = cp.Variable(n_assets)
        turnover = cp.norm1(w - previous)
        tc_rate = cfg.transaction_cost_bps / 10000.0
        objective = (
            cfg.variance_penalty * cp.quad_form(w, sigma)
            + cfg.budget_penalty * cp.sum_squares(w - target)
            + cfg.turnover_penalty * turnover
            - cfg.return_reward * (mu @ w)
        )
        if cfg.use_transaction_cost_objective:
            objective += cfg.transaction_cost_penalty * tc_rate * turnover
        constraints = [w >= 0.0, cp.sum(w) == 1.0, w <= cfg.max_weight]
        if cfg.turnover_cap is not None:
            constraints.append(turnover <= cfg.turnover_cap)
        for idxs, (lower, upper) in _group_constraints(returns_window.columns, cfg.group_bounds):
            exposure = cp.sum(w[idxs])
            constraints.extend([exposure >= lower, exposure <= upper])
        cvar_effective_obs = int((~returns_window.isna().any(axis=1)).sum())
        cvar_total_obs = len(returns_window)
        diagnostics.update({"cvar_effective_obs": cvar_effective_obs, "cvar_total_obs": cvar_total_obs})
        cvar_window = returns_window.fillna(0.0)
        if cfg.cvar_penalty > 0.0 and len(cvar_window) > 0:
            alpha = cp.Variable()
            u = cp.Variable(len(cvar_window))
            losses = -cvar_window.values @ w
            constraints.extend([u >= 0.0, u >= losses - alpha])
            cvar = alpha + cp.sum(u) / ((1.0 - cfg.cvar_beta) * len(cvar_window))
            objective += cfg.cvar_penalty * cvar
        problem = cp.Problem(cp.Minimize(objective), constraints)
        solvers = [cfg.solver] if cfg.solver else ["CLARABEL", "ECOS", "OSQP", "SCS"]
        for solver in solvers:
            if solver is None or solver not in cp.installed_solvers():
                continue
            try:
                problem.solve(solver=solver, verbose=False)
                diagnostics.update(
                    {
                        "solver_name": solver,
                        "solver_status": str(problem.status),
                        "objective_value": float(problem.value) if problem.value is not None else np.nan,
                        "inaccurate_solution": problem.status == cp.OPTIMAL_INACCURATE,
                    }
                )
                if problem.status in {cp.OPTIMAL, cp.OPTIMAL_INACCURATE} and w.value is not None:
                    return _clean_weights(w.value), diagnostics
            except Exception as exc:
                diagnostics["failure_reason"] = str(exc)
        if not diagnostics["failure_reason"]:
            diagnostics["failure_reason"] = f"cvxpy status: {diagnostics['solver_status']}"
    else:
        diagnostics["failure_reason"] = "cvxpy unavailable"

    diagnostics["fallback_used"] = True
    diagnostics["inaccurate_solution"] = False
    weights, value, reason = _solve_scipy_fallback(sigma, mu, previous, target, cfg)
    diagnostics.update({"solver_name": "scipy_slsqp_fallback", "solver_status": reason, "objective_value": value})
    return weights, diagnostics


def _solve_scipy_fallback(
    sigma: np.ndarray,
    mu: np.ndarray,
    previous: np.ndarray,
    target: np.ndarray,
    cfg: ConvexRRPConfig,
) -> tuple[np.ndarray, float, str]:
    tc_rate = cfg.transaction_cost_bps / 10000.0 if cfg.use_transaction_cost_objective else 0.0

    def objective(w):
        turnover = np.abs(w - previous).sum()
        return (
            cfg.variance_penalty * float(w @ sigma @ w)
            + cfg.budget_penalty * float(((w - target) ** 2).sum())
            + cfg.turnover_penalty * turnover
            + cfg.transaction_cost_penalty * tc_rate * turnover
            - cfg.return_reward * float(mu @ w)
        )

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    if cfg.turnover_cap is not None:
        constraints.append({"type": "ineq", "fun": lambda w: cfg.turnover_cap - np.abs(w - previous).sum()})
    bounds = [(0.0, cfg.max_weight)] * len(previous)
    result = minimize(objective, previous, method="SLSQP", bounds=bounds, constraints=constraints, options={"maxiter": 1000, "ftol": 1e-9})
    if result.success:
        return _clean_weights(result.x), float(result.fun), "success"
    return previous, float(objective(previous)), str(result.message)


def _monthly_rebalance_dates(returns: pd.DataFrame) -> set[pd.Timestamp]:
    return set(returns.groupby(returns.index.to_period("M")).tail(1).index)


def run_convex_adaptive_backtest(
    returns: pd.DataFrame,
    config: ConvexRRPConfig | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cfg = config or ConvexRRPConfig()
    dates = pd.to_datetime(returns.index)
    returns = returns.copy()
    returns.index = dates
    rebalance_dates = _monthly_rebalance_dates(returns)
    n_assets = len(returns.columns)
    weights = np.zeros(n_assets)
    nav_gross = 1.0
    nav_net = 1.0
    regime_state: dict = {}
    rows = []
    solver_rows = []
    graph_rows = []
    regime_rows = []
    cost_rate = cfg.transaction_cost_bps / 10000.0

    for date in returns.index:
        turnover = 0.0
        is_rebalance = date in rebalance_dates
        if is_rebalance:
            window_full = returns[returns.index < date].iloc[-cfg.lookback_days:]
            active_cols = investable_columns(window_full, min_observations=min(60, cfg.lookback_days))
            window = window_full[active_cols]
            if len(window) >= 30 and len(active_cols) > 1:
                previous = weights.copy()
                previous_active = pd.Series(previous, index=returns.columns).reindex(active_cols).fillna(0.0).values
                graph = rolling_correlation_graph_features(window) if cfg.use_graph_features else {}
                if cfg.use_graph_features:
                    graph_rows.append({"date": date, **graph})
                if cfg.use_online_regime:
                    regime_state = online_regime_state(window, regime_state, graph, cfg.trading_days_per_year)
                else:
                    regime_state = {"regime_label": "medium_risk", "raw_stress_score": 0.0, "smoothed_stress_score": 0.0}
                budget = adaptive_budget_target(window, graph, regime_state["regime_label"])
                active_weights, diag = solve_convex_rrp(window, previous_active, cfg, budget, graph, regime_state["regime_label"])
                weights = expand_weights(active_weights, active_cols, returns.columns)
                turnover = float(np.abs(weights - previous).sum())
                solver_rows.append({"date": date, **diag})
                regime_rows.append({"date": date, **regime_state})

        daily_return = portfolio_return_for_available(returns.loc[date], weights)
        cost = cost_rate * turnover if is_rebalance else 0.0
        gross_return = daily_return
        net_return = daily_return - cost
        nav_gross *= 1.0 + gross_return
        nav_net *= 1.0 + net_return
        row = {
            "date": date,
            "portfolio_return": net_return,
            "gross_return": gross_return,
            "net_return": net_return,
            "transaction_cost": cost,
            "turnover": turnover,
            "is_rebalance_day": is_rebalance,
            "nav_gross": nav_gross,
            "nav_net": nav_net,
        }
        for i, asset in enumerate(returns.columns):
            row[f"weight_{asset}"] = weights[i]
        rows.append(row)

    solver_df = pd.DataFrame(solver_rows)
    total_rebalance = len(solver_df)
    inaccurate_count = int(solver_df["inaccurate_solution"].fillna(False).sum()) if "inaccurate_solution" in solver_df.columns else 0
    inaccurate_ratio = inaccurate_count / total_rebalance if total_rebalance else 0.0
    print(f"[Solver QA] inaccurate_count={inaccurate_count}, total_rebalance={total_rebalance}, inaccurate_ratio={inaccurate_ratio:.4f}")
    solver_df["inaccurate_ratio_overall"] = inaccurate_ratio

    return (
        pd.DataFrame(rows),
        solver_df,
        pd.DataFrame(graph_rows),
        pd.DataFrame(regime_rows),
    )
