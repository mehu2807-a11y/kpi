# Task 3 — Anomaly Gate (the noise filter)

Role: ML Engineer (Anomaly Detection / Applied Statistics)
Phase: `detect` (last of 3 modules) · Pipeline position: `BaselineForecast → Anomaly Gate → [Task 4 / Task 5]`

Decides, per `(metric, region, date)`, whether a deviation from the baseline
forecast is real or noise. Only `"anomaly"` records are allowed to reach
Task 4 (correlate drivers) and Task 5 (retrieve evidence) — that's the
contract this module exists to enforce.

## Files

| File | What it is |
|---|---|
| `anomaly_gate.py` | The gate itself — importable, no I/O side effects beyond `JsonlLog`. |
| `synthetic_data.py` | Day-one test data generator (see brief: "measure your own detector's precision/recall before real data exists"). |
| `evaluate.py` | Runs the gate chronologically over the synthetic data, maintaining rolling state correctly, and reports precision/recall. |

Run `python3 evaluate.py` — prints a confusion matrix, a per-event-type
breakdown, a day-by-day trace of one sustained window, and three example
output records, and writes `pipeline_out/noise_log.jsonl`,
`pipeline_out/anomaly_events.jsonl`, `eval_results.csv`, and
`eval_summary.json`. Requires `numpy`, `pandas`, `scikit-learn`.

## The six steps → the code

| # | Brief | Function |
|---|---|---|
| 1 | Normalized residual | `normalized_residual()` |
| 2 | Statistical test (~1.5–2x) | `statistical_flag()` |
| 3 | Multivariate check (Isolation Forest) | `MultivariateChecker.score()` |
| 4 | Persistence check (3+ periods, or single-period 3x) | `persistence_check()` |
| 5 | Combine into `severity_score` | `severity_score()` |
| 6 | Decision + output | `run_gate()` |

## Two ambiguities in the brief, and how this resolves them

**Full-width vs. half-width.** Step 1 gives an explicit formula: `residual =
(actual - expected) / (upper_bound - lower_bound)` — normalized by the
*full* interval width. Step 2 then describes the threshold as "~1.5–2x the
interval *half*-width." Literally composed, those two lines need a factor of
2 reconciled somewhere. This module takes step 1's formula exactly as
written and applies "1.5–2x" directly as the threshold value on that
residual (`GateConfig.primary_threshold`, default **1.75**), treating
"half-width" as loose phrasing rather than a second formula to solve for.
If the intent was actually a factor-of-2-different threshold, it's one
number to change.

**"Weighted blend ... and a persistence multiplier."** A *multiplier* is
naturally multiplicative, not a third additive term, so:

```
severity = clip((w_residual * residual_component + w_multivariate * mv_score) * persistence_multiplier, 0, 1)
```

This also matches the brief's stated core rule ("if it's noise, the system
does nothing"): a single-period, moderate deviation gets damped by a
sub-1.0 multiplier unless it persists or is extreme — rather than
persistence just being added into the score as one more contributor.

## A bug this testing caught (worth knowing if you touch this code)

The Isolation Forest fits on a trailing window of recent residual vectors.
Early on, a **persisting** anomaly's own earlier days would get pushed into
that trailing window and start defining a new "normal" for themselves — by
day 4–5 of a 5-day sustained shift, the model had partly absorbed days 1–3
and stopped flagging it. Fixed by excluding previously-flagged days from
the Isolation Forest's fit set (`run_gate`'s `clean_rows` filter) — the
model still scores *today* against that filtered window, it just doesn't
train on days that were themselves already flagged. This is what
`detection.multivariate_fit_rows` in the output reports: how many clean
historical rows backed today's multivariate score.

## Output schema

