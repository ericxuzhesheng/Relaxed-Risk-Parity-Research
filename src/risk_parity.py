"""SLSQP-based risk-parity solvers with explicit diagnostics.

This module exposes the legacy ``solve_standard_rp``/``solve_relaxed_rp``/
``optimize_with_leverage`` API used by ``src.backtest`` and the dynamic-selection
pipeline. It previously hid SLSQP failures behind ``except: pass`` and silently
fell back to equal weights. The implementation below preserves the original
calling convention (callers still receive a weight array) but records the
solver state — exception info, convergence status, message, objective value,
and whether a fallback was used — into an optional ``diagnostics`` dict.

The diagnostics dict is the recommended channel for surfacing solver failures
into ``results/tables/`` artifacts. When ``diagnostics`` is ``None`` the
solver still logs a ``logging.WARNING`` so silent failures never go unnoticed.
"""

from __future__ import annotations

import logging
from typing import Tuple

import numpy as np
from scipy.optimize import minimize


logger = logging.getLogger(__name__)


_EMPTY_DIAG = {
    "solver_name": "scipy_slsqp",
    "solver_success": False,
    "solver_status": None,
    "solver_message": "",
    "objective_value": float("nan"),
    "fallback_used": False,
    "fallback_method": "",
    "exception_type": "",
    "exception_message": "",
}


def _new_diag() -> dict:
    return dict(_EMPTY_DIAG)


def _record(target: dict | None, payload: dict) -> None:
    """Merge ``payload`` into the user-supplied diagnostics dict, if any."""
    if target is None:
        return
    target.update(payload)


def _record_failure(
    target: dict | None,
    *,
    function: str,
    fallback_method: str,
    solver_status: int | None = None,
    solver_message: str = "",
    objective_value: float = float("nan"),
    exception: BaseException | None = None,
) -> None:
    payload = {
        "solver_name": "scipy_slsqp",
        "solver_success": False,
        "solver_status": solver_status,
        "solver_message": solver_message,
        "objective_value": objective_value,
        "fallback_used": True,
        "fallback_method": fallback_method,
        "exception_type": type(exception).__name__ if exception is not None else "",
        "exception_message": str(exception) if exception is not None else "",
    }
    _record(target, payload)
    if exception is not None:
        logger.warning(
            "%s: SLSQP raised %s (%s); using fallback=%s",
            function,
            payload["exception_type"],
            payload["exception_message"],
            fallback_method,
        )
    else:
        logger.warning(
            "%s: SLSQP did not converge (status=%s, message=%s); using fallback=%s",
            function,
            solver_status,
            solver_message,
            fallback_method,
        )


def _record_success(
    target: dict | None,
    *,
    solver_status: int,
    solver_message: str,
    objective_value: float,
) -> None:
    _record(
        target,
        {
            "solver_name": "scipy_slsqp",
            "solver_success": True,
            "solver_status": solver_status,
            "solver_message": solver_message,
            "objective_value": objective_value,
            "fallback_used": False,
            "fallback_method": "",
            "exception_type": "",
            "exception_message": "",
        },
    )


def solve_standard_rp(
    Sigma: np.ndarray,
    n_assets: int,
    config: dict,
    diagnostics: dict | None = None,
) -> np.ndarray:
    """Solve the standard relaxed risk-parity LP-style program via SLSQP.

    Returns the asset weight vector. On solver failure, returns equal weights
    and records the failure in ``diagnostics`` (if provided)."""
    if diagnostics is not None:
        _record(diagnostics, _new_diag())

    x0 = np.ones(n_assets) / n_assets
    zeta0 = Sigma @ x0
    sigma0 = np.sqrt(x0 @ Sigma @ x0)
    psi0 = sigma0 / np.sqrt(n_assets)
    gamma0 = np.min(x0 * zeta0)
    v0 = np.concatenate((x0, zeta0, [psi0, gamma0]))

    def objective(v):
        return v[2 * n_assets] - v[2 * n_assets + 1]

    def eq_constraints(v):
        x, zeta = v[:n_assets], v[n_assets : 2 * n_assets]
        return np.concatenate([zeta - Sigma @ x, [np.sum(x) - 1]])

    def ineq_constraints(v):
        x, zeta = v[:n_assets], v[n_assets : 2 * n_assets]
        psi, gamma = v[2 * n_assets], v[2 * n_assets + 1]
        return np.concatenate([x * zeta - gamma**2, [n_assets * psi**2 - x @ Sigma @ x]])

    bounds = (
        [config["asset_weight_bounds"]] * n_assets
        + [(0, None)] * n_assets
        + [(0, 10), (0, 10)]
    )

    try:
        res = minimize(
            objective,
            v0,
            method="SLSQP",
            constraints=[
                {"type": "eq", "fun": eq_constraints},
                {"type": "ineq", "fun": ineq_constraints},
            ],
            bounds=bounds,
            options={"ftol": config["optim_tol"], "maxiter": config["optim_maxiter"]},
        )
    except (ValueError, np.linalg.LinAlgError, RuntimeError) as exc:
        _record_failure(
            diagnostics,
            function="solve_standard_rp",
            fallback_method="equal_weight",
            exception=exc,
        )
        return np.ones(n_assets) / n_assets

    if res.success:
        _record_success(
            diagnostics,
            solver_status=int(res.status),
            solver_message=str(res.message),
            objective_value=float(res.fun),
        )
        return res.x[:n_assets]

    _record_failure(
        diagnostics,
        function="solve_standard_rp",
        fallback_method="equal_weight",
        solver_status=int(res.status),
        solver_message=str(res.message),
        objective_value=float(res.fun),
    )
    return np.ones(n_assets) / n_assets


