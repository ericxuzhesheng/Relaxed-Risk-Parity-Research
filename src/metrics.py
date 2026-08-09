import numpy as np
import pandas as pd


def _aligned_risk_free_returns(
    returns: pd.Series,
    risk_free_returns: pd.Series | float | int | None,
) -> pd.Series:
    if risk_free_returns is None:
        from src.risk_free import load_daily_risk_free_returns

        return load_daily_risk_free_returns(returns.index)
    if np.isscalar(risk_free_returns):
        if float(risk_free_returns) != 0.0:
            raise TypeError("risk_free_returns must be a daily risk-free return Series, not a nonzero scalar")
        return pd.Series(0.0, index=returns.index, name="risk_free_return")
    series = pd.Series(risk_free_returns, dtype=float).sort_index()
    if not isinstance(series.index, pd.DatetimeIndex):
        series.index = pd.to_datetime(series.index)
    aligned = series.reindex(returns.index)
    if aligned.isna().any():
        dates = aligned.index[aligned.isna()].strftime("%Y-%m-%d").tolist()
        raise ValueError(f"daily risk-free returns missing dates: {dates[:5]}")
    return aligned


def calculate_metrics(
    nav_series: pd.Series,
    risk_free_returns: pd.Series | float | int | None = None,
    trading_days: int = 243,
) -> dict:
    nav_series = pd.Series(nav_series, dtype=float).sort_index()
    returns = nav_series.pct_change().dropna()
    rf = _aligned_risk_free_returns(returns, risk_free_returns)
    excess_returns = returns - rf
    total_return = nav_series.iloc[-1] / nav_series.iloc[0] - 1
    annualized_return = (1 + total_return) ** (trading_days / len(nav_series)) - 1
    annualized_vol = returns.std() * np.sqrt(trading_days)
    sharpe = excess_returns.mean() / returns.std() * np.sqrt(trading_days) if annualized_vol > 0 else 0.0
    downside = excess_returns.clip(upper=0.0)
    downside_deviation = float(np.sqrt(downside.pow(2).mean()))
    sortino = (
        excess_returns.mean() / downside_deviation * np.sqrt(trading_days)
        if downside_deviation > 0
        else 0.0
    )
    
    max_drawdown = (nav_series / nav_series.cummax() - 1).min()
    calmar = annualized_return / abs(max_drawdown) if max_drawdown != 0 else 0
    
    return {
        "annualized_return": annualized_return,
        "annualized_volatility": annualized_vol,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "max_drawdown": max_drawdown,
        "calmar_ratio": calmar,
        "total_return": total_return
    }

def calculate_turnover(weights_df: pd.DataFrame) -> float:
    diff = weights_df.diff().abs().sum(axis=1)
    return diff.mean()


def calculate_annualized_turnover(turnover: pd.Series, rebalance_freq: int = 12) -> float:
    """Annualize a per-rebalance turnover series.

    Args:
        turnover: one value per rebalance event (e.g. monthly series)
        rebalance_freq: number of rebalance events per year (12 for monthly)
    """
    turnover = pd.Series(turnover).fillna(0.0)
    if turnover.empty:
        return 0.0
    return float(turnover.mean() * rebalance_freq)


def drawdown_series(nav_series: pd.Series) -> pd.Series:
    return nav_series / nav_series.cummax() - 1.0


def add_turnover_adjusted_metrics(
    metrics: dict,
    turnover: pd.Series,
    transaction_cost_bps: float = 3.0,
    trading_days: int = 243,
    rebalance_freq: int = 12,
) -> dict:
    adjusted = metrics.copy()
    annual_cost = calculate_annualized_turnover(turnover, rebalance_freq) * transaction_cost_bps / 10000.0
    adjusted["annualized_turnover"] = calculate_annualized_turnover(turnover, rebalance_freq)
    adjusted["turnover_adjusted_return"] = adjusted["annualized_return"] - annual_cost
    vol = adjusted.get("annualized_volatility", 0.0)
    adjusted["turnover_adjusted_sharpe"] = (
        adjusted["turnover_adjusted_return"] / vol if vol and vol > 0 else 0.0
    )
    return adjusted
