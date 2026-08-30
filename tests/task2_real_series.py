"""
task2_real_series.py -- turns Task 2's REAL backtest output (cached in
_diagnostics.pkl from its own run.py) into day-by-day MetricCheck sequences,
so Task 3's actual gate can be walked chronologically over real forecast /
actual / interval data instead of a hand-rolled stand-in baseline.

Why the backtest fold predictions, not the 30-day forward baseline_forecast.json:
the forward file only covers 30 future days with no actuals to gate against
yet. The backtest folds cover ~1 calendar year of *historical* out-of-sample
predictions, each with a real actual value already recorded -- including
Task 2's own injected, unflagged anomalies -- which is exactly the shape
Task 3's gate needs: many days of (actual, expected, lower, upper) to walk
chronologically while maintaining rolling state.
"""
from __future__ import annotations

import pickle
from pathlib import Path
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIAG_PATH = str(PROJECT_ROOT / "task2" / "outputs" / "_diagnostics.pkl")
DEV_DATA_PATH = str(PROJECT_ROOT / "task2" / "outputs" / "_dev_data.pkl")

INTERVAL_LOW_Q, INTERVAL_HIGH_Q = 0.10, 0.90  # matches Task 2's own pipeline.py constants


def _series_key(metric_name, region, product):
    return f"{metric_name}|{region}|{product}"


def load_real_baseline_series(metric_name: str, region: str, product: str) -> pd.DataFrame:
    """Returns date, actual, expected_value, lower_bound, upper_bound -- built
    from Task 2's chosen model's real out-of-sample backtest predictions,
    calibrated the same way Task 2's own pipeline.py calibrates its forward
    forecast interval (residual quantiles from the SAME backtest pool)."""
    with open(DIAG_PATH, "rb") as f:
        diag = pickle.load(f)
    key = _series_key(metric_name, region, product)
    diags = diag["diags"][key]
    reports = {f"{r['metric_name']}|{r['region']}|{r['product']}": r for r in diag["reports"]}
    chosen = reports[key]["chosen_model"]
    bts = diags["backtests"]

    if chosen == "ensemble":
        bt_p = bts["prophet"]["result"].set_index("date")
        bt_x = bts["xgboost"]["result"].set_index("date")
        common = bt_p.index.intersection(bt_x.index)
        pred = (bt_p.loc[common, "pred"] + bt_x.loc[common, "pred"]) / 2
        actual = bt_p.loc[common, "actual"]
        resid_pool = np.concatenate([
            bts["prophet"]["result"]["residual"].to_numpy(),
            bts["xgboost"]["result"]["residual"].to_numpy(),
        ])
        dates = common
    else:
        bt = bts[chosen]["result"].set_index("date")
        pred = bt["pred"]
        actual = bt["actual"]
        resid_pool = bt["residual"].to_numpy()
        dates = bt.index

    q_lo, q_hi = np.quantile(resid_pool, [INTERVAL_LOW_Q, INTERVAL_HIGH_Q])
    out = pd.DataFrame({
        "date": dates,
        "actual_value": actual.to_numpy(),
        "expected_value": pred.to_numpy(),
        "lower_bound": pred.to_numpy() + q_lo,
        "upper_bound": pred.to_numpy() + q_hi,
    }).sort_values("date").reset_index(drop=True)
    return out


def load_anomaly_label_dates(metric_name: str, region: str, product: str) -> dict:
    """The (date -> label) map of Task 2's injected, unflagged anomalies for
    this series, straight from its dev data generator, for cross-checking
    Task 3's real verdicts against what was actually planted."""
    dev = pd.read_pickle(DEV_DATA_PATH)
    mask = (
        (dev["metric_name"] == metric_name) & (dev["region"] == region) & (dev["product"] == product)
        & dev["_anomaly_label"].notna()
    )
    rows = dev.loc[mask, ["date", "_anomaly_label"]]
    return {row["date"].date().isoformat(): row["_anomaly_label"] for _, row in rows.iterrows()}