def solve_relaxed_rp(
    Sigma: np.ndarray,
    mu: np.ndarray,
    Theta: np.ndarray,
    n_assets: int,
    R_base: float,
    config: dict,
    diagnostics: dict | None = None,
) -> np.ndarray:
    """Solve the relaxed risk-parity (Model C) program.

    On SLSQP failure the fallback is the standard RP solution (already a
    feasible point of the relaxed program); this is preferred over equal
    weights because it preserves the risk-budget anchor.
    """
    if diagnostics is not None:
        _record(diagnostics, _new_diag())

    rp_diag = _new_diag()
    x_rp = solve_standard_rp(Sigma, n_assets, config, diagnostics=rp_diag)
    zeta0 = Sigma @ x_rp
    sigma0 = np.sqrt(x_rp @ Sigma @ x_rp)
    psi0 = sigma0 / np.sqrt(n_assets)
    gamma0 = np.min(x_rp * zeta0)
    rho0 = 0.1
    v0 = np.concatenate((x_rp, zeta0, [psi0, gamma0, rho0]))

    R_target = config["m"] * max(R_base, 0)

    def objective(v):
        return v[2 * n_assets] - v[2 * n_assets + 1]

    def eq_constraints(v):
        x, zeta = v[:n_assets], v[n_assets : 2 * n_assets]
        return np.concatenate([zeta - Sigma @ x, [np.sum(x) - 1]])

    def ineq_constraints(v):
        x, zeta = v[:n_assets], v[n_assets : 2 * n_assets]
        psi, gamma, rho = (
            v[2 * n_assets],
            v[2 * n_assets + 1],
            v[2 * n_assets + 2],
        )
        con1 = x * zeta - gamma**2
        con2 = rho**2 - config["lambda_pen"] * (x @ Theta @ x)
        con3 = n_assets * (psi**2 - rho**2) - x @ Sigma @ x
        con4 = mu @ x - R_target
        return np.concatenate([con1, [con2, con3, con4]])

    bounds = (
        [config["asset_weight_bounds"]] * n_assets
        + [(0, None)] * n_assets
        + [(0, 10)] * 3
    )

    try:
        res = minimize(
            objective,
            v0,
            method="SLSQP",
            constraints=[
                {"type": "eq", "fun": eq_constraints},
                {"type": "ineq", "fun": ineq_constraints},
            ],
            bounds=bounds,
            options={"ftol": config["optim_tol"], "maxiter": config["optim_maxiter"]},
        )
    except (ValueError, np.linalg.LinAlgError, RuntimeError) as exc:
        _record_failure(
            diagnostics,
            function="solve_relaxed_rp",
            fallback_method="standard_rp_solution",
            exception=exc,
        )
        return x_rp

    if res.success:
        _record_success(
            diagnostics,
            solver_status=int(res.status),
            solver_message=str(res.message),
            objective_value=float(res.fun),
        )
        return res.x[:n_assets]

    _record_failure(
        diagnostics,
        function="solve_relaxed_rp",
        fallback_method="standard_rp_solution",
        solver_status=int(res.status),
        solver_message=str(res.message),
        objective_value=float(res.fun),
    )
    return x_rp


