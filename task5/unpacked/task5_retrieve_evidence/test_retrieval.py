"""
Precision/recall sanity checks against the hand-labelled sample set --
this is the "validate retrieval precision early" step the brief calls
for, using the day-one sample DocumentStore before Task 1 / Task 4
exist.

Run:  python test_retrieval.py
   or python -m pytest test_retrieval.py -v
"""
from datetime import date

from schemas import AnomalyEvent, CorrelationResult, DriverSignal
from sample_data import ALL_DOCUMENTS, KNOWN_COMPETITORS
from vector_index import VectorIndex
from bm25_search import BM25Index
from pipeline import retrieve_evidence

# Hand-labelled ground truth for the mock anomaly below. Kept separate
# from DocumentRecord / DocumentStore on purpose -- this is evaluation
# data, not something the retrieval system itself should ever see.
RELEVANT_DOC_IDS = {
    "news_1001", "news_1002", "news_1003", "news_1004",
    "news_1005", "news_1006", "news_1007",
    "ticket_2001", "ticket_2002", "ticket_2003",
}
COMPETITOR_DOC_IDS = {
    "news_1001", "news_1002", "news_1003", "news_1004", "ticket_2001", "ticket_2003",
}
# Wrong date window and/or wrong region -- must never appear in output,
# even though some of them mention a known competitor by name.
OUT_OF_SCOPE_DOC_IDS = {
    "news_1008", "news_1009", "news_1010", "news_1011", "ticket_2004", "ticket_2005",
}


def _run_pipeline():
    anomaly = AnomalyEvent(
        anomaly_id="anom_2026_07_eu_west_rev",
        metric="weekly_revenue",
        region="EU-West",
        window_start=date(2026, 7, 10),
        window_end=date(2026, 7, 17),
        magnitude_pct=-18.4,
        direction="down",
    )
    correlation = CorrelationResult(
        anomaly_id=anomaly.anomaly_id,
        top_drivers=[
            DriverSignal("Northwind Retail price cut", "competitor", 0.82, entity="Northwind Retail"),
            DriverSignal("EU-West logistics disruption", "market", 0.41),
        ],
    )
    vector_index = VectorIndex(ALL_DOCUMENTS)
    bm25_index = BM25Index(ALL_DOCUMENTS)
    return retrieve_evidence(
        anomaly, correlation, vector_index, bm25_index, known_competitors=KNOWN_COMPETITORS
    )


def test_competitor_activity_flagged():
    result = _run_pipeline()
    assert result.competitor_activity_detected is True


def test_all_known_competitor_docs_surfaced():
    result = _run_pipeline()
    surfaced = {d.doc_id for d in result.competitor_documents}
    assert COMPETITOR_DOC_IDS.issubset(surfaced), surfaced


def test_out_of_scope_docs_never_leak_through():
    result = _run_pipeline()
    returned_ids = {e.doc_id for e in result.evidence} | {d.doc_id for d in result.competitor_documents}
    leaked = returned_ids.intersection(OUT_OF_SCOPE_DOC_IDS)
    assert not leaked, f"date/region filter failed, leaked: {leaked}"


def test_precision_at_k():
    result = _run_pipeline()
    returned_ids = [e.doc_id for e in result.evidence]
    assert returned_ids, "evidence should not be empty"
    hits = sum(1 for doc_id in returned_ids if doc_id in RELEVANT_DOC_IDS)
    precision = hits / len(returned_ids)
    assert precision >= 0.75, f"precision@{len(returned_ids)} = {precision:.2f}, evidence = {returned_ids}"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS  {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} checks passed")
