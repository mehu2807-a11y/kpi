"""
Task 6 -- Synthesize, score confidence, handle ambiguity
Shared data contracts.

These mirror the AnomalyEvent / CorrelationResult / RetrievedEvidence /
StoryOutput types described in the Task 6 brief. Tasks 4 and 5 hadn't shipped
real schemas yet at the time this was written, so these are the "hand-crafted
mock versions" the brief calls for -- reconcile exact field names with the
real Task 4 / Task 5 output schemas once those land. Only the *shape* matters
to the rest of this module: ranked structured drivers with a numeric
strength + stable id, and ranked evidence sources with a stable id.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Literal
import json


@dataclass
class AnomalyEvent:
    """The what / where / how-much, handed off from the detect phase."""
    anomaly_id: str
    metric_name: str             # e.g. "revenue"
    entity: str                   # e.g. "Region X" -- the "where"
    direction: Literal["increase", "decrease"]
    magnitude_pct: float          # unsigned magnitude of the move, e.g. 7.5
    baseline_value: float
    observed_value: float
    window_start: str             # ISO date
    window_end: str               # ISO date
    detected_at: str              # ISO datetime


@dataclass
class StructuredDriver:
    """One ranked, structured driver from Task 4's correlation engine."""
    driver_id: str                  # stable id, e.g. "avg_price" -- referenced in citations
    label: str                       # human-readable, e.g. "10% price increase on Product A (Jul 4)"
    stat_type: Literal["correlation", "shap"]
    value: float                      # correlation coefficient or SHAP value. Sign is informational
                                       # only -- scoring.py uses magnitude, never sign, for confidence.
    rank: int


@dataclass
class CorrelationResult:
    """Task 4's output for one anomaly."""
    anomaly_id: str
    drivers: List[StructuredDriver]     # sorted by rank ascending; drivers[0] is strongest


@dataclass
class EvidenceSource:
    """One ranked, retrieved source from Task 5's RAG pipeline."""
    source_id: str            # stable id, e.g. "news_00231" -- referenced in citations
    title: str
    snippet: str
    publisher: str              # used to count *independent* sources, not just citation count
    date: str                    # ISO date
    relevance_score: float
    rank: int
    url: Optional[str] = None


@dataclass
class RetrievedEvidence:
    """Task 5's output for one anomaly."""
    anomaly_id: str
    sources: List[EvidenceSource]       # sorted by rank ascending; sources[0] is most relevant


@dataclass
class Hypothesis:
    cause: str
    confidence: float                   # computed in scoring.py -- never the LLM's self-rating
    citations: List[str]                # validated driver_id / source_id references
    actions: List[str] = field(default_factory=list)


@dataclass
class StoryOutput:
    headline: str
    explanation: str
    hypotheses: List[Hypothesis]
    recommended_actions: List[str]
    overall_confidence: float
    escalate_flag: bool

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(asdict(self), indent=indent)
