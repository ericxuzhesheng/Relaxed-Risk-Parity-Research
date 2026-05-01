from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RiskOverlayConfig:
    drawdown_low: float = 0.025
    drawdown_high: float = 0.040
    drawdown_mid_scale: float = 0.75
    drawdown_high_scale: float = 0.50
    momentum_lookback: int = 60
    momentum_confirm_lookback: int = 20
    ewma_decay: float = 0.94
    target_vol: float = 0.060
    gross_exposure_cap: float = 1.50
    turnover_cap: float = 0.25
    transaction_cost_bps: float = 3.0
    trading_days_per_year: int = 243

    @classmethod
    def from_config(cls, config: dict | None = None) -> "RiskOverlayConfig":
        config = config or {}
        return cls(
            target_vol=float(config.get("target_vol", cls.target_vol)),
            gross_exposure_cap=float(config.get("gross_exposure_cap", cls.gross_exposure_cap)),
            turnover_cap=float(config.get("turnover_cap", cls.turnover_cap)),
            transaction_cost_bps=float(config.get("transaction_cost_bps", cls.transaction_cost_bps)),
            trading_days_per_year=int(config.get("trading_days_per_year", cls.trading_days_per_year)),
        )


def drawdown_scale(drawdown: float, overlay_config: RiskOverlayConfig | None = None) -> float:
    cfg = overlay_config or RiskOverlayConfig()
    dd = abs(min(float(drawdown), 0.0))
    if dd <= cfg.drawdown_low:
        return 1.0
    if dd <= cfg.drawdown_high:
        return cfg.drawdown_mid_scale
    return cfg.drawdown_high_scale


def trend_positive_mask(window: pd.DataFrame, overlay_config: RiskOverlayConfig | None = None) -> pd.Series:
    cfg = overlay_config or RiskOverlayConfig()
    long_mom = (1.0 + window.iloc[-cfg.momentum_lookback :]).prod() - 1.0
    confirm_mom = (1.0 + window.iloc[-cfg.momentum_confirm_lookback :]).prod() - 1.0
    return (long_mom > 0.0) & (confirm_mom > 0.0)


def apply_trend_confirmation(
    mu: pd.Series,
    window: pd.DataFrame,
    overlay_config: RiskOverlayConfig | None = None,
    negative_mu: float = -0.1,
) -> tuple[pd.Series, int]:
    mask = trend_positive_mask(window, overlay_config)
    filtered = mu.copy()
    filtered[~mask] = negative_mu
    return filtered, int(mask.sum())


def ewma_realized_vol(
    returns: pd.Series | pd.DataFrame,
    overlay_config: RiskOverlayConfig | None = None,
) -> float:
    cfg = overlay_config or RiskOverlayConfig()
    series = pd.Series(returns).dropna()
    if len(series) < 2:
        return 0.0
    variance = float(series.iloc[0] ** 2)
    for value in series.iloc[1:]:
        variance = cfg.ewma_decay * variance + (1.0 - cfg.ewma_decay) * float(value) ** 2
    return float(np.sqrt(max(variance, 0.0) * cfg.trading_days_per_year))


def vol_target_scale(
    portfolio_returns: pd.Series,
    overlay_config: RiskOverlayConfig | None = None,
) -> float:
    cfg = overlay_config or RiskOverlayConfig()
    realized_vol = ewma_realized_vol(portfolio_returns, cfg)
    if realized_vol <= 0.0:
        return 1.0
    return min(1.0, cfg.target_vol / realized_vol)


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
    if proposed_turnover <= cfg.turnover_cap or proposed_turnover <= 0.0:
        return proposed_weights, proposed_turnover, False
    blend = cfg.turnover_cap / proposed_turnover
    capped = previous_weights + blend * (proposed_weights - previous_weights)
    return capped, float(np.abs(capped - previous_weights).sum()), True


def apply_risk_overlay(
    proposed_weights: np.ndarray,
    previous_weights: np.ndarray,
    window: pd.DataFrame,
    drawdown: float,
    overlay_config: RiskOverlayConfig | None = None,
) -> tuple[np.ndarray, dict]:
    cfg = overlay_config or RiskOverlayConfig()
    weights = np.asarray(proposed_weights, dtype=float)
    previous = np.asarray(previous_weights, dtype=float)

    base_portfolio_returns = window.fillna(0.0) @ weights
    vol_scalar = vol_target_scale(base_portfolio_returns, cfg)
    dd_scalar = drawdown_scale(drawdown, cfg)
    weights = weights * vol_scalar * dd_scalar
    weights = cap_gross_exposure(weights, cfg.gross_exposure_cap)
    weights, turnover, turnover_cap_bound = apply_turnover_cap(weights, previous, cfg)

    state = {
        "target_vol_scalar": float(vol_scalar),
        "drawdown_scalar": float(dd_scalar),
        "turnover": float(turnover),
        "turnover_cap_bound": bool(turnover_cap_bound),
        "gross_exposure": float(np.abs(weights).sum()),
    }
    return weights, state


def transaction_cost_rate(overlay_config: RiskOverlayConfig | None = None) -> float:
    cfg = overlay_config or RiskOverlayConfig()
    return cfg.transaction_cost_bps / 10000.0
