"""
orchestrate.py -- Task 7 (Orchestrate & deliver), the piece none of the other
six deliverables were assigned to build. Wires Tasks 1/2 (already-produced
data) -> Task 3 (real gate) -> [STOP if noise] -> Task 4 + Task 5 -> Task 6,
using adapters.py to reconcile the schema differences between modules.

The one rule this file exists to enforce: if Task 3 returns verdict ==
"noise", NOTHING below it runs. No Task 4 call, no Task 5 call, no Task 6 /
LLM call. That's not a performance nicety -- it's the product's core design
principle, and it's asserted on, not just hoped for (see run_end_to_end's
docstring and the test suite's noise-path checks).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict
import time

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from data_quality_gate import check_series as dq_check_series, DataQualityConfig
from cohort_drilldown import decompose as cohort_decompose
from cross_kpi_correlation import detect_cascade
from early_warning import scan_all_regions as ew_scan, EarlyWarningConfig
from peer_benchmarking import benchmark as peer_benchmark
from causal_graph import rank_drivers_by_causal_proximity

sys.path.insert(0, str(PROJECT_ROOT / "orchestrator"))
from scoped_import import scoped_task_dir
import adapters

TASK3_DIR = str(PROJECT_ROOT / "task3")
TASK4_DIR = str(PROJECT_ROOT / "task4")
TASK5_DIR = str(PROJECT_ROOT / "task5" / "unpacked" / "task5_retrieve_evidence")
TASK6_DIR = str(PROJECT_ROOT / "task6")

# ---------------------------------------------------------------------------
# Load every task module ONCE, at import time, using the scoped importer.
# Heavy third-party deps (numpy/pandas/sklearn/scipy) must already be
# imported in the outer process before this runs -- see run_all.py's header
# -- because numpy's C extension cannot be reloaded once sys.modules purges
# it (see scoped_import.py's docstring / the bug this caught).
# ---------------------------------------------------------------------------

with scoped_task_dir(TASK3_DIR):
    import anomaly_gate as _t3
T3 = _t3

with scoped_task_dir(TASK4_DIR):
    import correlate_drivers as _t4
T4 = _t4

with scoped_task_dir(TASK5_DIR):
    import schemas as _t5_schemas
    import pipeline as _t5_pipeline
    from vector_index import VectorIndex as T5_VectorIndex
    from bm25_search import BM25Index as T5_BM25Index
T5_SCHEMAS = _t5_schemas
T5_retrieve_evidence = _t5_pipeline.retrieve_evidence

with scoped_task_dir(TASK6_DIR):
    import schemas as _t6_schemas
    import synthesize as _t6_synth
    import llm_client as _t6_llm
T6_SCHEMAS = _t6_schemas
T6_synthesize = _t6_synth.synthesize
T6_synthesize_enhanced = _t6_synth.synthesize_enhanced
T6_MockLLMClient = _t6_llm.MockLLMClient


@dataclass
class PipelineResult:
    gate_record: dict                              # Task 3's raw output, always present
    verdict: str                                    # "noise" or "anomaly"
    stopped_at_gate: bool
    canonical_anomaly: Optional[adapters.CanonicalAnomaly] = None
    task4_drivers: Optional[list] = None
    task4_precedent: Optional[dict] = None
    task5_output: Optional[object] = None           # RetrievalOutput
    task6_story: Optional[object] = None            # StoryOutput (original, for test compatibility)
    # Enhanced fields (new features)
    enhanced_actions: Optional[List[object]] = None  # List of StructuredAction
    persona_narratives: Optional[Dict] = None        # Dict of persona-specific narratives
    relevant_kpis: Optional[List[object]] = None     # List of relevant KPI definitions
    telemetry: Optional[Dict] = None                 # Telemetry data
    error_stage: Optional[str] = None
    error_message: Optional[str] = None
    data_quality_report: Optional[object] = None     # DataQualityReport
    cohort_drilldown: Optional[object] = None        # CohortDrilldown
    cross_kpi_cascade: Optional[object] = None       # CrossKPICascade
    peer_benchmark: Optional[object] = None          # PeerBenchmark
    causal_rankings: Optional[list] = None           # list[CausalRanking]


def run_downstream_from_record(
    record: dict,                       # Task 3's real output dict, verdict MUST be "anomaly"
    metrics_table: pd.DataFrame,        # Task 1's real long-format MetricsTable
    document_store_rows: list[dict],    # Task 1's real DocumentStore rows
    known_competitors: list[str],
    historical_log: list,
    llm_style: str = "single_dominant",
    top_k_evidence: int = 8,
    use_enhanced: bool = True,          # Flag to use enhanced features
) -> PipelineResult:
    """
    The Task 4 -> Task 5 -> Task 6 chain, factored out so a cheap day-by-day
    gate walk (tests/gate_walk.py) can call this ONLY on the specific days
    it flagged, instead of re-running the gate itself. run_end_to_end()
    below (gate + chain together, for a single check) calls this too, so
    there's exactly one implementation of the downstream wiring.
    """
    start_time = time.time()
    result = PipelineResult(gate_record=record, verdict="anomaly", stopped_at_gate=False)
    try:
        canonical = adapters.canonicalize_task3_record(record)
        result.canonical_anomaly = canonical

        # ---- Task 4 ----
        with scoped_task_dir(TASK4_DIR):
            pass  # module already loaded at import time; nothing to re-scope
        t4_anomaly = adapters.to_task4_anomaly_event(canonical, T4)
        region_wide = adapters.metrics_table_to_region_wide(metrics_table, canonical.region)
        # correlate_drivers() needs `date` + the metric column + candidate features
        if canonical.metric not in region_wide.columns:
            raise KeyError(
                f"metric {canonical.metric!r} not present in region-wide table for "
                f"{canonical.region!r} (columns: {list(region_wide.columns)})"
            )
        task4_drivers, task4_precedent = T4.correlate_drivers(t4_anomaly, region_wide, historical_log)
        result.task4_drivers = task4_drivers
        result.task4_precedent = task4_precedent

        # --- Causal Graph Re-ranking ---
        try:
            result.causal_rankings = rank_drivers_by_causal_proximity(
                task4_drivers, canonical.metric
            )
        except Exception:
            pass

        try:
            result.cohort_drilldown = cohort_decompose(record, metrics_table, dimension='product')
        except Exception:
            pass

        try:
            all_kpi_ids = [canonical.metric, 'revenue', 'units_sold', 'avg_price', 'marketing_spend', 'inventory_level']
            result.cross_kpi_cascade = detect_cascade(record, metrics_table, all_kpi_ids)
        except Exception:
            pass

        try:
            result.peer_benchmark = peer_benchmark(record, metrics_table)
        except Exception:
            pass

        # ---- Task 5 ----
        t5_anomaly = adapters.to_task5_anomaly_event(canonical, T5_SCHEMAS.AnomalyEvent)
        t5_correlation = adapters.to_task5_correlation_result(
            canonical.event_id, task4_drivers, T5_SCHEMAS.CorrelationResult, T5_SCHEMAS.DriverSignal
        )
        doc_records = adapters.to_task5_document_records(document_store_rows, T5_SCHEMAS.DocumentRecord)
        doc_lookup = {d.doc_id: d for d in doc_records}
        vector_index = T5_VectorIndex(doc_records)
        bm25_index = T5_BM25Index(doc_records)
        task5_output = T5_retrieve_evidence(
            t5_anomaly, t5_correlation, vector_index, bm25_index,
            known_competitors=known_competitors, top_k=top_k_evidence,
        )
        result.task5_output = task5_output

        # ---- Task 6 ----
        t6_anomaly = adapters.to_task6_anomaly_event(canonical, T6_SCHEMAS.AnomalyEvent)
        t6_correlation = adapters.to_task6_correlation_result(
            canonical.event_id, task4_drivers, T6_SCHEMAS.CorrelationResult, T6_SCHEMAS.StructuredDriver
        )
        t6_evidence = adapters.to_task6_retrieved_evidence(
            canonical.event_id, task5_output.evidence, doc_lookup,
            T6_SCHEMAS.RetrievedEvidence, T6_SCHEMAS.EvidenceSource,
        )

        import mock_llm
        canned = mock_llm.build_canned_response(llm_style, t6_correlation, t6_evidence)
        llm_client = T6_MockLLMClient(canned)

        if use_enhanced:
            # synthesize_enhanced() calls synthesize() internally and returns
            # the original story alongside the enhanced fields -- call it
            # once, not synthesize() again separately (that used to happen
            # here and silently doubled every LLM call).
            enhanced_result = T6_synthesize_enhanced(t6_anomaly, t6_correlation, t6_evidence, llm_client)
            result.task6_story = enhanced_result["original_story"]
            result.enhanced_actions = enhanced_result["structured_actions"]
            result.persona_narratives = enhanced_result["persona_narratives"]
            result.relevant_kpis = enhanced_result["relevant_kpis"]
            result.telemetry = enhanced_result["telemetry"]
            result.telemetry["latency_ms"] = (time.time() - start_time) * 1000
        else:
            result.task6_story = T6_synthesize(t6_anomaly, t6_correlation, t6_evidence, llm_client)

    except Exception as exc:  # noqa: BLE001 -- test harness needs to see every stage's failures
        import traceback
        result.error_stage = result.error_stage or _infer_stage(result)
        result.error_message = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"

    return result


def _infer_stage(result: PipelineResult) -> str:
    if result.task5_output is not None:
        return "task6"
    if result.task4_drivers is not None:
        return "task5"
    return "task4"


def run_end_to_end(
    check, correlated_checks: list, history, gate_config, event_counter,
    metrics_table: pd.DataFrame, document_store_rows: list[dict],
    known_competitors: list[str], historical_log: list,
    llm_style: str = "single_dominant", top_k_evidence: int = 8,
    use_enhanced: bool = True,
) -> PipelineResult:
    """
    Runs one (metric, region, date) check through the real Task 3 gate.
    If verdict == "noise": returns immediately -- Task 4/5/6 are never
    called, full stop, checked with an explicit early `return` rather than
    a flag something downstream could ignore.
    If verdict == "anomaly": delegates to run_downstream_from_record() for
    the Task 4 -> 5 -> 6 chain.
    """
    # --- Data Quality Gate (runs before Task 3) ---
    try:
        dates_list = list(metrics_table[
            (metrics_table['region'] == check.region) &
            (metrics_table.get('metric_name', metrics_table.columns[0]) == check.metric)
        ].sort_values('date')['date'].astype(str))
        values_list = list(metrics_table[
            (metrics_table['region'] == check.region) &
            (metrics_table.get('metric_name', metrics_table.columns[0]) == check.metric)
        ].sort_values('date')['value'].astype(float))
        dq_report = dq_check_series(dates_list, values_list, check.metric, check.region)
        if dq_report.skipped_gate:
            result = PipelineResult(gate_record={'metric': check.metric, 'region': check.region, 'date': check.date, 'verdict': 'data_quality_fail'}, verdict='data_quality_fail', stopped_at_gate=True)
            result.data_quality_report = dq_report
            return result
    except Exception:
        pass  # data quality gate is best-effort; never block the pipeline on its own failure

    record, internal = T3.run_gate(check, correlated_checks, history, gate_config, event_counter)
    history.push(internal)   # persistence state MUST advance regardless of verdict

    if record["verdict"] == "noise":
        return PipelineResult(gate_record=record, verdict="noise", stopped_at_gate=True)

    return run_downstream_from_record(
        record, metrics_table, document_store_rows, known_competitors,
        historical_log, llm_style=llm_style, top_k_evidence=top_k_evidence,
        use_enhanced=use_enhanced
    )