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

    if normalized == "sample":
        cov = data.cov().fillna(0.0)
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
    diagnostics["covariance_observations"] = int(len(data))
    diagnostics["covariance_assets"] = int(len(original_columns))
    diagnostics["covariance_ewma_halflife"] = halflife if normalized == "ewma" else np.nan

    if return_diagnostics:
        return CovarianceResult(covariance=cov, diagnostics=diagnostics)
    return cov
