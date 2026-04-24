import numpy as np
import pandas as pd
from scipy.optimize import minimize
from typing import Tuple, List, Dict

def solve_standard_rp(Sigma: np.ndarray, n_assets: int, config: dict) -> np.ndarray:
    """求解标准风险平价权重"""
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

    bounds = ([config["asset_weight_bounds"]] * n_assets + [(0, None)] * n_assets + [(0, 10), (0, 10)])
    
    try:
        res = minimize(objective, v0, method="SLSQP", constraints=[{"type": "eq", "fun": eq_constraints}, {"type": "ineq", "fun": ineq_constraints}], bounds=bounds, options={"ftol": config["optim_tol"], "maxiter": config["optim_maxiter"]})
        if res.success: return res.x[:n_assets]
    except: pass
    return np.ones(n_assets) / n_assets

def solve_relaxed_rp(Sigma: np.ndarray, mu: np.ndarray, Theta: np.ndarray, n_assets: int, R_base: float, config: dict) -> np.ndarray:
    """求解宽松风险平价权重 (Model C)"""
    x_rp = solve_standard_rp(Sigma, n_assets, config)
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
        psi, gamma, rho = v[2 * n_assets], v[2 * n_assets + 1], v[2 * n_assets + 2]
        con1 = x * zeta - gamma**2
        con2 = rho**2 - config["lambda_pen"] * (x @ Theta @ x)
        con3 = n_assets * (psi**2 - rho**2) - x @ Sigma @ x
        con4 = mu @ x - R_target
        return np.concatenate([con1, [con2, con3, con4]])

    bounds = ([config["asset_weight_bounds"]] * n_assets + [(0, None)] * n_assets + [(0, 10)] * 3)

    try:
        res = minimize(objective, v0, method="SLSQP", constraints=[{"type": "eq", "fun": eq_constraints}, {"type": "ineq", "fun": ineq_constraints}], bounds=bounds, options={"ftol": config["optim_tol"], "maxiter": config["optim_maxiter"]})
        if res.success: return res.x[:n_assets]
    except: pass
    return x_rp

def optimize_with_leverage(Sigma: np.ndarray, n_assets: int, bond_indices: list, mu: np.ndarray = None, Theta: np.ndarray = None, R_base: float = 0, is_relaxed: bool = False, config: dict = None) -> Tuple[np.ndarray, np.ndarray]:
    """通用杠杆优化函数"""
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
        x, zeta = v[:n_assets], v[n_assets:2*n_assets]
        lev = get_leverage(v)
        return np.concatenate([zeta - Sigma @ (x * lev), [np.sum(x) - 1]])

    def ineq_constraints(v):
        x, zeta = v[:n_assets], v[n_assets:2*n_assets]
        psi, gamma = v[2*n_assets], v[2*n_assets + 1]
        lev = get_leverage(v)
        lx = x * lev
        con1 = x * zeta - gamma**2
        con2 = n_assets * psi**2 - lx @ Sigma @ lx
        idx_lev = 2 * n_assets + (3 if is_relaxed else 2)
        bond_lev = v[idx_lev:]
        cons = [con1, [con2], bond_lev - 1.0, l_max - bond_lev]
        if is_relaxed:
            rho = v[2*n_assets + 2]
            R_target = config["m"] * max(R_base, 0)
            con_rho = rho**2 - config["lambda_pen"] * (x @ Theta @ x)
            cons[1] = [con_rho, n_assets * (psi**2 - rho**2) - lx @ Sigma @ lx, mu @ lx - R_target]
        return np.concatenate(cons)

    bounds = ([config["asset_weight_bounds"]] * n_assets + [(0, None)] * n_assets + [(0, 10)] * (3 if is_relaxed else 2) + [(1.0, l_max)] * n_bonds)
    try:
        res = minimize(objective, v0, method="SLSQP", constraints=[{"type": "eq", "fun": eq_constraints}, {"type": "ineq", "fun": ineq_constraints}], bounds=bounds, options={"ftol": config["optim_tol"], "maxiter": config["optim_maxiter"]})
        if res.success:
            x_opt = res.x[:n_assets]
            lev_opt = np.ones(n_assets)
            idx = 2 * n_assets + (3 if is_relaxed else 2)
            lev_opt[bond_indices] = res.x[idx:]
            return x_opt, lev_opt
    except: pass
    return np.ones(n_assets) / n_assets, np.ones(n_assets)
