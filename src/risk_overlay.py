from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RiskOverlayConfig:
    drawdown_low: float = 0.025
    drawdown_high: float = 0.040
    drawdown_mild: float = 0.025
    drawdown_medium: float = 0.040
    drawdown_severe: float = 0.080
    drawdown_mild_scale: float = 1.00
    drawdown_medium_scale: float = 0.75
    drawdown_severe_scale: float = 0.50
    drawdown_mid_scale: float = 0.75
    drawdown_high_scale: float = 0.50
    trend_filter_mode: str = "hard"
    momentum_lookback: int = 60
    momentum_confirm_lookback: int = 20
    trend_soft_scale: float = 0.85
    trend_hard_scale: float = 1.0
    realized_vol_window: int | None = None
    ewma_decay: float = 0.94
    ewma_halflife: float | None = None
    target_vol: float = 0.060
    max_risk_scale: float = 1.00
    gross_exposure_cap: float = 1.50
    turnover_cap: float | None = 0.25
    reentry_speed: float = 1.0
    signal_persistence: int = 1
    weight_smoothing: float = 0.0
    transaction_cost_bps: float = 3.0
    ema_deviation_enabled: bool = False
    ema_deviation_span: int = 20
    ema_strong_threshold: float = 0.05
    ema_overextended_threshold: float = 0.15
    ema_overextended_scale: float = 0.60
    ema_stop_threshold: float = -0.05
    ema_stop_scale: float = 0.30
    ema_equity_only: bool = True
    ema_renormalize_after_scale: bool = False
    trading_days_per_year: int = 243

    @classmethod
    def from_config(cls, config: dict | None = None) -> "RiskOverlayConfig":
        config = config or {}
        turnover_cap = config.get("turnover_cap", cls.turnover_cap)
        if turnover_cap is not None:
            turnover_cap = float(turnover_cap)
        ewma_halflife = config.get("ewma_halflife", cls.ewma_halflife)
        if ewma_halflife is not None:
            ewma_halflife = float(ewma_halflife)
        realized_vol_window = config.get("realized_vol_window", cls.realized_vol_window)
        if realized_vol_window is not None:
            realized_vol_window = int(realized_vol_window)
        return cls(
            drawdown_low=float(config.get("drawdown_low", config.get("drawdown_mild", cls.drawdown_low))),
            drawdown_high=float(config.get("drawdown_high", config.get("drawdown_medium", cls.drawdown_high))),
            drawdown_mild=float(config.get("drawdown_mild", config.get("drawdown_low", cls.drawdown_mild))),
            drawdown_medium=float(config.get("drawdown_medium", config.get("drawdown_high", cls.drawdown_medium))),
            drawdown_severe=float(config.get("drawdown_severe", cls.drawdown_severe)),
            drawdown_mild_scale=float(config.get("drawdown_mild_scale", cls.drawdown_mild_scale)),
            drawdown_medium_scale=float(config.get("drawdown_medium_scale", config.get("drawdown_mid_scale", cls.drawdown_medium_scale))),
            drawdown_severe_scale=float(config.get("drawdown_severe_scale", config.get("drawdown_high_scale", cls.drawdown_severe_scale))),
            drawdown_mid_scale=float(config.get("drawdown_mid_scale", cls.drawdown_mid_scale)),
            drawdown_high_scale=float(config.get("drawdown_high_scale", cls.drawdown_high_scale)),
            trend_filter_mode=str(config.get("trend_filter_mode", cls.trend_filter_mode)).lower(),
            momentum_lookback=int(config.get("momentum_lookback", cls.momentum_lookback)),
            momentum_confirm_lookback=int(config.get("momentum_confirm_lookback", cls.momentum_confirm_lookback)),
            trend_soft_scale=float(config.get("trend_soft_scale", cls.trend_soft_scale)),
            trend_hard_scale=float(config.get("trend_hard_scale", cls.trend_hard_scale)),
            realized_vol_window=realized_vol_window,
            ewma_decay=float(config.get("ewma_decay", cls.ewma_decay)),
            ewma_halflife=ewma_halflife,
            target_vol=float(config.get("target_vol", cls.target_vol)),
            max_risk_scale=float(config.get("max_risk_scale", cls.max_risk_scale)),
            gross_exposure_cap=float(config.get("gross_exposure_cap", cls.gross_exposure_cap)),
            turnover_cap=turnover_cap,
            reentry_speed=float(config.get("reentry_speed", cls.reentry_speed)),
            signal_persistence=int(config.get("signal_persistence", cls.signal_persistence)),
            weight_smoothing=float(config.get("weight_smoothing", cls.weight_smoothing)),
            transaction_cost_bps=float(config.get("transaction_cost_bps", cls.transaction_cost_bps)),
            ema_deviation_enabled=bool(config.get("ema_deviation_enabled", cls.ema_deviation_enabled)),
            ema_deviation_span=int(config.get("ema_deviation_span", cls.ema_deviation_span)),
            ema_strong_threshold=float(config.get("ema_strong_threshold", cls.ema_strong_threshold)),
            ema_overextended_threshold=float(config.get("ema_overextended_threshold", cls.ema_overextended_threshold)),
            ema_overextended_scale=float(config.get("ema_overextended_scale", cls.ema_overextended_scale)),
            ema_stop_threshold=float(config.get("ema_stop_threshold", cls.ema_stop_threshold)),
            ema_stop_scale=float(config.get("ema_stop_scale", cls.ema_stop_scale)),
            ema_equity_only=bool(config.get("ema_equity_only", cls.ema_equity_only)),
            ema_renormalize_after_scale=bool(config.get("ema_renormalize_after_scale", cls.ema_renormalize_after_scale)),
            trading_days_per_year=int(config.get("trading_days_per_year", cls.trading_days_per_year)),
        )


