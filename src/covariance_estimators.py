from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CovarianceResult:
    covariance: pd.DataFrame
    diagnostics: dict


EWMA_ALIASES = {
    "ewma_halflife_20": 20.0,
    "ewma_halflife_60": 60.0,
    "ewma_halflife_120": 120.0,
}


def _clean_returns(returns_window: pd.DataFrame) -> pd.DataFrame:
    data = returns_window.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    data = data.dropna(axis=1, how="all")
    data = data.dropna(how="any")
    if data.empty:
        data = returns_window.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return data


def _method_and_halflife(method: str, ewma_halflife: float) -> tuple[str, float]:
    normalized = str(method).lower()
    if normalized in EWMA_ALIASES:
        return "ewma", EWMA_ALIASES[normalized]
    return normalized, float(ewma_halflife)


def _symmetrize(cov: pd.DataFrame) -> pd.DataFrame:
    values = np.asarray(cov.values, dtype=float)
    values = (values + values.T) / 2.0
    return pd.DataFrame(values, index=cov.index, columns=cov.columns)


def _repair_psd(cov: pd.DataFrame, jitter: float = 1e-10) -> tuple[pd.DataFrame, dict]:
    cov = _symmetrize(cov).fillna(0.0)
    values = cov.values
    notes: list[str] = ["symmetrized"]
    if values.size == 0:
        return cov, {"covariance_psd_repaired": False, "covariance_jitter_added": 0.0, "covariance_psd_notes": "empty"}

    eigvals, eigvecs = np.linalg.eigh(values)
    min_eig = float(eigvals.min())
    jitter_added = 0.0
    repaired = False
    if min_eig < jitter:
        repaired = True
        eigvals = np.clip(eigvals, jitter, None)
        values = eigvecs @ np.diag(eigvals) @ eigvecs.T
        values = (values + values.T) / 2.0
        jitter_added = max(jitter - min_eig, 0.0)
        notes.append("eigenvalue_floor")
    repaired_cov = pd.DataFrame(values, index=cov.index, columns=cov.columns)
    return repaired_cov, {
        "covariance_psd_repaired": repaired,
        "covariance_jitter_added": jitter_added,
        "covariance_psd_notes": ";".join(notes),
    }


