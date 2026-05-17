import os
from pathlib import Path
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent

# 年化无风险利率。取值 1.82% 对应中国 1 年期国债收益率在评价区间
# 2019-01-01 至 2026-05-07 上的近似平均水平，数据来源为中国人民银行公布的
# 国债收益率曲线（Wind/CSMAR 同步收录）。引文键 chinabond2026 用于
# references.bib 中的 Sharpe 分母口径说明。如需重估，请同步更新
# scripts/generate_thesis_numbers.py 中 \riskFreeRate 宏对应的数值。
RISK_FREE_RATE_ANNUAL: float = 0.0182

DEFAULT_CONFIG = {
    "lookback_weeks": 48,
    "trading_days_per_year": 243,
    "plot_start_date": "2019-01-01",
    "lambda_pen": 1.9,
    "m": 1.9,
    "optim_tol": 1e-6,
    "optim_maxiter": 2000,
    "asset_weight_bounds": (0.00, 1.0),
    "max_single_asset_weight": 1.0,
    "bond_keywords": ["国债", "信用票", "美债", "债"],
    "bond_leverage_upper": 1.4,
    "risk_free_rate": RISK_FREE_RATE_ANNUAL,
    "target_vol": 0.080, # 目标波动率：8.0%，提升平均仓位至 ~75%
    "gross_exposure_cap": 1.50,
    "turnover_cap": 0.25,
    "transaction_cost_bps": 3.0,
    "tushare_token": os.environ.get("TUSHARE_TOKEN", ""),
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


def infer_asset_class(asset_name: str) -> str:
    name = str(asset_name)
    if "红利" in name:
        return "defensive"
    if "债" in name or "信用" in name:
        return "bond"
    if any(token in name for token in ["黄金", "有色", "豆粕", "原油", "WTI"]):
        return "commodity_gold"
    return "equity"


def apply_asset_class_budget_multipliers(weights, columns, config: dict):
    multipliers = config.get("asset_class_budget_multipliers")
    if not multipliers:
        return weights
    adjusted = np.asarray(weights, dtype=float).copy()
    target_sum = float(adjusted.sum())
    for i, col in enumerate(columns):
        adjusted[i] *= float(multipliers.get(infer_asset_class(col), 1.0))
    adjusted_sum = float(adjusted.sum())
    if abs(adjusted_sum) > 1e-12:
        adjusted *= target_sum / adjusted_sum
    return adjusted
