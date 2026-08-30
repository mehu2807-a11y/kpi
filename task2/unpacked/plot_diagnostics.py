"""
plot_diagnostics.py
Loads the pickled outputs from run.py (no recompute) and renders one
sanity-check chart per revenue series: history + out-of-sample backtest
band + injected anomalies + the forward 30-day forecast band.
"""

import pickle

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from pipeline import INTERVAL_HIGH_Q, INTERVAL_LOW_Q, load_series

OUT_DIR = "/home/claude/bi_forecast/outputs"


def plot_series(cfg, all_data, report, diagnostics, ax):
    series_df = load_series(all_data, cfg["region"], cfg["product"], cfg["metric_name"])
    chosen = report["chosen_model"]
    bts = diagnostics["backtests"]

    if chosen == "ensemble":
        bt_p = bts["prophet"]["result"].set_index("date")
        bt_x = bts["xgboost"]["result"].set_index("date")
        common = bt_p.index.intersection(bt_x.index)
        bt_pred = (bt_p.loc[common, "pred"] + bt_x.loc[common, "pred"]) / 2
        resid_pool = np.concatenate([bts["prophet"]["result"]["residual"].to_numpy(),
                                      bts["xgboost"]["result"]["residual"].to_numpy()])
    else:
        bt = bts[chosen]["result"].set_index("date")
        bt_pred = bt["pred"]
        resid_pool = bts[chosen]["result"]["residual"].to_numpy()
    q_lo, q_hi = np.quantile(resid_pool, [INTERVAL_LOW_Q, INTERVAL_HIGH_Q])
    bt_lower, bt_upper = bt_pred + q_lo, bt_pred + q_hi

    future_df = diagnostics["future_df"]
    pf = diagnostics["point_forecasts"]
    fwd_expected = np.mean([pf["prophet"], pf["xgboost"]], axis=0) if chosen == "ensemble" else pf[chosen]
    fwd_lower, fwd_upper = fwd_expected + q_lo, fwd_expected + q_hi
    fwd_dates = future_df["date"]

    plot_from = bt_pred.index.min() - pd.Timedelta(days=30)
    hist = series_df[series_df["date"] >= plot_from]

    ax.plot(hist["date"], hist["value"], color="#8b91a0", lw=1, label="actual")
    ax.fill_between(bt_pred.index, bt_lower, bt_upper, color="#e7a33e", alpha=0.25,
                     label="backtest band (80%, out-of-sample)")
    ax.plot(bt_pred.index, bt_pred.values, color="#e7a33e", lw=1.2, label=f"backtest pred ({chosen})")

    ax.fill_between(fwd_dates, fwd_lower, fwd_upper, color="#4f8fd1", alpha=0.20, label="forward forecast band")
    ax.plot(fwd_dates, fwd_expected, color="#4f8fd1", lw=1.4, ls="--", label="forward forecast")
    ax.axvline(fwd_dates.iloc[0], color="#444", lw=0.8, ls=":")

    anomalies = series_df[series_df["_anomaly_label"].notna()]
    for _, row in anomalies.iterrows():
        ax.scatter([row["date"]], [row["value"]], color="#d64550", zorder=5, s=45,
                    label="injected anomaly" if "injected anomaly" not in [h.get_label() for h in ax.get_legend_handles_labels()[0]] else None)
        ax.annotate(row["_anomaly_label"], (row["date"], row["value"]),
                    textcoords="offset points", xytext=(6, 6), fontsize=8, color="#d64550")

    ax.set_title(f"{cfg['metric_name']} — {cfg['region']} / {cfg['product']}  "
                 f"(chosen={chosen}, backtest MAPE={report['chosen_model_mape_pct']}%)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9)
    ax.set_ylabel(cfg["metric_name"])


def main():
    all_data = pd.read_pickle(f"{OUT_DIR}/_dev_data.pkl")
    with open(f"{OUT_DIR}/_diagnostics.pkl", "rb") as f:
        saved = pickle.load(f)
    reports, diags = saved["reports"], saved["diags"]

    from data_gen import SERIES_CONFIG
    revenue_cfgs = [c for c in SERIES_CONFIG if c["metric_name"] == "revenue"]

    fig, axes = plt.subplots(len(revenue_cfgs), 1, figsize=(11, 4.2 * len(revenue_cfgs)), sharex=False)
    if len(revenue_cfgs) == 1:
        axes = [axes]

    for ax, cfg in zip(axes, revenue_cfgs):
        key = f"{cfg['metric_name']}|{cfg['region']}|{cfg['product']}"
        report = next(r for r in reports if r["region"] == cfg["region"]
                       and r["product"] == cfg["product"] and r["metric_name"] == cfg["metric_name"])
        plot_series(cfg, all_data, report, diags[key], ax)

    fig.tight_layout()
    out_path = f"{OUT_DIR}/baseline_forecast_diagnostic.png"
    fig.savefig(out_path, dpi=140)
    print("wrote", out_path)


if __name__ == "__main__":
    main()
