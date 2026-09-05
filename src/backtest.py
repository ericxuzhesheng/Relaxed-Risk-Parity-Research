"""Static monthly-rebalance backtester for the standard / relaxed RP models.

The backtest is intentionally simple and serves as the reference path for the
"Global RRP" and "Defensive Dynamic RRP" entries reported in the thesis. It
preserves the original calling convention used throughout ``scripts/`` while
adding three optional diagnostics streams via the ``diagnostics_out`` channel:

* ``solver`` — per rebalance solver outcome from ``src.risk_parity``
  (status, message, objective, fallback flag).
* ``covariance`` — per rebalance covariance metadata from
  ``src.covariance_estimators.estimate_covariance`` (n_obs, n_assets, condition
  number, PSD repair flags, sample-size warning).
* ``universe`` — per rebalance investable universe (included, excluded,
  exclusion reason, count). The investable set is determined strictly from
  data prior to the rebalance date (``returns.index < d``) and is frozen for
  the month that follows.

Point-in-time behaviour. The investable universe is recomputed at every
rebalance from the strictly-prior return window. Inclusion is based solely on
non-missing observation count and positive within-window variance, so no
forward information leaks into the inclusion decision; this is documented in
the README "Reliability and Diagnostics" section.
"""

from __future__ import annotations

import logging
from typing import Iterable

import numpy as np
import pandas as pd

from src.covariance_estimators import estimate_covariance
from src.convex_adaptive_rrp import drift_weights
from src.hierarchical_risk_parity import solve_herc, solve_hrp
from src.investable import expand_weights, investable_columns, portfolio_return_for_available
from src.risk_overlay import (
    RiskOverlayConfig,
    apply_risk_overlay,
    apply_trend_confirmation,
    transaction_cost_rate,
)
from src.risk_parity import optimize_with_leverage, solve_relaxed_rp, solve_standard_rp
from src.utils import apply_asset_class_budget_multipliers, get_config


logger = logging.getLogger(__name__)


# When the ratio of usable observations to assets falls below this floor,
# emit a warning. The threshold is deliberately conservative (3:1) because the
# legacy backtest uses ``min_observations=min(60, lookback)`` which can admit
# windows with only 60 daily observations versus ~30 assets.
COV_SAMPLE_RATIO_FLOOR = 3.0
# Above this condition number the covariance is treated as ill-conditioned for
# diagnostic purposes (post PSD repair).
COV_CONDITION_NUMBER_CEILING = 1e8


def _rrp_parameter_schedule(config: dict) -> list[tuple[pd.Timestamp, float, float]]:
    """Validate an optional point-in-time penalty schedule."""
    rows = []
    for item in config.get("rrp_parameter_schedule", []):
        date = pd.Timestamp(item["effective_date"])
        variance = float(item["rrp_variance_penalty"])
        shortfall = float(item["lambda_pen"])
        if pd.isna(date):
            raise ValueError("scheduled RRP effective dates must be valid")
        if not np.isfinite([variance, shortfall]).all() or min(variance, shortfall) < 0:
            raise ValueError("scheduled RRP penalties must be finite and nonnegative")
        rows.append((date, variance, shortfall))
    if any(rows[i][0] >= rows[i + 1][0] for i in range(len(rows) - 1)):
        raise ValueError("rrp_parameter_schedule dates must be strictly increasing")
    return rows


def _monthly_rebalance_dates(returns: pd.DataFrame) -> set[pd.Timestamp]:
    return set(returns.groupby(returns.index.to_period("M")).tail(1).index)


def _universe_exclusion_reasons(
    df_window_full: pd.DataFrame, active_cols: Iterable[str]
) -> dict[str, str]:
    """Return a reason string per excluded column."""
    data = df_window_full.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    counts = data.notna().sum()
    variance = data.std(skipna=True)
    active = set(active_cols)
    reasons: dict[str, str] = {}
    for col in data.columns:
        if col in active:
            continue
        n_obs = int(counts.get(col, 0))
        var = float(variance.get(col, np.nan))
        if n_obs == 0:
            reasons[col] = "no_observations"
        elif np.isnan(var) or var <= 0.0:
            reasons[col] = "zero_variance"
        else:
            reasons[col] = f"insufficient_observations({n_obs})"
    return reasons


