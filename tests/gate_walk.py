"""
gate_walk.py -- walks Task 3's real run_gate() chronologically over a
(actual, expected, lower, upper) series, maintaining RegionHistory state
exactly the way a live orchestrator would (state advances on every day,
noise or anomaly alike -- this is what makes the persistence check work).
"""
from __future__ import annotations
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "orchestrator"))
from scoped_import import scoped_task_dir

with scoped_task_dir(str(PROJECT_ROOT / "task3")):
    import anomaly_gate as T3


def walk_series(baseline_df, region: str, metric: str, correlated_series: dict[str, "pd.DataFrame"] = None,
                 gate_config=None, event_counter=None, history=None):
    """
    baseline_df: DataFrame with date, actual_value, expected_value, lower_bound, upper_bound
                 for the PRIMARY metric, one row per day, chronological.
    correlated_series: {metric_name: same-shaped DataFrame} for correlated metrics,
                 aligned by date (missing dates on a given day are simply omitted
                 from that day's correlated_checks -- Task 1's "missing data stays
                 missing, not zero" principle, carried through here).
    Returns: list of (date, record_dict, PipelineResult-or-None) -- PipelineResult
             is None for every row where the caller doesn't ask this function to
             run the full downstream chain (see run_all.py for that wiring).
    """
    gate_config = gate_config or T3.GateConfig()
    event_counter = event_counter or T3.EventCounter()
    history = history or T3.RegionHistory()
    correlated_series = correlated_series or {}

    results = []
    for _, row in baseline_df.iterrows():
        d = row["date"]
        d_str = d.date().isoformat() if hasattr(d, "date") else str(d)
        check = T3.MetricCheck(
            date=d_str, region=region, metric=metric,
            actual_value=float(row["actual_value"]), expected_value=float(row["expected_value"]),
            lower_bound=float(row["lower_bound"]), upper_bound=float(row["upper_bound"]),
        )
        correlated_checks = []
        for cmetric, cdf in correlated_series.items():
            crow = cdf[cdf["date"] == d]
            if len(crow) == 1:
                r = crow.iloc[0]
                correlated_checks.append(T3.MetricCheck(
                    date=d_str, region=region, metric=cmetric,
                    actual_value=float(r["actual_value"]), expected_value=float(r["expected_value"]),
                    lower_bound=float(r["lower_bound"]), upper_bound=float(r["upper_bound"]),
                ))
        record, internal = T3.run_gate(check, correlated_checks, history, gate_config, event_counter)
        history.push(internal)
        results.append((d_str, record))
    return results, history, event_counter
