"""
adapters.py -- Task 7's schema-reconciliation layer.

Every task built its own version of "AnomalyEvent" / "CorrelationResult" /
"RetrievedEvidence" as a day-one, standalone assumption (each README says so
explicitly). None of them are wrong -- they just don't match each other
field-for-field. This is the one place those differences get reconciled, so
no individual task module has to change.

Concretely, three different AnomalyEvent shapes exist:
  Task 3 (real, from anomaly_gate.py)  : event_id, metric_name, region, date,
                                          actual_value, expected_value, ...,
                                          direction="above_expected"/"below_expected"
  Task 4 (its own dataclass)           : metric, region, window_start, window_end, magnitude
  Task 5 (its own dataclass)           : anomaly_id, metric, region, window_start,
                                          window_end, magnitude_pct, direction="up"/"down"
  Task 6 (its own dataclass)           : anomaly_id, metric_name, entity, direction=
                                          "increase"/"decrease", magnitude_pct (UNSIGNED),
                                          baseline_value, observed_value, window_start,
                                          window_end, detected_at
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_cls, datetime, timedelta
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# One canonical, orchestrator-level anomaly record built from Task 3's real
# output. Every downstream adapter below reads from THIS, not from Task 3's
# raw dict directly, so there's exactly one place the "how many days was
# this window" decision gets made.
# ---------------------------------------------------------------------------

@dataclass
class CanonicalAnomaly:
    event_id: str
    metric: str
    region: str
    date: str                  # the day the gate fired, ISO
    window_start: str          # ISO
    window_end: str            # ISO, == date
    actual_value: float
    expected_value: float
    direction_down: bool       # True if actual < expected
    magnitude_frac: float      # signed fractional deviation, e.g. -0.075
    severity_score: float


def canonicalize_task3_record(record: dict) -> CanonicalAnomaly:
    """record is Task 3's real run_gate() output dict with verdict == 'anomaly'."""
    assert record["verdict"] == "anomaly", "canonicalize_task3_record called on a noise record"
    window_days = max(1, record["detection"]["consecutive_flagged_periods"])
    end = datetime.fromisoformat(record["date"]).date()
    start = end - timedelta(days=window_days - 1)
    magnitude_frac = (record["actual_value"] - record["expected_value"]) / record["expected_value"]
    return CanonicalAnomaly(
        event_id=record["event_id"],
        metric=record["metric_name"],
        region=record["region"],
        date=record["date"],
        window_start=start.isoformat(),
        window_end=end.isoformat(),
        actual_value=record["actual_value"],
        expected_value=record["expected_value"],
        direction_down=record["direction"] == "below_expected",
        magnitude_frac=magnitude_frac,
        severity_score=record["severity_score"],
    )


def to_task4_anomaly_event(a: CanonicalAnomaly, task4_module):
    """task4_module is the imported correlate_drivers.py module (has AnomalyEvent)."""
    return task4_module.AnomalyEvent(
        metric=a.metric,
        region=a.region,
        window_start=a.window_start,
        window_end=a.window_end,
        magnitude=round(a.magnitude_frac, 4),
    )


def to_task5_anomaly_event(a: CanonicalAnomaly, t5_AnomalyEvent):
    return t5_AnomalyEvent(
        anomaly_id=a.event_id,
        metric=a.metric,
        region=a.region,
        window_start=date_cls.fromisoformat(a.window_start),
        window_end=date_cls.fromisoformat(a.window_end),
        magnitude_pct=round(a.magnitude_frac * 100, 2),
        direction="down" if a.direction_down else "up",
    )


def to_task6_anomaly_event(a: CanonicalAnomaly, t6_AnomalyEvent):
    return t6_AnomalyEvent(
        anomaly_id=a.event_id,
        metric_name=a.metric,
        entity=a.region,
        direction="decrease" if a.direction_down else "increase",
        magnitude_pct=round(abs(a.magnitude_frac) * 100, 2),   # Task 6's field is UNSIGNED
        baseline_value=a.expected_value,
        observed_value=a.actual_value,
        window_start=a.window_start,
        window_end=a.window_end,
        detected_at=datetime.fromisoformat(a.date).isoformat() + "T00:00:00",
    )


# ---------------------------------------------------------------------------
# MetricsTable (Task 1, long format: date, region, product, metric_name,
# value) -> the wide per-region DataFrame Task 4's correlate_drivers() needs
# (one row per date, one column per candidate feature + the target metric).
#
# Aggregation choices (region-level, since Task 3 gates at region grain, not
# product grain -- MetricCheck has no product field):
#   revenue, units_sold        -> sum across products (additive)
#   inventory_level            -> sum across products (total regional stock)
#   avg_price                  -> simple mean across products (no per-unit
#                                  sales weight available at this layer;
#                                  documented simplification, not a hidden one)
#   marketing_spend            -> product == "ALL" rows only, per Task 1's
#                                  own README ("branch on that sentinel")
#   complaint_sentiment_score  -> mean across whatever products/docs it
#                                  was attributed to for that region/day
# ---------------------------------------------------------------------------

_SUM_METRICS = {"revenue", "units_sold", "inventory_level"}
_MEAN_METRICS = {"avg_price", "complaint_sentiment_score"}


