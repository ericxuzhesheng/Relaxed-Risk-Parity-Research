"""AFML-inspired, strictly past-only OOS parameter selection utilities.

The public path uses quarterly test windows.  Each candidate is scored on the
completed six-month validation window immediately before the test window, with
one trading day embargo by default.  Pre-evaluation data may warm the candidate
paths, but no test-window observation is used for selection.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from statistics import NormalDist

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
    required = {
        "split_id",
        "candidate_id",
        "validation_score",
        "validation_solver_fallback_rate",
    }
    missing = sorted(required.difference(scores.columns))
    if missing:
        raise ValueError(f"OOS candidate score table is missing columns: {missing}")

    selected_rows: list[pd.Series] = []
    gate_passed: list[bool] = []
    for _, split_scores in scores.groupby("split_id", sort=False):
        fallback_rates = pd.to_numeric(
            split_scores["validation_solver_fallback_rate"], errors="coerce"
        )
        if fallback_rates.isna().any() or (fallback_rates < 0.0).any():
            raise ValueError("Validation solver fallback rates must be finite and non-negative")

        zero_fallback = fallback_rates <= 1e-12
        if zero_fallback.any():
            eligible = split_scores.loc[zero_fallback]
            split_gate_passed = True
        else:
            minimum_fallback = float(fallback_rates.min())
            eligible = split_scores.loc[fallback_rates <= minimum_fallback + 1e-12]
            split_gate_passed = False

        winner = eligible.sort_values(
            ["validation_score", "candidate_id"],
            ascending=[False, True],
            kind="mergesort",
        ).iloc[0]
        selected_rows.append(winner)
        gate_passed.append(split_gate_passed)

    selected = pd.DataFrame(selected_rows).reset_index(drop=True)
    selected = selected.rename(columns={"candidate_id": "selected_candidate_id"})
    selected["uses_future_data"] = False
    selected["solver_gate_passed"] = pd.Series(gate_passed, dtype=object)
    selected["selection_rule"] = (
        "prefer zero validation solver fallback; otherwise minimize fallback rate; "
        "then maximize past-only validation score; candidate_id breaks exact ties"
    )
    selected["validation_status"] = "strict_rolling_oos_no_test_reselection"
    return selected.reset_index(drop=True)


def _annualized_sharpe_standard_error(
    annualized_sharpe: float,
    observations: int,
    trading_days_per_year: int,
) -> float:
    """Return the normal-approximation standard error of annualized Sharpe."""
    if observations < 2:
        raise ValueError("Sharpe comparison requires at least two validation observations")
    daily_sharpe = float(annualized_sharpe) / trading_days_per_year**0.5
    daily_se = ((1.0 + 0.5 * daily_sharpe**2) / (observations - 1)) ** 0.5
    return float(daily_se * trading_days_per_year**0.5)


def select_public_low_turnover_oos_candidates(
    scores: pd.DataFrame,
    *,
    eligible_candidate_ids: Sequence[str],
    turnover_limit: float = 0.02,
    switch_confidence: float = 0.95,
    trading_days_per_year: int = 243,
) -> pd.DataFrame:
    """Select the public low-turnover candidate with statistical switch hysteresis.

    The first window initializes from the highest cost-adjusted validation
    Sharpe among the pre-declared low-turnover family.  Later windows retain
    the incumbent unless a zero-fallback, turnover-compliant challenger has a
    one-sided Sharpe improvement above the requested confidence threshold.
    """
    required = {
        "split_id",
        "candidate_id",
        "validation_sharpe",
        "validation_avg_monthly_turnover",
        "validation_solver_fallback_rate",
        "validation_observations",
        "test_start",
        "test_end",
    }
    missing = sorted(required.difference(scores.columns))
    if missing:
        raise ValueError(f"Public OOS score table is missing columns: {missing}")
    if not eligible_candidate_ids:
        raise ValueError("Public low-turnover candidate family is empty")
    if turnover_limit < 0.0:
        raise ValueError("turnover_limit cannot be negative")
    if not 0.5 < switch_confidence < 1.0:
        raise ValueError("switch_confidence must be between 0.5 and 1.0")

    eligible_ids = set(eligible_candidate_ids)
    preference_rank = {
        candidate_id: rank for rank, candidate_id in enumerate(eligible_candidate_ids)
    }
    ordered_scores = scores.copy()
    ordered_scores["test_start"] = pd.to_datetime(ordered_scores["test_start"])
    ordered_scores = ordered_scores.sort_values(
        ["test_start", "split_id", "candidate_id"], kind="mergesort"
    )
    z_score = NormalDist().inv_cdf(switch_confidence)
    incumbent_id: str | None = None
    selected_rows: list[pd.Series] = []

    for _, all_split_scores in ordered_scores.groupby("split_id", sort=False):
        family_scores = all_split_scores[
            all_split_scores["candidate_id"].isin(eligible_ids)
        ].copy()
        if family_scores.empty:
            raise ValueError("No public low-turnover candidates exist in an OOS split")

        fallback_rates = pd.to_numeric(
            family_scores["validation_solver_fallback_rate"], errors="coerce"
        )
        if fallback_rates.isna().any() or (fallback_rates < 0.0).any():
            raise ValueError("Validation solver fallback rates must be finite and non-negative")
        zero_fallback = fallback_rates <= 1e-12
        if zero_fallback.any():
            solver_eligible = family_scores.loc[zero_fallback]
            solver_gate_passed = True
        else:
            minimum_fallback = float(fallback_rates.min())
            solver_eligible = family_scores.loc[fallback_rates <= minimum_fallback + 1e-12]
            solver_gate_passed = False

        low_turnover = solver_eligible[
            pd.to_numeric(
                solver_eligible["validation_avg_monthly_turnover"], errors="coerce"
            )
            <= turnover_limit + 1e-12
        ]
        turnover_gate_passed = not low_turnover.empty
        challenger_pool = low_turnover if turnover_gate_passed else solver_eligible
        challenger = challenger_pool.sort_values(
            ["validation_sharpe", "validation_avg_monthly_turnover", "candidate_id"],
            ascending=[False, True, True],
            kind="mergesort",
        ).iloc[0]

        incumbent_before = incumbent_id
        sharpe_improvement = 0.0
        switch_threshold = 0.0
        initialization_confidence_set_size = 0
        if incumbent_id is None:
            challenger_se = _annualized_sharpe_standard_error(
                float(challenger["validation_sharpe"]),
                int(challenger["validation_observations"]),
                trading_days_per_year,
            )
            confidence_rows = []
            for _, candidate in challenger_pool.iterrows():
                candidate_se = _annualized_sharpe_standard_error(
                    float(candidate["validation_sharpe"]),
                    int(candidate["validation_observations"]),
                    trading_days_per_year,
                )
                confidence_threshold = z_score * (
                    challenger_se**2 + candidate_se**2
                ) ** 0.5
                if (
                    float(challenger["validation_sharpe"])
                    - float(candidate["validation_sharpe"])
                    <= confidence_threshold
                ):
                    confidence_rows.append(candidate)
            confidence_set = pd.DataFrame(confidence_rows)
            initialization_confidence_set_size = len(confidence_set)
            confidence_set["_preference_rank"] = confidence_set["candidate_id"].map(
                preference_rank
            )
            winner = confidence_set.sort_values(
                ["_preference_rank", "validation_avg_monthly_turnover", "candidate_id"],
                ascending=[True, True, True],
                kind="mergesort",
            ).iloc[0]
            winner = winner.drop(labels=["_preference_rank"])
            switch_threshold = z_score * (
                challenger_se**2
                + _annualized_sharpe_standard_error(
                    float(winner["validation_sharpe"]),
                    int(winner["validation_observations"]),
                    trading_days_per_year,
                )
                ** 2
            ) ** 0.5
            selection_action = "initialize"
        else:
            incumbent_rows = family_scores[family_scores["candidate_id"].eq(incumbent_id)]
            if incumbent_rows.empty:
                winner = challenger
                selection_action = "switch_missing_incumbent"
            else:
                incumbent = incumbent_rows.iloc[0]
                incumbent_fallback = float(incumbent["validation_solver_fallback_rate"])
                if solver_gate_passed and incumbent_fallback > 1e-12:
                    winner = challenger
                    selection_action = "switch_solver_gate"
                elif str(challenger["candidate_id"]) == incumbent_id:
                    winner = incumbent
                    selection_action = "retain_incumbent"
                elif not turnover_gate_passed:
                    winner = incumbent
                    selection_action = "retain_turnover_gate"
                else:
                    sharpe_improvement = float(
                        challenger["validation_sharpe"] - incumbent["validation_sharpe"]
                    )
                    challenger_se = _annualized_sharpe_standard_error(
                        float(challenger["validation_sharpe"]),
                        int(challenger["validation_observations"]),
                        trading_days_per_year,
                    )
                    incumbent_se = _annualized_sharpe_standard_error(
                        float(incumbent["validation_sharpe"]),
                        int(incumbent["validation_observations"]),
                        trading_days_per_year,
                    )
                    switch_threshold = z_score * (challenger_se**2 + incumbent_se**2) ** 0.5
                    if sharpe_improvement > switch_threshold:
                        winner = challenger
                        selection_action = "switch_significant_sharpe"
                    else:
                        winner = incumbent
                        selection_action = "retain_incumbent"

        incumbent_id = str(winner["candidate_id"])
        audited = winner.copy()
        audited["incumbent_candidate_id"] = incumbent_before
        audited["challenger_candidate_id"] = str(challenger["candidate_id"])
        audited["selected_candidate_id"] = incumbent_id
        audited["solver_gate_passed"] = bool(solver_gate_passed)
        audited["turnover_gate_passed"] = bool(turnover_gate_passed)
        audited["selection_action"] = selection_action
        audited["initialization_confidence_set_size"] = initialization_confidence_set_size
        audited["sharpe_improvement"] = sharpe_improvement
        audited["sharpe_switch_threshold"] = switch_threshold
        selected_rows.append(audited)

    selected = pd.DataFrame(selected_rows).reset_index(drop=True)
    selected = selected.drop(columns=["candidate_id"], errors="ignore")
    selected["uses_future_data"] = False
    selected["selection_rule"] = (
        "predeclared low-turnover family; zero solver fallback; validation monthly turnover "
        f"at most {turnover_limit:.2%}; maximize past-only net Sharpe; switch only when the "
        f"one-sided Sharpe improvement exceeds the {switch_confidence:.0%} threshold"
    )
    selected["validation_status"] = "strict_rolling_oos_no_test_reselection"
    return selected
