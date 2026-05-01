import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, leaves_list
from scipy.spatial.distance import squareform


def _clean_weights(weights: np.ndarray) -> np.ndarray:
    weights = np.asarray(weights, dtype=float)
    weights = np.nan_to_num(weights, nan=0.0, posinf=0.0, neginf=0.0)
    weights = np.clip(weights, 0.0, None)
    total = weights.sum()
    if total <= 0:
        return np.ones_like(weights) / len(weights)
    return weights / total


def estimate_cov_corr(returns: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    clean = returns.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    clean = clean.ffill().bfill().fillna(0.0)
    cov = clean.cov()
    diag = np.diag(cov.values).copy()
    positive = diag[diag > 0]
    floor = positive.min() * 1e-6 if len(positive) else 1e-12
    cov_values = cov.values.copy()
    np.fill_diagonal(cov_values, np.maximum(diag, floor))
    cov = pd.DataFrame(cov_values, index=returns.columns, columns=returns.columns)
    corr = cov_to_corr(cov)
    return cov, corr


def cov_to_corr(cov: pd.DataFrame) -> pd.DataFrame:
    vol = np.sqrt(np.diag(cov.values))
    denom = np.outer(vol, vol)
    corr_values = np.divide(cov.values, denom, out=np.zeros_like(cov.values), where=denom > 0)
    corr_values = np.clip(corr_values, -1.0, 1.0)
    np.fill_diagonal(corr_values, 1.0)
    return pd.DataFrame(corr_values, index=cov.index, columns=cov.columns)


def corr_to_distance(corr: pd.DataFrame) -> pd.DataFrame:
    distance = np.sqrt(np.clip((1.0 - corr.values) / 2.0, 0.0, 1.0))
    np.fill_diagonal(distance, 0.0)
    return pd.DataFrame(distance, index=corr.index, columns=corr.columns)


def _tree_order(corr: pd.DataFrame, method: str = "single") -> list[int]:
    if len(corr) <= 1:
        return list(range(len(corr)))
    distance = corr_to_distance(corr)
    condensed = squareform(distance.values, checks=False)
    link = linkage(condensed, method=method)
    return leaves_list(link).astype(int).tolist()


def _cluster_variance(cov: pd.DataFrame, assets: list[str]) -> float:
    cluster_cov = cov.loc[assets, assets].values
    inv_diag = 1.0 / np.clip(np.diag(cluster_cov), 1e-12, None)
    weights = inv_diag / inv_diag.sum()
    variance = float(weights @ cluster_cov @ weights)
    return max(variance, 1e-12)


def _recursive_allocation(cov: pd.DataFrame, ordered_assets: list[str], mode: str) -> pd.Series:
    weights = pd.Series(1.0, index=ordered_assets, dtype=float)
    clusters = [ordered_assets]
    while clusters:
        next_clusters = []
        for cluster in clusters:
            if len(cluster) <= 1:
                continue
            split = len(cluster) // 2
            left = cluster[:split]
            right = cluster[split:]
            left_var = _cluster_variance(cov, left)
            right_var = _cluster_variance(cov, right)
            if mode == "herc":
                left_vol = np.sqrt(left_var)
                right_vol = np.sqrt(right_var)
                alpha = right_vol / (left_vol + right_vol)
            else:
                alpha = 1.0 - left_var / (left_var + right_var)
            weights.loc[left] *= alpha
            weights.loc[right] *= 1.0 - alpha
            next_clusters.extend([left, right])
        clusters = next_clusters
    return weights


def solve_hrp(returns: pd.DataFrame, linkage_method: str = "single") -> pd.Series:
    cov, corr = estimate_cov_corr(returns)
    ordered_assets = corr.index[_tree_order(corr, linkage_method)].tolist()
    weights = _recursive_allocation(cov, ordered_assets, mode="hrp")
    weights = weights.reindex(returns.columns).fillna(0.0)
    return pd.Series(_clean_weights(weights.values), index=returns.columns)


def solve_herc(returns: pd.DataFrame, linkage_method: str = "single") -> pd.Series:
    cov, corr = estimate_cov_corr(returns)
    ordered_assets = corr.index[_tree_order(corr, linkage_method)].tolist()
    weights = _recursive_allocation(cov, ordered_assets, mode="herc")
    weights = weights.reindex(returns.columns).fillna(0.0)
    return pd.Series(_clean_weights(weights.values), index=returns.columns)
