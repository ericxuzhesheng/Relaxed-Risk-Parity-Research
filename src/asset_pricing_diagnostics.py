from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.utils import infer_asset_class

FACTOR_CLASSES = ["equity", "bond", "commodity_gold", "defensive"]
FACTOR_NAMES = FACTOR_CLASSES + ["global_risk"]
TRADING_DAYS = 243


@dataclass(frozen=True)
class DiagnosticOutputs:
    factor_exposure_summary: pd.DataFrame
    return_attribution: pd.DataFrame
    risk_attribution: pd.DataFrame
    rolling_beta_summary: pd.DataFrame


def prepare_returns(returns: pd.DataFrame) -> pd.DataFrame:
    out = returns.copy()
    out.index = pd.to_datetime(out.index)
    out = out.sort_index()
    return out.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)


def build_factor_proxies(returns: pd.DataFrame) -> pd.DataFrame:
    returns = prepare_returns(returns)
    groups: dict[str, list[str]] = {}
    for col in returns.columns:
        groups.setdefault(infer_asset_class(str(col)), []).append(col)

    factors = {}
    for asset_class in FACTOR_CLASSES:
        cols = groups.get(asset_class, [])
        if cols:
            factors[asset_class] = returns[cols].mean(axis=1)
    factors["global_risk"] = returns.mean(axis=1)
    return pd.DataFrame(factors, index=returns.index).dropna(how="all")


def _return_col(result: pd.DataFrame) -> str:
    for col in ["net_return", "portfolio_return", "gross_return"]:
        if col in result.columns:
            return col
    raise ValueError("Result frame needs net_return, portfolio_return, or gross_return.")


def _model_returns(result: pd.DataFrame) -> pd.Series:
    data = result.copy()
    data["date"] = pd.to_datetime(data["date"])
    data = data.set_index("date").sort_index()
    return pd.to_numeric(data[_return_col(data)], errors="coerce").fillna(0.0)


def _weight_columns(result: pd.DataFrame) -> list[str]:
    return [col for col in result.columns if col.startswith("weight_")]


def _weight_frame(result: pd.DataFrame) -> pd.DataFrame:
    data = result.copy()
    data["date"] = pd.to_datetime(data["date"])
    data = data.set_index("date").sort_index()
    weights = data[_weight_columns(data)].copy()
    weights.columns = [col.replace("weight_", "", 1) for col in weights.columns]
    return weights.apply(pd.to_numeric, errors="coerce").fillna(0.0)


def _ols(y: pd.Series, x: pd.DataFrame) -> dict:
    aligned = pd.concat([y.rename("y"), x], axis=1, join="inner").dropna()
    if len(aligned) < max(5, len(x.columns) + 2):
        return {
            "alpha": np.nan,
            "r_squared": np.nan,
            "residual_volatility": np.nan,
            "n_obs": len(aligned),
            "betas": {col: np.nan for col in x.columns},
            "tstats": {col: np.nan for col in ["alpha", *x.columns]},
        }
    yv = aligned["y"].values
    xv = aligned.drop(columns=["y"])
    design = np.column_stack([np.ones(len(xv)), xv.values])
    coef, *_ = np.linalg.lstsq(design, yv, rcond=None)
    fitted = design @ coef
    resid = yv - fitted
    sst = float(((yv - yv.mean()) ** 2).sum())
    r2 = 1.0 - float((resid**2).sum()) / sst if sst > 0 else np.nan
    residual_vol = float(np.std(resid, ddof=1) * np.sqrt(TRADING_DAYS)) if len(resid) > 1 else np.nan

    tstats = {col: np.nan for col in ["alpha", *x.columns]}
    dof = len(yv) - design.shape[1]
    if dof > 0:
        try:
            sigma2 = float((resid @ resid) / dof)
            cov = sigma2 * np.linalg.pinv(design.T @ design)
            stderr = np.sqrt(np.diag(cov))
            with np.errstate(divide="ignore", invalid="ignore"):
                tvals = coef / stderr
            tstats = dict(zip(["alpha", *x.columns], [float(v) for v in tvals]))
        except Exception:
            pass

    return {
        "alpha": float(coef[0]),
        "r_squared": float(r2),
        "residual_volatility": residual_vol,
        "n_obs": len(aligned),
        "betas": dict(zip(x.columns, [float(v) for v in coef[1:]])),
        "tstats": tstats,
    }


