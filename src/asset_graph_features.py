from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform


def _clean_returns(returns: pd.DataFrame) -> pd.DataFrame:
    data = returns.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    clean = data.dropna(how="any")
    return clean if not clean.empty else data.fillna(0.0)


def rolling_correlation_graph_features(
    window: pd.DataFrame,
    corr_threshold: float = 0.55,
) -> dict:
    """Compute lightweight lagged correlation-graph diagnostics.

    The output is intentionally descriptive. It is suitable as a bounded risk-state
    input, but it does not produce asset selections or portfolio weights.
    """
    data = _clean_returns(window)
    n_assets = len(data.columns)
    if n_assets <= 1 or len(data) < 3:
        return {
            "avg_pairwise_corr": 0.0,
            "avg_abs_corr": 0.0,
            "effective_cluster_count": float(n_assets),
            "largest_cluster_size_ratio": 1.0 if n_assets else 0.0,
            "correlation_stress_score": 0.0,
        }

    corr = data.corr().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    corr_values = np.clip(corr.values, -1.0, 1.0)
    np.fill_diagonal(corr_values, 1.0)
    upper = corr_values[np.triu_indices(n_assets, k=1)]
    avg_pairwise = float(np.mean(upper)) if len(upper) else 0.0
    avg_abs = float(np.mean(np.abs(upper))) if len(upper) else 0.0

    distance = np.sqrt(np.clip((1.0 - corr_values) / 2.0, 0.0, 1.0))
    np.fill_diagonal(distance, 0.0)
    if n_assets == 2:
        clusters = np.array([1, 1 if corr_values[0, 1] >= corr_threshold else 2])
    else:
        link = linkage(squareform(distance, checks=False), method="average")
        clusters = fcluster(link, t=np.sqrt((1.0 - corr_threshold) / 2.0), criterion="distance")
    cluster_sizes = pd.Series(clusters).value_counts()
    effective_clusters = float(len(cluster_sizes))
    largest_ratio = float(cluster_sizes.max() / n_assets)

    concentration = max(0.0, (largest_ratio - 1.0 / n_assets) / max(1.0 - 1.0 / n_assets, 1e-12))
    corr_component = np.clip((avg_abs - 0.20) / 0.60, 0.0, 1.0)
    stress = float(np.clip(0.65 * corr_component + 0.35 * concentration, 0.0, 1.0))

    return {
        "avg_pairwise_corr": avg_pairwise,
        "avg_abs_corr": avg_abs,
        "effective_cluster_count": effective_clusters,
        "largest_cluster_size_ratio": largest_ratio,
        "correlation_stress_score": stress,
    }


def graph_feature_frame(
    returns: pd.DataFrame,
    rebalance_dates: list[pd.Timestamp] | set[pd.Timestamp],
    lookback: int,
    corr_threshold: float = 0.55,
) -> pd.DataFrame:
    rows = []
    for date in sorted(pd.to_datetime(list(rebalance_dates))):
        window = returns[returns.index < date].iloc[-lookback:]
        if len(window) < 3:
            continue
        row = {"date": date}
        row.update(rolling_correlation_graph_features(window, corr_threshold=corr_threshold))
        rows.append(row)
    return pd.DataFrame(rows)
