"""
Task 5 orchestration.

retrieve_evidence() is the single entry point Task 7 (orchestrate &
deliver) calls once Task 3's AnomalyEvent fires. It wires together:

  1. query_builder  -> build the retrieval query text
  2. vector_index    -> semantic search, metadata-filtered
  3. bm25_search      -> exact-entity keyword search, metadata-filtered
  4. rerank           -> merge + recency/relevance weighted rerank      -> `evidence`
  5. competitor tag   -> surface entity-tag matches directly            -> `competitor_documents`
"""
from __future__ import annotations

from datetime import timedelta
from typing import List, Set

from schemas import (
    AnomalyEvent,
    CorrelationResult,
    DocumentRecord,
    RetrievedEvidenceItem,
    RetrievalOutput,
)
from vector_index import VectorIndex
from bm25_search import BM25Index
from query_builder import build_query, competitor_entity_terms
from rerank import merge_and_rerank

DATE_WINDOW_PAD_DAYS = 30       # anomaly window +/- 30 days, per process step 2
CANDIDATE_POOL_TOP_K = 500      # effectively "no cap" -- score the whole filtered pool
FINAL_TOP_K = 8                 # size of the reranked `evidence` list returned to Task 7
SNIPPET_CHARS = 160


def _snippet(text: str, n: int = SNIPPET_CHARS) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= n else flat[: n - 1].rstrip() + "\u2026"


def _tag_for(doc: DocumentRecord, competitor_names: Set[str]) -> str:
    """
    competitor > internal > market. A support ticket that names a known
    competitor is tagged "competitor" (not "internal") since that's the
    more useful signal for the inter-company question in step 5.
    """
    if competitor_names.intersection(doc.entity_tags):
        return "competitor"
    if doc.source == "support":
        return "internal"
    return "market"


def _to_evidence_item(doc: DocumentRecord, score: float, competitor_names: Set[str]) -> RetrievedEvidenceItem:
    return RetrievedEvidenceItem(
        doc_id=doc.doc_id,
        date=doc.date.isoformat(),
        source=doc.source,
        relevance_score=max(0.0, min(1.0, score)),
        tag=_tag_for(doc, competitor_names),
        snippet_ref=_snippet(doc.text),
    )


def retrieve_evidence(
    anomaly: AnomalyEvent,
    correlation: CorrelationResult,
    vector_index: VectorIndex,
    bm25_index: BM25Index,
    *,
    known_competitors: List[str],
    top_k: int = FINAL_TOP_K,
) -> RetrievalOutput:
    date_window = (
        anomaly.window_start - timedelta(days=DATE_WINDOW_PAD_DAYS),
        anomaly.window_end + timedelta(days=DATE_WINDOW_PAD_DAYS),
    )
    region_tags = [anomaly.region]
    competitor_set = set(known_competitors)

    # 1. query
    query = build_query(anomaly, correlation)

    # 2. semantic search over the full in-window/in-region candidate pool
    #    (rerank, not this call, decides the final cut)
    semantic_hits = vector_index.search(
        query, date_window=date_window, region_tags=region_tags, top_k=CANDIDATE_POOL_TOP_K
    )

    # 3. BM25 keyword search for named entities -- prefer the specific
    #    entity(ies) Task 4 correlated; fall back to the full known-
    #    competitor registry (e.g. on a day-one run before Task 4 exists)
    entity_terms = competitor_entity_terms(correlation) or known_competitors
    bm25_hits = bm25_index.search(
        entity_terms, date_window=date_window, region_tags=region_tags, top_k=CANDIDATE_POOL_TOP_K
    )

    # 4. merge + rerank -> this becomes the `evidence` output
    ranked = merge_and_rerank(semantic_hits, bm25_hits, anchor_date=anomaly.window_end, top_k=top_k)
    evidence = [_to_evidence_item(rc.doc, rc.combined_score, competitor_set) for rc in ranked]

    # 5. separately surface every competitor-tagged doc in the candidate
    #    pool, using its semantic relevance score, regardless of whether
    #    the rerank cutoff kept it in `evidence` -- a competitor mention
    #    should never silently disappear just because it didn't crack
    #    the top-K.
    semantic_score_by_id = {sh.doc.doc_id: sh.score for sh in semantic_hits}
    competitor_documents = [
        _to_evidence_item(sh.doc, semantic_score_by_id.get(sh.doc.doc_id, 0.0), competitor_set)
        for sh in semantic_hits
        if competitor_set.intersection(sh.doc.entity_tags)
    ]
    competitor_documents.sort(key=lambda item: item.relevance_score, reverse=True)

    return RetrievalOutput(
        evidence=evidence,
        competitor_activity_detected=len(competitor_documents) > 0,
        competitor_documents=competitor_documents,
    )