def factor_regression_summary(models: dict[str, pd.DataFrame], factors: pd.DataFrame) -> pd.DataFrame:
    rows = []
    global_returns = _model_returns(models["Global Relaxed Risk Parity"]) if "Global Relaxed Risk Parity" in models else None
    for name, result in models.items():
        y = _model_returns(result)
        reg = _ols(y, factors)
        row = {
            "model": name,
            "available_factors": ";".join(factors.columns),
            "n_obs": reg["n_obs"],
            "alpha_daily": reg["alpha"],
            "alpha_annualized": reg["alpha"] * TRADING_DAYS if pd.notna(reg["alpha"]) else np.nan,
            "alpha_tstat": reg["tstats"].get("alpha", np.nan),
            "r_squared": reg["r_squared"],
            "residual_volatility": reg["residual_volatility"],
        }
        for factor in FACTOR_NAMES:
            row[f"beta_{factor}"] = reg["betas"].get(factor, np.nan)
            row[f"tstat_{factor}"] = reg["tstats"].get(factor, np.nan)
        if global_returns is not None and name != "Global Relaxed Risk Parity":
            aligned = pd.concat([y.rename("model"), global_returns.rename("global")], axis=1, join="inner").dropna()
            row["tracking_error_vs_global_rrp"] = (
                float((aligned["model"] - aligned["global"]).std(ddof=1) * np.sqrt(TRADING_DAYS)) if len(aligned) > 1 else np.nan
            )
        else:
            row["tracking_error_vs_global_rrp"] = 0.0 if name == "Global Relaxed Risk Parity" else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def asset_class_exposure_summary(models: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, result in models.items():
        weights = _weight_frame(result)
        class_weights = _class_weight_frame(weights)
        avg = class_weights.mean()
        row = {"model": name}
        for asset_class in FACTOR_CLASSES:
            row[f"avg_exposure_{asset_class}"] = float(avg.get(asset_class, 0.0))
        row["exposure_herfindahl"] = float((avg.reindex(FACTOR_CLASSES, fill_value=0.0) ** 2).sum())
        row["max_asset_class_exposure"] = float(avg.max()) if not avg.empty else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def _class_weight_frame(weights: pd.DataFrame) -> pd.DataFrame:
    class_data = {}
    for asset_class in FACTOR_CLASSES:
        cols = [col for col in weights.columns if infer_asset_class(col) == asset_class]
        if cols:
            class_data[asset_class] = weights[cols].sum(axis=1)
    return pd.DataFrame(class_data, index=weights.index).reindex(columns=FACTOR_CLASSES, fill_value=0.0)


def return_attribution(models: dict[str, pd.DataFrame], returns: pd.DataFrame) -> pd.DataFrame:
    returns = prepare_returns(returns)
    rows = []
    for name, result in models.items():
        weights = _weight_frame(result).reindex(columns=returns.columns).fillna(0.0)
        aligned_returns = returns.reindex(weights.index).fillna(0.0)
        contributions = weights * aligned_returns
        total = contributions.sum(axis=1)
        for asset_class in FACTOR_CLASSES:
            cols = [col for col in contributions.columns if infer_asset_class(col) == asset_class]
            series = contributions[cols].sum(axis=1) if cols else pd.Series(0.0, index=contributions.index)
            mean_daily = float(series.mean()) if len(series) else np.nan
            total_mean = float(total.mean()) if len(total) else np.nan
            share = mean_daily / total_mean if pd.notna(total_mean) and abs(total_mean) > 1e-12 else np.nan
            rows.append(
                {
                    "model": name,
                    "asset_class": asset_class,
                    "average_daily_contribution": mean_daily,
                    "annualized_return_contribution": mean_daily * TRADING_DAYS if pd.notna(mean_daily) else np.nan,
                    "share_of_average_portfolio_return": share,
                }
            )
    return pd.DataFrame(rows)


def risk_attribution(models: dict[str, pd.DataFrame], returns: pd.DataFrame) -> pd.DataFrame:
    returns = prepare_returns(returns)
    rows = []
    for name, result in models.items():
        weights = _weight_frame(result).reindex(columns=returns.columns).fillna(0.0)
        aligned_returns = returns.reindex(weights.index).fillna(0.0)
        contributions = weights * aligned_returns
        class_contrib = pd.DataFrame(index=weights.index)
        for asset_class in FACTOR_CLASSES:
            cols = [col for col in contributions.columns if infer_asset_class(col) == asset_class]
            class_contrib[asset_class] = contributions[cols].sum(axis=1) if cols else 0.0
        portfolio = class_contrib.sum(axis=1)
        var = float(portfolio.var(ddof=1)) if len(portfolio) > 1 else np.nan
        nav = (1.0 + portfolio).cumprod()
        drawdown = nav / nav.cummax() - 1.0
        stress_mask = drawdown <= drawdown.quantile(0.10) if len(drawdown) else pd.Series(False, index=portfolio.index)
        for asset_class in FACTOR_CLASSES:
            series = class_contrib[asset_class]
            cov_share = float(series.cov(portfolio) / var) if pd.notna(var) and var > 0 else np.nan
            rows.append(
                {
                    "model": name,
                    "asset_class": asset_class,
                    "annualized_volatility_contribution_approx": cov_share * float(portfolio.std(ddof=1) * np.sqrt(TRADING_DAYS)) if pd.notna(cov_share) else np.nan,
                    "variance_share_approx": cov_share,
                    "average_stress_drawdown_contribution": float(series[stress_mask].mean()) if stress_mask.any() else np.nan,
                }
            )
    return pd.DataFrame(rows)


def rolling_beta_summary(
    models: dict[str, pd.DataFrame],
    factors: pd.DataFrame,
    model_names: list[str] | None = None,
    window: int = 252,
) -> pd.DataFrame:
    selected = model_names or ["Global Relaxed Risk Parity", "Improved Convex Adaptive Global RRP"]
    rows = []
    for name in selected:
        if name not in models:
            rows.append({"model": name, "factor": "", "window": window, "status": "missing_model", "n_windows": 0})
            continue
        y = _model_returns(models[name])
        aligned = pd.concat([y.rename("y"), factors], axis=1, join="inner").dropna()
        if len(aligned) < window:
            rows.append({"model": name, "factor": "", "window": window, "status": "insufficient_data", "n_windows": 0, "n_obs": len(aligned)})
            continue
        beta_records = {factor: [] for factor in factors.columns}
        for end in range(window, len(aligned) + 1):
            sample = aligned.iloc[end - window : end]
            reg = _ols(sample["y"], sample[factors.columns])
            for factor in factors.columns:
                beta_records[factor].append(reg["betas"].get(factor, np.nan))
        for factor, values in beta_records.items():
            clean = pd.Series(values, dtype=float).dropna()
            rows.append(
                {
                    "model": name,
                    "factor": factor,
                    "window": window,
                    "status": "ok" if not clean.empty else "insufficient_data",
                    "n_windows": int(clean.size),
                    "beta_mean": float(clean.mean()) if not clean.empty else np.nan,
                    "beta_min": float(clean.min()) if not clean.empty else np.nan,
                    "beta_max": float(clean.max()) if not clean.empty else np.nan,
                    "beta_last": float(clean.iloc[-1]) if not clean.empty else np.nan,
                }
            )
    return pd.DataFrame(rows)


def run_diagnostics(models: dict[str, pd.DataFrame], returns: pd.DataFrame) -> DiagnosticOutputs:
    returns = prepare_returns(returns)
    factors = build_factor_proxies(returns)
    exposure = factor_regression_summary(models, factors)
    class_exposure = asset_class_exposure_summary(models)
    exposure = exposure.merge(class_exposure, on="model", how="left")
    return DiagnosticOutputs(
        factor_exposure_summary=exposure,
        return_attribution=return_attribution(models, returns),
        risk_attribution=risk_attribution(models, returns),
        rolling_beta_summary=rolling_beta_summary(models, factors),
    )


def write_outputs(outputs: DiagnosticOutputs, output_root: Path) -> dict[str, Path]:
    tables = output_root / "results" / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    paths = {
        "factor_exposure_summary": tables / "asset_pricing_factor_exposure_summary.csv",
        "return_attribution": tables / "asset_pricing_return_attribution.csv",
        "risk_attribution": tables / "asset_pricing_risk_attribution.csv",
        "rolling_beta_summary": tables / "asset_pricing_rolling_beta_summary.csv",
    }
    outputs.factor_exposure_summary.to_csv(paths["factor_exposure_summary"], index=False)
    outputs.return_attribution.to_csv(paths["return_attribution"], index=False)
    outputs.risk_attribution.to_csv(paths["risk_attribution"], index=False)
    outputs.rolling_beta_summary.to_csv(paths["rolling_beta_summary"], index=False)
    return paths
