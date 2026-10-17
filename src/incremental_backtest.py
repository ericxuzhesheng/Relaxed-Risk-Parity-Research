"""Resume publication backtests from an unchanged, completed daily prefix."""
from pathlib import Path
import json

import numpy as np
import pandas as pd

from src.convex_adaptive_rrp import drift_weights


def resume_weights(returns, resume):
    if resume is None:
        return returns.index, np.zeros(len(returns.columns))
    date = pd.Timestamp(resume["date"])
    weights = np.array([resume[f"weight_{asset}"] for asset in returns.columns], dtype=float)
    return returns.index[returns.index > date], drift_weights(weights, returns.loc[date])


def _frame_record(frame):
    return {"columns": frame.columns.tolist(), "data": frame.to_numpy(dtype=object).tolist(),
            "dtypes": frame.dtypes.astype(str).to_dict()}


def _restore_frame(record):
    return pd.DataFrame(record["data"], columns=record["columns"]).astype(record["dtypes"])


def _json_value(value):
    if value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"Unsupported checkpoint value: {type(value)}")


def _past_contract(contract, date):
    result = dict(contract)
    config = dict(result["configuration"])
    config.pop("evaluation_end_date", None)
    config.pop("tushare_token", None)
    if "rrp_parameter_schedule" in config:
        config["rrp_parameter_schedule"] = [
            row for row in config["rrp_parameter_schedule"]
            if pd.Timestamp(row["effective_date"]) <= date
        ]
    result["configuration"] = config
    return result


def run_incremental_backtest(returns, runner, *, path, contract, diagnostics_out=None, force=False):
    """Runner receives the full input history and an optional last retained row.

    An append replays the old final observation: its provisional period-end
    rebalance may disappear when another observation in that period arrives.
    Historical revisions, changed settings/code, and invalid files use a full run.
    """
    if not returns.index.is_unique or not returns.index.is_monotonic_increasing:
        raise ValueError("Backtest inputs must have unique, increasing dates")
    path = Path(path)
    contract = json.loads(json.dumps(contract))
    prefix = pd.DataFrame()
    previous_diagnostics = {}
    mode = "full"
    if not force:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            old_inputs = _restore_frame(record["inputs"])
            old_inputs.index = pd.DatetimeIndex(record["dates"], name=record["index_name"])
            old = _restore_frame(record["result"])
            count = len(old_inputs)
            if (count > 0 and count <= len(returns)
                    and old_inputs.equals(returns.iloc[:count])
                    and pd.DatetimeIndex(old.date).equals(old_inputs.index)):
                keep = count if count == len(returns) else count - 1
                if keep > 0:
                    cutoff = pd.Timestamp(old.date.iloc[keep - 1])
                    if _past_contract(record["contract"], cutoff) == _past_contract(contract, cutoff):
                        prefix = old.iloc[:keep].copy()
                        previous_diagnostics = {
                            key: _restore_frame(value) for key, value in record["diagnostics"].items()
                        }
                        mode = "unchanged" if keep == len(returns) else "incremental"
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            prefix = pd.DataFrame()
            previous_diagnostics = {}
            mode = "full"
    diagnostics = {}
    if mode == "unchanged":
        result = prefix
        diagnostics = previous_diagnostics
    else:
        resume = None if prefix.empty else prefix.iloc[-1]
        tail = runner(returns, resume, diagnostics)
        result = tail if prefix.empty else pd.concat([prefix, tail], ignore_index=True)
        if not pd.DatetimeIndex(result.date).equals(returns.index):
            raise ValueError("Resumed backtest does not cover the input dates exactly")
        for key, previous in previous_diagnostics.items():
            retained = previous if previous.empty else previous[pd.to_datetime(previous.date) <= resume["date"]]
            current = diagnostics.get(key, pd.DataFrame())
            diagnostics[key] = (retained.reset_index(drop=True) if current.empty
                                else pd.concat([retained, current], ignore_index=True)
                                if not retained.empty else current)
    if diagnostics_out is not None:
        diagnostics_out.update(diagnostics)
    if mode != "unchanged":
        record = {"contract": contract, "inputs": _frame_record(returns),
                  "dates": returns.index.astype(str).tolist(), "index_name": returns.index.name,
                  "result": _frame_record(result),
                  "diagnostics": {key: _frame_record(value) for key, value in diagnostics.items()}}
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(record, default=_json_value), encoding="utf-8")
        temporary.replace(path)
    print(f"{path.stem}: {mode}; reused {len(prefix)} days, computed {len(result) - len(prefix)} days", flush=True)
    return result
