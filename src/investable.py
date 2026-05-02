from __future__ import annotations

import numpy as np
import pandas as pd


def investable_columns(returns_window: pd.DataFrame, min_observations: int = 30) -> list[str]:
    data = returns_window.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    counts = data.notna().sum()
    has_variance = data.std(skipna=True) > 0.0
    return [col for col in data.columns if counts.get(col, 0) >= min_observations and bool(has_variance.get(col, False))]


def expand_weights(subset_weights, subset_columns, all_columns) -> np.ndarray:
    out = pd.Series(0.0, index=pd.Index(all_columns))
    if subset_weights is not None and len(subset_columns) > 0:
        out.loc[list(subset_columns)] = np.asarray(subset_weights, dtype=float)
    return out.values


def portfolio_return_for_available(row: pd.Series, weights: np.ndarray) -> float:
    values = pd.to_numeric(row, errors="coerce")
    w = pd.Series(np.asarray(weights, dtype=float), index=values.index)
    valid = values.notna() & w.ne(0.0)
    if not valid.any():
        return 0.0
    return float(np.dot(values.loc[valid].values, w.loc[valid].values))
