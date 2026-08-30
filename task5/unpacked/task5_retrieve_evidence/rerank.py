"""
Task 5 process step 4: merge the semantic and BM25 candidate sets, then
rerank. The brief allows either a cross-encoder rerank or a simple
recency + relevance weighted score -- this implements the latter (no
network path to a cross-encoder model in this sandbox) behind a small
interface so a real cross-encoder is a one-file swap later.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Protocol

from schemas import DocumentRecord

SEMANTIC_WEIGHT = 0.55
BM25_WEIGHT = 0.30
RECENCY_WEIGHT = 0.15
RECENCY_HALF_LIFE_DAYS = 14


@dataclass
class RankedCandidate:
    doc: DocumentRecord
    combined_score: float


def _normalize(scores: Dict[str, float]) -> Dict[str, float]:
    if not scores:
        return {}
    lo, hi = min(scores.values()), max(scores.values())
    if hi - lo < 1e-9:
        return {k: (1.0 if hi > 0 else 0.0) for k in scores}
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}


def _recency_score(doc_date: date, anchor_date: date) -> float:
    age_days = abs((anchor_date - doc_date).days)
    return 0.5 ** (age_days / RECENCY_HALF_LIFE_DAYS)


class Reranker(Protocol):
    def rerank(self, semantic_hits, bm25_hits, *, anchor_date: date, top_k: int) -> List[RankedCandidate]:
        ...


def merge_and_rerank(
    semantic_hits,
    bm25_hits,
    *,
    anchor_date: date,
    top_k: int = 10,
) -> List[RankedCandidate]:
    """Default reranker: recency + relevance weighted score."""
    sem_by_id: Dict[str, float] = {sd.doc.doc_id: sd.score for sd in semantic_hits}
    bm25_by_id: Dict[str, float] = {sd.doc.doc_id: sd.score for sd in bm25_hits}
    docs_by_id: Dict[str, DocumentRecord] = {
        sd.doc.doc_id: sd.doc for sd in [*semantic_hits, *bm25_hits]
    }

    sem_norm = _normalize(sem_by_id)
    bm25_norm = _normalize(bm25_by_id)

    ranked: List[RankedCandidate] = []
    for doc_id, doc in docs_by_id.items():
        recency = _recency_score(doc.date, anchor_date)
        combined = (
            SEMANTIC_WEIGHT * sem_norm.get(doc_id, 0.0)
            + BM25_WEIGHT * bm25_norm.get(doc_id, 0.0)
            + RECENCY_WEIGHT * recency
        )
        ranked.append(RankedCandidate(doc=doc, combined_score=combined))

    ranked.sort(key=lambda rc: rc.combined_score, reverse=True)
    return ranked[:top_k]


class CrossEncoderReranker:
    """
    Production upgrade slot: score each (query, doc) pair with a
    cross-encoder (e.g. ms-marco-MiniLM) for higher precision than the
    bi-encoder + BM25 fusion above. Not implemented -- this sandbox has
    no network path to a model hub -- but pipeline.py only depends on
    the Reranker interface, so dropping in a real implementation later
    doesn't touch anything else.
    """

    def rerank(self, semantic_hits, bm25_hits, *, anchor_date: date, top_k: int) -> List[RankedCandidate]:
        raise NotImplementedError("Swap in a real cross-encoder model here.")
