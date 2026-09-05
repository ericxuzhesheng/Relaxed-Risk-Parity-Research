"""Fixed Global RRP structural experiments; no adaptive parameter search."""
from pathlib import Path
import json
import logging
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.backtest import run_static_backtest
from src.data_loader import load_data
from src.utils import get_config
from scripts.run_convex_adaptive_rrp import summarize_result, slice_and_rebase_result

COMMON = {"rebalance_frequency": "W", "bond_leverage_upper": 1.0,
          "gross_exposure_cap": 1.0, "risk_free_rate": 0.0, "transaction_cost_bps": 3.0}
VARIANTS = {
    "weekly_overlay": {},
    "without_overlay": {"risk_overlay_enabled": False, "trend_filter_mode": "off"},
    "equal_weight_scale": {"risk_overlay_enabled": False, "trend_filter_mode": "off", "rrp_variance_reference": "equal_weight"},
    "return_target": {"risk_overlay_enabled": False, "trend_filter_mode": "off", "rrp_variance_reference": "equal_weight", "rrp_target_annual_return": .05},
}
PRIMARY_VARIANT = "return_target"


def participation(result, universe):
    decisions = result[result.is_rebalance_day].set_index("date")
    universe = universe.set_index("date").reindex(decisions.index)
    rows = []
    for col in result.filter(regex="^weight_"):
        asset = col.removeprefix("weight_")
        eligible = universe.included_assets.fillna("").map(lambda x: asset in x.split("|"))
        weights = decisions[col]
        rows.append({"asset": asset, "eligible_weeks": int(eligible.sum()),
                     "held_eligible_weeks": int((eligible & weights.gt(5e-5)).sum()),
                     "max_eligible_weight": float(weights[eligible].max()) if eligible.any() else 0.0,
                     "ever_used": bool((eligible & weights.gt(5e-5)).any())})
    return pd.DataFrame(rows)


def main():
    logging.getLogger().setLevel(logging.ERROR)
    output = ROOT / "results/global_rrp_research"
    output.mkdir(parents=True, exist_ok=True)
    config = get_config(COMMON)
    manifest = {"variants": {k: {**COMMON, **v} for k, v in VARIANTS.items()},
                "primary_variant": PRIMARY_VARIANT, "net_return_target": .05,
                "selection": "Structural specification declared before execution; do not replace with highest-return experiment.",
                "risk_free_rate": 0.0, "risk_free_refresh": "Not required under explicit user instruction; ChinaBond diagnostic retired.",
                "participation_tolerance": 5e-5, "leverage": False}
    (output / "configuration.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    returns = load_data(source="tushare", force_update=False).dropna(how="all")
    rows = []
    for name, overrides in VARIANTS.items():
        print("Running", name, flush=True)
        folder = output / name
        folder.mkdir(exist_ok=True)
        try:
            diagnostics = {}
            result = run_static_backtest(returns, "relaxed", {**COMMON, **overrides}, diagnostics)
            result = slice_and_rebase_result(result, config["evaluation_start_date"])
            diag = diagnostics["solver"]
            diag = diag[pd.to_datetime(diag.date).ge(config["evaluation_start_date"])]
            if not diag.problem_is_dcp.all() or not diag.solver_success.all():
                raise ValueError("Non-convex or unsuccessful solve")
            if not (pd.to_datetime(diag.information_cutoff) < pd.to_datetime(diag.date)).all():
                raise ValueError("Future information")
            if not overrides.get("risk_overlay_enabled", True):
                np.testing.assert_allclose(result.filter(regex="^weight_").sum(axis=1), 1, atol=1e-6)
                delta = result.filter(regex="^weight_").to_numpy() - result.filter(regex="^previous_weight_").to_numpy()
                np.testing.assert_allclose(np.abs(delta[result.is_rebalance_day]).sum(axis=1), result.loc[result.is_rebalance_day, "turnover"], atol=1e-6)
            result.to_csv(folder / "daily_returns.csv", index=False)
            for key, frame in diagnostics.items():
                frame.to_csv(folder / f"{key}.csv", index=False)
            usage = participation(result, diagnostics["universe"])
            usage.to_csv(folder / "asset_participation.csv", index=False)
            row = summarize_result("Global RRP", result, config["evaluation_start_date"], config)
            row.update({"variant": name, "status": "passed", "target_met": row["net_annual_return"] > .05,
                        "assets_ever_used": int(usage.ever_used.sum()), "all_eligible_assets_ever_used": bool(usage.loc[usage.eligible_weeks.gt(0), "ever_used"].all())})
            rows.append(row)
            print(name, row["net_annual_return"], row["sharpe_ratio"], row["assets_ever_used"], flush=True)
        except Exception as exc:
            rows.append({"variant": name, "status": "failed", "error": str(exc)})
            print(name, "FAILED", str(exc), flush=True)
        pd.DataFrame(rows).to_csv(output / "summary.csv", index=False)


if __name__ == "__main__":
    main()
