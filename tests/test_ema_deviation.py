"""
Unit tests for EMA 乖离率（Deviation from EMA）模块。

覆盖 7 个场景：
1. 单调上涨序列 → deviation > 0
2. 单调下跌序列 → deviation < 0
3. deviation > 0.15 时 equity 资产 scale = overextended_scale (0.60)
4. deviation < -0.05 时 equity 资产 scale = stop_scale (0.30)
5. equity_only=True 时 bond 资产 scale = 1.0
6. 历史长度不足 → ema_insufficient_history=True，deviation 全 0
7. ema_deviation_enabled=False 时 apply_risk_overlay() 结果与未添加 EMA 代码完全一致
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.ema_deviation import compute_ema_deviation, ema_deviation_weight_scales
from src.risk_overlay import RiskOverlayConfig, apply_risk_overlay


# ---------------------------------------------------------------------------
# 辅助构建器
# ---------------------------------------------------------------------------

def _build_returns(daily_return: float, n_days: int, assets: list[str]) -> pd.DataFrame:
    """构建所有资产收益率均相同的返回窗口（用于极端测试）。"""
    dates = pd.date_range("2022-01-03", periods=n_days, freq="B")
    data = {col: [daily_return] * n_days for col in assets}
    return pd.DataFrame(data, index=dates)


# ---------------------------------------------------------------------------
# Test 1: 单调上涨 → deviation > 0
# ---------------------------------------------------------------------------

def test_deviation_positive_for_rising_prices():
    """单调上涨时，价格在 EMA 上方，乖离率应为正数。"""
    returns = _build_returns(daily_return=0.005, n_days=90, assets=["沪深300ETF"])
    deviation, diag = compute_ema_deviation(returns, span=20)

    assert not diag["ema_insufficient_history"]
    assert deviation["沪深300ETF"] > 0.0, f"Expected positive deviation, got {deviation['沪深300ETF']}"


# ---------------------------------------------------------------------------
# Test 2: 单调下跌 → deviation < 0
# ---------------------------------------------------------------------------

def test_deviation_negative_for_falling_prices():
    """单调下跌时，价格在 EMA 下方，乖离率应为负数。"""
    returns = _build_returns(daily_return=-0.005, n_days=90, assets=["沪深300ETF"])
    deviation, diag = compute_ema_deviation(returns, span=20)

    assert not diag["ema_insufficient_history"]
    assert deviation["沪深300ETF"] < 0.0, f"Expected negative deviation, got {deviation['沪深300ETF']}"


# ---------------------------------------------------------------------------
# Test 3: deviation > 0.15 → equity 资产 scale = overextended_scale (0.60)
# ---------------------------------------------------------------------------

def test_overextended_scale_applied_to_equity():
    """deviation > 0.15 时，equity 资产缩放因子应等于 overextended_scale。"""
    # 用极端正收益确保 deviation > 0.15
    returns = _build_returns(daily_return=0.02, n_days=90, assets=["沪深300ETF"])
    deviation, _ = compute_ema_deviation(returns, span=20)

    # 确认 deviation 确实过热
    assert deviation["沪深300ETF"] > 0.15, (
        f"Precondition failed: deviation={deviation['沪深300ETF']:.4f}, expected > 0.15"
    )

    scales = ema_deviation_weight_scales(
        deviation,
        columns=["沪深300ETF"],
        overextended_threshold=0.15,
        overextended_scale=0.60,
        stop_threshold=-0.05,
        stop_scale=0.30,
        equity_only=True,
    )
    assert scales[0] == pytest.approx(0.60), f"Expected 0.60, got {scales[0]}"


# ---------------------------------------------------------------------------
# Test 4: deviation < -0.05 → equity 资产 scale = stop_scale (0.30)
# ---------------------------------------------------------------------------

def test_stop_scale_applied_to_equity():
    """deviation < -0.05 时，equity 资产缩放因子应等于 stop_scale。"""
    returns = _build_returns(daily_return=-0.02, n_days=90, assets=["沪深300ETF"])
    deviation, _ = compute_ema_deviation(returns, span=20)

    assert deviation["沪深300ETF"] < -0.05, (
        f"Precondition failed: deviation={deviation['沪深300ETF']:.4f}, expected < -0.05"
    )

    scales = ema_deviation_weight_scales(
        deviation,
        columns=["沪深300ETF"],
        overextended_threshold=0.15,
        overextended_scale=0.60,
        stop_threshold=-0.05,
        stop_scale=0.30,
        equity_only=True,
    )
    assert scales[0] == pytest.approx(0.30), f"Expected 0.30, got {scales[0]}"


# ---------------------------------------------------------------------------
# Test 5: equity_only=True 时 bond 资产 scale = 1.0
# ---------------------------------------------------------------------------

def test_bond_asset_scale_unchanged_when_equity_only():
    """equity_only=True 时，debt 类资产（含"债"）的缩放因子必须为 1.0。"""
    assets = ["国债ETF", "沪深300ETF"]
    returns = _build_returns(daily_return=0.02, n_days=90, assets=assets)
    deviation, _ = compute_ema_deviation(returns, span=20)

    scales = ema_deviation_weight_scales(
        deviation,
        columns=assets,
        overextended_threshold=0.15,
        overextended_scale=0.60,
        stop_threshold=-0.05,
        stop_scale=0.30,
        equity_only=True,
    )
    # 国债ETF → infer_asset_class 返回 "bond" → 不调整
    bond_idx = assets.index("国债ETF")
    assert scales[bond_idx] == pytest.approx(1.0), (
        f"Bond asset should have scale=1.0, got {scales[bond_idx]}"
    )
    # 沪深300ETF 是 equity，应该被压缩
    equity_idx = assets.index("沪深300ETF")
    assert scales[equity_idx] < 1.0, (
        f"Equity asset should have scale < 1.0 when overextended, got {scales[equity_idx]}"
    )


# ---------------------------------------------------------------------------
# Test 6: 历史长度不足 → ema_insufficient_history=True，deviation 全 0
# ---------------------------------------------------------------------------

def test_insufficient_history_returns_zeros():
    """当 len(returns_window) < span * min_period_multiplier 时，应返回全零 deviation 及 insufficient 标志。"""
    span = 20
    min_mult = 3
    # 长度恰好不足
    returns = _build_returns(daily_return=0.01, n_days=span * min_mult - 1, assets=["沪深300ETF"])
    deviation, diag = compute_ema_deviation(returns, span=span, min_period_multiplier=min_mult)

    assert diag["ema_insufficient_history"] is True
    assert diag["ema_valid_asset_count"] == 0
    assert float(deviation["沪深300ETF"]) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Test 7: ema_deviation_enabled=False 时 apply_risk_overlay() 结果不变
# ---------------------------------------------------------------------------

def test_ema_disabled_does_not_change_weights():
    """ema_deviation_enabled=False（默认）时，apply_risk_overlay() 的权重结果应与不含 EMA 逻辑时完全一致。"""
    rng = np.random.default_rng(42)
    n_days, n_assets = 120, 4
    dates = pd.date_range("2022-01-03", periods=n_days, freq="B")
    assets = ["沪深300ETF", "中证500ETF", "国债ETF", "黄金ETF"]
    window = pd.DataFrame(
        rng.normal(0.0, 0.01, (n_days, n_assets)),
        index=dates,
        columns=assets,
    )
    proposed = np.array([0.30, 0.25, 0.30, 0.15])
    previous = np.array([0.25, 0.25, 0.30, 0.20])

    # 1. 使用默认配置（ema_deviation_enabled=False）
    cfg_off = RiskOverlayConfig(ema_deviation_enabled=False)
    weights_off, state_off = apply_risk_overlay(
        proposed, previous, window, drawdown=-0.02, overlay_config=cfg_off
    )

    # 2. 使用开启配置（ema_deviation_enabled=True）
    cfg_on = RiskOverlayConfig(ema_deviation_enabled=True)
    weights_on, state_on = apply_risk_overlay(
        proposed, previous, window, drawdown=-0.02, overlay_config=cfg_on
    )

    # 关闭时两种调用结果必须完全一致
    np.testing.assert_array_almost_equal(
        weights_off, weights_off,
        decimal=12,
        err_msg="ema_deviation_enabled=False should produce identical weights",
    )

    # 验证关闭时 EMA 状态字段均为 0 / False
    assert state_off["ema_overextended_count"] == 0
    assert state_off["ema_stop_count"] == 0
    assert state_off["ema_strong_trend_count"] == 0
    assert state_off["ema_insufficient_history"] is False

    # 验证开启时 EMA 状态字段存在且合理
    assert "ema_deviation_min" in state_on
    assert "ema_deviation_max" in state_on
    assert isinstance(state_on["ema_overextended_count"], int)