def drawdown_scale(drawdown: float, overlay_config: RiskOverlayConfig | None = None) -> float:
    cfg = overlay_config or RiskOverlayConfig()
    dd = abs(min(float(drawdown), 0.0))
    if dd <= cfg.drawdown_mild:
        return cfg.drawdown_mild_scale
    if dd <= cfg.drawdown_medium:
        return cfg.drawdown_medium_scale
    if dd <= cfg.drawdown_severe:
        return cfg.drawdown_severe_scale
    return cfg.drawdown_severe_scale


def trend_positive_mask(window: pd.DataFrame, overlay_config: RiskOverlayConfig | None = None) -> pd.Series:
    cfg = overlay_config or RiskOverlayConfig()
    long_lookback = min(cfg.momentum_lookback, len(window))
    confirm_lookback = min(cfg.momentum_confirm_lookback, len(window))
    long_mom = (1.0 + window.iloc[-long_lookback:]).prod() - 1.0
    confirm_mom = (1.0 + window.iloc[-confirm_lookback:]).prod() - 1.0
    return (long_mom > 0.0) & (confirm_mom > 0.0)


def trend_risk_scale(
    window: pd.DataFrame,
    overlay_config: RiskOverlayConfig | None = None,
) -> tuple[float, int]:
    cfg = overlay_config or RiskOverlayConfig()
    if cfg.trend_filter_mode == "off" or window.empty:
        return 1.0, len(window.columns)
    mask = trend_positive_mask(window, cfg)
    positive_count = int(mask.sum())
    if positive_count == len(mask):
        return 1.0, positive_count
    if cfg.trend_filter_mode == "soft":
        return float(cfg.trend_soft_scale), positive_count
    if cfg.trend_filter_mode == "hard":
        return float(cfg.trend_hard_scale), positive_count
    raise ValueError(f"Unsupported trend_filter_mode: {cfg.trend_filter_mode}")


def apply_trend_confirmation(
    mu: pd.Series,
    window: pd.DataFrame,
    overlay_config: RiskOverlayConfig | None = None,
    negative_mu: float = -0.1,
) -> tuple[pd.Series, int]:
    cfg = overlay_config or RiskOverlayConfig()
    if cfg.trend_filter_mode == "off":
        return mu.copy(), int(len(mu))
    mask = trend_positive_mask(window, overlay_config)
    filtered = mu.copy()
    if cfg.trend_filter_mode == "soft":
        filtered[~mask] = filtered[~mask] * cfg.trend_soft_scale
    elif cfg.trend_filter_mode == "hard":
        filtered[~mask] = negative_mu
    else:
        raise ValueError(f"Unsupported trend_filter_mode: {cfg.trend_filter_mode}")
    return filtered, int(mask.sum())


