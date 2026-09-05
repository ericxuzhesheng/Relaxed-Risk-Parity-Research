from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from src.adaptive_risk_budget import adaptive_budget_target, online_regime_state
from src.asset_graph_features import rolling_correlation_graph_features
from src.covariance_estimators import estimate_covariance
from src.investable import expand_weights, investable_columns, portfolio_return_for_available
from src.utils import infer_asset_class

logger = logging.getLogger(__name__)
VALID_IMPLEMENTATION_GROUPS = {
    "cash",
    "bond",
    "defensive",
    "commodity_gold",
    "equity",
}

try:
    import cvxpy as cp
except ImportError as exc:  # pragma: no cover - exercised when dependency is absent
    cp = None
    logger.warning(
        "cvxpy import failed (%s); convex solver path is disabled. Install cvxpy to enable "
        "Convex Adaptive RRP. Calls that require the solver will raise RuntimeError.",
        exc,
    )


def _require_cvxpy() -> None:
    """Raise a clear error if cvxpy is not importable.

    Call this from any code path that needs to construct a cvxpy problem. The
    historical behaviour of silently falling back to ``cp = None`` masked
    environment misconfiguration; raising here surfaces it at the first
    actual use rather than producing an obscure ``AttributeError`` deep
    inside the solver.
    """
    if cp is None:
        raise RuntimeError(
            "cvxpy is not installed in this environment. "
            "Run `pip install cvxpy` (and reinstall its solver backends) before using "
            "the Convex Adaptive RRP optimizer."
        )


@dataclass
class ConvexRRPConfig:
    trading_days_per_year: int = 243
    lookback_days: int = 240
    rebalance_frequency: str = "M"
    covariance_method: str = "ewma"
    covariance_allow_fallback: bool = True
    ewma_halflife: float = 60.0
    max_weight: float = 0.35
    turnover_cap: float | None = 0.35
    turnover_penalty: float = 0.02
    transaction_cost_bps: float = 3.0
    transaction_cost_penalty: float = 1.0
    # Public model: track an exact risk-budgeting reference, then impose
    # implementation constraints in a separate DCP-compliant convex program.
    # Expected-return and variance tilts default to zero.  Public candidates
    # optionally add a scale-normalized scenario-CVaR penalty.
    variance_penalty: float = 0.0
    budget_penalty: float = 0.35
    return_reward: float = 0.0
    cvar_penalty: float = 0.0
    cvar_beta: float = 0.95
    cvar_limit: float | None = None
    cvar_limit_multiplier: float | None = None
    min_cvar_observations: int = 60
    regime_stress_quantile: float = 0.67
    regime_crisis_prior: float = 0.40
    regime_prior_weight: float = 0.50
    use_graph_features: bool = False
    use_transaction_cost_objective: bool = False
    use_online_regime: bool = False
    group_bounds: dict[str, tuple[float, float]] = field(default_factory=dict)
    portfolio_vol_cap: float = 0.0
    portfolio_vol_cap_enabled: bool = False
    solver: str | None = None
    vol_target_enabled: bool = False
    vol_target: float = 0.040
    ema_deviation_enabled: bool = False
    ema_deviation_span: int = 20
    ema_strong_threshold: float = 0.05
    ema_overextended_threshold: float = 0.15
    ema_overextended_max_weight: float = 0.20
    ema_stop_threshold: float = -0.05
    ema_stop_max_weight: float = 0.05
    ema_equity_only: bool = True


