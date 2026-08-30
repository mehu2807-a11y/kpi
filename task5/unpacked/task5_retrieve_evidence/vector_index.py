"""
Vector index abstraction.

Task 1 will build a real embedding-based vector index (OpenAI / Cohere /
a local sentence-transformer) over the DocumentStore. This sandbox has
no network path to a model hub, so VectorIndex embeds with TF-IDF +
cosine similarity here as a stand-in dense retriever.

What matters is the *interface*: `.search(query, date_window,
region_tags, top_k)` returning ScoredDoc objects. Swap `__init__` and
`search`'s scoring internals for a real embedding model / ANN index
(FAISS, pgvector, etc.) later; nothing downstream in this module
changes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from schemas import DocumentRecord


@dataclass
class ScoredDoc:
    doc: DocumentRecord
    score: float


class VectorIndex:
    def __init__(self, documents: List[DocumentRecord]):
        self.documents = documents
        self._id_to_pos = {d.doc_id: i for i, d in enumerate(documents)}
        if documents:
            self._vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
            corpus = [f"{d.title}. {d.text}" for d in documents]
            self._matrix = self._vectorizer.fit_transform(corpus)
        else:
            self._vectorizer = None
            self._matrix = None

    def search(
        self,
        query: str,
        *,
        date_window: Optional[Tuple[date, date]] = None,
        region_tags: Optional[List[str]] = None,
        top_k: int = 10,
    ) -> List[ScoredDoc]:
        """Semantic search filtered by metadata, per Task 5 process step 2."""
        if not self.documents:
            return []

        candidates = self._filter_by_metadata(date_window, region_tags)
        if not candidates:
            return []

        idxs = [self._id_to_pos[d.doc_id] for d in candidates]
        q_vec = self._vectorizer.transform([query])
        sims = cosine_similarity(q_vec, self._matrix[idxs])[0]

        scored = [ScoredDoc(doc=d, score=float(s)) for d, s in zip(candidates, sims)]
        scored.sort(key=lambda sd: sd.score, reverse=True)
        return scored[:top_k]

    def all_in_window(
        self,
        date_window: Optional[Tuple[date, date]] = None,
        region_tags: Optional[List[str]] = None,
    ) -> List[DocumentRecord]:
        """Expose the metadata-filtered candidate pool directly (used for introspection/tests)."""
        return self._filter_by_metadata(date_window, region_tags)

    def _filter_by_metadata(self, date_window, region_tags) -> List[DocumentRecord]:
        out = self.documents
        if date_window:
            start, end = date_window
            out = [d for d in out if start <= d.date <= end]
        if region_tags:
            wanted = set(region_tags)
            out = [d for d in out if wanted.intersection(d.region_tags)]
        return out
