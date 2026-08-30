"""
End-to-end demo using the Task-1-shaped sample DocumentStore and a mock
Task-4 CorrelationResult, so this module is independently runnable
before Tasks 1 and 4 exist ("day-one start" per the brief).

Run:  python demo.py
"""
import json
from datetime import date

from schemas import AnomalyEvent, CorrelationResult, DriverSignal
from sample_data import ALL_DOCUMENTS, KNOWN_COMPETITORS
from vector_index import VectorIndex
from bm25_search import BM25Index
from query_builder import build_query
from pipeline import retrieve_evidence


def main():
    anomaly = AnomalyEvent(
        anomaly_id="anom_2026_07_eu_west_rev",
        metric="weekly_revenue",
        region="EU-West",
        window_start=date(2026, 7, 10),
        window_end=date(2026, 7, 17),
        magnitude_pct=-18.4,
        direction="down",
    )

    # Mock Task 4 output
    correlation = CorrelationResult(
        anomaly_id=anomaly.anomaly_id,
        top_drivers=[
            DriverSignal(
                name="Northwind Retail price cut",
                category="competitor",
                correlation_strength=0.82,
                entity="Northwind Retail",
            ),
            DriverSignal(
                name="EU-West logistics disruption",
                category="market",
                correlation_strength=0.41,
            ),
        ],
    )

    vector_index = VectorIndex(ALL_DOCUMENTS)
    bm25_index = BM25Index(ALL_DOCUMENTS)

    result = retrieve_evidence(
        anomaly,
        correlation,
        vector_index,
        bm25_index,
        known_competitors=KNOWN_COMPETITORS,
    )

    print(
        "anomaly:      ",
        f"{anomaly.region} {anomaly.metric} {anomaly.direction} {anomaly.magnitude_pct}% "
        f"({anomaly.window_start} to {anomaly.window_end})",
    )
    print("query:        ", build_query(anomaly, correlation))
    print()
    print("=== evidence (RetrievedEvidence) ===")
    print(json.dumps([e.to_dict() for e in result.evidence], indent=2))
    print()
    print("competitor_activity_detected:", result.competitor_activity_detected)
    print()
    print("=== competitor_documents ===")
    print(json.dumps([e.to_dict() for e in result.competitor_documents], indent=2))


if __name__ == "__main__":
    main()
