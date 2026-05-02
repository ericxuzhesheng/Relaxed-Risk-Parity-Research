from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.run_rrp_pipeline import _parameter_grid
from src.asset_pricing_diagnostics import build_factor_proxies, run_diagnostics, write_outputs
from src.backtest import run_static_backtest
from src.data_loader import load_data
from src.dynamic_selection import run_dynamic_rrp_selection
from src.utils import get_config, resolve_path

GLOBAL_LABEL = "Global Relaxed Risk Parity"
IMPROVED_CONVEX_LABEL = "Improved Convex Adaptive Global RRP"
BASE_CONVEX_LABEL = "Convex Adaptive Global RRP"
DYNAMIC_LABEL = "Defensive Dynamic Relaxed Risk Parity"


def _project_path(path: str | Path) -> Path:
    return Path(resolve_path(path))


def _read_cached_convex(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    df = pd.read_csv(path)
    return df if {"date", "portfolio_return"}.issubset(df.columns) else None


def _load_returns(smoke: bool) -> pd.DataFrame:
    returns = load_data(source="tushare", force_update=False).dropna(how="all")
    if smoke:
        returns = returns.iloc[: min(320, len(returns)), : min(6, len(returns.columns))]
    return returns


def load_or_build_models(returns: pd.DataFrame, smoke: bool) -> dict[str, pd.DataFrame]:
    config = get_config({"transaction_cost_bps": 3.0, "turnover_cap": 0.25, "target_vol": 0.060})
    print("Building in-memory Global Relaxed Risk Parity diagnostics input...")
    global_rrp = run_static_backtest(returns, model_type="relaxed", config_overrides=config)

    print("Building in-memory Defensive Dynamic Relaxed Risk Parity diagnostics input...")
    dynamic = run_dynamic_rrp_selection(
        returns,
        _parameter_grid(smoke),
        train_window_months=12 if smoke else 24,
        selection_metric="utility",
        top_k=1 if smoke else 2,
        config_base=config,
    )
    if dynamic.empty:
        dynamic = global_rrp.copy()
        print("Defensive dynamic result was empty; using Global RRP as smoke-safe diagnostic placeholder.")

    improved = _read_cached_convex(_project_path("results/tables/improved_convex_adaptive_global_relaxed_risk_parity_returns.csv"))
    base = _read_cached_convex(_project_path("results/tables/convex_adaptive_global_relaxed_risk_parity_returns.csv"))
    if smoke:
        if improved is not None:
            improved = improved.head(len(global_rrp))
        if base is not None:
            base = base.head(len(global_rrp))
    if improved is None:
        improved = global_rrp.copy()
        print("Cached improved convex returns missing; using Global RRP as smoke-safe diagnostic placeholder.")
    if base is None:
        base = global_rrp.copy()
        print("Cached base convex returns missing; using Global RRP as smoke-safe diagnostic placeholder.")

    return {
        GLOBAL_LABEL: global_rrp,
        IMPROVED_CONVEX_LABEL: improved,
        BASE_CONVEX_LABEL: base,
        DYNAMIC_LABEL: dynamic,
    }


def plot_factor_exposure(summary: pd.DataFrame, path: Path) -> None:
    beta_cols = [col for col in summary.columns if col.startswith("beta_")]
    data = summary.set_index("model")[beta_cols].copy()
    data.columns = [col.replace("beta_", "") for col in data.columns]
    ax = data.plot(kind="bar", figsize=(12, 6))
    ax.set_title("Asset-Pricing Factor Exposures")
    ax.set_ylabel("Regression beta")
    ax.grid(axis="y", alpha=0.3)
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def plot_return_attribution(attribution: pd.DataFrame, path: Path) -> None:
    data = attribution.pivot(index="model", columns="asset_class", values="annualized_return_contribution").fillna(0.0)
    ax = data.plot(kind="bar", stacked=True, figsize=(12, 6))
    ax.set_title("Asset-Class Return Attribution")
    ax.set_ylabel("Annualized contribution")
    ax.grid(axis="y", alpha=0.3)
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def plot_risk_attribution(attribution: pd.DataFrame, path: Path) -> None:
    data = attribution.pivot(index="model", columns="asset_class", values="variance_share_approx").fillna(0.0)
    ax = data.plot(kind="bar", stacked=True, figsize=(12, 6))
    ax.set_title("Asset-Class Risk Attribution")
    ax.set_ylabel("Approximate variance share")
    ax.grid(axis="y", alpha=0.3)
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def plot_rolling_betas(rolling: pd.DataFrame, path: Path) -> None:
    data = rolling[rolling["status"].eq("ok")].copy()
    plt.figure(figsize=(12, 6))
    if data.empty:
        plt.text(0.5, 0.5, "Insufficient data for 252-day rolling betas", ha="center", va="center")
        plt.axis("off")
    else:
        pivot = data.pivot(index="factor", columns="model", values="beta_last")
        pivot.plot(kind="bar", ax=plt.gca())
        plt.title("Latest 252-Day Rolling Betas")
        plt.ylabel("Latest beta")
        plt.grid(axis="y", alpha=0.3)
        plt.xticks(rotation=0)
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def write_figures(outputs, output_root: Path) -> dict[str, Path]:
    fig_dir = output_root / "results" / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "factor_exposure": fig_dir / "asset_pricing_factor_exposure.png",
        "rolling_betas": fig_dir / "asset_pricing_rolling_betas.png",
        "return_attribution": fig_dir / "asset_pricing_return_attribution.png",
        "risk_attribution": fig_dir / "asset_pricing_risk_attribution.png",
    }
    plot_factor_exposure(outputs.factor_exposure_summary, paths["factor_exposure"])
    plot_rolling_betas(outputs.rolling_beta_summary, paths["rolling_betas"])
    plot_return_attribution(outputs.return_attribution, paths["return_attribution"])
    plot_risk_attribution(outputs.risk_attribution, paths["risk_attribution"])
    return paths