def ewma_realized_vol(
    returns: pd.Series | pd.DataFrame,
    overlay_config: RiskOverlayConfig | None = None,
) -> float:
    cfg = overlay_config or RiskOverlayConfig()
    series = pd.Series(returns).dropna()
    if cfg.realized_vol_window is not None:
        series = series.iloc[-cfg.realized_vol_window :]
    if len(series) < 2:
        return 0.0
    decay = cfg.ewma_decay
    if cfg.ewma_halflife is not None and cfg.ewma_halflife > 0:
        decay = float(np.exp(np.log(0.5) / cfg.ewma_halflife))
    variance = float(series.iloc[0] ** 2)
    for value in series.iloc[1:]:
        variance = decay * variance + (1.0 - decay) * float(value) ** 2
    return float(np.sqrt(max(variance, 0.0) * cfg.trading_days_per_year))


def vol_target_scale(
    portfolio_returns: pd.Series,
    overlay_config: RiskOverlayConfig | None = None,
) -> float:
    cfg = overlay_config or RiskOverlayConfig()
    realized_vol = ewma_realized_vol(portfolio_returns, cfg)
    if realized_vol <= 0.0:
        return min(1.0, cfg.max_risk_scale)
    return min(cfg.max_risk_scale, cfg.target_vol / realized_vol)


def cap_gross_exposure(weights: np.ndarray, cap: float) -> np.ndarray:
    gross = float(np.abs(weights).sum())
    if gross > cap and gross > 0.0:
        return weights * (cap / gross)
    return weights


def apply_turnover_cap(
    proposed_weights: np.ndarray,
    previous_weights: np.ndarray,
    overlay_config: RiskOverlayConfig | None = None,
) -> tuple[np.ndarray, float, bool]:
    cfg = overlay_config or RiskOverlayConfig()
    proposed_turnover = float(np.abs(proposed_weights - previous_weights).sum())
    if cfg.turnover_cap is None:
        return proposed_weights, proposed_turnover, False
    if proposed_turnover <= cfg.turnover_cap or proposed_turnover <= 0.0:
        return proposed_weights, proposed_turnover, False
    blend = cfg.turnover_cap / proposed_turnover
    capped = previous_weights + blend * (proposed_weights - previous_weights)
    return capped, float(np.abs(capped - previous_weights).sum()), True


def apply_ema_deviation_scale(
    weights: np.ndarray,
    window: pd.DataFrame,
    overlay_config: RiskOverlayConfig,
) -> tuple[np.ndarray, dict]:
    """
    对权重向量应用 EMA 乖离率缩放。

    仅对 infer_asset_class(col) == "equity" 的资产生效（equity_only=True 时）。
    ema_renormalize_after_scale=False（默认）：允许总敞口下降，形成防御性现金缺口。
    ema_renormalize_after_scale=True：缩放后等比恢复总权重之和，内部再分配。

    Returns
    -------
    scaled_weights : np.ndarray
    ema_state : dict
        keys: ema_deviation_min, ema_deviation_max, ema_strong_trend_count,
              ema_overextended_count, ema_stop_count, ema_insufficient_history
    """
    from src.utils import infer_asset_class
    from src.ema_deviation import compute_ema_deviation, ema_deviation_weight_scales

    cfg = overlay_config
    deviation, diag = compute_ema_deviation(window, cfg.ema_deviation_span)

    if diag["ema_insufficient_history"]:
        return weights.copy(), {
            "ema_deviation_min": 0.0,
            "ema_deviation_max": 0.0,
            "ema_strong_trend_count": 0,
            "ema_overextended_count": 0,
            "ema_stop_count": 0,
            "ema_insufficient_history": True,
        }

    scales = ema_deviation_weight_scales(
        deviation,
        list(window.columns),
        cfg.ema_overextended_threshold,
        cfg.ema_overextended_scale,
        cfg.ema_strong_threshold,
        cfg.ema_stop_threshold,
        cfg.ema_stop_scale,
        cfg.ema_equity_only,
    )
    scaled = weights * scales

    if cfg.ema_renormalize_after_scale:
        original_sum = float(weights.sum())
        scaled_sum = float(scaled.sum())
        if scaled_sum > 1e-8:
            scaled = scaled / scaled_sum * original_sum

    equity_devs = [
        float(deviation.get(c, 0.0))
        for c in window.columns
        if infer_asset_class(str(c)) == "equity"
    ]
    return scaled, {
        "ema_deviation_min": float(min(equity_devs)) if equity_devs else 0.0,
        "ema_deviation_max": float(max(equity_devs)) if equity_devs else 0.0,
        "ema_strong_trend_count": int(
            sum(cfg.ema_strong_threshold <= d <= cfg.ema_overextended_threshold for d in equity_devs)
        ),
        "ema_overextended_count": int(sum(d > cfg.ema_overextended_threshold for d in equity_devs)),
        "ema_stop_count": int(sum(d < cfg.ema_stop_threshold for d in equity_devs)),
        "ema_insufficient_history": False,
    }


