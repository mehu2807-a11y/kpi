"""
evaluate.py — day-one precision/recall harness for the anomaly gate (Task 3)

Runs anomaly_gate.run_gate() across the synthetic dataset in chronological
order per region (exactly as the real pipeline will encounter daily rows),
maintaining rolling state (RegionHistory) correctly across days, and scores
the "revenue" verdicts against the injected ground-truth labels.
"""

import json
import os

import pandas as pd

from anomaly_gate import EventCounter, GateConfig, JsonlLog, MetricCheck, RegionHistory, run_gate
from synthetic_data import METRICS, REGIONS, generate_dataset

PRIMARY_METRIC = "revenue"
OUT_DIR = "/home/claude/pipeline_out"


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = generate_dataset()
    config = GateConfig()
    counter = EventCounter()

    noise_log = JsonlLog(os.path.join(OUT_DIR, "noise_log.jsonl"))
    anomaly_log = JsonlLog(os.path.join(OUT_DIR, "anomaly_events.jsonl"))

    results = []
    example_noise_suppressed_blip = None
    example_anomaly = None
    example_shock_day1 = None

    for region in REGIONS:
        region_df = df[df.region == region].sort_values("date")
        history = RegionHistory()

        for d, group in region_df.groupby("date", sort=True):
            checks = {
                row.metric: MetricCheck(
                    date=row.date, region=row.region, metric=row.metric,
                    actual_value=row.actual_value, expected_value=row.expected_value,
                    lower_bound=row.lower_bound, upper_bound=row.upper_bound,
                )
                for row in group.itertuples()
            }
            if PRIMARY_METRIC not in checks:
                continue

            primary_check = checks[PRIMARY_METRIC]
            correlated = [checks[m] for m in METRICS if m != PRIMARY_METRIC and m in checks]

            record, internal = run_gate(primary_check, correlated, history, config, counter)
            history.push(internal)  # update AFTER scoring today -- no leakage

            truth_row = group[group.metric == PRIMARY_METRIC].iloc[0]
            is_true_anomaly = bool(truth_row.is_true_anomaly)
            predicted_anomaly = record["verdict"] == "anomaly"

            results.append({
                "date": d, "region": region,
                "is_true_anomaly": is_true_anomaly,
                "anomaly_type": truth_row.anomaly_type,
                "predicted_anomaly": predicted_anomaly,
                "severity_score": record["severity_score"],
            })

            if record["verdict"] == "noise":
                noise_log.write(record)
                if example_noise_suppressed_blip is None and truth_row.anomaly_type == "single_metric_noise":
                    example_noise_suppressed_blip = record
            else:
                anomaly_log.write(record)
                if example_anomaly is None and is_true_anomaly:
                    example_anomaly = record
                if (example_shock_day1 is None and truth_row.anomaly_type == "shock"
                        and record["detection"]["consecutive_flagged_periods"] == 1):
                    example_shock_day1 = record

    noise_log.close()
    anomaly_log.close()

    res_df = pd.DataFrame(results)
    tp = int(((res_df.is_true_anomaly) & (res_df.predicted_anomaly)).sum())
    fp = int(((~res_df.is_true_anomaly) & (res_df.predicted_anomaly)).sum())
    fn = int(((res_df.is_true_anomaly) & (~res_df.predicted_anomaly)).sum())
    tn = int(((~res_df.is_true_anomaly) & (~res_df.predicted_anomaly)).sum())

    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    f1 = 2 * precision * recall / (precision + recall) if (precision and recall) else float("nan")

    print("=== Confusion matrix (metric=revenue, all 3 regions, 180 days each) ===")
    print(f"TP={tp}  FP={fp}  FN={fn}  TN={tn}")
    print(f"Precision={precision:.3f}  Recall={recall:.3f}  F1={f1:.3f}")

    print("\n=== Flag rate by injected event type ===")
    for atype, grp in res_df.groupby("anomaly_type"):
        rate = grp.predicted_anomaly.mean()
        print(f"{atype:22s} n={len(grp):3d}  flagged_as_anomaly_rate={rate:.2f}")

    print("\n=== Day-by-day detail for one full 'sustained' window (shows persistence kicking in) ===")
    sustained_dates = res_df[res_df.anomaly_type == "sustained"][["date", "region"]].drop_duplicates()
    first_region, first_dates = None, []
    if len(sustained_dates):
        first_region = sustained_dates.iloc[0].region
        first_dates = sorted(sustained_dates[sustained_dates.region == first_region].date)[:5]
        detail = res_df[(res_df.region == first_region) & (res_df.date.isin(first_dates))]
        print(detail[["date", "region", "predicted_anomaly", "severity_score"]].to_string(index=False))

    print("\n=== Example: single-metric blip correctly suppressed as noise ===")
    print(json.dumps(example_noise_suppressed_blip, indent=2))

    print("\n=== Example: single-day shock confirmed as anomaly on day 1 (secondary-threshold / strong-corroboration path) ===")
    print(json.dumps(example_shock_day1, indent=2))

    print("\n=== Example: confirmed anomaly record (full schema) ===")
    print(json.dumps(example_anomaly, indent=2))

    res_df.to_csv(os.path.join(OUT_DIR, "eval_results.csv"), index=False)
    with open(os.path.join(OUT_DIR, "eval_summary.json"), "w") as f:
        json.dump({
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": precision, "recall": recall, "f1": f1,
        }, f, indent=2)


if __name__ == "__main__":
    main()
