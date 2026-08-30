"""
Task 6 orchestration -- the join point that runs once Task 4's
CorrelationResult and Task 5's RetrievedEvidence are both available for a
given AnomalyEvent.

    story = synthesize(anomaly, correlation, evidence, llm_client)

Swap `llm_client` between MockLLMClient (offline, for demo.py /
test_synthesize.py) and AnthropicLLMClient (real) -- everything else here is
deterministic and doesn't change based on which one you pass in.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import List, Dict, Optional, Any
from enum import Enum

# Ensure the task6 directory is in sys.path to import the correct schemas
TASK6_DIR = Path(__file__).parent
if str(TASK6_DIR) not in sys.path:
    sys.path.insert(0, str(TASK6_DIR))

from schemas import (
    AnomalyEvent, CorrelationResult, RetrievedEvidence,
    Hypothesis, StoryOutput,
)
from llm_client import LLMClient, SYSTEM_PROMPT, build_user_prompt
from scoring import score_hypothesis, detect_disagreement

# Import enhancement modules
import sys
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kpi_contract import DEFAULT_KPI_CONTRACT
from action_enhancer import ActionEnhancer, StructuredAction, enhance_story_output_actions
from persona_narrative import Persona, PersonaNarrative, generate_persona_narratives

logger = logging.getLogger(__name__)

MAX_HYPOTHESES = 3


def _build_headline(anomaly: AnomalyEvent, hypotheses: List[Hypothesis], escalate: bool) -> str:
    """Headline text is templated programmatically, not written by the LLM.

    This is deliberate: the brief's core rule is that confidence language
    should never outrun the computed score. If the LLM drafted the headline
    directly, it could say "most likely driven by X" before scoring even
    runs -- and that framing could end up contradicting an escalate_flag the
    numbers later produce. Templating it off the already-computed result
    keeps the two consistent by construction.
    """
    direction_word = "up" if anomaly.direction == "increase" else "down"
    base = f"{anomaly.entity} {anomaly.metric_name} {direction_word} {abs(anomaly.magnitude_pct):.1f}%"
    if not hypotheses:
        return f"{base} — cause undetermined, no citable evidence"
    if escalate and len(hypotheses) >= 2:
        return f"{base} — unclear cause, two competing explanations need review"
    return f"{base}, most likely driven by {hypotheses[0].cause}"


def synthesize(
    anomaly: AnomalyEvent,
    correlation: CorrelationResult,
    evidence: RetrievedEvidence,
    llm_client: LLMClient,
) -> StoryOutput:
    """
    Original synthesize function - kept unchanged for backward compatibility with tests.
    """
    user_prompt = build_user_prompt(anomaly, correlation, evidence)
    raw = llm_client.complete_json(SYSTEM_PROMPT, user_prompt)

    explanation = raw.get("explanation", "")
    hypotheses: List[Hypothesis] = []

    for raw_hyp in raw.get("hypotheses", [])[:MAX_HYPOTHESES]:
        cause = (raw_hyp.get("cause") or "").strip()
        raw_citations = raw_hyp.get("citations", [])
        actions = raw_hyp.get("actions", [])

        confidence, resolved = score_hypothesis(raw_citations, correlation, evidence)

        if resolved.unresolved:
            logger.warning(
                "Dropping unresolved citation(s) %s for hypothesis %r",
                resolved.unresolved, cause,
            )
        valid_citations = [c for c in raw_citations if c not in resolved.unresolved]

        if not valid_citations:
            # The brief is explicit: every hypothesis needs a citation. One
            # that resolves to none is a bare assertion -- drop it rather
            # than keep it with a fabricated source of confidence.
            logger.warning("Dropping hypothesis %r -- no citations resolved", cause)
            continue

        hypotheses.append(Hypothesis(
            cause=cause,
            confidence=confidence,
            citations=valid_citations,
            actions=list(actions),
        ))

    hypotheses.sort(key=lambda h: h.confidence, reverse=True)

    if not hypotheses:
        return StoryOutput(
            headline=_build_headline(anomaly, [], escalate=True),
            explanation=explanation or (
                "No citable root cause could be constructed from the available "
                "structured drivers or retrieved evidence."
            ),
            hypotheses=[],
            recommended_actions=[
                "Route to an analyst for manual review — automated synthesis "
                "could not ground any hypothesis in the retrieved evidence."
            ],
            overall_confidence=0.0,
            escalate_flag=True,
        )

    escalate = detect_disagreement(hypotheses, correlation, evidence)
    recommended_actions = [a for h in hypotheses for a in h.actions]

    return StoryOutput(
        headline=_build_headline(anomaly, hypotheses, escalate),
        explanation=explanation,
        hypotheses=hypotheses,
        recommended_actions=recommended_actions,
        overall_confidence=hypotheses[0].confidence,
        escalate_flag=escalate,
    )


def synthesize_enhanced(
    anomaly: AnomalyEvent,
    correlation: CorrelationResult,
    evidence: RetrievedEvidence,
    llm_client: LLMClient,
) -> Dict:
    """
    Enhanced synthesize function that returns:
    - Original StoryOutput (for backward compatibility)
    - Structured actions
    - Persona-specific narratives
    - KPI contract references
    - Telemetry data
    """
    start_time = time.time()

    # Get original story
    story = synthesize(anomaly, correlation, evidence, llm_client)

    # Enhance with structured actions
    action_enhancer = ActionEnhancer()
    structured_actions = action_enhancer.enhance_actions(
        story.hypotheses, correlation, evidence, anomaly
    )

    # Generate persona-specific narratives
    persona_narratives = generate_persona_narratives(story, anomaly, correlation, evidence)

    # Get relevant KPI definitions
    relevant_kpis = []
    # Create a mapping from driver names to KPI IDs for lookup
    driver_to_kpi_id = {
        "avg_price": "avg_price",
        "marketing_spend": "marketing_spend",
        "inventory_level": "inventory_level",
        "revenue": "revenue_total",
        "units_sold": "units_sold",
        "complaint_sentiment_score": None  # We don't have a specific KPI for this yet
    }

    for driver in correlation.drivers:
        kpi_id = driver_to_kpi_id.get(driver.driver_id)
        if kpi_id:
            kpi_def = DEFAULT_KPI_CONTRACT.get_kpi(kpi_id)
            if kpi_def:
                relevant_kpis.append(kpi_def)

    # If no specific KPIs found, add default ones that match the anomaly metric
    if not relevant_kpis:
        # Map anomaly metric name to possible KPI IDs
        metric_to_kpi_id = {
            "revenue": "revenue_total",
            "units_sold": "units_sold",
            # Add more mappings as needed
        }
        kpi_id = metric_to_kpi_id.get(anomaly.metric_name)
        if kpi_id:
            kpi_def = DEFAULT_KPI_CONTRACT.get_kpi(kpi_id)
            if kpi_def:
                relevant_kpis.append(kpi_def)

    # Calculate processing time
    processing_time_ms = (time.time() - start_time) * 1000

    # Generate detailed telemetry data
    telemetry = {
        # Core metrics
        "confidence_score": story.overall_confidence,
        "escalation_triggered": story.escalate_flag,
        "hypotheses_count": len(story.hypotheses),
        "evidence_sources_count": len(evidence.sources),
        "structured_drivers_count": len(correlation.drivers),

        # Processing metrics
        "processing_timestamp": time.time(),  # Unix timestamp for precision
        "processing_latency_ms": round(processing_time_ms, 2),

        # LLM usage metrics
        "llm_calls": 1,
        "llm_prompt_tokens_estimate": _estimate_prompt_tokens(anomaly, correlation, evidence),
        "llm_completion_tokens_estimate": _estimate_completion_tokens(story),
        "llm_total_tokens_estimate": 0,  # Will be calculated below

        # Cost estimation (based on typical LLM pricing)
        "estimated_cost_usd": 0.0,  # Will be calculated below

        # Quality indicators
        "avg_hypothesis_confidence": sum(h.confidence for h in story.hypotheses) / len(story.hypotheses) if story.hypotheses else 0.0,
        "confidence_std_dev": _calculate_confidence_std_dev(story.hypotheses) if len(story.hypotheses) > 1 else 0.0,
        "evidence_quality_score": sum(s.relevance_score for s in evidence.sources) / len(evidence.sources) if evidence.sources else 0.0,
        "driver_strength_concentration": _calculate_driver_concentration(correlation.drivers) if correlation.drivers else 0.0,
    }

    # Calculate derived telemetry fields
    telemetry["llm_total_tokens_estimate"] = (
        telemetry["llm_prompt_tokens_estimate"] +
        telemetry["llm_completion_tokens_estimate"]
    )

    # Rough cost estimate (using GPT-3.5-turbo pricing as example: $0.002 per 1K tokens)
    telemetry["estimated_cost_usd"] = round(
        (telemetry["llm_total_tokens_estimate"] / 1000) * 0.002,
        6
    )

    # Add human-readable timestamp
    from datetime import datetime
    telemetry["processing_timestamp_iso"] = datetime.fromtimestamp(
        telemetry["processing_timestamp"]
    ).isoformat() + "Z"

    return {
        "original_story": story,
        "structured_actions": structured_actions,
        "persona_narratives": persona_narratives,
        "relevant_kpis": relevant_kpis,
        "telemetry": telemetry
    }


def _estimate_prompt_tokens(anomaly: AnomalyEvent, correlation: CorrelationResult, evidence: RetrievedEvidence) -> int:
    """Estimate number of tokens in the LLM prompt."""
    # Rough estimation: 4 characters per token on average
    prompt_length = len(SYSTEM_PROMPT) + len(build_user_prompt(anomaly, correlation, evidence))
    return max(1, prompt_length // 4)


def _estimate_completion_tokens(story: StoryOutput) -> int:
    """Estimate number of tokens in the LLM completion."""
    # Rough estimation based on output length
    output_length = len(story.explanation or "")
    for hypothesis in story.hypotheses:
        output_length += len(hypothesis.cause or "")
        output_length += sum(len(cite or "") for cite in hypothesis.citations)
        output_length += sum(len(action or "") for action in hypothesis.actions)
    return max(1, output_length // 4)


def _calculate_confidence_std_dev(hypotheses: List[Hypothesis]) -> float:
    """Calculate standard deviation of hypothesis confidences."""
    if len(hypotheses) < 2:
        return 0.0

    mean = sum(h.confidence for h in hypotheses) / len(hypotheses)
    variance = sum((h.confidence - mean) ** 2 for h in hypotheses) / len(hypotheses)
    return variance ** 0.5


def _calculate_driver_concentration(drivers) -> float:
    """Calculate how concentrated the driver strengths are (0 = even, 1 = one dominant)."""
    if not drivers:
        return 0.0

    strengths = [abs(d.value) for d in drivers]
    total = sum(strengths)
    if total == 0:
        return 0.0

    # Calculate Herfindahl-Hirschman Index equivalent
    normalized = [s / total for s in strengths]
    hhi = sum(n * n for n in normalized)

    # Normalize to 0-1 range where 1 is completely concentrated
    max_hhi = 1.0  # When one driver has 100% strength
    min_hhi = 1.0 / len(drivers)  # When all drivers are equal

    if max_hhi == min_hhi:
        return 0.0

    return (hhi - min_hhi) / (max_hhi - min_hhi)