**Noise** (matches the brief's example exactly):
```json
{"date": "2026-07-14", "region": "Region X", "metric": "revenue", "residual": 0.31, "severity_score": 0.22, "verdict": "noise"}
```

**Anomaly** (completing the brief's cut-off fragment
`{"event_id": "evt_00087", "metric_name": "revenue", "region": ...`):
```json
{
  "event_id": "evt_00003",
  "metric_name": "revenue",
  "region": "Region X",
  "date": "2026-05-12",
  "actual_value": 48238.67,
  "expected_value": 25897.12,
  "lower_bound": 22843.49,
  "upper_bound": 28950.75,
  "residual": 3.6582,
  "direction": "above_expected",
  "severity_score": 1.0,
  "verdict": "anomaly",
  "detection": {
    "statistical_flag": true,
    "multivariate_flag": true,
    "multivariate_status": "ok",
    "multivariate_score": 1.0,
    "multivariate_fit_rows": 70,
    "consecutive_flagged_periods": 1,
    "secondary_threshold_breach": true,
    "persistence_multiplier": 1.0
  },
  "correlated_metrics": [
    {"metric": "units_sold", "actual_value": 1136.37, "expected_value": 618.93, "residual": 4.6266},
    {"metric": "traffic", "actual_value": 17213.91, "expected_value": 10287.3, "residual": 5.0532},
    {"metric": "avg_order_value", "actual_value": 41.56, "expected_value": 41.59, "residual": -0.0067}
  ]
}
```
`direction` and `correlated_metrics` are there so Task 4 (correlate
drivers) doesn't have to re-derive "what else moved" from scratch — it's
carried forward, not recomputed. `detection` is the audit trail: it exists
because "explain why a metric moved" was the whole point of the product in
the first place, so the gate's own reasoning should be inspectable, not
just its verdict.

## Tuning knobs (all in `GateConfig`)

| Knob | Default | What moving it does |
|---|---|---|
| `primary_threshold` | 1.75 | Lower = more days reach the statistical flag; brief says start 1.5–2x. |
| `secondary_threshold` | 3.0 | The single-period override bar (step 4) — also caps `residual_component`. |
| `min_consecutive` | 3 | Days of persistence for "confirmed" (brief's number, not adjusted here). |
| `w_residual` / `w_multivariate` | 0.5 / 0.5 | Blend weights — see below, this is the main precision/recall lever. |
| `severity_threshold` | 0.5 | Final noise/anomaly cutoff on the 0–1 score. |

The brief gives explicit starting numbers for the first three; it doesn't
for the blend weights or the decision threshold, so 0.5/0.5/0.5 is used as
a neutral, unbiased starting point rather than something fit to this
synthetic set.

## Evaluation (synthetic, day-one, `python3 evaluate.py`)

3 regions × 180 days, gating `revenue` with `units_sold` / `traffic` /
`avg_order_value` as correlates. 51 injected events across 3 types
(9 single-day shocks, 30 sustained-window days, 12 single-metric blips)
plus 447 ordinary days:

| | Count | Result |
|---|---|---|
| Precision | — | **0.733** (22 TP / 8 FP) |
| Recall | — | **0.564** (22 TP / 17 FN) |
| F1 | — | **0.638** |
| Shocks caught | 9 | 78% |
| Sustained-window days caught | 30 | 50% |
| Single-metric blips correctly suppressed | 12 | 83% (2 leaked through) |
| Ordinary days correctly left alone | 447 | 99% |

Reading this: the gate is precision-leaning by default, exactly matching
the brief's stated priority ("no false alarm, no analyst time spent") —
99% of ordinary noisy days and 83% of uncorroborated single-metric blips
are correctly left alone. The cost shows up as recall on the *sustained*
category: moderate (15–30%), multi-day shifts often don't cross the
decision threshold until day 2–3 of 5, so roughly half of those days are
still (correctly, if conservatively) sitting in `NoiseLog` on their first
day or two.

If recall matters more than precision for your use case, `w_multivariate`
is the lever: shifting the blend to 0.35/0.65 (residual/multivariate) on
this same synthetic set moves recall to 0.769 and precision down to 0.638
(F1 0.698) — more of the sustained window gets caught earlier, at the cost
of more ordinary-noise false positives. Not shipped as the default because
it trades away exactly the property (few false alarms) the brief calls out
as the core design goal — but it's one number to change if your priorities
differ.

## Known simplification

The baseline forecast used for testing (`synthetic_data._rolling_baseline`)
is a day-of-week-adjusted trailing mean ± 2σ — a reasonable stand-in, not
Task 2's actual model. Once Task 2 ships, `MetricsTable` / `BaselineForecast`
rows feed `MetricCheck` the same way the synthetic rows do here; nothing in
`anomaly_gate.py` changes.
