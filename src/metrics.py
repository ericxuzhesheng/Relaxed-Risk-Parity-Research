import numpy as np
import pandas as pd

def calculate_metrics(nav_series: pd.Series, risk_free_rate: float = 0.0, trading_days: int = 243) -> dict:
    returns = nav_series.pct_change().dropna()
    total_return = nav_series.iloc[-1] / nav_series.iloc[0] - 1
    annualized_return = (1 + total_return) ** (trading_days / len(nav_series)) - 1
    annualized_vol = returns.std() * np.sqrt(trading_days)
    sharpe = (annualized_return - risk_free_rate) / annualized_vol if annualized_vol > 0 else 0
    
    max_drawdown = (nav_series / nav_series.cummax() - 1).min()
    calmar = annualized_return / abs(max_drawdown) if max_drawdown != 0 else 0
    
    return {
        "annualized_return": annualized_return,
        "annualized_volatility": annualized_vol,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_drawdown,
        "calmar_ratio": calmar,
        "total_return": total_return
    }

def calculate_turnover(weights_df: pd.DataFrame) -> float:
    diff = weights_df.diff().abs().sum(axis=1)
    return diff.mean()
