"""DCP-compliant risk-parity and relaxed risk-parity solvers.

The public API is retained for the backtest pipeline, but the former SLSQP
programs have been replaced by convex formulations. Standard risk parity is
obtained from the log-barrier risk-budgeting problem. Relaxed RRP uses a
second convex program that trades reference tracking, portfolio variance and
a soft expected-return shortfall. Bond leverage is represented by a separate
exposure vector, so no weight-times-leverage product enters the optimization.

All programs are checked for DCP compliance and fail closed. A failed solve
therefore cannot silently replace a model portfolio with equal weights.
"""

from __future__ import annotations

from typing import Tuple
import warnings

import cvxpy as cp
import numpy as np

from src.convex_adaptive_rrp import solve_risk_budget_reference


_SOLVERS = ("CLARABEL", "ECOS", "SCS")


def _record(target: dict | None, payload: dict) -> None:
    if target is not None:
        target.clear()
        target.update(payload)


def _validated_covariance(Sigma: np.ndarray, n_assets: int) -> tuple[np.ndarray, float]:
    sigma = np.asarray(Sigma, dtype=float)
    if sigma.shape != (n_assets, n_assets):
        raise ValueError("covariance dimensions do not match n_assets")
    if not np.isfinite(sigma).all():
        raise ValueError("covariance contains non-finite values")
    sigma = 0.5 * (sigma + sigma.T)
    eigenvalues, eigenvectors = np.linalg.eigh(sigma)
    scale = max(
        float(np.max(np.abs(eigenvalues))),
        float(np.max(np.diag(sigma))),
        1e-12,
    )
    if float(eigenvalues.min()) < -1e-8 * scale:
        raise ValueError("covariance is not positive semidefinite")
    floor = max(scale * 1e-6, 1e-12)
    clipped = np.maximum(eigenvalues, floor)
    adjustment = float(np.max(clipped - eigenvalues))
    sigma_psd = (eigenvectors * clipped) @ eigenvectors.T
    return 0.5 * (sigma_psd + sigma_psd.T), adjustment


def _validated_bounds(config: dict, n_assets: int) -> tuple[float, float]:
    lower, upper = config.get("asset_weight_bounds", (0.0, 1.0))
    lower, upper = float(lower), float(upper)
    if lower < 0.0 or upper <= lower:
        raise ValueError("asset_weight_bounds must satisfy 0 <= lower < upper")
    if n_assets * lower > 1.0 + 1e-10 or n_assets * upper < 1.0 - 1e-10:
        raise ValueError("asset_weight_bounds are incompatible with the simplex")
    return lower, upper


def _solve(problem: cp.Problem, variables: tuple[cp.Variable, ...]) -> tuple[str, str]:
    if not problem.is_dcp():
        raise RuntimeError("risk-parity optimization is not DCP compliant")
    errors: list[str] = []
    installed = set(cp.installed_solvers())
    for solver_name in _SOLVERS:
        if solver_name not in installed:
            continue
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="Solution may be inaccurate")
                problem.solve(solver=solver_name, verbose=False)
        except Exception as exc:
            errors.append(f"{solver_name}: {exc}")
            continue
        if problem.status == cp.OPTIMAL and all(
            variable.value is not None for variable in variables
        ):
            return solver_name, str(problem.status)
        errors.append(f"{solver_name}: status={problem.status}")
    detail = "; ".join(errors) if errors else "no supported convex solver is installed"
    raise RuntimeError(f"risk-parity optimization failed: {detail}")


def _risk_budget_error(weights: np.ndarray, sigma: np.ndarray) -> float:
    contributions = weights * (sigma @ weights)
    total = float(contributions.sum())
    if total <= 0.0:
        return float("nan")
    return float(np.max(np.abs(contributions / total - 1.0 / len(weights))))


