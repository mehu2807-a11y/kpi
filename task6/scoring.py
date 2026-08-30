"""
Confidence scoring + disagreement/escalation logic for Task 6.

The one hard rule from the brief: never take the model's self-rating. The
LLM (see llm_client.py) is never even asked for a confidence number -- this
module computes it from three signals, all derived mechanically from the
citations the LLM attached to each hypothesis, checked against the actual
CorrelationResult / RetrievedEvidence data:

  (a) structured strength  -- how strong is the strongest structured driver
      (correlation / SHAP magnitude) this hypothesis cites, relative to the
      strongest driver anywhere in this anomaly?
  (b) source support        -- how many *independent* (distinct-publisher)
      retrieved sources corroborate this hypothesis, with diminishing
      returns per additional source?
  (c) cross-modal agreement -- is this hypothesis backed by BOTH a
      structured driver and an independent source, or only one modality?

These combine into a single confidence in [0, 1] per hypothesis. Weights are
tunable constants below -- there's nothing sacred about 0.45 / 0.25 / 0.30,
they're a reasonable starting point to tune against real Task 4/5 output.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the task6 directory is in sys.path to import the correct schemas
TASK6_DIR = Path(__file__).parent
if str(TASK6_DIR) not in sys.path:
    sys.path.insert(0, str(TASK6_DIR))

from dataclasses import dataclass
from typing import Dict, List, Optional

from schemas import CorrelationResult, RetrievedEvidence, Hypothesis, StructuredDriver, EvidenceSource

# --- tunable weights (must sum to 1.0) -------------------------------------
STRUCTURED_WEIGHT = 0.45
SOURCE_WEIGHT = 0.25
AGREEMENT_WEIGHT = 0.30

# If the top two hypotheses' confidences are closer than this, treat the
# result as ambiguous and escalate.
DISAGREEMENT_MARGIN = 0.15


@dataclass
class ResolvedCitations:
    driver_ids: List[str]
    source_ids: List[str]
    unresolved: List[str]   # citations that matched nothing in the input -- dropped, not trusted


def resolve_citations(
    raw_citations: List[str],
    correlation: CorrelationResult,
    evidence: RetrievedEvidence,
) -> ResolvedCitations:
    """Match each citation the LLM produced back to a real driver_id or source_id.

    Guards against hallucinated citations: anything that doesn't resolve is
    reported as unresolved and excluded from scoring, rather than trusted at
    face value.
    """
    known_drivers = {d.driver_id for d in correlation.drivers}
    known_sources = {s.source_id for s in evidence.sources}

    driver_ids, source_ids, unresolved = [], [], []
    for raw in raw_citations:
        candidate = raw.split("CorrelationResult.", 1)[-1] if raw.startswith("CorrelationResult.") else raw
        if candidate in known_drivers:
            driver_ids.append(candidate)
        elif candidate in known_sources:
            source_ids.append(candidate)
        else:
            unresolved.append(raw)
    return ResolvedCitations(driver_ids=driver_ids, source_ids=source_ids, unresolved=unresolved)


def _structured_strength(driver_ids: List[str], correlation: CorrelationResult) -> float:
    """Cited driver strength, normalized against the strongest driver for this anomaly."""
    if not driver_ids:
        return 0.0
    by_id: Dict[str, StructuredDriver] = {d.driver_id: d for d in correlation.drivers}
    max_abs = max((abs(d.value) for d in correlation.drivers), default=0.0) or 1e-9
    cited = [abs(by_id[did].value) for did in driver_ids if did in by_id]
    if not cited:
        return 0.0
    return min(max(cited) / max_abs, 1.0)


def _source_support(source_ids: List[str], evidence: RetrievedEvidence) -> float:
    """Diminishing-returns score from the count of *independent* (distinct-publisher) sources.

    n=0 -> 0.0, n=1 -> 0.5, n=2 -> 0.67, n=3 -> 0.75, saturating toward 1.0.
    """
    if not source_ids:
        return 0.0
    by_id: Dict[str, EvidenceSource] = {s.source_id: s for s in evidence.sources}
    publishers = {by_id[sid].publisher for sid in source_ids if sid in by_id}
    n = len(publishers)
    return 1 - (1 / (1 + n)) if n else 0.0


def _cross_modal_agreement(driver_ids: List[str], source_ids: List[str]) -> float:
    """1.0 if both a structured driver and an independent source back this hypothesis,
    0.5 if exactly one modality does, 0.0 if neither does.

    The 0.0 case shouldn't reach a final StoryOutput -- synthesize.py drops any
    hypothesis with zero valid citations as a bare assertion before scoring is used
    for anything -- but score_hypothesis() is a standalone function callers may use
    directly (tests do), so it needs to be correct on its own, not just as called
    from the one place that happens to filter this case out first.
    """
    modality_count = bool(driver_ids) + bool(source_ids)
    return {0: 0.0, 1: 0.5, 2: 1.0}[modality_count]


def score_hypothesis(
    raw_citations: List[str],
    correlation: CorrelationResult,
    evidence: RetrievedEvidence,
):
    """Returns (confidence, ResolvedCitations) for one hypothesis's citation list."""
    resolved = resolve_citations(raw_citations, correlation, evidence)
    structured = _structured_strength(resolved.driver_ids, correlation)
    support = _source_support(resolved.source_ids, evidence)
    agreement = _cross_modal_agreement(resolved.driver_ids, resolved.source_ids)

    confidence = (
        STRUCTURED_WEIGHT * structured
        + SOURCE_WEIGHT * support
        + AGREEMENT_WEIGHT * agreement
    )
    return round(min(max(confidence, 0.0), 1.0), 2), resolved


def detect_disagreement(
    hypotheses: List[Hypothesis],
    correlation: CorrelationResult,
    evidence: RetrievedEvidence,
) -> bool:
    """True if either disagreement condition from the brief is met:

    1. The top two hypotheses (by confidence, so `hypotheses` must already be
       sorted descending) are within DISAGREEMENT_MARGIN of each other -- too
       close to call.
    2. The single strongest structured driver and the single most relevant
       retrieved source back *different* hypotheses -- structured and
       unstructured evidence disagree about which cause is primary, even if
       the confidence scores themselves aren't close.
    """
    if len(hypotheses) < 2:
        return False

    top, runner_up = hypotheses[0], hypotheses[1]
    if (top.confidence - runner_up.confidence) < DISAGREEMENT_MARGIN:
        return True

    top_driver = max(correlation.drivers, key=lambda d: abs(d.value), default=None)
    top_source = max(evidence.sources, key=lambda s: s.relevance_score, default=None)
    if top_driver is None or top_source is None:
        return False

    def owner(citation_id: str) -> Optional[int]:
        for i, h in enumerate(hypotheses):
            if citation_id in h.citations or f"CorrelationResult.{citation_id}" in h.citations:
                return i
        return None

    driver_owner = owner(top_driver.driver_id)
    source_owner = owner(top_source.source_id)
    if driver_owner is not None and source_owner is not None and driver_owner != source_owner:
        return True

    return False
