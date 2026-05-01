from __future__ import annotations

import numpy as np
import pandas as pd

from src.dynamic_selection import monthly_rebalance_dates, score_params
from src.metrics import calculate_metrics


def adjusted_sharpe(
    sharpe: float,
    n_trials: int,
    skew: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    multiple_testing_penalty = 0.10 * np.sqrt(max(np.log(max(n_trials, 1)), 0.0))
    non_normality_penalty = 0.025 * abs(skew) + 0.005 * max(kurtosis - 3.0, 0.0)
    return float(sharpe - multiple_testing_penalty - non_normality_penalty)


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
                "model": "Dynamic_RRP_overlay",
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