def _append_universe_row(
    collector: list[dict] | None,
    *,
    date: pd.Timestamp,
    active_cols: list[str],
    excluded: dict[str, str],
    min_observations: int,
) -> None:
    if collector is None:
        return
    collector.append(
        {
            "date": pd.Timestamp(date),
            "asset_count": len(active_cols),
            "min_observations_required": int(min_observations),
            "included_assets": "|".join(active_cols),
            "excluded_assets": "|".join(sorted(excluded.keys())),
            "exclusion_reasons": "|".join(
                f"{name}:{reason}" for name, reason in sorted(excluded.items())
            ),
        }
    )


def _append_covariance_row(
    collector: list[dict] | None,
    *,
    date: pd.Timestamp,
    diag: dict,
) -> None:
    if collector is None:
        return
    n_obs = int(diag.get("covariance_observations", 0))
    n_assets = int(diag.get("covariance_assets", 0))
    ratio = float(n_obs) / float(n_assets) if n_assets else float("nan")
    condition_number = float(diag.get("covariance_condition_number", float("nan")))
    low_sample = bool(np.isfinite(ratio) and ratio < COV_SAMPLE_RATIO_FLOOR)
    ill_conditioned = bool(
        np.isfinite(condition_number) and condition_number > COV_CONDITION_NUMBER_CEILING
    )
    if low_sample:
        logger.warning(
            "%s: covariance window has low n_obs/n_assets ratio (%d / %d = %.2f); "
            "estimates may be unstable.",
            pd.Timestamp(date).date(),
            n_obs,
            n_assets,
            ratio,
        )
    if ill_conditioned:
        logger.warning(
            "%s: covariance is ill-conditioned post PSD repair (condition number %.2e).",
            pd.Timestamp(date).date(),
            condition_number,
        )
    row = {"date": pd.Timestamp(date), "n_obs_to_n_assets_ratio": ratio,
           "low_sample_warning": low_sample, "ill_conditioned_warning": ill_conditioned}
    row.update(diag)
    collector.append(row)


def _append_solver_row(
    collector: list[dict] | None,
    *,
    date: pd.Timestamp,
    model_type: str,
    n_assets: int,
    diag: dict,
) -> None:
    if collector is None:
        return
    row = {
        "date": pd.Timestamp(date),
        "model_type": model_type,
        "active_n_assets": int(n_assets),
    }
    row.update(diag)
    collector.append(row)