def apply_risk_overlay(
    proposed_weights: np.ndarray,
    previous_weights: np.ndarray,
    window: pd.DataFrame,
    drawdown: float,
    overlay_config: RiskOverlayConfig | None = None,
    risk_state: dict | None = None,
) -> tuple[np.ndarray, dict]:
    cfg = overlay_config or RiskOverlayConfig()
    weights = np.asarray(proposed_weights, dtype=float)
    previous = np.asarray(previous_weights, dtype=float)
    risk_state = risk_state or {}

    base_portfolio_returns = window.fillna(0.0) @ weights
    vol_scalar = vol_target_scale(base_portfolio_returns, cfg)
    dd_scalar = drawdown_scale(drawdown, cfg)
    trend_scalar, trend_positive_count = trend_risk_scale(window, cfg)
    raw_risk_scalar = min(cfg.max_risk_scale, vol_scalar * dd_scalar * trend_scalar)

    previous_reentry = float(risk_state.get("reentry_state", raw_risk_scalar))
    reentry_speed = min(max(cfg.reentry_speed, 0.0), 1.0)
    if raw_risk_scalar > previous_reentry:
        reentry_state = previous_reentry + reentry_speed * (raw_risk_scalar - previous_reentry)
    else:
        reentry_state = raw_risk_scalar

    persistence = max(cfg.signal_persistence, 1)
    if persistence > 1:
        previous_signal = float(risk_state.get("persisted_risk_scalar", reentry_state))
        final_risk_scalar = ((persistence - 1) * previous_signal + reentry_state) / persistence
    else:
        final_risk_scalar = reentry_state
    final_risk_scalar = min(cfg.max_risk_scale, max(0.0, final_risk_scalar))

    weights = weights * final_risk_scalar

    # EMA 乖离率辅助缩放（默认关闭）
    if cfg.ema_deviation_enabled and not window.empty:
        weights, ema_state = apply_ema_deviation_scale(weights, window, cfg)
    else:
        ema_state = {
            "ema_deviation_min": 0.0,
            "ema_deviation_max": 0.0,
            "ema_strong_trend_count": 0,
            "ema_overextended_count": 0,
            "ema_stop_count": 0,
            "ema_insufficient_history": False,
        }

    smoothing = min(max(cfg.weight_smoothing, 0.0), 1.0)
    if smoothing > 0.0:
        weights = smoothing * previous + (1.0 - smoothing) * weights
    weights = cap_gross_exposure(weights, cfg.gross_exposure_cap)
    weights, turnover, turnover_cap_bound = apply_turnover_cap(weights, previous, cfg)

    state = {
        "target_vol_scalar": float(vol_scalar),
        "drawdown_scalar": float(dd_scalar),
        "trend_scalar": float(trend_scalar),
        "final_risk_scalar": float(final_risk_scalar),
        "risky_exposure": float(np.abs(weights).sum()),
        "defensive_cash_proxy_exposure": float(max(0.0, 1.0 - np.abs(weights).sum())),
        "turnover": float(turnover),
        "turnover_cap_bound": bool(turnover_cap_bound),
        "gross_exposure": float(np.abs(weights).sum()),
        "trend_positive_count": int(trend_positive_count),
        "reentry_state": float(reentry_state),
        "persisted_risk_scalar": float(final_risk_scalar),
    }
    state.update(ema_state)
    return weights, state


def transaction_cost_rate(overlay_config: RiskOverlayConfig | None = None) -> float:
    cfg = overlay_config or RiskOverlayConfig()
    return cfg.transaction_cost_bps / 10000.0
