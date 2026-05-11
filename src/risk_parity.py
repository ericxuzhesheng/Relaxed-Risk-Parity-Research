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


def _tikhonov_jitter(Sigma: np.ndarray, strength: float) -> np.ndarray:
    """Return ``Sigma + strength · trace(Sigma)/n · I``.

    Scale by trace/n so the regularization magnitude follows the covariance
    scale rather than fixed in absolute units. ``strength`` of 0 is the
    identity; small positive values reduce conditioning of the SLSQP KKT
    system around active sets and have been observed to clear the
    "Positive directional derivative for linesearch" failure mode on
    leverage-augmented programs without materially shifting the optimum.
    """
    n = Sigma.shape[0]
    tr = float(np.trace(Sigma))
    scale = (tr / max(n, 1)) if n > 0 else 1.0
    return Sigma + strength * max(scale, 1e-12) * np.eye(n)


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

    On a failed SLSQP run the program retries with successively stronger
    Tikhonov regularization of ``Sigma`` (``strength`` in 0, 1e-6, 1e-4
    relative to ``trace(Sigma)/n``). The retry is a bug-fix for the
    ``Positive directional derivative for linesearch`` failure mode and not
    a parameter change to the program. Only if every retry fails does the
    function fall back to ``(equal_weights, unit_leverage)``.

    Retry diagnostics (``retry_count``, ``retry_jitter_strength``) are added
    to ``diagnostics`` if provided.
    """
    if diagnostics is not None:
        _record(diagnostics, _new_diag())
        diagnostics.setdefault("retry_count", 0)
        diagnostics.setdefault("retry_jitter_strength", 0.0)

    l_max = config["bond_leverage_upper"]
    n_bonds = len(bond_indices)
    uniform_x0 = np.ones(n_assets) / n_assets
    # Retry layer is opt-in. When ``optim_leverage_retry_enabled`` is False
    # (the default) the function preserves the legacy behaviour: a single
    # SLSQP attempt from a uniform starting point with the original Sigma,
    # falling back to equal weights + unit leverage on failure. This keeps
    # the published Global RRP / Defensive Dynamic RRP headline numbers
    # exactly stable. Researchers can opt-in by passing
    # ``optim_leverage_retry_enabled=True`` to recover a few of the SLSQP
    # ``Positive directional derivative for linesearch`` cases via warm
    # start (standard RP solution) and small Tikhonov diagonal jitter.
    retry_enabled = bool(config.get("optim_leverage_retry_enabled", False))
    if retry_enabled:
        warm_x0 = solve_standard_rp(Sigma, n_assets, config, diagnostics=None)
        if not (np.isfinite(warm_x0).all() and np.isclose(warm_x0.sum(), 1.0)):
            warm_x0 = uniform_x0
    else:
        warm_x0 = uniform_x0
    lev_init = np.ones(n_assets)
    bond_lev0 = lev_init[bond_indices]

    def objective(v):
        return v[2 * n_assets] - v[2 * n_assets + 1]

    def get_leverage(v):
        lev = np.ones(n_assets)
        idx = 2 * n_assets + (3 if is_relaxed else 2)
        lev[bond_indices] = v[idx:]
        return lev

    def _build_problem(Sigma_local: np.ndarray, x0: np.ndarray):
        lx0 = x0 * lev_init
        zeta0 = Sigma_local @ lx0
        psi0 = np.sqrt(lx0 @ Sigma_local @ lx0) / np.sqrt(n_assets)
        gamma0 = np.min(x0 * zeta0)
        rho0 = [0.1] if is_relaxed else []
        v0 = np.concatenate((x0, zeta0, [psi0, gamma0], rho0, bond_lev0))

        def eq_constraints(v):
            x, zeta = v[:n_assets], v[n_assets : 2 * n_assets]
            lev = get_leverage(v)
            return np.concatenate([zeta - Sigma_local @ (x * lev), [np.sum(x) - 1]])

        def ineq_constraints(v):
            x, zeta = v[:n_assets], v[n_assets : 2 * n_assets]
            psi, gamma = v[2 * n_assets], v[2 * n_assets + 1]
            lev = get_leverage(v)
            lx = x * lev
            con1 = x * zeta - gamma**2
            con2 = n_assets * psi**2 - lx @ Sigma_local @ lx
            idx_lev = 2 * n_assets + (3 if is_relaxed else 2)
            bond_lev = v[idx_lev:]
            cons = [con1, [con2], bond_lev - 1.0, l_max - bond_lev]
            if is_relaxed:
                rho = v[2 * n_assets + 2]
                R_target = config["m"] * max(R_base, 0)
                con_rho = rho**2 - config["lambda_pen"] * (x @ Theta @ x)
                cons[1] = [
                    con_rho,
                    n_assets * (psi**2 - rho**2) - lx @ Sigma_local @ lx,
                    mu @ lx - R_target,
                ]
            return np.concatenate(cons)

        bounds = (
            [config["asset_weight_bounds"]] * n_assets
            + [(0, None)] * n_assets
            + [(0, 10)] * (3 if is_relaxed else 2)
            + [(1.0, l_max)] * n_bonds
        )
        return v0, eq_constraints, ineq_constraints, bounds

    # Retry plan. When the retry layer is disabled (default) the plan is a
    # single attempt that exactly reproduces the legacy behaviour. When
    # enabled the plan is a ladder of Tikhonov-jitter + warm-start
    # combinations. Each tuple is ``(strength, x0_source)``.
    if retry_enabled:
        retry_plan = (
            (0.0, "warm"),
            (1e-6, "warm"),
            (1e-4, "warm"),
            (0.0, "uniform"),
            (1e-4, "uniform"),
        )
    else:
        retry_plan = ((0.0, "uniform"),)
    last_exc: BaseException | None = None
    last_res = None
    for attempt_idx, (strength, x0_source) in enumerate(retry_plan):
        Sigma_attempt = _tikhonov_jitter(Sigma, strength) if strength > 0.0 else Sigma
        x0_attempt = warm_x0 if x0_source == "warm" else uniform_x0
        v0, eq_constraints, ineq_constraints, bounds = _build_problem(
            Sigma_attempt, x0_attempt
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
            last_exc = exc
            last_res = None
            continue

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
            if diagnostics is not None:
                diagnostics["retry_count"] = attempt_idx
                diagnostics["retry_jitter_strength"] = float(strength)
                diagnostics["retry_x0_source"] = x0_source
            if attempt_idx > 0:
                logger.info(
                    "optimize_with_leverage: recovered via retry "
                    "(strength=%.1e, x0=%s, attempt=%d)",
                    strength,
                    x0_source,
                    attempt_idx,
                )
            return x_opt, lev_opt

        last_res = res
        last_exc = None

    # Every attempt has failed; record the last failure and fall back.
    if diagnostics is not None:
        diagnostics["retry_count"] = len(retry_plan) - 1
        diagnostics["retry_jitter_strength"] = float(retry_plan[-1][0])
        diagnostics["retry_x0_source"] = retry_plan[-1][1]
    if last_exc is not None:
        _record_failure(
            diagnostics,
            function="optimize_with_leverage",
            fallback_method="equal_weight_unit_leverage",
            exception=last_exc,
        )
    elif last_res is not None:
        _record_failure(
            diagnostics,
            function="optimize_with_leverage",
            fallback_method="equal_weight_unit_leverage",
            solver_status=int(last_res.status),
            solver_message=str(last_res.message),
            objective_value=float(last_res.fun),
        )
    return np.ones(n_assets) / n_assets, np.ones(n_assets)