def _clean_weights(weights: np.ndarray) -> np.ndarray:
    w = np.nan_to_num(np.asarray(weights, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
    w = np.clip(w, 0.0, None)
    total = float(w.sum())
    if total <= 0.0:
        return np.ones_like(w) / len(w)
    return w / total


def _portfolio_cvar(losses: np.ndarray, beta: float) -> float:
    values = np.asarray(losses, dtype=float)
    if values.size == 0:
        raise ValueError("CVaR requires at least one loss observation")
    quantile = float(np.quantile(values, beta))
    tail = values[values >= quantile]
    return float(tail.mean()) if tail.size else quantile


def solve_risk_budget_reference(
    covariance: np.ndarray,
    risk_budgets: np.ndarray,
    solver: str | None = None,
) -> tuple[np.ndarray, dict]:
    """Solve the convex log-barrier risk-budgeting problem.

    The first-order condition of

        minimize 0.5 x' Sigma x - sum_i b_i log(x_i)

    is x_i (Sigma x)_i = b_i.  Normalizing the positive solution therefore
    produces portfolio weights whose relative risk contributions match the
    requested budget shares.  This is the first stage of the model; real-world
    constraints are imposed by ``solve_convex_rrp`` in a second convex stage.
    """
    _require_cvxpy()
    sigma = np.asarray(covariance, dtype=float)
    budgets = _clean_weights(np.asarray(risk_budgets, dtype=float))
    if sigma.shape != (len(budgets), len(budgets)):
        raise ValueError("covariance and risk_budgets dimensions do not match")
    if np.any(budgets <= 0.0):
        raise ValueError("risk budgets must be strictly positive")
    if not np.isfinite(sigma).all():
        raise ValueError("covariance contains non-finite values")
    spectral_scale = max(
        float(np.linalg.eigvalsh(0.5 * (sigma + sigma.T)).max()), 1e-12
    )
    sigma_scaled = sigma / spectral_scale

    x = cp.Variable(len(budgets), pos=True)
    problem = cp.Problem(
        cp.Minimize(
            0.5 * cp.quad_form(x, cp.psd_wrap(sigma_scaled)) - budgets @ cp.log(x)
        )
    )
    if not problem.is_dcp():
        raise RuntimeError("risk-budget reference problem is not DCP compliant")

    solvers = [solver] if solver else ["CLARABEL", "ECOS", "SCS"]
    errors: list[str] = []
    for solver_name in solvers:
        if solver_name is None or solver_name not in cp.installed_solvers():
            continue
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="Solution may be inaccurate")
                problem.solve(solver=solver_name, verbose=False)
        except Exception as exc:
            errors.append(f"{solver_name}: {exc}")
            continue
        if problem.status == cp.OPTIMAL and x.value is not None:
            reference = _clean_weights(np.asarray(x.value, dtype=float))
            marginal = sigma @ reference
            contributions = reference * marginal
            contribution_total = float(contributions.sum())
            contribution_shares = contributions / contribution_total
            return reference, {
                "reference_solver_name": solver_name,
                "reference_solver_status": str(problem.status),
                "reference_problem_is_dcp": True,
                "reference_covariance_scale": spectral_scale,
                "reference_max_risk_budget_error": float(
                    np.max(np.abs(contribution_shares - budgets))
                ),
            }
        errors.append(f"{solver_name}: status={problem.status}")

    detail = "; ".join(errors) if errors else f"status={problem.status}"
    raise RuntimeError(f"risk-budget reference solve failed: {detail}")


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
    forced_turnover: float = 0.0,
) -> tuple[np.ndarray, dict]:
    """Solve the implementable second stage of the risk-budgeting model.

    Stage 1 constructs an exact unconstrained risk-budgeting reference with a
    convex log-barrier problem.  Stage 2 tracks that reference while imposing
    only DCP-valid constraints: simplex and box bounds, group bounds, turnover,
    portfolio variance, and scenario CVaR.  Public candidates leave expected
    return and variance tilts at zero; selected variants add a normalized CVaR
    penalty for tail-risk control.
    """
    _require_cvxpy()
    cfg = config or ConvexRRPConfig()
    n_assets = len(returns_window.columns)
    if n_assets == 0:
        raise ValueError("returns_window must contain at least one asset")
    if not 0.0 < cfg.cvar_beta < 1.0:
        raise ValueError("cvar_beta must lie strictly between zero and one")
    forced_turnover = max(float(forced_turnover), 0.0)
    has_previous = previous_weights is not None and (
        float(np.abs(np.asarray(previous_weights, dtype=float)).sum()) > 1e-12
        or forced_turnover > 1e-12
    )
    previous = (
        np.clip(np.nan_to_num(np.asarray(previous_weights, dtype=float)), 0.0, None)
        if previous_weights is not None
        else np.zeros(n_assets)
    )
    if previous.shape != (n_assets,):
        raise ValueError("previous_weights dimension does not match returns_window")
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
        regime_stress_quantile=cfg.regime_stress_quantile,
        regime_crisis_prior=cfg.regime_crisis_prior,
        regime_prior_weight=cfg.regime_prior_weight,
    )
    cov = cov_result.covariance
    sigma = cov.values
    mu = returns_window.mean().fillna(0.0).values * cfg.trading_days_per_year
    if budget_target is None:
        risk_budgets = adaptive_budget_target(returns_window, graph_features, regime_label).values
    else:
        risk_budgets = _clean_weights(np.asarray(budget_target, dtype=float))

    reference_solver = cfg.solver if cfg.solver in {"CLARABEL", "ECOS", "SCS"} else None
    reference, reference_diagnostics = solve_risk_budget_reference(
        sigma, risk_budgets, solver=reference_solver
    )

    diagnostics = {
        "solver_name": None,
        "solver_status": None,
        "objective_value": np.nan,
        "failure_reason": "",
        "fallback_used": False,
        "inaccurate_solution": False,
        **cov_result.diagnostics,
        **reference_diagnostics,
    }

    # --- EMA 乖离率动态上限 ---
    per_asset_max = np.full(n_assets, cfg.max_weight)
    ema_diag: dict = {
        "ema_insufficient_history": False,
        "ema_deviation_span": cfg.ema_deviation_span,
        "ema_valid_asset_count": 0,
    }
    if cfg.ema_deviation_enabled:
        from src.ema_deviation import compute_ema_deviation

        dev_series, ema_diag = compute_ema_deviation(returns_window, cfg.ema_deviation_span)
        if not ema_diag["ema_insufficient_history"]:
            for i, col in enumerate(returns_window.columns):
                if cfg.ema_equity_only and infer_asset_class(str(col)) != "equity":
                    continue
                dev = float(dev_series.get(col, 0.0))
                if dev > cfg.ema_overextended_threshold:
                    per_asset_max[i] = min(cfg.max_weight, cfg.ema_overextended_max_weight)
                elif dev < cfg.ema_stop_threshold:
                    per_asset_max[i] = min(cfg.max_weight, cfg.ema_stop_max_weight)
    diagnostics.update(ema_diag)
    if float(per_asset_max.sum()) < 1.0 - 1e-10:
        raise ValueError("infeasible box bounds: asset upper bounds sum to less than one")

    active_groups = {infer_asset_class(str(column)) for column in returns_window.columns}
    unknown_groups = sorted(set(cfg.group_bounds) - VALID_IMPLEMENTATION_GROUPS)
    if unknown_groups:
        raise ValueError("unknown implementation groups: " + ", ".join(unknown_groups))
    for group, (lower, upper) in cfg.group_bounds.items():
        if not 0.0 <= float(lower) <= float(upper) <= 1.0:
            raise ValueError("group bounds must satisfy 0 <= lower <= upper <= 1")
        if group not in active_groups and float(lower) > 0.0:
            raise ValueError(f"group {group!r} has a positive lower bound but no active assets")
    if sum(float(bounds[0]) for bounds in cfg.group_bounds.values()) > 1.0 + 1e-10:
        raise ValueError("group lower bounds sum to more than one")
    effective_group_bounds = dict(cfg.group_bounds)
    group_constraints = _group_constraints(returns_window.columns, effective_group_bounds)
    for idxs, (lower, _) in group_constraints:
        if float(per_asset_max[idxs].sum()) < float(lower) - 1e-10:
            raise ValueError("group lower bound exceeds the active assets' total capacity")
    group_asset_capacity: dict[str, float] = {}
    effective_upper: dict[str, float] = {}
    for group in active_groups:
        idxs = [
            index
            for index, column in enumerate(returns_window.columns)
            if infer_asset_class(str(column)) == group
        ]
        group_asset_capacity[group] = min(float(per_asset_max[idxs].sum()), 1.0)
        upper = float(cfg.group_bounds.get(group, (0.0, 1.0))[1])
        effective_upper[group] = min(upper, group_asset_capacity[group])
    group_capacity = sum(effective_upper.values())
    if group_capacity < 1.0 - 1e-10:
        missing_capacity = 1.0 - group_capacity
        available_slack = sum(
            group_asset_capacity[group] - effective_upper[group] for group in active_groups
        )
        if available_slack < missing_capacity - 1e-10:
            raise ValueError("combined asset and group upper bounds cannot fund the portfolio")
        for group in active_groups:
            slack = group_asset_capacity[group] - effective_upper[group]
            if slack <= 0.0:
                continue
            effective_upper[group] += missing_capacity * slack / available_slack
            lower = float(effective_group_bounds.get(group, (0.0, 1.0))[0])
            effective_group_bounds[group] = (lower, effective_upper[group])
        diagnostics["group_bounds_point_in_time_relaxed"] = True
        diagnostics["group_bounds_capacity_before_relaxation"] = group_capacity
    else:
        diagnostics["group_bounds_point_in_time_relaxed"] = False
        diagnostics["group_bounds_capacity_before_relaxation"] = group_capacity
    diagnostics["effective_group_upper_bounds"] = ";".join(
        f"{group}={effective_group_bounds.get(group, (0.0, 1.0))[1]:.8f}"
        for group in sorted(active_groups)
    )
    group_constraints = _group_constraints(returns_window.columns, effective_group_bounds)

    w = cp.Variable(n_assets)
    traded_amount = cp.norm1(w - previous) + forced_turnover if has_previous else cp.Constant(0.0)
    tc_rate = cfg.transaction_cost_bps / 10000.0
    objective = cfg.budget_penalty * cp.sum_squares(w - reference)
    if has_previous:
        objective += cfg.turnover_penalty * traded_amount
        if cfg.use_transaction_cost_objective:
            objective += cfg.transaction_cost_penalty * tc_rate * traded_amount

    # Optional research variants.  The public specification leaves these at
    # zero and expresses risk controls as constraints instead.
    reference_variance = max(float(reference @ sigma @ reference), 1e-12)
    if cfg.variance_penalty > 0.0:
        objective += cfg.variance_penalty * cp.quad_form(w, sigma) / reference_variance
    if cfg.return_reward > 0.0:
        return_scale = max(float(np.max(np.abs(mu))), 1e-4)
        objective -= cfg.return_reward * (mu @ w) / return_scale

    constraints = [w >= 0.0, cp.sum(w) == 1.0, w <= per_asset_max]
    if has_previous and cfg.turnover_cap is not None:
        constraints.append(traded_amount <= cfg.turnover_cap)
    for idxs, (lower, upper) in group_constraints:
        exposure = cp.sum(w[idxs])
        constraints.extend([exposure >= lower, exposure <= upper])
    if cfg.portfolio_vol_cap_enabled and cfg.portfolio_vol_cap > 0.0:
        constraints.append(cp.quad_form(w, sigma) <= cfg.portfolio_vol_cap**2)

    clean_scenarios = (
        returns_window.apply(pd.to_numeric, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .dropna(how="any")
    )
    diagnostics.update(
        {
            "cvar_effective_obs": int(len(clean_scenarios)),
            "cvar_total_obs": int(len(returns_window)),
            "cvar_scale": np.nan,
            "cvar_limit_effective": np.nan,
            "cvar_active": False,
            "cvar_inactive_reason": "not_requested",
        }
    )
    has_hard_cvar = cfg.cvar_limit is not None or cfg.cvar_limit_multiplier is not None
    needs_cvar = (
        cfg.cvar_penalty > 0.0
        or has_hard_cvar
    )
    effective_limit: float | None = None
    if needs_cvar:
        if len(clean_scenarios) < cfg.min_cvar_observations:
            if has_hard_cvar:
                raise ValueError(
                    "insufficient complete observations for hard CVaR constraint: "
                    f"{len(clean_scenarios)} < {cfg.min_cvar_observations}"
                )
            diagnostics["cvar_inactive_reason"] = "insufficient_complete_observations"
            needs_cvar = False
    if needs_cvar:
        diagnostics["cvar_active"] = True
        diagnostics["cvar_inactive_reason"] = ""
        eta = cp.Variable()
        excess_loss = cp.Variable(len(clean_scenarios), nonneg=True)
        scenario_losses = -clean_scenarios.values @ w
        constraints.append(excess_loss >= scenario_losses - eta)
        cvar = eta + cp.sum(excess_loss) / (
            (1.0 - cfg.cvar_beta) * len(clean_scenarios)
        )
        reference_cvar = _portfolio_cvar(
            -clean_scenarios.values @ reference, cfg.cvar_beta
        )
        equal_weight_cvar = _portfolio_cvar(
            -clean_scenarios.values @ (np.ones(n_assets) / n_assets),
            cfg.cvar_beta,
        )
        diagnostics["reference_cvar"] = reference_cvar
        diagnostics["cvar_scale"] = max(abs(equal_weight_cvar), 1e-4)
        if cfg.cvar_penalty > 0.0:
            cvar_scale = diagnostics["cvar_scale"]
            objective += cfg.cvar_penalty * cvar / cvar_scale
        effective_limit = cfg.cvar_limit
        if effective_limit is None and cfg.cvar_limit_multiplier is not None:
            effective_limit = max(reference_cvar, 1e-4) * cfg.cvar_limit_multiplier
        if effective_limit is not None:
            if effective_limit < 0.0:
                raise ValueError("cvar_limit must be nonnegative")
            constraints.append(cvar <= float(effective_limit))
            diagnostics["cvar_limit_effective"] = float(effective_limit)

    problem = cp.Problem(cp.Minimize(objective), constraints)
    diagnostics["problem_is_dcp"] = bool(problem.is_dcp())
    if not problem.is_dcp():
        raise RuntimeError("implementable risk-budgeting problem is not DCP compliant")

    solvers = [cfg.solver] if cfg.solver else ["CLARABEL", "ECOS", "OSQP", "SCS"]
    errors: list[str] = []
    for solver_name in solvers:
        if solver_name is None or solver_name not in cp.installed_solvers():
            continue
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="Solution may be inaccurate")
                problem.solve(solver=solver_name, verbose=False)
        except Exception as exc:
            errors.append(f"{solver_name}: {exc}")
            continue
        diagnostics.update(
            {
                "solver_name": solver_name,
                "solver_status": str(problem.status),
                "objective_value": float(problem.value) if problem.value is not None else np.nan,
                "inaccurate_solution": problem.status == cp.OPTIMAL_INACCURATE,
            }
        )
        if problem.status == cp.OPTIMAL and w.value is not None:
            weights = np.asarray(w.value, dtype=float)
            weights[np.abs(weights) < 1e-10] = 0.0
            if weights.min() < -1e-6 or abs(float(weights.sum()) - 1.0) > 1e-5:
                errors.append(f"{solver_name}: returned weights violate the simplex")
                continue
            weights = np.clip(weights, 0.0, None)
            weights /= weights.sum()
            if np.any(weights > per_asset_max + 1e-5):
                errors.append(f"{solver_name}: returned weights violate asset caps")
                continue
            final_turnover = (
                float(np.abs(weights - previous).sum()) + forced_turnover
                if has_previous
                else 0.0
            )
            predicted_vol = float(np.sqrt(max(weights @ sigma @ weights, 0.0)))
            final_contributions = weights * (sigma @ weights)
            contribution_total = float(final_contributions.sum())
            final_budget_error = (
                float(
                    np.max(
                        np.abs(final_contributions / contribution_total - risk_budgets)
                    )
                )
                if contribution_total > 1e-12
                else np.nan
            )
            violations = [
                abs(float(weights.sum()) - 1.0),
                max(0.0, -float(weights.min())),
                max(0.0, float(np.max(weights - per_asset_max))),
            ]
            for idxs, (lower, upper) in group_constraints:
                exposure = float(weights[idxs].sum())
                violations.extend(
                    [max(0.0, float(lower) - exposure), max(0.0, exposure - float(upper))]
                )
            if has_previous and cfg.turnover_cap is not None:
                violations.append(max(0.0, final_turnover - float(cfg.turnover_cap)))
            if cfg.portfolio_vol_cap_enabled and cfg.portfolio_vol_cap > 0.0:
                violations.append(max(0.0, predicted_vol - float(cfg.portfolio_vol_cap)))
            final_cvar = np.nan
            if needs_cvar:
                final_cvar = _portfolio_cvar(
                    -clean_scenarios.values @ weights, cfg.cvar_beta
                )
                if effective_limit is not None:
                    violations.append(max(0.0, final_cvar - float(effective_limit)))
            max_violation = float(max(violations))
            diagnostics.update(
                {
                    "final_turnover": final_turnover,
                    "predicted_volatility": predicted_vol,
                    "final_cvar": final_cvar,
                    "final_max_risk_budget_error": final_budget_error,
                    "reference_tracking_error": float(np.linalg.norm(weights - reference)),
                    "max_constraint_violation": max_violation,
                }
            )
            for group in sorted(active_groups):
                idxs = [
                    index
                    for index, column in enumerate(returns_window.columns)
                    if infer_asset_class(str(column)) == group
                ]
                diagnostics[f"group_exposure_{group}"] = float(weights[idxs].sum())
            if max_violation > 5e-5:
                errors.append(
                    f"{solver_name}: post-solve constraint violation {max_violation:.3e}"
                )
                continue
            return weights, diagnostics
        errors.append(f"{solver_name}: status={problem.status}")

    detail = "; ".join(errors) if errors else f"status={problem.status}"
    diagnostics["failure_reason"] = detail
    raise RuntimeError(f"implementable risk-budgeting solve failed: {detail}")


