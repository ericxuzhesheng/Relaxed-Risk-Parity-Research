from __future__ import annotations

import itertools
import json
from dataclasses import asdict
from typing import Iterable

import numpy as np
import pandas as pd

from src.dynamic_selection import monthly_rebalance_dates, score_params
from src.metrics import calculate_metrics
from src.public_labels import public_model_label


VALIDATION_STATUS = "validation_only_no_reselection_from_test"
VALIDATION_NOTE = (
    "Validation-only diagnostic. Candidate selection uses only the declared "
    "selection window; test-window metrics are reported after selection."
)


def adjusted_sharpe(
    sharpe: float,
    n_trials: int,
    skew: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    multiple_testing_penalty = 0.10 * np.sqrt(max(np.log(max(n_trials, 1)), 0.0))
    non_normality_penalty = 0.025 * abs(skew) + 0.005 * max(kurtosis - 3.0, 0.0)
    return float(sharpe - multiple_testing_penalty - non_normality_penalty)


def ensure_datetime_index(returns: pd.DataFrame) -> pd.DataFrame:
    if returns.empty:
        raise ValueError("Return data is empty.")
    data = returns.copy()
    data.index = pd.to_datetime(data.index)
    data = data.sort_index().dropna(how="all")
    if data.empty:
        raise ValueError("Return data is empty after dropping all-NA rows.")
    return data


def monthly_window_ends(returns: pd.DataFrame) -> pd.DatetimeIndex:
    data = ensure_datetime_index(returns)
    return pd.DatetimeIndex(data.groupby(data.index.to_period("M")).tail(1).index)


def next_trading_day(index: pd.DatetimeIndex, after: pd.Timestamp, inclusive: bool = False) -> pd.Timestamp:
    idx = pd.DatetimeIndex(pd.to_datetime(index)).sort_values()
    later = idx[idx >= after] if inclusive else idx[idx > after]
    if later.empty:
        raise ValueError(f"No trading day exists after {pd.Timestamp(after).date()}.")
    return pd.Timestamp(later[0])


def _window_start(returns: pd.DataFrame, month_ends: pd.DatetimeIndex, start_idx: int) -> pd.Timestamp:
    if start_idx == 0:
        return pd.Timestamp(returns.index[0])
    return next_trading_day(returns.index, month_ends[start_idx - 1])


def generate_walkforward_splits(
    returns: pd.DataFrame,
    train_months: int = 24,
    validation_months: int = 6,
    test_months: int = 3,
    step_months: int = 3,
    max_splits: int | None = None,
) -> list[dict[str, pd.Timestamp]]:
    data = ensure_datetime_index(returns)
    month_ends = monthly_window_ends(data)
    total = train_months + validation_months + test_months
    if len(month_ends) < total:
        raise ValueError(f"Not enough monthly data: need {total} months, found {len(month_ends)}.")
    splits = []
    for start_idx in range(0, len(month_ends) - total + 1, step_months):
        train_end = pd.Timestamp(month_ends[start_idx + train_months - 1])
        validation_end = pd.Timestamp(month_ends[start_idx + train_months + validation_months - 1])
        test_end = pd.Timestamp(month_ends[start_idx + total - 1])
        split = {
            "split_id": f"wf_{len(splits) + 1:02d}",
            "train_start": _window_start(data, month_ends, start_idx),
            "train_end": train_end,
            "validation_start": next_trading_day(data.index, train_end),
            "validation_end": validation_end,
            "test_start": next_trading_day(data.index, validation_end),
            "test_end": test_end,
        }
        splits.append(split)
        if max_splits is not None and len(splits) >= max_splits:
            break
    return splits


def generate_nested_splits(
    returns: pd.DataFrame,
    train_months: int = 24,
    validation_months: int = 6,
    test_months: int = 3,
    step_months: int = 3,
    max_splits: int | None = None,
) -> list[dict[str, pd.Timestamp]]:
    splits = generate_walkforward_splits(
        returns,
        train_months=train_months,
        validation_months=validation_months,
        test_months=test_months,
        step_months=step_months,
        max_splits=max_splits,
    )
    for i, split in enumerate(splits, start=1):
        split["split_id"] = f"nested_{i:02d}"
    return splits


def generate_frozen_oos_split(
    returns: pd.DataFrame,
    frozen_start: str | pd.Timestamp = "2025-01-01",
) -> dict[str, pd.Timestamp]:
    data = ensure_datetime_index(returns)
    requested = pd.Timestamp(frozen_start)
    test_start = next_trading_day(data.index, requested, inclusive=True)
    train = data[data.index < test_start]
    test = data[data.index >= test_start]
    if train.empty or test.empty:
        raise ValueError("Frozen OOS split requires non-empty pre-frozen and frozen periods.")
    return {
        "split_id": "frozen_oos",
        "train_start": pd.Timestamp(train.index.min()),
        "train_end": pd.Timestamp(train.index.max()),
        "test_start": pd.Timestamp(test.index.min()),
        "test_end": pd.Timestamp(test.index.max()),
        "requested_frozen_start": requested,
    }


def generate_cscv_splits(
    returns: pd.DataFrame,
    num_blocks: int = 8,
    max_combinations: int | None = None,
) -> tuple[list[dict[str, pd.Timestamp]], list[dict]]:
    data = ensure_datetime_index(returns)
    if num_blocks < 4 or num_blocks % 2 != 0:
        raise ValueError("CSCV requires an even num_blocks of at least 4.")
    blocks = []
    positions = np.array_split(np.arange(len(data)), num_blocks)
    for i, pos in enumerate(positions):
        if len(pos) == 0:
            raise ValueError("Not enough rows to create CSCV blocks.")
        blocks.append(
            {
                "block_id": i,
                "start": pd.Timestamp(data.index[pos[0]]),
                "end": pd.Timestamp(data.index[pos[-1]]),
            }
        )
    combos = []
    half = num_blocks // 2
    all_combos = list(itertools.combinations(range(num_blocks), half))
    seen = set()
    for combo in all_combos:
        is_blocks = tuple(combo)
        oos_blocks = tuple(i for i in range(num_blocks) if i not in is_blocks)
        key = tuple(sorted([is_blocks, oos_blocks]))
        if key in seen:
            continue
        seen.add(key)
        combos.append(
            {
                "split_id": f"cscv_{len(combos) + 1:03d}",
                "in_sample_blocks": is_blocks,
                "out_of_sample_blocks": oos_blocks,
            }
        )
        if max_combinations is not None and len(combos) >= max_combinations:
            break
    return blocks, combos


def cvar(returns: pd.Series, beta: float = 0.95) -> float:
    losses = -pd.Series(returns).dropna()
    if losses.empty:
        return 0.0
    var = losses.quantile(beta)
    tail = losses[losses >= var]
    return float(tail.mean()) if not tail.empty else float(var)


def result_window_metrics(
    result: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    config: dict | None = None,
) -> dict:
    cfg = config or {}
    data = result.copy()
    data["date"] = pd.to_datetime(data["date"])
    data = data[(data["date"] >= pd.Timestamp(start)) & (data["date"] <= pd.Timestamp(end))].copy()
    if data.empty:
        raise ValueError(f"No backtest rows found between {pd.Timestamp(start).date()} and {pd.Timestamp(end).date()}.")
    net_returns = data["net_return"] if "net_return" in data else data["portfolio_return"]
    nav = (1.0 + net_returns.fillna(0.0)).cumprod()
    nav.index = pd.to_datetime(data["date"])
    metrics = calculate_metrics(nav, cfg.get("risk_free_rate", 0.0), cfg.get("trading_days_per_year", 243))
    dates = pd.to_datetime(data["date"])
    years = max((dates.max() - dates.min()).days / 365.25, 1.0 / 12.0)
    months = max(len(dates.dt.to_period("M").unique()), 1)
    turnover = data["turnover"].fillna(0.0) if "turnover" in data else pd.Series(0.0, index=data.index)
    return {
        "net_annual_return": float(metrics["annualized_return"]),
        "annual_volatility": float(metrics["annualized_volatility"]),
        "sharpe": float(metrics["sharpe_ratio"]),
        "calmar": float(metrics["calmar_ratio"]),
        "max_drawdown": float(metrics["max_drawdown"]),
        "cvar": cvar(net_returns, 0.95),
        "annual_turnover": float(turnover.sum() / years),
        "avg_monthly_turnover": float(turnover.sum() / months),
        "total_return": float(metrics["total_return"]),
    }


def validation_score(metrics: dict, fallback_rate: float = 0.0) -> float:
    drawdown_penalty = abs(min(float(metrics.get("max_drawdown", 0.0)), 0.0))
    turnover_penalty = float(metrics.get("avg_monthly_turnover", 0.0))
    cvar_penalty = float(metrics.get("cvar", 0.0))
    return float(
        metrics.get("sharpe", 0.0)
        + 0.35 * metrics.get("calmar", 0.0)
        - 2.0 * drawdown_penalty
        - 0.25 * turnover_penalty
        - 10.0 * cvar_penalty
        - 0.5 * fallback_rate
    )


def candidate_params(cfg) -> dict:
    return asdict(cfg) if hasattr(cfg, "__dataclass_fields__") else dict(cfg)


def candidate_params_json(cfg) -> str:
    return json.dumps(candidate_params(cfg), sort_keys=True, ensure_ascii=False, default=str)


def config_fields(candidate_id: str, cfg) -> dict:
    params = candidate_params(cfg)
    fields = {
        "selected_candidate_id": candidate_id,
        "selected_params_json": candidate_params_json(cfg),
        "group_bounds_json": json.dumps(params.get("group_bounds", {}), sort_keys=True, ensure_ascii=False, default=str),
    }
    for key in [
        "lookback_days",
        "covariance_method",
        "max_weight",
        "turnover_cap",
        "turnover_penalty",
        "cvar_penalty",
        "budget_penalty",
        "cvar_beta",
        "return_reward",
        "transaction_cost_bps",
    ]:
        fields[key] = params.get(key)
    return fields


def metadata_columns(metadata: dict) -> dict:
    return {key: value for key, value in metadata.items() if value is not None}


def evaluate_candidate_window(
    returns: pd.DataFrame,
    cfg,
    history_start: pd.Timestamp,
    history_end: pd.Timestamp,
    metric_start: pd.Timestamp,
    metric_end: pd.Timestamp,
    config: dict | None = None,
) -> tuple[dict, float, pd.DataFrame]:
    from src.convex_adaptive_rrp import run_convex_adaptive_backtest

    data = ensure_datetime_index(returns)
    history = data[(data.index >= pd.Timestamp(history_start)) & (data.index <= pd.Timestamp(history_end))]
    if history.empty:
        raise ValueError("Candidate evaluation history is empty.")
    result, solver_diag, _, _ = run_convex_adaptive_backtest(history, cfg)
    metrics = result_window_metrics(result, metric_start, metric_end, config)
    fallback_rate = float(solver_diag["fallback_used"].mean()) if not solver_diag.empty and "fallback_used" in solver_diag else 0.0
    return metrics, fallback_rate, result


def select_candidate(
    returns: pd.DataFrame,
    candidates: list[tuple[str, object]],
    history_start: pd.Timestamp,
    history_end: pd.Timestamp,
    metric_start: pd.Timestamp,
    metric_end: pd.Timestamp,
    config: dict | None = None,
) -> tuple[tuple[str, object], dict, float, float, pd.DataFrame]:
    rows = []
    for candidate_id, cfg in candidates:
        metrics, fallback_rate, result = evaluate_candidate_window(
            returns,
            cfg,
            history_start,
            history_end,
            metric_start,
            metric_end,
            config,
        )
        rows.append((validation_score(metrics, fallback_rate), candidate_id, cfg, metrics, fallback_rate, result))
    if not rows:
        raise ValueError("No candidate configurations were available for validation.")
    rows.sort(key=lambda row: row[0], reverse=True)
    score, candidate_id, cfg, metrics, fallback_rate, result = rows[0]
    return (candidate_id, cfg), metrics, fallback_rate, score, result


def summarize_validation_rows(rows: pd.DataFrame, prefix: str = "test") -> pd.DataFrame:
    if rows.empty:
        raise ValueError("Cannot summarize an empty validation table.")
    metric_cols = [col for col in rows.columns if col.startswith(f"{prefix}_") and pd.api.types.is_numeric_dtype(rows[col])]
    summary_rows = []
    for col in metric_cols:
        series = rows[col].dropna()
        if series.empty:
            continue
        summary_rows.append(
            {
                "metric": col,
                "mean": float(series.mean()),
                "median": float(series.median()),
                "std": float(series.std(ddof=0)),
                "min": float(series.min()),
                "max": float(series.max()),
                "count": int(series.count()),
                "validation_status": VALIDATION_STATUS,
            }
        )
    return pd.DataFrame(summary_rows)


def validation_run_metadata(
    *,
    validation_method: str,
    validation_kind: str,
    eval_start: pd.Timestamp | str | None,
    eval_end: pd.Timestamp | str | None,
    selection_rule: str,
    limitations: str,
    candidate_count: int | None = None,
    num_splits: int | None = None,
    num_blocks: int | None = None,
    num_combinations: int | None = None,
    requested_eval_start: pd.Timestamp | str | None = None,
    requested_frozen_start: pd.Timestamp | str | None = None,
    **extra: object,
) -> dict:
    def iso_date(value: pd.Timestamp | str | None) -> str | None:
        if value is None:
            return None
        return pd.Timestamp(value).date().isoformat()

    metadata = {
        "validation_method": validation_method,
        "validation_kind": validation_kind,
        "requested_eval_start": iso_date(requested_eval_start),
        "eval_start": iso_date(eval_start),
        "eval_end": iso_date(eval_end),
        "candidate_count": candidate_count,
        "num_splits": num_splits,
        "num_blocks": num_blocks,
        "num_combinations": num_combinations,
        "selection_rule": selection_rule,
        "limitations": limitations,
    }
    if requested_frozen_start is not None:
        metadata["requested_frozen_start"] = iso_date(requested_frozen_start)
    metadata.update(extra)
    return metadata


def pbo_from_cscv(score_rows: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if score_rows.empty:
        raise ValueError("CSCV score table is empty.")
    required = {"split_id", "candidate_id", "is_score", "oos_score"}
    missing = required - set(score_rows.columns)
    if missing:
        raise ValueError(f"CSCV score table is missing columns: {sorted(missing)}")
    rows = []
    for split_id, group in score_rows.groupby("split_id"):
        ranked = group.sort_values("is_score", ascending=False).reset_index(drop=True)
        winner = ranked.iloc[0]
        oos_ranked = group.sort_values("oos_score", ascending=False).reset_index(drop=True)
        candidate_order = list(oos_ranked["candidate_id"])
        rank = candidate_order.index(winner["candidate_id"]) + 1
        n = len(candidate_order)
        relative_rank = rank / n
        percentile = 1.0 - (rank - 1) / max(n - 1, 1)
        clipped = min(max(percentile, 1e-6), 1.0 - 1e-6)
        rows.append(
            {
                "split_id": split_id,
                "selected_candidate_id": winner["candidate_id"],
                "is_score": float(winner["is_score"]),
                "oos_score": float(winner["oos_score"]),
                "oos_rank": int(rank),
                "candidate_count": int(n),
                "relative_rank": float(relative_rank),
                "logit_rank": float(np.log(clipped / (1.0 - clipped))),
                "pbo_event": bool(relative_rank > 0.5),
                "notes": "CSCV/PBO diagnostic estimate; not proof of future generalization.",
            }
        )
    result = pd.DataFrame(rows)
    summary = pd.DataFrame(
        [
            {
                "num_splits": int(len(result)),
                "pbo": float(result["pbo_event"].mean()),
                "median_logit_rank": float(result["logit_rank"].median()),
                "mean_relative_rank": float(result["relative_rank"].mean()),
                "validation_status": VALIDATION_STATUS,
                "notes": "PBO is a diagnostic estimate, not proof.",
            }
        ]
    )
    return result, summary


def walk_forward_validation(
    returns: pd.DataFrame,
    param_grid: list[dict],
    config: dict,
    train_window_months: int = 24,
    test_window_months: int = 1,
    selection_metric: str = "utility",
    rolling: bool = True,
) -> pd.DataFrame:
    rows = []
    rebalance_dates = monthly_rebalance_dates(returns)
    for i, date in enumerate(rebalance_dates):
        if rolling:
            train_start = date - pd.DateOffset(months=train_window_months)
            df_train = returns[(returns.index >= train_start) & (returns.index < date)]
        else:
            df_train = returns[returns.index < date]
        if len(df_train) < 60:
            continue

        scores = [(score_params(df_train, params, config, selection_metric), params) for params in param_grid]
        scores.sort(key=lambda item: item[0], reverse=True)
        best_score, best_params = scores[0]
        test_end = date + pd.DateOffset(months=test_window_months)
        if i + 1 < len(rebalance_dates):
            test_end = min(test_end, rebalance_dates[i + 1])
        df_test = returns[(returns.index >= date) & (returns.index < test_end)]
        if df_test.empty:
            continue

        rows.append(
            {
                "rebalance_date": date,
                "train_start": df_train.index.min(),
                "train_end": df_train.index.max(),
                "test_start": df_test.index.min(),
                "test_end": df_test.index.max(),
                "selected_lambda": best_params.get("lambda_pen", config.get("lambda_pen")),
                "selected_m": best_params.get("m", config.get("m")),
                "selected_bond_leverage_upper": best_params.get(
                    "bond_leverage_upper",
                    config.get("bond_leverage_upper"),
                ),
                "selection_score": best_score,
                "train_rows": len(df_train),
                "test_rows": len(df_test),
                "uses_future_data": bool(df_train.index.max() >= df_test.index.min()),
            }
        )
    return pd.DataFrame(rows)


def parameter_stability(dynamic_result: pd.DataFrame) -> pd.DataFrame:
    if dynamic_result.empty:
        return pd.DataFrame()
    monthly = dynamic_result.copy()
    monthly["date"] = pd.to_datetime(monthly["date"])
    monthly = monthly.groupby(monthly["date"].dt.to_period("M")).head(1)
    rows = []
    mapping = {
        "avg_selected_lambda": "lambda_pen",
        "avg_selected_m": "m",
        "avg_selected_bond_leverage_upper": "bond_leverage_upper",
        "drawdown_scalar": "drawdown_scale",
        "target_vol_scalar": "vol_scalar",
        "trend_scalar": "trend_scalar",
        "final_risk_scalar": "final_risk_scalar",
        "reentry_state": "reentry_state",
        "gross_exposure": "gross_exposure",
    }
    for col, label in mapping.items():
        if col in monthly:
            series = monthly[col].dropna()
            rows.append(
                {
                    "parameter": label,
                    "mean": series.mean(),
                    "std": series.std(),
                    "min": series.min(),
                    "max": series.max(),
                    "switch_count": int(series.diff().fillna(0.0).ne(0.0).sum()),
                }
            )
    if "turnover_cap_bound" in monthly:
        rows.append(
            {
                "parameter": "turnover_cap_binding_frequency",
                "mean": monthly["turnover_cap_bound"].astype(float).mean(),
                "std": monthly["turnover_cap_bound"].astype(float).std(),
                "min": monthly["turnover_cap_bound"].astype(float).min(),
                "max": monthly["turnover_cap_bound"].astype(float).max(),
                "switch_count": int(monthly["turnover_cap_bound"].astype(int).diff().fillna(0).ne(0).sum()),
            }
        )
    return pd.DataFrame(rows)


def afml_diagnostics(
    performance_summary: pd.DataFrame,
    dynamic_result: pd.DataFrame,
    param_grid: list[dict],
) -> pd.DataFrame:
    rows = []
    for _, row in performance_summary.iterrows():
        sharpe = float(row.get("sharpe_ratio", 0.0))
        rows.append(
            {
                "model": row["model"],
                "raw_sharpe": sharpe,
                "adjusted_sharpe_conservative": adjusted_sharpe(sharpe, len(param_grid)),
                "diagnostic_note": "Conservative multiple-testing adjustment; not full Deflated Sharpe Ratio.",
            }
        )
    if not dynamic_result.empty and "turnover_cap_bound" in dynamic_result:
        rows.append(
            {
                "model": public_model_label("Dynamic_RRP") + " overlay diagnostics",
                "raw_sharpe": np.nan,
                "adjusted_sharpe_conservative": np.nan,
                "diagnostic_note": (
                    f"Turnover cap bound on {dynamic_result['turnover_cap_bound'].astype(float).mean():.1%} "
                    "of rows; simplified diagnostic."
                ),
            }
        )
    return pd.DataFrame(rows)


def simplified_pbo_diagnostic(
    returns: pd.DataFrame,
    param_grid: list[dict],
    config: dict,
    selection_metric: str = "utility",
    max_splits: int = 8,
) -> pd.DataFrame:
    dates = monthly_rebalance_dates(returns)
    rows = []
    usable = dates[24:]
    if len(usable) < 4:
        return pd.DataFrame(rows)

    split_dates = usable[:: max(1, len(usable) // max_splits)][:max_splits]
    for split_date in split_dates:
        train = returns[returns.index < split_date].tail(config["trading_days_per_year"] * 2)
        test = returns[(returns.index >= split_date) & (returns.index < split_date + pd.DateOffset(months=3))]
        if len(train) < 60 or len(test) < 20:
            continue
        train_scores = [(score_params(train, params, config, selection_metric), idx, params) for idx, params in enumerate(param_grid)]
        test_scores = [(score_params(test, params, config, selection_metric), idx, params) for idx, params in enumerate(param_grid)]
        train_scores.sort(reverse=True, key=lambda item: item[0])
        test_scores.sort(reverse=True, key=lambda item: item[0])
        best_idx = train_scores[0][1]
        test_rank = [idx for _, idx, _ in test_scores].index(best_idx) + 1
        rows.append(
            {
                "split_date": split_date,
                "best_train_param_index": best_idx,
                "test_rank_percentile": test_rank / len(param_grid),
                "pbo_event": bool(test_rank > len(param_grid) / 2),
                "label": "Simplified PBO-style diagnostic; not full CSCV.",
            }
        )
    return pd.DataFrame(rows)
