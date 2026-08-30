"""
Task 5 -- shared data contracts.

AnomalyEvent and DocumentRecord mirror the brief's Task 3 / Task 1
outputs. CorrelationResult (Task 4's output) isn't specced anywhere
Task 5 can see, so the shape below is a documented assumption -- only
query_builder.py depends on its exact fields, so reconciling it with
the real Task 4 output later is a one-file change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Literal, Optional


# --------------------------------------------------------------------------
# Upstream inputs (produced by other tasks)
# --------------------------------------------------------------------------

@dataclass
class AnomalyEvent:
    """Task 3 output (anomaly gate)."""
    anomaly_id: str
    metric: str                   # e.g. "weekly_revenue"
    region: str                   # e.g. "EU-West"
    window_start: date
    window_end: date
    magnitude_pct: float          # signed, e.g. -18.4
    direction: Literal["up", "down"]


@dataclass
class DriverSignal:
    """One correlated driver surfaced by Task 4."""
    name: str                     # human-readable, e.g. "Northwind Retail price cut"
    category: str                 # "competitor" | "pricing" | "market" | "internal_ops" | ...
    correlation_strength: float   # 0..1
    entity: Optional[str] = None  # named entity this driver ties to, e.g. "Northwind Retail"


@dataclass
class CorrelationResult:
    """
    Task 4 output (correlate drivers). ASSUMED SHAPE -- see module
    docstring. Only `top_drivers` is consumed downstream.
    """
    anomaly_id: str
    top_drivers: List[DriverSignal] = field(default_factory=list)

    def competitor_entities(self) -> List[str]:
        """Named entities Task 4 itself flagged as competitor-category drivers."""
        return sorted({
            d.entity for d in self.top_drivers
            if d.category == "competitor" and d.entity
        })


# --------------------------------------------------------------------------
# DocumentStore (Task 1 output) -- what the vector index is built from
# --------------------------------------------------------------------------

@dataclass
class DocumentRecord:
    doc_id: str
    date: date
    source: str                               # outlet name, or "support" for tickets
    title: str
    text: str
    region_tags: List[str] = field(default_factory=list)
    entity_tags: List[str] = field(default_factory=list)   # includes competitor names when relevant


# --------------------------------------------------------------------------
# Task 5 output
# --------------------------------------------------------------------------

@dataclass
class RetrievedEvidenceItem:
    doc_id: str
    date: str
    source: str
    relevance_score: float
    tag: str                      # "competitor" | "internal" | "market"
    snippet_ref: str

    def to_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "date": self.date,
            "source": self.source,
            "relevance_score": round(self.relevance_score, 2),
            "tag": self.tag,
            "snippet_ref": self.snippet_ref,
        }


@dataclass
class RetrievalOutput:
    evidence: List[RetrievedEvidenceItem]
    competitor_activity_detected: bool
    competitor_documents: List[RetrievedEvidenceItem]

    def to_dict(self) -> dict:
        return {
            "evidence": [e.to_dict() for e in self.evidence],
            "competitor_activity_detected": self.competitor_activity_detected,
            "competitor_documents": [e.to_dict() for e in self.competitor_documents],
        }