def optimize_with_leverage(
    Sigma: np.ndarray,
    n_assets: int,
    bond_indices: list,
    mu: np.ndarray = None,
    Theta: np.ndarray = None,
    R_base: float = 0,
    is_relaxed: bool = False,
    config: dict = None,
    diagnostics: dict | None = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """SLSQP optimizer with bond leverage variables.

    On failure returns ``(equal_weights, unit_leverage)`` and records the
    failure in ``diagnostics`` (if provided).
    """
    if diagnostics is not None:
        _record(diagnostics, _new_diag())

    l_max = config["bond_leverage_upper"]
    n_bonds = len(bond_indices)
    x0 = np.ones(n_assets) / n_assets
    lev_init = np.ones(n_assets)
    bond_lev0 = lev_init[bond_indices]
    lx0 = x0 * lev_init
    zeta0 = Sigma @ lx0
    psi0 = np.sqrt(lx0 @ Sigma @ lx0) / np.sqrt(n_assets)
    gamma0 = np.min(x0 * zeta0)
    rho0 = [0.1] if is_relaxed else []
    v0 = np.concatenate((x0, zeta0, [psi0, gamma0], rho0, bond_lev0))

    def objective(v):
        return v[2 * n_assets] - v[2 * n_assets + 1]

    def get_leverage(v):
        lev = np.ones(n_assets)
        idx = 2 * n_assets + (3 if is_relaxed else 2)
        lev[bond_indices] = v[idx:]
        return lev

    def eq_constraints(v):
        x, zeta = v[:n_assets], v[n_assets : 2 * n_assets]
        lev = get_leverage(v)
        return np.concatenate([zeta - Sigma @ (x * lev), [np.sum(x) - 1]])

    def ineq_constraints(v):
        x, zeta = v[:n_assets], v[n_assets : 2 * n_assets]
        psi, gamma = v[2 * n_assets], v[2 * n_assets + 1]
        lev = get_leverage(v)
        lx = x * lev
        con1 = x * zeta - gamma**2
        con2 = n_assets * psi**2 - lx @ Sigma @ lx
        idx_lev = 2 * n_assets + (3 if is_relaxed else 2)
        bond_lev = v[idx_lev:]
        cons = [con1, [con2], bond_lev - 1.0, l_max - bond_lev]
        if is_relaxed:
            rho = v[2 * n_assets + 2]
            R_target = config["m"] * max(R_base, 0)
            con_rho = rho**2 - config["lambda_pen"] * (x @ Theta @ x)
            cons[1] = [
                con_rho,
                n_assets * (psi**2 - rho**2) - lx @ Sigma @ lx,
                mu @ lx - R_target,
            ]
        return np.concatenate(cons)

    bounds = (
        [config["asset_weight_bounds"]] * n_assets
        + [(0, None)] * n_assets
        + [(0, 10)] * (3 if is_relaxed else 2)
        + [(1.0, l_max)] * n_bonds
    )

    try:
        res = minimize(
            objective,
            v0,
            method="SLSQP",
            constraints=[
                {"type": "eq", "fun": eq_constraints},
                {"type": "ineq", "fun": ineq_constraints},
            ],
            bounds=bounds,
            options={"ftol": config["optim_tol"], "maxiter": config["optim_maxiter"]},
        )
    except (ValueError, np.linalg.LinAlgError, RuntimeError) as exc:
        _record_failure(
            diagnostics,
            function="optimize_with_leverage",
            fallback_method="equal_weight_unit_leverage",
            exception=exc,
        )
        return np.ones(n_assets) / n_assets, np.ones(n_assets)

    if res.success:
        x_opt = res.x[:n_assets]
        lev_opt = np.ones(n_assets)
        idx = 2 * n_assets + (3 if is_relaxed else 2)
        lev_opt[bond_indices] = res.x[idx:]
        _record_success(
            diagnostics,
            solver_status=int(res.status),
            solver_message=str(res.message),
            objective_value=float(res.fun),
        )
        return x_opt, lev_opt

    _record_failure(
        diagnostics,
        function="optimize_with_leverage",
        fallback_method="equal_weight_unit_leverage",
        solver_status=int(res.status),
        solver_message=str(res.message),
        objective_value=float(res.fun),
    )
    return np.ones(n_assets) / n_assets, np.ones(n_assets)