def rebalance_dates_for_frequency(
    returns: pd.DataFrame,
    frequency: str = "M",
) -> set[pd.Timestamp]:
    """Return last available trading dates for a fixed rebalance frequency."""
    if returns.empty:
        return set()
    dates = pd.to_datetime(returns.index)
    frame = pd.DataFrame(index=dates).sort_index()
    freq = frequency.upper()
    if freq in {"W", "WEEKLY"}:
        return set(frame.groupby(frame.index.to_period("W")).tail(1).index)
    if freq in {"2W", "BIWEEKLY", "BI-WEEKLY"}:
        weekly = list(frame.groupby(frame.index.to_period("W")).tail(1).index)
        return set(weekly[::2])
    if freq in {"M", "ME", "MONTHLY"}:
        return set(frame.groupby(frame.index.to_period("M")).tail(1).index)
    if freq in {"Q", "QE", "QUARTERLY"}:
        return set(frame.groupby(frame.index.to_period("Q")).tail(1).index)
    raise ValueError(
        "rebalance_frequency must be one of W, 2W, M, or Q "
        f"(got {frequency!r})"
    )


def _monthly_rebalance_dates(returns: pd.DataFrame) -> set[pd.Timestamp]:
    return rebalance_dates_for_frequency(returns, "M")


