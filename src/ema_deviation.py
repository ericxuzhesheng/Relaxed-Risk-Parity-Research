"""
EMA 乖离率（Deviation from EMA）辅助信号模块。

公式（对数减法版）：
    prices = (1 + returns_window.fillna(0)).cumprod()
    ema    = prices.ewm(span=span, adjust=False).mean()
    deviation = ln(prices[-1]) - ln(ema[-1])

该指标用于广发策略口径的趋势温度判断：
    > 0.15  过热区，不追高，降低权重/上限
    0.05 ~ 0.15  强趋势区，只记录状态，不默认加仓
    -0.05 ~ 0    刚跌破均线，坚守，不调整
    < -0.05 趋势失速，降低权重/上限

设计约束：
- 只对 infer_asset_class(col) == "equity" 的资产生效
- 历史长度不足时（< span * min_period_multiplier）不启用信号
- 默认不改变总仓位，只调整权益资产间比例
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.utils import infer_asset_class


def compute_ema_deviation(
    returns_window: pd.DataFrame,
    span: int = 20,
    min_period_multiplier: int = 3,
) -> tuple[pd.Series, dict]:
    """
    从收益率窗口重建相对价格序列，计算末日各资产的对数乖离率。

    Parameters
    ----------
    returns_window : pd.DataFrame
        日收益率宽表，index=日期，columns=资产名。
    span : int
        EMA 周期（pandas ewm span 参数）。
    min_period_multiplier : int
        最小历史倍数。len(returns_window) < span * min_period_multiplier 时
        视为历史不足，不启用信号。

    Returns
    -------
    deviation : pd.Series
        index=资产名，value=ln(close) - ln(EMA_span)。
        历史不足时返回全 0 Series。
    diagnostics : dict
        ema_insufficient_history : bool
        ema_deviation_span : int
        ema_valid_asset_count : int
    """
    n = len(returns_window)
    insufficient = n < span * min_period_multiplier
    if insufficient:
        return (
            pd.Series(0.0, index=returns_window.columns),
            {
                "ema_insufficient_history": True,
                "ema_deviation_span": span,
                "ema_valid_asset_count": 0,
            },
        )

    prices = (1.0 + returns_window.fillna(0.0)).cumprod()
    ema = prices.ewm(span=span, adjust=False).mean()
    last_price = prices.iloc[-1]
    last_ema = ema.iloc[-1]
    # 防止对数计算中出现零或负值
    safe_ema = last_ema.where(last_ema > 1e-12, np.nan)
    safe_price = last_price.where(last_price > 1e-12, np.nan)
    deviation = (np.log(safe_price) - np.log(safe_ema)).fillna(0.0)

    return (
        deviation,
        {
            "ema_insufficient_history": False,
            "ema_deviation_span": span,
            "ema_valid_asset_count": int((deviation != 0.0).sum()),
        },
    )


def ema_deviation_weight_scales(
    deviation: pd.Series,
    columns: list[str],
    overextended_threshold: float = 0.15,
    overextended_scale: float = 0.60,
    strong_threshold: float = 0.05,
    stop_threshold: float = -0.05,
    stop_scale: float = 0.30,
    equity_only: bool = True,
) -> np.ndarray:
    """
    根据各资产乖离率返回权重缩放因子数组。

    映射规则（per-asset）：
    - 非 equity 资产（equity_only=True 时）→ 1.0，不调整
    - deviation > overextended_threshold → overextended_scale（降低过热仓位）
    - deviation < stop_threshold → stop_scale（趋势失速减仓）
    - 其他区间（含 strong_threshold~overextended_threshold）→ 1.0

    注意：5%~15% 强趋势区不放大权重，仅通过 ema_strong_trend_count 记录。

    Parameters
    ----------
    deviation : pd.Series
        由 compute_ema_deviation() 返回的乖离率 Series。
    columns : list[str]
        当前持仓的资产名称列表（与权重数组顺序一致）。
    overextended_threshold : float
        过热阈值（默认 0.15 = 15%）。
    overextended_scale : float
        过热时权重缩放因子（默认 0.60）。
    strong_threshold : float
        强趋势区下界（默认 0.05 = 5%），仅用于 state 统计。
    stop_threshold : float
        趋势失速阈值（默认 -0.05 = -5%）。
    stop_scale : float
        趋势失速时权重缩放因子（默认 0.30）。
    equity_only : bool
        若为 True，仅对 infer_asset_class(col) == "equity" 的资产生效。

    Returns
    -------
    scales : np.ndarray
        shape=(len(columns),)，各资产权重缩放因子，取值范围 [stop_scale, 1.0]。
    """
    scales = np.ones(len(columns), dtype=float)
    for i, col in enumerate(columns):
        if equity_only and infer_asset_class(str(col)) != "equity":
            continue
        dev = float(deviation.get(col, 0.0))
        if dev > overextended_threshold:
            scales[i] = overextended_scale
        elif dev < stop_threshold:
            scales[i] = stop_scale
        # strong_threshold <= dev <= overextended_threshold: scale = 1.0 (不加仓)
        # stop_threshold <= dev < 0: scale = 1.0 (坚守)
    return scales