def run_static_backtest(
    returns: pd.DataFrame,
    model_type: str = "relaxed",
    config_overrides: dict = None,
    diagnostics_out: dict | None = None,
) -> pd.DataFrame:
    """Run the monthly rebalance backtest.

    Parameters
    ----------
    diagnostics_out
        Optional dict. When supplied, three keys are populated with
        ``pd.DataFrame`` rows after the run completes:

        ``solver`` — per rebalance solver status / message / fallback flag.
        ``covariance`` — covariance diagnostics including condition number.
        ``universe`` — investable universe per rebalance with inclusion and
        exclusion details.

        The backtest's primary return value (the per-day result DataFrame) is
        unchanged so existing callers continue to work without modification.
    """
    config = get_config(config_overrides)
    n_assets = len(returns.columns)
    dates = returns.index
    model_type = model_type.lower()
    if model_type not in {"standard", "relaxed", "hrp", "herc"}:
        raise ValueError(f"Unsupported model_type: {model_type}")

    keywords = config["bond_keywords"]
    frequency = config.get("rebalance_frequency", "M")
    if frequency not in {"W", "M", "Q", "2W"}:
        raise ValueError("Unsupported rebalance_frequency")
    if frequency == "2W":
        rebalance_dates = set(returns.groupby(returns.index.to_period("W")).tail(1).index[::2])
    else:
        rebalance_dates = set(returns.groupby(returns.index.to_period(frequency)).tail(1).index)
    overlay_config = RiskOverlayConfig.from_config(config)
    cost_rate = transaction_cost_rate(overlay_config)
    rrp_schedule = _rrp_parameter_schedule(config)

    solver_rows: list[dict] | None = [] if diagnostics_out is not None else None
    cov_rows: list[dict] | None = [] if diagnostics_out is not None else None
    universe_rows: list[dict] | None = [] if diagnostics_out is not None else None

    results = []
    current_weights = np.zeros(n_assets)
    portfolio_navs = [1.0]
    high_water_mark = 1.0
    risk_state = {}

    for d in dates:
        pretrade_weights = current_weights.copy()
        current_nav = portfolio_navs[-1]
        high_water_mark = max(high_water_mark, current_nav)
        drawdown = (current_nav / high_water_mark) - 1.0
        turnover = 0.0
        overlay_state = {
            "target_vol_scalar": 1.0,
            "drawdown_scalar": 1.0,
            "trend_scalar": 1.0,
            "final_risk_scalar": 1.0,
            "turnover_cap_bound": False,
            "gross_exposure": float(np.abs(current_weights).sum()),
            "risky_exposure": float(np.abs(current_weights).sum()),
            "defensive_cash_proxy_exposure": float(max(0.0, 1.0 - np.abs(current_weights).sum())),
            "reentry_state": 1.0,
            "trend_positive_count": n_assets,
        }

        if d in rebalance_dates:
            lookback = int(config.get("lookback_days", config["lookback_weeks"] * 5))
            if lookback < 2:
                raise ValueError("lookback_days must be at least two")
            # Strictly point-in-time: only data observed before the rebalance date d
            # enters the investable filter and the covariance estimate.
            df_window_full = returns[returns.index < d].iloc[-lookback:]
            min_obs = min(60, lookback)
            active_cols = investable_columns(df_window_full, min_observations=min_obs)
            df_window = df_window_full[active_cols]
            excluded = _universe_exclusion_reasons(df_window_full, active_cols)
            _append_universe_row(
                universe_rows,
                date=d,
                active_cols=active_cols,
                excluded=excluded,
                min_observations=min_obs,
            )
            if len(df_window) >= 20 and len(active_cols) > 1:
                previous_weights = current_weights.copy()
                trend_positive_count = len(active_cols)

                if model_type == "hrp":
                    active_weights = solve_hrp(df_window).values
                elif model_type == "herc":
                    active_weights = solve_herc(df_window).values
                else:
                    mean_method = config.get("mean_estimator", "sample")
                    if mean_method == "sample":
                        mu = df_window.mean() * config["trading_days_per_year"]
                    elif mean_method == "ewma":
                        halflife = float(config.get("mean_ewma_halflife", 60.0))
                        if not np.isfinite(halflife) or halflife <= 0:
                            raise ValueError("mean_ewma_halflife must be finite and positive")
                        mu = df_window.ewm(halflife=halflife, ignore_na=True).mean().iloc[-1] * config["trading_days_per_year"]
                    else:
                        raise ValueError("Unsupported mean_estimator")
                    cov_result = estimate_covariance(
                        df_window,
                        method=config.get("covariance_method", "sample"),
                        ewma_halflife=float(config.get("ewma_halflife", 60.0)),
                        trading_days=config["trading_days_per_year"],
                        annualize=True,
                        allow_fallback=True,
                        return_diagnostics=True,
                        point_in_time=True,
                    )
                    sigma = cov_result.covariance
                    cov_diag = dict(cov_result.diagnostics)
                    _append_covariance_row(cov_rows, date=d, diag=cov_diag)
                    theta = np.diag(np.diag(sigma))
                    active_bond_indices = [i for i, col in enumerate(active_cols) if any(k in col for k in keywords)]

                    mu_filtered, trend_positive_count = apply_trend_confirmation(
                        mu,
                        df_window,
                        overlay_config,
                    )
                    r_base = mu.mean()

                    solver_diag: dict = {}
                    solver_config = config
                    effective_rows = [row for row in rrp_schedule if row[0] <= d]
                    if effective_rows:
                        effective_date, variance_penalty, shortfall_penalty = effective_rows[-1]
                        solver_config = {**config, "rrp_variance_penalty": variance_penalty,
                                         "lambda_pen": shortfall_penalty}
                    else:
                        effective_date = pd.NaT
                    if model_type == "standard":
                        if active_bond_indices:
                            w, lev = optimize_with_leverage(
                                sigma.values,
                                len(active_cols),
                                active_bond_indices,
                                config=solver_config,
                                diagnostics=solver_diag,
                            )
                            active_weights = w * lev
                        else:
                            active_weights = solve_standard_rp(
                                sigma.values,
                                len(active_cols),
                                solver_config,
                                diagnostics=solver_diag,
                            )
                    else:
                        if active_bond_indices:
                            w, lev = optimize_with_leverage(
                                sigma.values,
                                len(active_cols),
                                active_bond_indices,
                                mu_filtered.values,
                                theta,
                                r_base,
                                is_relaxed=True,
                                config=solver_config,
                                diagnostics=solver_diag,
                            )
                            active_weights = w * lev
                        else:
                            active_weights = solve_relaxed_rp(
                                sigma.values,
                                mu_filtered.values,
                                theta,
                                len(active_cols),
                                r_base,
                                solver_config,
                                diagnostics=solver_diag,
                            )
                    solver_diag["information_cutoff"] = df_window.index.max()
                    solver_diag["mean_estimator"] = mean_method
                    solver_diag["parameter_effective_date"] = effective_date
                    solver_diag["selected_variance_penalty"] = float(solver_config.get("rrp_variance_penalty", 0.10))
                    solver_diag["selected_shortfall_penalty"] = float(solver_config.get("lambda_pen", 1.9))
                    _append_solver_row(
                        solver_rows,
                        date=d,
                        model_type=model_type,
                        n_assets=len(active_cols),
                        diag=solver_diag,
                    )

                active_weights = apply_asset_class_budget_multipliers(active_weights, active_cols, config)
                current_weights = expand_weights(active_weights, active_cols, returns.columns)
                if model_type in {"standard", "relaxed"} and config.get("risk_overlay_enabled", True):
                    current_weights, overlay_state = apply_risk_overlay(
                        current_weights,
                        previous_weights,
                        df_window_full,
                        drawdown,
                        overlay_config,
                        risk_state,
                    )
                    risk_state = overlay_state.copy()
                    overlay_state["trend_positive_count"] = trend_positive_count
                    turnover = overlay_state["turnover"]
                    # Fill any uninvested residual into 日利ETF so weights always sum to 100%
                    _rili_residual = 1.0 - float(np.abs(current_weights).sum())
                    if _rili_residual > 1e-6 and "日利ETF" in returns.columns:
                        _rili_idx = returns.columns.get_loc("日利ETF")
                        current_weights[_rili_idx] += _rili_residual
                        overlay_state["defensive_cash_proxy_exposure"] = 0.0
                else:
                    turnover = float(np.abs(current_weights - previous_weights).sum())
                    overlay_state["turnover"] = turnover

        gross_ret = portfolio_return_for_available(returns.loc[d], current_weights)
        ret = gross_ret
        if turnover > 0.0 and cost_rate > 0.0:
            ret -= cost_rate * turnover

        portfolio_navs.append(portfolio_navs[-1] * (1.0 + ret))
        res = {
            "date": d,
            "portfolio_return": ret,
            "net_return": ret,
            "gross_return": gross_ret,
            "transaction_cost": cost_rate * turnover,
            "is_rebalance_day": d in rebalance_dates,
            "turnover": turnover,
            "target_vol_scalar": overlay_state["target_vol_scalar"],
            "drawdown_scalar": overlay_state["drawdown_scalar"],
            "trend_scalar": overlay_state["trend_scalar"],
            "final_risk_scalar": overlay_state["final_risk_scalar"],
            "turnover_cap_bound": overlay_state["turnover_cap_bound"],
            "gross_exposure": overlay_state["gross_exposure"],
            "risky_exposure": overlay_state["risky_exposure"],
            "defensive_cash_proxy_exposure": overlay_state["defensive_cash_proxy_exposure"],
            "reentry_state": overlay_state["reentry_state"],
            "trend_positive_count": overlay_state["trend_positive_count"],
        }
        for key in (
            "ema_deviation_min",
            "ema_deviation_max",
            "ema_strong_trend_count",
            "ema_overextended_count",
            "ema_stop_count",
            "ema_insufficient_history",
        ):
            res[key] = overlay_state.get(key, None)
        for j, asset in enumerate(returns.columns):
            res[f"weight_{asset}"] = current_weights[j]
            res[f"previous_weight_{asset}"] = pretrade_weights[j]
        results.append(res)
        current_weights = drift_weights(current_weights, returns.loc[d])

    if diagnostics_out is not None:
        diagnostics_out["solver"] = pd.DataFrame(solver_rows or [])
        diagnostics_out["covariance"] = pd.DataFrame(cov_rows or [])
        diagnostics_out["universe"] = pd.DataFrame(universe_rows or [])

    return pd.DataFrame(results)