def metrics_table_to_region_wide(metrics_table: pd.DataFrame, region: str) -> pd.DataFrame:
    df = metrics_table[metrics_table["region"] == region].copy()
    df["date"] = pd.to_datetime(df["date"])

    frames = []
    for metric in sorted(df["metric_name"].unique()):
        sub = df[df["metric_name"] == metric]
        if metric == "marketing_spend":
            sub = sub[sub["product"] == "ALL"]
            g = sub.groupby("date")["value"].sum()
        elif metric in _SUM_METRICS:
            g = sub.groupby("date")["value"].sum()
        elif metric in _MEAN_METRICS:
            g = sub.groupby("date")["value"].mean()
        else:
            g = sub.groupby("date")["value"].mean()
        frames.append(g.rename(metric))

    wide = pd.concat(frames, axis=1).sort_index().reset_index()
    wide = wide.rename(columns={"index": "date"})
    return wide


# ---------------------------------------------------------------------------
# Task 1 DocumentStore rows (dicts) -> Task 5's DocumentRecord dataclass.
# Task 1's schema has no `title` field; Task 5's DocumentRecord requires one.
# Filled here from the first few words of raw_text -- flagging it as a fill,
# not silently inventing a "real" title.
# ---------------------------------------------------------------------------

# Task 1's real source values include "support_ticket"; Task 5's pipeline.py
# tags a doc "internal" with an EXACT string match on `doc.source == "support"`
# (see _tag_for() there). Left unreconciled, every real support ticket falls
# through to the "market" tag by accident -- found by inspecting Task 5's
# real output on Task 1's real DocumentStore (every ticket came back tagged
# "market"), not a hypothetical. Normalized here rather than editing Task 5's
# own tagging logic, since the fix belongs at the boundary between the two
# tasks' independently-chosen vocabularies, not inside either task.
_SOURCE_NORMALIZE = {
    "support_ticket": "support",
}


def to_task5_document_records(document_store_rows: list[dict], t5_DocumentRecord):
    out = []
    for row in document_store_rows:
        text = row["raw_text"]
        title = text if len(text) <= 72 else text[:71].rsplit(" ", 1)[0] + "\u2026"
        source = _SOURCE_NORMALIZE.get(row["source"], row["source"])
        out.append(t5_DocumentRecord(
            doc_id=row["doc_id"],
            date=date_cls.fromisoformat(row["date"]),
            source=source,
            title=title,
            text=text,
            region_tags=list(row["region_tags"]),
            entity_tags=list(row["entity_tags"]),
        ))
    return out


# ---------------------------------------------------------------------------
# Task 4's raw correlation_result (list of dicts, already sorted by
# shap_contribution desc) -> Task 5's CorrelationResult(top_drivers=[...])
# and Task 6's CorrelationResult(drivers=[...]).
# ---------------------------------------------------------------------------

_DRIVER_CATEGORY = {
    "avg_price": "pricing",
    "inventory_level": "internal_ops",
    "marketing_spend": "internal_ops",
    "complaint_sentiment_score": "internal_ops",
}


def to_task5_correlation_result(anomaly_id: str, task4_drivers: list[dict], t5_CorrelationResult, t5_DriverSignal):
    signals = [
        t5_DriverSignal(
            name=f"{d['driver']} (r={d['correlation']:+.2f}, {d['lag_days']}d lag"
                 f"{', Granger precedence' if d['precedence'] else ''})",
            category=_DRIVER_CATEGORY.get(d["driver"], "internal_ops"),
            correlation_strength=round(float(d["shap_contribution"]), 4),
            entity=None,
        )
        for d in task4_drivers
    ]
    return t5_CorrelationResult(anomaly_id=anomaly_id, top_drivers=signals)


def _human_driver_phrase(driver_name: str, lag_days: int) -> str:
    """Short, headline-safe phrasing -- Task 6's own docstring example for
    StructuredDriver.label is '10% price increase on Product A (Jul 4)', not
    a technical stats readout. The full correlation/lag/precedence detail
    still goes to Task 4's raw output and stays inspectable there; `label`
    here is specifically the field Task 6 templates directly into headlines
    and explanations, so it needs to read like a sentence fragment."""
    phrase = driver_name.replace("_", " ")
    return f"a shift in {phrase}" + (f" about {lag_days}d earlier" if lag_days else "")


def to_task6_correlation_result(anomaly_id: str, task4_drivers: list[dict], t6_CorrelationResult, t6_StructuredDriver):
    drivers = [
        t6_StructuredDriver(
            driver_id=d["driver"],
            label=_human_driver_phrase(d["driver"], d["lag_days"]),
            stat_type="shap",
            value=round(float(d["shap_contribution"]), 4),
            rank=i + 1,
        )
        for i, d in enumerate(task4_drivers)
    ]
    return t6_CorrelationResult(anomaly_id=anomaly_id, drivers=drivers)


# ---------------------------------------------------------------------------
# Task 5's RetrievalOutput -> Task 6's RetrievedEvidence(sources=[...]).
# Task 5's own RetrievedEvidenceItem drops `title` after retrieval (matches
# the brief's RetrievedEvidence shape exactly, which has no title field) --
# recovered here from the doc_id -> DocumentRecord map built when we called
# Task 5, so Task 6 gets a real title instead of a second synthetic one.
# ---------------------------------------------------------------------------

def to_task6_retrieved_evidence(anomaly_id: str, evidence_items, doc_lookup: dict,
                                 t6_RetrievedEvidence, t6_EvidenceSource):
    sources = [
        t6_EvidenceSource(
            source_id=item.doc_id,
            title=doc_lookup[item.doc_id].title if item.doc_id in doc_lookup else item.snippet_ref[:60],
            snippet=item.snippet_ref,
            publisher=item.source,
            date=item.date,
            relevance_score=item.relevance_score,
            rank=i + 1,
            url=None,
        )
        for i, item in enumerate(evidence_items)
    ]
    return t6_RetrievedEvidence(anomaly_id=anomaly_id, sources=sources)
