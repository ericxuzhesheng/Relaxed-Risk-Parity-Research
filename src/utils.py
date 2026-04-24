import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DEFAULT_CONFIG = {
    "lookback_weeks": 48,
    "trading_days_per_year": 243,
    "plot_start_date": "2021-01-01",
    "lambda_pen": 1.9,
    "m": 1.9,
    "optim_tol": 1e-6,
    "optim_maxiter": 2000,
    "asset_weight_bounds": (0.00, 1.0),
    "max_single_asset_weight": 1.0,
    "bond_keywords": ["国债", "信用票", "美债", "债"],
    "bond_leverage_upper": 1.4,
    "risk_free_rate": 0.0182,
    "target_vol": 0.060, # 激进型目标：6.0% (追求 Sharpe > 1)
    "tushare_token": "ddd1b26b20ff085ac9b60c9bd902ae76bbff60910863e8cc0168da53",
}

def resolve_path(path_like):
    if path_like is None:
        return None
    p = Path(path_like)
    return p if p.is_absolute() else (BASE_DIR / p)

def get_config(overrides=None):
    config = DEFAULT_CONFIG.copy()
    if overrides:
        config.update(overrides)
    return config