def _reference_with_bounds(
    sigma: np.ndarray,
    n_assets: int,
    config: dict,
) -> tuple[np.ndarray, dict]:
    reference, reference_diag = solve_risk_budget_reference(
        sigma, np.ones(n_assets) / n_assets
    )
    lower, upper = _validated_bounds(config, n_assets)
    if reference.min() >= lower - 1e-10 and reference.max() <= upper + 1e-10:
        return reference, reference_diag

    weights = cp.Variable(n_assets)
    problem = cp.Problem(
        cp.Minimize(cp.sum_squares(weights - reference)),
        [cp.sum(weights) == 1.0, weights >= lower, weights <= upper],
    )
    solver_name, status = _solve(problem, (weights,))
    bounded = np.asarray(weights.value, dtype=float).reshape(-1)
    bounded = np.clip(bounded, lower, upper)
    bounded /= bounded.sum()
    reference_diag.update(
        {
            "reference_projection_solver_name": solver_name,
            "reference_projection_solver_status": status,
        }
    )
    return bounded, reference_diag


def solve_standard_rp(
    Sigma: np.ndarray,
    n_assets: int,
    config: dict,
    diagnostics: dict | None = None,
) -> np.ndarray:
    """Return the bounded equal-risk-budget portfolio from a convex program."""
    sigma, psd_adjustment = _validated_covariance(Sigma, n_assets)
    weights, reference_diag = _reference_with_bounds(sigma, n_assets, config)
    payload = {
        "solver_name": reference_diag["reference_solver_name"],
        "solver_success": True,
        "solver_status": reference_diag["reference_solver_status"],
        "solver_message": "optimal convex log-barrier risk-budget solution",
        "objective_value": float("nan"),
        "problem_is_dcp": True,
        "fallback_used": False,
        "fallback_method": "",
        "exception_type": "",
        "exception_message": "",
        "covariance_psd_adjustment": psd_adjustment,
        "max_risk_budget_error": _risk_budget_error(weights, sigma),
        **reference_diag,
    }
    _record(diagnostics, payload)
    return weights


