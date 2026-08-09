"""AFML-inspired, strictly past-only OOS parameter selection utilities.

The public path uses quarterly test windows.  Each candidate is scored on the
completed six-month validation window immediately before the test window, with
one trading day embargo by default.  Pre-evaluation data may warm the candidate
paths, but no test-window observation is used for selection.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pandas as pd

from src.validation import result_window_metrics, validation_score


def _first_on_or_after(index: pd.DatetimeIndex, date: pd.Timestamp) -> pd.Timestamp:
    values = index[index >= date]
    if values.empty:
        raise ValueError(f"no trading observation exists on or after {date.date()}")
    return pd.Timestamp(values[0])


def _last_on_or_before(index: pd.DatetimeIndex, date: pd.Timestamp) -> pd.Timestamp:
    values = index[index <= date]
    if values.empty:
        raise ValueError(f"no trading observation exists on or before {date.date()}")
    return pd.Timestamp(values[-1])


def generate_quarterly_oos_windows(
    returns: pd.DataFrame,
    *,
    evaluation_start: str | pd.Timestamp,
    evaluation_end: str | pd.Timestamp,
    train_months: int = 24,
    validation_months: int = 6,
    embargo_trading_days: int = 1,
) -> list[dict[str, pd.Timestamp | str | int | bool]]:
    """Create consecutive quarterly OOS windows, including a partial final quarter."""
    if returns.empty:
        raise ValueError("returns are empty")
    if train_months < 1 or validation_months < 1:
        raise ValueError("train_months and validation_months must be positive")
    if embargo_trading_days < 0:
        raise ValueError("embargo_trading_days cannot be negative")

    index = pd.DatetimeIndex(pd.to_datetime(returns.index)).sort_values().unique()
    start = pd.Timestamp(evaluation_start)
    end = pd.Timestamp(evaluation_end)
    if start > end:
        raise ValueError("evaluation_start must not exceed evaluation_end")
    available = index[(index >= start) & (index <= end)]
    if available.empty or available[0] != start or available[-1] != end:
        raise ValueError("evaluation boundaries must be available trading observations")

    first_quarter = start.to_period("Q").start_time
    quarter_starts = pd.date_range(first_quarter, end, freq="QS")
    windows: list[dict[str, pd.Timestamp | str | int | bool]] = []
    for number, quarter_start in enumerate(quarter_starts, start=1):
        quarter_end = quarter_start.to_period("Q").end_time.normalize()
        test_start = _first_on_or_after(index, max(start, quarter_start))
        test_end = _last_on_or_before(index, min(end, quarter_end))

        prior = index[index < test_start]
        if len(prior) <= embargo_trading_days:
            raise ValueError(f"insufficient pre-test observations for {test_start.date()}")
        if embargo_trading_days:
            embargo = prior[-embargo_trading_days:]
            validation_end = pd.Timestamp(prior[-embargo_trading_days - 1])
            embargo_start = pd.Timestamp(embargo[0])
            embargo_end = pd.Timestamp(embargo[-1])
        else:
            validation_end = pd.Timestamp(prior[-1])
            embargo_start = pd.NaT
            embargo_end = pd.NaT

        validation_calendar_start = quarter_start - pd.DateOffset(months=validation_months)
        validation_start = _first_on_or_after(index, validation_calendar_start)
        train_calendar_start = quarter_start - pd.DateOffset(months=train_months + validation_months)
        train_start = _first_on_or_after(index, train_calendar_start)
        train_end = _last_on_or_before(index, validation_start - pd.Timedelta(days=1))
        if not (train_start <= train_end < validation_start <= validation_end < test_start <= test_end):
            raise ValueError(f"invalid chronological OOS window beginning {test_start.date()}")

        windows.append(
            {
                "split_id": f"afml_oos_{number:02d}",
                "train_start": train_start,
                "train_end": train_end,
                "validation_start": validation_start,
                "validation_end": validation_end,
                "embargo_start": embargo_start,
                "embargo_end": embargo_end,
                "embargo_trading_days": embargo_trading_days,
                "test_start": test_start,
                "test_end": test_end,
                "uses_future_data": False,
            }
        )

    covered = pd.DatetimeIndex([])
    for window in windows:
        covered = covered.append(index[(index >= window["test_start"]) & (index <= window["test_end"])])
    if not covered.equals(available):
        raise ValueError("OOS test windows do not cover the evaluation index exactly once")
    return windows


def score_oos_candidates(
    windows: Sequence[Mapping[str, object]],
    candidate_results: Mapping[str, pd.DataFrame],
    candidate_solver_diagnostics: Mapping[str, pd.DataFrame],
    *,
    risk_free_returns: pd.Series | float | int | None = None,
    trading_days_per_year: int = 243,
) -> pd.DataFrame:
    """Score every candidate using only each completed validation window."""
    rows: list[dict[str, object]] = []
    for window in windows:
        validation_start = pd.Timestamp(window["validation_start"])
        validation_end = pd.Timestamp(window["validation_end"])
        test_start = pd.Timestamp(window["test_start"])
        if validation_end >= test_start:
            raise ValueError("validation data overlaps the OOS test window")
        for candidate_id, result in candidate_results.items():
            if candidate_id not in candidate_solver_diagnostics:
                raise ValueError(f"missing solver diagnostics for {candidate_id}")
            metrics = result_window_metrics(
                result,
                validation_start,
                validation_end,
                {
                    "risk_free_rate": risk_free_returns,
                    "trading_days_per_year": trading_days_per_year,
                },
            )
            solver = candidate_solver_diagnostics[candidate_id].copy()
            if not solver.empty:
                solver["date"] = pd.to_datetime(solver["date"])
                solver = solver[(solver["date"] >= validation_start) & (solver["date"] <= validation_end)]
            fallback_rate = (
                float(solver["fallback_used"].fillna(False).mean())
                if not solver.empty and "fallback_used" in solver
                else 0.0
            )
            rows.append(
                {
                    **window,
                    "candidate_id": candidate_id,
                    "validation_score": validation_score(metrics, fallback_rate),
                    "validation_solver_fallback_rate": fallback_rate,
                    **{f"validation_{key}": value for key, value in metrics.items()},
                }
            )
    return pd.DataFrame(rows)


def select_oos_candidates(
    windows: Sequence[Mapping[str, object]],
    candidate_results: Mapping[str, pd.DataFrame],
    candidate_solver_diagnostics: Mapping[str, pd.DataFrame],
    *,
    risk_free_returns: pd.Series | float | int | None = None,
    trading_days_per_year: int = 243,
) -> pd.DataFrame:
    """Return the deterministic highest-scoring past-only candidate per OOS window."""
    scores = score_oos_candidates(
        windows,
        candidate_results,
        candidate_solver_diagnostics,
        risk_free_returns=risk_free_returns,
        trading_days_per_year=trading_days_per_year,
    )
    return select_oos_candidates_from_scores(scores)


def select_oos_candidates_from_scores(scores: pd.DataFrame) -> pd.DataFrame:
    """Choose one deterministic winner per OOS split from an audited score table."""
    if scores.empty:
        raise ValueError("OOS candidate score table is empty")
    ordered = scores.sort_values(
        ["split_id", "validation_score", "candidate_id"],
        ascending=[True, False, True],
        kind="mergesort",
    )
    selected = ordered.groupby("split_id", sort=False, as_index=False).head(1).copy()
    selected = selected.rename(columns={"candidate_id": "selected_candidate_id"})
    selected["uses_future_data"] = False
    selected["selection_rule"] = "highest past-only validation score; candidate_id breaks exact ties"
    selected["validation_status"] = "strict_rolling_oos_no_test_reselection"
    return selected.reset_index(drop=True)
