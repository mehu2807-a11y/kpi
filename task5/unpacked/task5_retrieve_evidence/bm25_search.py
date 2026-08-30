"""
Keyword / exact-entity-match search.

Embeddings under-rank exact proper-noun matches -- a competitor's name
is a small change buried inside a big vector. BM25 catches those by
rewarding exact term overlap, so it runs as a second, parallel
retrieval path (Task 5 process step 3) and its hits get merged with
the semantic results before reranking.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

from rank_bm25 import BM25Okapi

from schemas import DocumentRecord


def _tokenize(text: str) -> List[str]:
    return text.lower().replace("-", " ").split()


@dataclass
class ScoredDoc:
    doc: DocumentRecord
    score: float


class BM25Index:
    def __init__(self, documents: List[DocumentRecord]):
        self.documents = documents
        self._id_to_pos = {d.doc_id: i for i, d in enumerate(documents)}
        corpus = [
            _tokenize(f"{d.title} {d.text} {' '.join(d.entity_tags)}")
            for d in documents
        ]
        self._bm25 = BM25Okapi(corpus) if corpus else None

    def search(
        self,
        query_terms: List[str],
        *,
        date_window: Optional[Tuple[date, date]] = None,
        region_tags: Optional[List[str]] = None,
        top_k: int = 10,
    ) -> List[ScoredDoc]:
        """Keyword search for named entities, per Task 5 process step 3."""
        if not self._bm25 or not query_terms:
            return []

        candidates = self._filter_by_metadata(date_window, region_tags)
        if not candidates:
            return []

        scores = self._bm25.get_scores(_tokenize(" ".join(query_terms)))
        scored = [
            ScoredDoc(doc=d, score=float(scores[self._id_to_pos[d.doc_id]]))
            for d in candidates
        ]
        scored = [sd for sd in scored if sd.score > 0]
        scored.sort(key=lambda sd: sd.score, reverse=True)
        return scored[:top_k]

    def _filter_by_metadata(self, date_window, region_tags) -> List[DocumentRecord]:
        out = self.documents
        if date_window:
            start, end = date_window
            out = [d for d in out if start <= d.date <= end]
        if region_tags:
            wanted = set(region_tags)
            out = [d for d in out if wanted.intersection(d.region_tags)]
        return out