def drift_weights(weights: np.ndarray, asset_returns: pd.Series) -> np.ndarray:
    """Return self-financing end-of-day risky weights after returns accrue.

    Any residual ``1 - sum(weights)`` is treated as an implicit zero-return
    cash or financing position, so the calculation also supports overlays
    whose risky exposure differs from one.
    """
    current = np.clip(np.nan_to_num(np.asarray(weights, dtype=float)), 0.0, None)
    if float(current.sum()) <= 0.0:
        return current
    returns = (
        pd.to_numeric(asset_returns, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
        .values
    )
    portfolio_gross = float(1.0 + current @ returns)
    if portfolio_gross <= 0.0:
        raise ValueError("portfolio gross return is nonpositive; weights cannot be drifted")
    drifted = current * (1.0 + returns) / portfolio_gross
    drifted[np.abs(drifted) < 1e-15] = 0.0
    return drifted


def run_convex_adaptive_backtest(
    returns: pd.DataFrame,
    config: ConvexRRPConfig | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cfg = config or ConvexRRPConfig()
    dates = pd.to_datetime(returns.index)
    returns = returns.copy()
    returns.index = dates
    rebalance_dates = rebalance_dates_for_frequency(returns, cfg.rebalance_frequency)
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
            if (
                len(window) >= 30
                and len(active_cols) > 1
                and len(active_cols) * cfg.max_weight >= 1.0 - 1e-10
            ):
                previous = weights.copy()
                previous_active = pd.Series(previous, index=returns.columns).reindex(active_cols).fillna(0.0).values
                has_previous = float(np.abs(previous).sum()) > 1e-12
                inactive_mask = ~returns.columns.isin(active_cols)
                forced_turnover = float(np.abs(previous[inactive_mask]).sum()) if has_previous else 0.0
                graph = rolling_correlation_graph_features(window) if cfg.use_graph_features else {}
                if cfg.use_graph_features:
                    graph_rows.append({"date": date, **graph})
                if cfg.use_online_regime:
                    regime_state = online_regime_state(window, regime_state, graph, cfg.trading_days_per_year)
                else:
                    regime_state = {"regime_label": "medium_risk", "raw_stress_score": 0.0, "smoothed_stress_score": 0.0}
                budget = adaptive_budget_target(window, graph, regime_state["regime_label"])
                active_weights, diag = solve_convex_rrp(
                    window,
                    previous_active if has_previous else None,
                    cfg,
                    budget,
                    graph,
                    regime_state["regime_label"],
                    forced_turnover=forced_turnover,
                )
                weights = expand_weights(active_weights, active_cols, returns.columns)
                if cfg.vol_target_enabled:
                    from src.risk_overlay import RiskOverlayConfig as _OvCfg, vol_target_scale
                    _port_rets = pd.Series(
                        window_full.fillna(0.0).values @ weights,
                        index=window_full.index,
                    )
                    _scalar = vol_target_scale(
                        _port_rets,
                        _OvCfg(target_vol=cfg.vol_target, max_risk_scale=1.0),
                    )
                    weights = weights * _scalar
                turnover = float(np.abs(weights - previous).sum())
                solver_rows.append({"date": date, **diag})
                regime_rows.append({"date": date, **regime_state})

        # Fill any uninvested residual into 日利ETF so weights always sum to 100%.
        # Skip fill during warmup (all-zero weights) to avoid corrupting the optimizer's
        # previous-weight reference: _clean_weights normalises previous, so a 100%-in-日利ETF
        # warmup vector would force w_rili >= 82.5% while max_weight=0.35 → infeasible.
        _invested = float(np.abs(weights).sum())
        _rili_residual = 1.0 - _invested
        if _rili_residual > 1e-6 and _invested > 1e-6 and "日利ETF" in returns.columns:
            weights[returns.columns.get_loc("日利ETF")] += _rili_residual
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
        weights = drift_weights(weights, returns.loc[date])

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


def run_convex_adaptive_schedule_backtest(
    returns: pd.DataFrame,
    schedule: pd.DataFrame,
    candidate_configs: dict[str, ConvexRRPConfig],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run one continuous OOS path while candidate parameters change over time.

    Schedule boundaries force a rebalance from the public portfolio's actual
    prior weights, so parameter changes incur their full transaction cost.
    Candidate selection itself is performed separately using completed
    validation windows only.
    """
    required = {"test_start", "test_end", "selected_candidate_id"}
    missing = required.difference(schedule.columns)
    if missing:
        raise ValueError(f"schedule missing columns: {sorted(missing)}")
    if schedule.empty:
        raise ValueError("schedule is empty")

    data = returns.copy()
    data.index = pd.to_datetime(data.index)
    data = data.sort_index()
    planned = schedule.copy().sort_values("test_start").reset_index(drop=True)
    planned["test_start"] = pd.to_datetime(planned["test_start"])
    planned["test_end"] = pd.to_datetime(planned["test_end"])
    unknown = sorted(set(planned["selected_candidate_id"]) - set(candidate_configs))
    if unknown:
        raise ValueError(f"schedule references unknown candidates: {unknown}")

    output_start = pd.Timestamp(planned["test_start"].min())
    output_end = pd.Timestamp(planned["test_end"].max())
    output_index = data.index[(data.index >= output_start) & (data.index <= output_end)]
    assignment = pd.Series(index=output_index, dtype="object")
    for row in planned.itertuples(index=False):
        mask = (assignment.index >= row.test_start) & (assignment.index <= row.test_end)
        if assignment.loc[mask].notna().any():
            raise ValueError("schedule test windows overlap")
        assignment.loc[mask] = row.selected_candidate_id
    if assignment.isna().any():
        raise ValueError("schedule does not continuously cover the OOS trading index")

    candidate_switch_dates = set(pd.DatetimeIndex(planned["test_start"]))
    # The evaluation inception needs one initial allocation.  Later parameter
    # changes preserve the existing holdings until the normal monthly
    # rebalance, so the public strategy does not add quarterly trades.
    forced_rebalances = {output_start}
    frequencies = {cfg.rebalance_frequency for cfg in candidate_configs.values()}
    rebalance_by_frequency = {
        frequency: rebalance_dates_for_frequency(data.loc[output_index], frequency)
        for frequency in frequencies
    }
    n_assets = len(data.columns)
    weights = np.zeros(n_assets)
    nav_gross = 1.0
    nav_net = 1.0
    regime_state: dict = {}
    rows: list[dict[str, object]] = []
    solver_rows: list[dict[str, object]] = []
    graph_rows: list[dict[str, object]] = []
    regime_rows: list[dict[str, object]] = []

    for date in output_index:
        candidate_id = str(assignment.loc[date])
        cfg = candidate_configs[candidate_id]
        is_rebalance = date in forced_rebalances or date in rebalance_by_frequency[cfg.rebalance_frequency]
        turnover = 0.0
        if is_rebalance:
            window_full = data[data.index < date].iloc[-cfg.lookback_days:]
            active_cols = investable_columns(window_full, min_observations=min(60, cfg.lookback_days))
            window = window_full[active_cols]
            if (
                len(window) >= 30
                and len(active_cols) > 1
                and len(active_cols) * cfg.max_weight >= 1.0 - 1e-10
            ):
                previous = weights.copy()
                previous_active = pd.Series(previous, index=data.columns).reindex(active_cols).fillna(0.0).values
                has_previous = float(np.abs(previous).sum()) > 1e-12
                inactive_mask = ~data.columns.isin(active_cols)
                forced_turnover = float(np.abs(previous[inactive_mask]).sum()) if has_previous else 0.0
                graph = rolling_correlation_graph_features(window) if cfg.use_graph_features else {}
                if cfg.use_graph_features:
                    graph_rows.append({"date": date, "selected_candidate_id": candidate_id, **graph})
                if cfg.use_online_regime:
                    regime_state = online_regime_state(window, regime_state, graph, cfg.trading_days_per_year)
                else:
                    regime_state = {
                        "regime_label": "medium_risk",
                        "raw_stress_score": 0.0,
                        "smoothed_stress_score": 0.0,
                    }
                budget = adaptive_budget_target(window, graph, regime_state["regime_label"])
                active_weights, diag = solve_convex_rrp(
                    window,
                    previous_active if has_previous else None,
                    cfg,
                    budget,
                    graph,
                    regime_state["regime_label"],
                    forced_turnover=forced_turnover,
                )
                weights = expand_weights(active_weights, active_cols, data.columns)
                if cfg.vol_target_enabled:
                    from src.risk_overlay import RiskOverlayConfig as _OvCfg, vol_target_scale

                    portfolio_history = pd.Series(
                        window_full.fillna(0.0).values @ weights,
                        index=window_full.index,
                    )
                    scalar = vol_target_scale(
                        portfolio_history,
                        _OvCfg(target_vol=cfg.vol_target, max_risk_scale=1.0),
                    )
                    weights = weights * scalar
                turnover = float(np.abs(weights - previous).sum())
                solver_rows.append({"date": date, "selected_candidate_id": candidate_id, **diag})
                regime_rows.append({"date": date, "selected_candidate_id": candidate_id, **regime_state})

        invested = float(np.abs(weights).sum())
        residual = 1.0 - invested
        if residual > 1e-6 and invested > 1e-6 and "日利ETF" in data.columns:
            weights[data.columns.get_loc("日利ETF")] += residual
        gross_return = portfolio_return_for_available(data.loc[date], weights)
        transaction_cost = cfg.transaction_cost_bps / 10000.0 * turnover if is_rebalance else 0.0
        net_return = gross_return - transaction_cost
        nav_gross *= 1.0 + gross_return
        nav_net *= 1.0 + net_return
        result_row: dict[str, object] = {
            "date": date,
            "selected_candidate_id": candidate_id,
            "portfolio_return": net_return,
            "gross_return": gross_return,
            "net_return": net_return,
            "transaction_cost": transaction_cost,
            "turnover": turnover,
            "is_rebalance_day": is_rebalance,
            "is_candidate_switch_day": date in candidate_switch_dates,
            "nav_gross": nav_gross,
            "nav_net": nav_net,
        }
        for position, asset in enumerate(data.columns):
            result_row[f"weight_{asset}"] = weights[position]
        rows.append(result_row)
        weights = drift_weights(weights, data.loc[date])

    solver_df = pd.DataFrame(solver_rows)
    if not solver_df.empty:
        inaccurate = (
            solver_df["inaccurate_solution"].fillna(False)
            if "inaccurate_solution" in solver_df
            else pd.Series(False, index=solver_df.index)
        )
        inaccurate_count = int(inaccurate.sum())
        inaccurate_ratio = inaccurate_count / len(solver_df)
        solver_df["inaccurate_ratio_overall"] = inaccurate_ratio
        print(
            f"[Scheduled Solver QA] inaccurate_count={inaccurate_count}, "
            f"total_rebalance={len(solver_df)}, inaccurate_ratio={inaccurate_ratio:.4f}"
        )
    return pd.DataFrame(rows), solver_df, pd.DataFrame(graph_rows), pd.DataFrame(regime_rows)