def write_report(outputs, output_root: Path) -> Path:
    report_dir = output_root / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / "asset_pricing_interpretation.md"
    summary = outputs.factor_exposure_summary.set_index("model")
    global_beta = summary.loc[GLOBAL_LABEL].get("beta_global_risk", float("nan")) if GLOBAL_LABEL in summary.index else float("nan")
    improved_beta = summary.loc[IMPROVED_CONVEX_LABEL].get("beta_global_risk", float("nan")) if IMPROVED_CONVEX_LABEL in summary.index else float("nan")
    text = f"""# 资产定价解释层

## 中文

本层只用于解释既有组合结果，不新增组合模型，不调参，不改变回测逻辑，也不使用因子诊断输出生成权重。

因子代理来自现有收益率资产池，并按资产名称推断为 equity、bond、commodity_gold、defensive 和 global_risk。不可识别或缺失的资产组会被跳过，并通过 `available_factors` 字段记录。

### 模型解释

- Global Relaxed Risk Parity 是解释基准组合。当前 `global_risk` beta 为 {global_beta:.3f}，因此其收益应放在广义多资产风险代理下理解，而不是解释为独立 alpha 预测。
- Improved Convex Adaptive Global RRP 是受约束优化器结果。当前 `global_risk` beta 为 {improved_beta:.3f}；它相对 Global RRP 的差异应理解为暴露、换手、约束和尾部风险惩罚共同作用的结果。
- Convex Adaptive Global RRP 是凸优化增强的基础版本，用于区分基础约束优化与改进配置的解释差异。
- Defensive Dynamic Relaxed Risk Parity 是防御型风险覆盖模型。较低或不稳定的因子 beta 可能反映风险缩放和状态响应，而不是更强的因子择时能力。

### 归因

收益归因使用已有每日权重和资产收益，将组合实现收益分摊到推断出的资产类别。风险归因使用协方差式波动贡献和压力回撤阶段平均贡献作为近似解释。

### 局限

这些因子是由同一可交易资产池构造的近似代理，不是外部学术因子。结果依赖样本区间和可用资产，不应被解释为预测信号或投资建议。最终权重仍由既有风险预算、动态选择和凸优化代码路径生成；本模块不导出生成式组合权重建议。

## English

This layer is explanatory only. It does not create portfolio models, tune parameters, alter backtest logic, or use asset-pricing outputs to generate weights.

The factor proxies are broad equal-weight proxies inferred from the existing return universe: equity, bond, commodity_gold, defensive, and global_risk. Missing groups are skipped in the regressions and recorded through the `available_factors` column.

### Model Interpretation

- Global Relaxed Risk Parity is the reference RRP portfolio. Its current `global_risk` beta is {global_beta:.3f}, so its returns are interpreted against the broad multi-asset proxy rather than as a standalone alpha forecast.
- Improved Convex Adaptive Global RRP is interpreted as a constrained optimizer result. Its current `global_risk` beta is {improved_beta:.3f}; differences versus Global RRP should be read as exposure, turnover, constraint, and tail-risk penalty effects.
- Convex Adaptive Global RRP is the base convex enhancement and helps separate base optimizer behavior from the improved configuration.
- Defensive Dynamic Relaxed Risk Parity is a defensive overlay model. Lower or unstable factor betas can reflect risk scaling and regime response rather than superior factor timing.

### Attribution

Return attribution allocates realized portfolio returns to inferred asset classes using available daily weights and asset returns. Risk attribution uses covariance-style volatility contribution and stress-period drawdown contribution approximations by asset class.

### Limitations

These are approximate proxies built from the same tradable universe, not external academic factors. The results are sample-dependent, sensitive to available assets, and should not be interpreted as predictive signals or investment advice.

Final weights remain generated by the existing risk-budgeting, dynamic selection, and convex optimization code paths. This module never exports generated portfolio weight recommendations.
"""
    path.write_text(text, encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run interpretation-only asset-pricing diagnostics.")
    parser.add_argument("--smoke", action="store_true", help="Run a small fast diagnostics pass.")
    parser.add_argument("--output-root", type=Path, default=ROOT_DIR, help="Directory where report/results outputs are written.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_root = args.output_root.resolve()
    returns = _load_returns(args.smoke)
    factors = build_factor_proxies(returns)
    print(f"Available factor proxies: {', '.join(factors.columns)}")
    models = load_or_build_models(returns, args.smoke)
    outputs = run_diagnostics(models, returns)
    table_paths = write_outputs(outputs, output_root)
    figure_paths = write_figures(outputs, output_root)
    report_path = write_report(outputs, output_root)

    print("\nGenerated asset-pricing diagnostics:")
    for path in [*table_paths.values(), *figure_paths.values(), report_path]:
        print(f"- {path}")


if __name__ == "__main__":
    main()
