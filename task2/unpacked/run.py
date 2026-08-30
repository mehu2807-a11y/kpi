"""
run.py -- entry point.
Generates the dev dataset, runs the Baseline Forecast pipeline per series,
writes outputs matching the brief's schema, and sanity-checks the chosen
model's backtest predictions against the two injected anomalies per
revenue series (does the calibrated interval actually catch a real
deviation, vs. treating it as noise?).
"""

import json
import os
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from data_gen import SERIES_CONFIG, build_all
from pipeline import load_series, run_series

OUT_DIR = "/home/claude/bi_forecast/outputs"


def anomaly_check(cfg, series_df, report, diagnostics):
    anomaly_rows = series_df[series_df["_anomaly_label"].notna()]
    if anomaly_rows.empty:
        return []

    chosen = report["chosen_model"]
    bts = diagnostics["backtests"]

    if chosen == "ensemble":
        bt_p = bts["prophet"]["result"].set_index("date")
        bt_x = bts["xgboost"]["result"].set_index("date")
        common = bt_p.index.intersection(bt_x.index)
        preds = (bt_p.loc[common, "pred"] + bt_x.loc[common, "pred"]) / 2
        resid_pool = np.concatenate([bts["prophet"]["result"]["residual"].to_numpy(),
                                      bts["xgboost"]["result"]["residual"].to_numpy()])
    else:
        bt = bts[chosen]["result"].set_index("date")
        preds = bt["pred"]
        resid_pool = bts[chosen]["result"]["residual"].to_numpy()

    q_lo, q_hi = np.quantile(resid_pool, [0.10, 0.90])
    lines = []
    for _, row in anomaly_rows.iterrows():
        d = row["date"]
        if d not in preds.index:
            lines.append(f"  [{cfg['metric_name']}/{cfg['region']}] {row['_anomaly_label']} on {d.date()}: "
                          f"outside the backtest region (no fold covers it), skipped")
            continue
        pred = preds.loc[d]
        lo, hi = pred + q_lo, pred + q_hi
        caught = row["value"] < lo or row["value"] > hi
        verdict = "OUTSIDE interval -> real signal, gate would fire" if caught else \
                  "inside interval -> would be treated as noise"
        lines.append(f"  [{cfg['metric_name']}/{cfg['region']}] {row['_anomaly_label']} on {d.date()}: "
                      f"actual={row['value']:.0f} vs band [{lo:.0f}, {hi:.0f}] -> {verdict}")
    return lines


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    all_data = build_all()

    forecast_frames, reports, diags = [], [], {}

    for cfg in SERIES_CONFIG:
        series_df = load_series(all_data, cfg["region"], cfg["product"], cfg["metric_name"])
        print(f"--- {cfg['metric_name']} | {cfg['region']} / {cfg['product']} "
              f"(heavy_external_drivers={cfg['heavy_external_drivers']}) ---")
        result = run_series(series_df, cfg["heavy_external_drivers"])
        forecast_frames.append(result["forecast_rows"])
        reports.append(result["accuracy_report"])
        key = f"{cfg['metric_name']}|{cfg['region']}|{cfg['product']}"
        diags[key] = result["diagnostics"]

        rep = result["accuracy_report"]
        print(f"  chosen: {rep['chosen_model']:<9s} mape={rep['chosen_model_mape_pct']}%  "
              f"per_model={rep['per_model_mape_pct']}")

    baseline_forecast = pd.concat(forecast_frames, ignore_index=True)
    baseline_forecast.to_json(f"{OUT_DIR}/baseline_forecast.json", orient="records", indent=2)
    with open(f"{OUT_DIR}/backtest_accuracy_report.json", "w") as f:
        json.dump(reports, f, indent=2)

    print(f"\nWrote {OUT_DIR}/baseline_forecast.json ({len(baseline_forecast)} rows)")
    print(f"Wrote {OUT_DIR}/backtest_accuracy_report.json ({len(reports)} series)")

    print("\n--- anomaly sanity check (chosen model's out-of-sample backtest predictions) ---")
    for cfg, report in zip(SERIES_CONFIG, reports):
        series_df = load_series(all_data, cfg["region"], cfg["product"], cfg["metric_name"])
        key = f"{cfg['metric_name']}|{cfg['region']}|{cfg['product']}"
        for line in anomaly_check(cfg, series_df, report, diags[key]):
            print(line)

    # keep raw data + diagnostics around so plot_diagnostics.py doesn't need to recompute
    import pickle
    all_data.to_pickle(f"{OUT_DIR}/_dev_data.pkl")
    with open(f"{OUT_DIR}/_diagnostics.pkl", "wb") as f:
        pickle.dump({"reports": reports, "diags": diags}, f)
    return all_data, reports, diags


if __name__ == "__main__":
    main()