def _solve_relaxed_exposure(
    sigma: np.ndarray,
    mu: np.ndarray,
    n_assets: int,
    bond_indices: list[int],
    R_base: float,
    is_relaxed: bool,
    config: dict,
    diagnostics: dict | None,
) -> tuple[np.ndarray, np.ndarray]:
    sigma, psd_adjustment = _validated_covariance(sigma, n_assets)
    expected_returns = np.asarray(mu, dtype=float).reshape(-1)
    if expected_returns.shape != (n_assets,) or not np.isfinite(expected_returns).all():
        raise ValueError("mu must be a finite vector with n_assets entries")
    lower, upper = _validated_bounds(config, n_assets)
    bond_set = {int(i) for i in bond_indices}
    if any(i < 0 or i >= n_assets for i in bond_set):
        raise ValueError("bond_indices contains an out-of-range index")
    leverage_upper = float(config.get("bond_leverage_upper", 1.0))
    if leverage_upper < 1.0:
        raise ValueError("bond_leverage_upper must be at least one")

    reference, reference_diag = _reference_with_bounds(sigma, n_assets, config)
    weights = cp.Variable(n_assets)
    exposure = cp.Variable(n_assets)
    constraints = [
        cp.sum(weights) == 1.0,
        weights >= lower,
        weights <= upper,
        exposure >= 0.0,
    ]
    for i in range(n_assets):
        if i in bond_set:
            constraints.extend([exposure[i] >= weights[i], exposure[i] <= leverage_upper * weights[i]])
        else:
            constraints.append(exposure[i] == weights[i])

    reference_variance = max(float(reference @ sigma @ reference), 1e-12)
    objective_terms = [cp.sum_squares(weights - reference)]
    target_return = float(config.get("m", 1.0)) * max(float(R_base), 0.0)
    return_scale = max(abs(target_return), float(np.max(np.abs(expected_returns))), 1e-3)
    if is_relaxed:
        variance_penalty = float(config.get("rrp_variance_penalty", 0.10))
        shortfall_penalty = float(config.get("lambda_pen", 1.9))
        leverage_penalty = float(config.get("rrp_leverage_penalty", 0.02))
        if min(variance_penalty, shortfall_penalty, leverage_penalty) < 0.0:
            raise ValueError("convex RRP penalty coefficients must be nonnegative")
        objective_terms.extend(
            [
                variance_penalty * cp.quad_form(exposure, cp.psd_wrap(sigma)) / reference_variance,
                shortfall_penalty
                * cp.square(cp.pos((target_return - expected_returns @ exposure) / return_scale)),
                leverage_penalty * cp.sum_squares(exposure - weights),
            ]
        )
    else:
        target_return = float("nan")
        objective_terms.append(cp.sum_squares(exposure - weights))

    problem = cp.Problem(cp.Minimize(sum(objective_terms)), constraints)
    solver_name, status = _solve(problem, (weights, exposure))
    base = np.asarray(weights.value, dtype=float).reshape(-1)
    active = np.asarray(exposure.value, dtype=float).reshape(-1)
    base[np.abs(base) < 1e-10] = 0.0
    active[np.abs(active) < 1e-10] = 0.0
    base = np.clip(base, lower, upper)
    base /= base.sum()
    active = np.maximum(active, 0.0)
    leverage = np.ones(n_assets)
    for i in bond_set:
        leverage[i] = active[i] / base[i] if base[i] > 1e-10 else 1.0
    reconstructed = base * leverage
    constraint_violation = max(
        abs(float(base.sum()) - 1.0),
        max(float(lower - base.min()), 0.0),
        max(float(base.max() - upper), 0.0),
        float(np.max(np.abs(reconstructed - active))),
    )
    predicted_return = float(expected_returns @ active)
    payload = {
        "solver_name": solver_name,
        "solver_success": True,
        "solver_status": status,
        "solver_message": "optimal DCP-compliant convex RRP solution",
        "objective_value": float(problem.value),
        "problem_is_dcp": True,
        "fallback_used": False,
        "fallback_method": "",
        "exception_type": "",
        "exception_message": "",
        "covariance_psd_adjustment": psd_adjustment,
        "reference_max_risk_budget_error": _risk_budget_error(reference, sigma),
        "final_max_risk_budget_error": _risk_budget_error(base, sigma),
        "predicted_annual_return": predicted_return,
        "target_annual_return": target_return,
        "return_shortfall": max(target_return - predicted_return, 0.0) if is_relaxed else 0.0,
        "predicted_annual_volatility": float(np.sqrt(max(active @ sigma @ active, 0.0))),
        "gross_exposure": float(active.sum()),
        "max_constraint_violation": constraint_violation,
        **reference_diag,
    }
    _record(diagnostics, payload)
    if constraint_violation > 1e-6:
        raise RuntimeError(f"convex RRP solution violates constraints by {constraint_violation:.3e}")
    return base, leverage


def solve_relaxed_rp(
    Sigma: np.ndarray,
    mu: np.ndarray,
    Theta: np.ndarray,
    n_assets: int,
    R_base: float,
    config: dict,
    diagnostics: dict | None = None,
) -> np.ndarray:
    """Solve the unlevered convex Global RRP program.

    ``Theta`` is retained for API compatibility. The convex formulation uses
    the full covariance matrix directly and returns the active exposure.
    """
    del Theta
    weights, leverage = _solve_relaxed_exposure(
        Sigma, mu, n_assets, [], R_base, True, config, diagnostics
    )
    return weights * leverage


def optimize_with_leverage(
    Sigma: np.ndarray,
    n_assets: int,
    bond_indices: list,
    mu: np.ndarray | None = None,
    Theta: np.ndarray | None = None,
    R_base: float = 0,
    is_relaxed: bool = False,
    config: dict | None = None,
    diagnostics: dict | None = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """Solve the convex exposure formulation and recover bond leverage ratios."""
    del Theta
    cfg = config or {}
    expected_returns = np.zeros(n_assets) if mu is None else np.asarray(mu, dtype=float)
    return _solve_relaxed_exposure(
        Sigma,
        expected_returns,
        n_assets,
        list(bond_indices),
        R_base,
        is_relaxed,
        cfg,
        diagnostics,
    )
