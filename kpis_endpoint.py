"""
kpis_endpoint.py -- computes live status for every KPI in kpi_contract.py by
running Task 1's real data through Task 3's real gate. This is the missing
piece INTEGRATION.md pointed at: /analyze tells you the STORY behind one
already-known anomaly; this tells you WHICH of your KPIs currently has one.

Import this into app.py and add:

    from kpis_endpoint import get_kpi_statuses

    @app.route('/kpis', methods=['GET'])
    def kpis():
        return jsonify(get_kpi_statuses())
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "orchestrator"))
sys.path.insert(0, str(PROJECT_ROOT / "task1"))

from scoped_import import scoped_task_dir
from kpi_contract import DEFAULT_KPI_CONTRACT

DB_PATH = str(PROJECT_ROOT / "task1" / "bi_pipeline.db")
REGION, PRODUCT = "Region X", "Product A"   # which slice this endpoint watches


def _load_metrics_table():
    with scoped_task_dir(str(PROJECT_ROOT / "task1")):
        from ingest_pipeline import storage
    return storage.query(DB_PATH, "SELECT * FROM metrics_table")


def _trailing_baseline(series, history_window=24, holdout_days=5):
    """Trailing mean/std baseline (fallback for short series < 60 days)."""
    pre = series[:-holdout_days] if len(series) > holdout_days else series
    window = pre[-history_window:]
    mu = float(window.mean())
    sigma = float(window.std() or mu * 0.02 or 1.0)
    return mu, sigma


def _prophet_baseline(dates_list: list, values: list, holdout_days: int = 5):
    """
    Prophet-backed expected value + sigma for the last data point.
    Falls back to _trailing_baseline if Prophet unavailable or < 60 points.
    Returns (mu, sigma, method_str).
    """
    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from prophet_forecast import forecast_next
        hist_dates = dates_list[:-holdout_days] if len(dates_list) > holdout_days else dates_list
        hist_vals = list(values[:-holdout_days]) if len(values) > holdout_days else list(values)
        result = forecast_next(hist_dates, hist_vals, horizon_days=holdout_days)
        mu = result.expected
        # Use half the CI width as the sigma proxy
        sigma = max((result.upper - result.lower) / 4.0, abs(mu) * 0.02, 1.0)
        return float(mu), float(sigma), result.method
    except Exception:
        import numpy as _np
        mu, sigma = _trailing_baseline(_np.array(values))
        return mu, sigma, "trailing_mean_fallback"


# kpi_contract.py's ids don't all match Task 1's real metric_name values --
# found by running this against real data: "revenue_total" silently came
# back insufficient_data because Task 1 actually stores it as "revenue".
# Same class of mismatch as the marketing_spend/support_ticket ones found
# earlier in this project; bridged here, in the adapter, not by renaming
# either side.
KPI_ID_TO_METRIC_NAME = {"revenue_total": "revenue"}


def get_kpi_statuses() -> list[dict]:
    with scoped_task_dir(str(PROJECT_ROOT / "task3")):
        import anomaly_gate as T3

    metrics_table = _load_metrics_table()
    metrics_table["date"] = metrics_table["date"].astype(str)

    out = []
    import time
    for kpi_id, kpi_def in DEFAULT_KPI_CONTRACT.kpis.items():
        t0 = time.time()
        metric_name = KPI_ID_TO_METRIC_NAME.get(kpi_id, kpi_id)
        product_filter = "ALL" if kpi_id == "marketing_spend" else PRODUCT
        series = metrics_table[
            (metrics_table["region"] == REGION)
            & (metrics_table["product"] == product_filter)
            & (metrics_table["metric_name"] == metric_name)
        ].sort_values("date")

        if len(series) < 6:
            out.append({"kpi_id": kpi_id, "name": kpi_def.name, "status": "insufficient_data"})
            continue

        values = series["value"].to_numpy()
        dates_list = series["date"].tolist()
        t1 = time.time()
        mu, sigma, forecast_method = _prophet_baseline(dates_list, values)
        t2 = time.time()
        latest_date, latest_value = series["date"].iloc[-1], float(values[-1])

        history = T3.RegionHistory()
        config, counter = T3.GateConfig(), T3.EventCounter()
        record = None

        eval_days = min(1, len(series))
        fast_forward_days = max(0, len(series) - eval_days)
        
        for date, val in zip(series["date"].iloc[:fast_forward_days], 
                             values[:fast_forward_days]):
            residual = (float(val) - mu) / max(sigma * 5.0, 1.0)
            history.push(T3.GateInternal(
                metric=kpi_id, region=REGION, flagged_today=False, 
                residual=residual, correlated_residuals={}
            ))

        for date, val in zip(series["date"].iloc[fast_forward_days:], 
                             values[fast_forward_days:]):
            check = T3.MetricCheck(date=date, region=REGION, metric=kpi_id,
                                    actual_value=float(val), expected_value=mu,
                                    lower_bound=mu - 2.5 * sigma, upper_bound=mu + 2.5 * sigma)
            record, internal = T3.run_gate(check, [], history, config, counter)
            history.push(internal)
        
        t3 = time.time()
        delta_pct = (latest_value - mu) / mu * 100 if mu else 0.0
        out.append({
            "kpi_id": kpi_id,
            "name": kpi_def.name,
            "value": round(latest_value, 2),
            "expected_value": round(mu, 2),
            "delta_pct": round(delta_pct, 1),
            "date": latest_date,
            "status": "anomaly" if record["verdict"] == "anomaly" else "noise",
            "severity_score": record.get("severity_score"),
            "forecast_method": forecast_method,
            "gate_record": record,   # feed straight into orchestrate.run_downstream_from_record()
        })
        print(f"DEBUG KPI {kpi_id}: {t1-t0:.2f}s prep, {t2-t1:.2f}s prophet, {t3-t2:.2f}s gate")
    print("DEBUG KPI ENDPOINT DONE")
    return out


if __name__ == "__main__":
    import json
    print(json.dumps(get_kpi_statuses(), indent=2, default=str))