def _regime_conditional_covariance(
    data: pd.DataFrame,
    stress_quantile: float = 0.67,
    crisis_prior: float = 0.40,
    prior_weight: float = 0.50,
    vol_window: int = 21,
) -> tuple[pd.DataFrame, dict]:
    """State-conditional covariance estimated from the supplied window only.

    The classic ERC failure mode is that an *unconditional* covariance pools
    calm and crisis days into one distribution, which under-weights the tail
    co-movement that only shows up in stress regimes. This estimator instead:

    1. classifies each day in the window as calm or stress using the trailing
       realized volatility of the equal-weight portfolio (a point-in-time
       regime proxy computed from the window itself, so no look-ahead);
    2. estimates a within-regime sample covariance for each bucket;
    3. recombines them as ``Σ = (1-π) Σ_calm + π Σ_stress`` where the stress
       weight ``π`` is the *empirical* stress frequency shrunk toward a fixed
       ``crisis_prior``. Shrinking the frequency toward a prior that exceeds
       the empirical share over-weights rare-but-severe regimes, which is the
       robustness mechanism described for regime-resilient risk parity.

    Returns the daily covariance and a diagnostics dict. Falls back to the
    pooled sample covariance when the window is too short to split reliably.
    """
    n_obs = len(data)
    cols = data.columns
    min_obs = max(len(cols) + 1, vol_window)
    eq = data.mean(axis=1)
    realized_vol = eq.rolling(vol_window, min_periods=max(5, vol_window // 4)).std()
    valid = realized_vol.dropna()

    def _fallback(note: str) -> tuple[pd.DataFrame, dict]:
        cov = data.cov().fillna(0.0)
        return cov, {
            "regime_fallback": True,
            "regime_n_stress": 0,
            "regime_n_calm": int(n_obs),
            "regime_pi_empirical": np.nan,
            "regime_pi_stress": np.nan,
            "regime_vol_threshold": np.nan,
            "regime_note": note,
        }

    if len(valid) < 2 * len(cols) or n_obs < 3 * vol_window:
        return _fallback("insufficient_history")

    threshold = float(valid.quantile(stress_quantile))
    stress_mask = (realized_vol >= threshold) & realized_vol.notna()
    calm_mask = (realized_vol < threshold) & realized_vol.notna()
    stress_data = data.loc[stress_mask]
    calm_data = data.loc[calm_mask]
    n_stress = int(len(stress_data))
    n_calm = int(len(calm_data))
    if n_stress + n_calm == 0:
        return _fallback("empty_buckets")

    pooled = data.loc[realized_vol.notna()].cov().fillna(0.0)
    cov_stress = stress_data.cov().fillna(0.0) if n_stress >= min_obs else pooled
    cov_calm = calm_data.cov().fillna(0.0) if n_calm >= min_obs else pooled

    pi_empirical = n_stress / float(n_stress + n_calm)
    prior_weight = float(np.clip(prior_weight, 0.0, 1.0))
    pi_stress = float(np.clip((1.0 - prior_weight) * pi_empirical + prior_weight * crisis_prior, 0.0, 1.0))
    cov = (1.0 - pi_stress) * cov_calm + pi_stress * cov_stress
    cov = cov.reindex(index=cols, columns=cols).fillna(0.0)
    return cov, {
        "regime_fallback": False,
        "regime_n_stress": n_stress,
        "regime_n_calm": n_calm,
        "regime_pi_empirical": float(pi_empirical),
        "regime_pi_stress": pi_stress,
        "regime_vol_threshold": threshold,
        "regime_note": "ok",
    }


def _ewma_covariance(data: pd.DataFrame, halflife: float) -> pd.DataFrame:
    values = data.values.astype(float)
    n_obs = len(data)
    if n_obs <= 1:
        return data.cov().fillna(0.0)
    decay = float(np.exp(np.log(0.5) / max(float(halflife), 1e-12)))
    weights = decay ** np.arange(n_obs - 1, -1, -1, dtype=float)
    weights = weights / weights.sum()
    mean = weights @ values
    centered = values - mean
    cov_values = (centered * weights[:, None]).T @ centered
    return pd.DataFrame(cov_values, index=data.columns, columns=data.columns)


def covariance_diagnostics(
    cov: pd.DataFrame,
    method: str,
    annualize: bool,
    trading_days: int,
    fallback_used: bool = False,
    fallback_method: str = "",
    failure_note: str = "",
    point_in_time: bool = True,
) -> dict:
    values = np.asarray(cov.values, dtype=float)
    if values.size == 0:
        min_eig = max_eig = condition = np.nan
    else:
        eigvals = np.linalg.eigvalsh((values + values.T) / 2.0)
        min_eig = float(eigvals.min())
        max_eig = float(eigvals.max())
        condition = float(max_eig / max(min_eig, 1e-12)) if max_eig > 0 else np.nan
    return {
        "covariance_method": method,
        "covariance_annualized": bool(annualize),
        "covariance_trading_days": int(trading_days),
        "covariance_fallback_used": bool(fallback_used),
        "covariance_fallback_method": fallback_method,
        "covariance_failure_note": failure_note,
        "covariance_min_eigenvalue": min_eig,
        "covariance_max_eigenvalue": max_eig,
        "covariance_condition_number": condition,
        "covariance_point_in_time": bool(point_in_time),
    }


def estimate_covariance(
    returns_window: pd.DataFrame,
    method: str = "sample",
    trading_days: int = 243,
    ewma_halflife: float = 60.0,
    annualize: bool = False,
    allow_fallback: bool = False,
    return_diagnostics: bool = False,
    point_in_time: bool = True,
    regime_stress_quantile: float = 0.67,
    regime_crisis_prior: float = 0.40,
    regime_prior_weight: float = 0.50,
) -> pd.DataFrame | CovarianceResult:
    """
    Estimate a covariance matrix from the supplied return window only.

    Outputs daily covariance by default. Set annualize=True when the caller's
    optimization objective expects annualized risk inputs.
    """
    original_columns = pd.Index(returns_window.columns)
    data = _clean_returns(returns_window)
    normalized, halflife = _method_and_halflife(method, ewma_halflife)
    fallback_used = False
    fallback_method = ""
    failure_note = ""
    regime_diag: dict = {}

    if normalized == "sample":
        cov = data.cov().fillna(0.0)
    elif normalized == "regime_conditional":
        cov, regime_diag = _regime_conditional_covariance(
            data,
            stress_quantile=regime_stress_quantile,
            crisis_prior=regime_crisis_prior,
            prior_weight=regime_prior_weight,
        )
    elif normalized == "ledoit_wolf":
        try:
            from sklearn.covariance import LedoitWolf

            cov_values = LedoitWolf().fit(data.values).covariance_
            cov = pd.DataFrame(cov_values, index=data.columns, columns=data.columns)
        except Exception as exc:
            if not allow_fallback:
                raise RuntimeError("Ledoit-Wolf covariance estimation failed and fallback is disabled") from exc
            fallback_used = True
            fallback_method = "sample"
            failure_note = str(exc)
            cov = data.cov().fillna(0.0)
    elif normalized == "ewma":
        try:
            cov = _ewma_covariance(data, halflife)
        except Exception as exc:
            cov = data.cov().fillna(0.0)
            fallback_used = True
            fallback_method = "sample"
            failure_note = f"EWMA covariance unavailable for the supplied window: {exc}"
    else:
        raise ValueError(f"Unsupported covariance estimator: {method}")

    cov = cov.reindex(index=original_columns, columns=original_columns).fillna(0.0)
    if annualize:
        cov = cov * float(trading_days)
    cov, psd_diag = _repair_psd(cov)
    diagnostics = covariance_diagnostics(
        cov,
        method=str(method).lower(),
        annualize=annualize,
        trading_days=trading_days,
        fallback_used=fallback_used,
        fallback_method=fallback_method,
        failure_note=failure_note,
        point_in_time=point_in_time,
    )
    diagnostics.update(psd_diag)
    if regime_diag:
        diagnostics.update(regime_diag)
    diagnostics["covariance_observations"] = int(len(data))
    diagnostics["covariance_assets"] = int(len(original_columns))
    diagnostics["covariance_ewma_halflife"] = halflife if normalized == "ewma" else np.nan

    if return_diagnostics:
        return CovarianceResult(covariance=cov, diagnostics=diagnostics)
    return cov
