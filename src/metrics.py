import numpy as np
import pandas as pd

def calculate_metrics(nav_series: pd.Series, risk_free_rate: float = 0.0, trading_days: int = 243) -> dict:
    returns = nav_series.pct_change().dropna()
    total_return = nav_series.iloc[-1] / nav_series.iloc[0] - 1
    annualized_return = (1 + total_return) ** (trading_days / len(nav_series)) - 1
    annualized_vol = returns.std() * np.sqrt(trading_days)
    sharpe = (annualized_return - risk_free_rate) / annualized_vol if annualized_vol > 0 else 0
    downside = returns[returns < 0.0]
    downside_vol = downside.std() * np.sqrt(trading_days) if len(downside) > 1 else 0.0
    sortino = (annualized_return - risk_free_rate) / downside_vol if downside_vol > 0 else 0.0
    
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


def calculate_annualized_turnover(turnover: pd.Series, trading_days: int = 243) -> float:
    turnover = pd.Series(turnover).fillna(0.0)
    if turnover.empty:
        return 0.0
    return float(turnover.mean() * trading_days)


def drawdown_series(nav_series: pd.Series) -> pd.Series:
    return nav_series / nav_series.cummax() - 1.0


def add_turnover_adjusted_metrics(
    metrics: dict,
    turnover: pd.Series,
    transaction_cost_bps: float = 3.0,
    trading_days: int = 243,
) -> dict:
    adjusted = metrics.copy()
    annual_cost = calculate_annualized_turnover(turnover, trading_days) * transaction_cost_bps / 10000.0
    adjusted["annualized_turnover"] = calculate_annualized_turnover(turnover, trading_days)
    adjusted["turnover_adjusted_return"] = adjusted["annualized_return"] - annual_cost
    vol = adjusted.get("annualized_volatility", 0.0)
    adjusted["turnover_adjusted_sharpe"] = (
        adjusted["turnover_adjusted_return"] / vol if vol and vol > 0 else 0.0
    )
    return adjusted
