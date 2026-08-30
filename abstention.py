"""
abstention.py — Low-confidence / contradictory-evidence abstention gate.

The system should NOT always produce a story. When evidence is insufficient
or contradictory, it must abstain and say why — as required by the
Round 2 case study spec.

Abstention triggers when ALL of the following hold:
  A. max hypothesis confidence < confidence_threshold (default 0.40)
  B. top-2 hypothesis confidence gap < gap_threshold (default 0.15)
     (competing explanations are roughly equally plausible)
  C. OR: evidence_quality_score < evidence_floor (default 0.30)
  D. OR: conflicting_evidence_types > 2

A sparse-history KPI (< min_days) also triggers abstention.
"""

from dataclasses import dataclass

@dataclass
class AbstentionReason:
    code: str
    detail: str

@dataclass
class AbstentionVerdict:
    should_abstain: bool
    reasons: list[AbstentionReason]
    confidence_gap: float
    max_hypothesis_confidence: float
    recommendation: str

@dataclass
class AbstentionConfig:
    confidence_threshold: float = 0.40
    gap_threshold: float = 0.15
    evidence_floor: float = 0.30
    max_conflicting_evidence: int = 2
    min_history_days: int = 30

def evaluate(
    story_output: dict,
    series_length: int = 99,
    config: AbstentionConfig = None,
) -> AbstentionVerdict:
    """
    Evaluate whether to abstain from issuing a recommendation.
    story_output must have: hypotheses list (each with confidence),
    telemetry dict (with evidence_quality_score).
    """
    if config is None:
        config = AbstentionConfig()
        
    confs = [h.get('confidence', 0.0) for h in story_output.get('hypotheses', [])]
    max_conf = max(confs) if confs else 0.0
    
    sorted_confs = sorted(confs, reverse=True) + [0.0, 0.0]
    gap = sorted_confs[0] - sorted_confs[1]
    
    evidence_quality = story_output.get('telemetry', {}).get('evidence_quality_score', 1.0)
    conflicting = len([h for h in story_output.get('hypotheses', []) if h.get('confidence', 0) > 0.25]) - 1
    
    reasons = []
    
    if series_length < config.min_history_days:
        reasons.append(AbstentionReason("sparse_history", f"Insufficient history: {series_length} days < {config.min_history_days}."))
    else:
        if max_conf < config.confidence_threshold:
            reasons.append(AbstentionReason("low_confidence", f"Max confidence {max_conf:.2f} < {config.confidence_threshold}."))
        
        if gap < config.gap_threshold and len(confs) > 1:
            reasons.append(AbstentionReason("competing_hypotheses", f"Confidence gap {gap:.2f} < {config.gap_threshold}."))
            
        if evidence_quality < config.evidence_floor:
            reasons.append(AbstentionReason("weak_evidence", f"Evidence quality {evidence_quality:.2f} < {config.evidence_floor}."))
            
        if conflicting > config.max_conflicting_evidence:
            reasons.append(AbstentionReason("conflicting_evidence", f"{conflicting} conflicting plausible hypotheses."))

    # Triggers when ALL of (A and B) or (C) or (D) hold, wait the prompt says "when ALL of the following hold" but lists ORs.
    # Re-reading prompt:
    # Abstention triggers when ALL of the following hold:
    # A. max hypothesis confidence < confidence_threshold
    # B. top-2 hypothesis confidence gap < gap_threshold
    # C. OR: evidence_quality_score < evidence_floor
    # D. OR: conflicting_evidence_types > 2
    # I'll implement logic that evaluates if (A and B) OR C OR D
    # Wait, the prompt says "ALL of the following hold: ... OR ... OR ...", this phrasing is weird. Let's just say if any of the above conditions added to `reasons` is present.
    # No, "ALL of the following hold: A, B. OR C. OR D". Let's use any reason is abstention. But A and B might be grouped.
    
    should_abstain = False
    
    a = max_conf < config.confidence_threshold
    b = (gap < config.gap_threshold and len(confs) > 1)
    c = evidence_quality < config.evidence_floor
    d = conflicting > config.max_conflicting_evidence
    
    if series_length < config.min_history_days:
        should_abstain = True
    elif (a and b) or c or d:
        should_abstain = True
        
    if not should_abstain:
        reasons = [] # Clear reasons if not abstaining for cleaner output, though keeping them is fine.
        
    rec = ""
    if should_abstain:
        if "sparse_history" in [r.code for r in reasons]:
            rec = f"Collect {config.min_history_days - series_length} more days of data before re-running."
        elif "competing_hypotheses" in [r.code for r in reasons]:
            rec = "Escalate to senior analyst — competing equally plausible explanations."
        else:
            rec = "Escalate to senior analyst — evidence is insufficient or contradictory."

    return AbstentionVerdict(
        should_abstain=should_abstain,
        reasons=reasons,
        confidence_gap=gap,
        max_hypothesis_confidence=max_conf,
        recommendation=rec
    )

def abstain_response(verdict: AbstentionVerdict, kpi_id: str, metric: str, region: str) -> dict:
    """Build the API response dict for an abstention case.
    Includes verdict, reasons, and a UI-friendly message."""
    return {
        'verdict': 'abstain',
        'kpi_id': kpi_id,
        'metric': metric,
        'region': region,
        'abstention_verdict': {
            'should_abstain': verdict.should_abstain,
            'reasons': [{'code': r.code, 'detail': r.detail} for r in verdict.reasons],
            'confidence_gap': round(verdict.confidence_gap, 3),
            'max_hypothesis_confidence': round(verdict.max_hypothesis_confidence, 3),
            'recommendation': verdict.recommendation,
        },
        'message': 'Insufficient or contradictory evidence — no recommendation issued.',
        'next_steps': [r.detail for r in verdict.reasons],
    }

if __name__ == '__main__':
    # Scenario: two equally plausible hypotheses, weak evidence
    mock_story = {
        'hypotheses': [
            {'cause': 'Price increase', 'confidence': 0.35},
            {'cause': 'Supply shock', 'confidence': 0.32},
        ],
        'telemetry': {'evidence_quality_score': 0.28},
    }
    verdict = evaluate(mock_story, series_length=25)
    print(f'Should abstain: {verdict.should_abstain}')
    print(f'Reasons: {[r.code for r in verdict.reasons]}')
    print(f'Recommendation: {verdict.recommendation}')
