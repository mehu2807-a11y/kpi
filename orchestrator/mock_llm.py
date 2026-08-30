"""
mock_llm.py -- builds MockLLMClient canned responses for the orchestrator's
test suite.

Task 6's own MockLLMClient (from llm_client.py) takes one fixed canned
response per instance -- exactly how its own demo.py/test_synthesize.py use
it. This module generates a *plausible* response shaped like a real Claude
completion for whatever CorrelationResult/RetrievedEvidence a given test
scenario actually produced, in one of a few styles, so the 15-scenario test
suite can exercise Task 6's scoring and escalation logic against realistic
input without needing network access or an API key -- consistent with how
Task 6 was built to run "day-one, no network needed" per its own README.

IMPORTANT: this module writes prompts for a MOCK client standing in for the
LLM -- it does not call any model. Nothing here talks to the network.
"""
from __future__ import annotations


def _driver_by_id(correlation, driver_id):
    return next(d for d in correlation.drivers if d.driver_id == driver_id)


def _source_by_id(evidence, source_id):
    return next(s for s in evidence.sources if s.source_id == source_id)


def single_dominant_cause(correlation, evidence) -> dict:
    """Style: one clear driver, corroborated by the top 1-2 sources. Should
    resolve to escalate_flag=False if the margin over the runner-up is wide."""
    top_driver = correlation.drivers[0]
    top_sources = evidence.sources[:2] if len(evidence.sources) >= 2 else evidence.sources[:1]
    citations = [f"CorrelationResult.{top_driver.driver_id}"] + [s.source_id for s in top_sources]
    hyps = [{
        "cause": top_driver.label,
        "citations": citations,
        "actions": [
            f"Review the {top_driver.driver_id.replace('_', ' ')} change against the affected window.",
            "Confirm with the regional lead before reversing any related decision.",
        ],
    }]
    if len(correlation.drivers) > 1:
        runner_up = correlation.drivers[1]
        hyps.append({
            "cause": runner_up.label,
            "citations": [f"CorrelationResult.{runner_up.driver_id}"],
            "actions": ["Rule this out only if the primary driver is confirmed."],
        })
    return {
        "explanation": (
            f"{top_driver.label} is the strongest signal in the anomaly window, "
            f"and it lines up with what the retrieved evidence shows."
        ),
        "hypotheses": hyps,
    }


def two_competing_causes(correlation, evidence) -> dict:
    """Style: two structurally close drivers, each backed by a distinct,
    non-overlapping source -- should trigger escalate_flag via close margin
    and/or cross-modal mismatch."""
    d0 = correlation.drivers[0]
    d1 = correlation.drivers[1] if len(correlation.drivers) > 1 else correlation.drivers[0]
    s0 = evidence.sources[0] if evidence.sources else None
    s1 = evidence.sources[1] if len(evidence.sources) > 1 else (evidence.sources[0] if evidence.sources else None)
    hyp0 = {
        "cause": d0.label,
        "citations": [f"CorrelationResult.{d0.driver_id}"] + ([s0.source_id] if s0 else []),
        "actions": ["Investigate this driver first; it has the stronger structured signal."],
    }
    hyp1 = {
        "cause": d1.label,
        "citations": [f"CorrelationResult.{d1.driver_id}"] + ([s1.source_id] if s1 else []),
        "actions": ["Investigate this as the alternate explanation before committing to a fix."],
    }
    return {
        "explanation": (
            "Two plausible explanations are both consistent with part of the evidence, "
            "and neither one dominates -- this needs a human call."
        ),
        "hypotheses": [hyp0, hyp1],
    }


def hallucinated_citation(correlation, evidence) -> dict:
    """Style: deliberately cites an id that does not exist, alongside one
    that does -- proves Task 6 drops the bad citation instead of trusting it."""
    real_driver = correlation.drivers[0]
    return {
        "explanation": "Testing citation validation with one real and one fabricated id.",
        "hypotheses": [{
            "cause": real_driver.label,
            "citations": [f"CorrelationResult.{real_driver.driver_id}", "news_99999_DOES_NOT_EXIST"],
            "actions": ["Verify this against the source data before acting."],
        }],
    }


def no_grounding(correlation, evidence) -> dict:
    """Style: a hypothesis with zero valid citations -- proves Task 6 drops
    it entirely and falls back to the 'route to analyst' response."""
    return {
        "explanation": "No structured driver or retrieved source clearly explains this move.",
        "hypotheses": [{
            "cause": "Unclear -- possibly a data quality issue upstream.",
            "citations": ["totally_fabricated_id_1", "totally_fabricated_id_2"],
            "actions": ["Have an analyst inspect the raw feed for this window."],
        }],
    }


STYLES = {
    "single_dominant": single_dominant_cause,
    "two_competing": two_competing_causes,
    "hallucinated_citation": hallucinated_citation,
    "no_grounding": no_grounding,
}


def build_canned_response(style: str, correlation, evidence) -> dict:
    if style not in STYLES:
        raise ValueError(f"unknown mock LLM style {style!r}, choose from {list(STYLES)}")
    return STYLES[style](correlation, evidence)
