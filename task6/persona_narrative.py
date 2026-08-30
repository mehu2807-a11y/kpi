"""
Persona Narrative Generator - Creates different narrative versions for different audiences:
- Executives: High-level, strategic, impact-focused
- Analysts: Detailed, methodological, process-oriented
- Operations: Tactical, action-focused, immediate
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

# Add project root and task6 directory to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TASK6_DIR = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(TASK6_DIR) not in sys.path:
    sys.path.insert(0, str(TASK6_DIR))

from schemas import (
    StoryOutput, Hypothesis, AnomalyEvent, CorrelationResult, RetrievedEvidence
)
from action_enhancer import StructuredAction, enhance_story_output_actions


class Persona(Enum):
    EXECUTIVE = "executive"
    ANALYST = "analyst"
    OPERATIONS = "operations"


@dataclass
class PersonaNarrative:
    """Narrative tailored for a specific persona."""
    persona: Persona
    headline: str
    explanation: str
    hypotheses: List[Hypothesis]
    structured_actions: List[StructuredAction]
    overall_confidence: float
    escalate_flag: bool
    persona_specific_notes: str = ""


class PersonaNarrativeGenerator:
    """Generates persona-specific narratives from a base StoryOutput."""

    def __init__(self):
        pass

    def generate_persona_narratives(
        self,
        base_story: StoryOutput,
        anomaly: AnomalyEvent,
        correlation: CorrelationResult,
        evidence: RetrievedEvidence
    ) -> Dict[Persona, PersonaNarrative]:
        """Generate narratives for all three personas."""
        # First enhance the actions
        structured_actions = enhance_story_output_actions(base_story, correlation, evidence, anomaly)

        narratives = {}

        # Executive Narrative
        narratives[Persona.EXECUTIVE] = self._generate_executive_narrative(
            base_story, anomaly, correlation, evidence, structured_actions
        )

        # Analyst Narrative
        narratives[Persona.ANALYST] = self._generate_analyst_narrative(
            base_story, anomaly, correlation, evidence, structured_actions
        )

        # Operations Narrative
        narratives[Persona.OPERATIONS] = self._generate_operations_narrative(
            base_story, anomaly, correlation, evidence, structured_actions
        )

        return narratives

    def _generate_executive_narrative(
        self,
        base_story: StoryOutput,
        anomaly: AnomalyEvent,
        correlation: CorrelationResult,
        evidence: RetrievedEvidence,
        structured_actions: List[StructuredAction]
    ) -> PersonaNarrative:
        """Generate executive-focused narrative."""
        # Executive headline: focus on business impact
        direction_word = "up" if anomaly.direction == "increase" else "down"
        exec_headline = f"{anomaly.entity} {anomaly.metric_name} {direction_word} {abs(anomaly.magnitude_pct):.1f}% - Business Impact Analysis"

        # Executive explanation: focus on implications, not methodology
        if base_story.explanation:
            # Simplify explanation for executive audience
            exec_explanation = self._simplify_for_executive(base_story.explanation)
        else:
            exec_explanation = f"The {anomaly.metric_name} movement requires attention due to potential business impact."

        # Executive notes: strategic considerations
        exec_notes = self._generate_executive_notes(anomaly, correlation, structured_actions)

        return PersonaNarrative(
            persona=Persona.EXECUTIVE,
            headline=exec_headline,
            explanation=exec_explanation,
            hypotheses=base_story.hypotheses,
            structured_actions=structured_actions,
            overall_confidence=base_story.overall_confidence,
            escalate_flag=base_story.escalate_flag,
            persona_specific_notes=exec_notes
        )

    def _generate_analyst_narrative(
        self,
        base_story: StoryOutput,
        anomaly: AnomalyEvent,
        correlation: CorrelationResult,
        evidence: RetrievedEvidence,
        structured_actions: List[StructuredAction]
    ) -> PersonaNarrative:
        """Generate analyst-focused narrative."""
        # Analyst headline: methodological
        direction_word = "up" if anomaly.direction == "increase" else "down"
        analyst_headline = f"{anomaly.entity} {anomaly.metric_name} {direction_word} {abs(anomaly.magnitude_pct):.1f}% - Root Cause Analysis"

        # Analyst explanation: detailed, methodological
        analyst_explanation = base_story.explanation
        if not analyst_explanation:
            analyst_explanation = f"Analysis of {anomaly.metric_name} movement for {anomaly.entity} using correlation analysis and evidence retrieval."

        # Analyst notes: methodological details, limitations, next steps
        analyst_notes = self._generate_analyst_notes(anomaly, correlation, evidence, base_story)

        return PersonaNarrative(
            persona=Persona.ANALYST,
            headline=analyst_headline,
            explanation=analyst_explanation,
            hypotheses=base_story.hypotheses,
            structured_actions=structured_actions,
            overall_confidence=base_story.overall_confidence,
            escalate_flag=base_story.escalate_flag,
            persona_specific_notes=analyst_notes
        )

    def _generate_operations_narrative(
        self,
        base_story: StoryOutput,
        anomaly: AnomalyEvent,
        correlation: CorrelationResult,
        evidence: RetrievedEvidence,
        structured_actions: List[StructuredAction]
    ) -> PersonaNarrative:
        """Generate operations-focused narrative."""
        # Operations headline: action-oriented
        direction_word = "up" if anomaly.direction == "increase" else "down"
        ops_headline = f"{anomaly.entity} {anomaly.metric_name} {direction_word} {abs(anomaly.magnitude_pct):.1f}% - Action Required"

        # Operations explanation: focus on what to do next
        ops_explanation = f"Based on analysis of {anomaly.metric_name} movement, immediate actions are recommended to address the underlying drivers."

        # Operations notes: immediate next steps, ownership, timing
        ops_notes = self._generate_operations_notes(structured_actions)

        return PersonaNarrative(
            persona=Persona.OPERATIONS,
            headline=ops_headline,
            explanation=ops_explanation,
            hypotheses=base_story.hypotheses,
            structured_actions=structured_actions,
            overall_confidence=base_story.overall_confidence,
            escalate_flag=base_story.escalate_flag,
            persona_specific_notes=ops_notes
        )

    def _simplify_for_executive(self, explanation: str) -> str:
        """Simplify technical explanation for executive audience."""
        # Remove jargon, focus on business implications
        simplified = explanation.replace("correlation", "relationship")
        simplified = simplified.replace("SHAP value", "impact strength")
        simplified = simplified.replace("p-value", "statistical significance")
        # Truncate if too long
        if len(simplified) > 200:
            simplified = simplified[:197] + "..."
        return simplified

    def _generate_executive_notes(
        self,
        anomaly: AnomalyEvent,
        correlation: CorrelationResult,
        structured_actions: List[StructuredAction]
    ) -> str:
        """Generate executive-specific notes."""
        notes = []

        # Strategic impact
        notes.append(f"Potential financial impact: {abs(anomaly.magnitude_pct):.1f}% change in {anomaly.metric_name}")

        # Key driver insight
        if correlation.drivers:
            top_driver = correlation.drivers[0]
            notes.append(f"Primary driver: {top_driver.label} ({top_driver.value:+.3f} impact)")

        # Recommended actions summary
        if structured_actions:
            high_conf_actions = [a for a in structured_actions if a.confidence == "High"]
            if high_conf_actions:
                notes.append(f"{len(high_conf_actions)} high-confidence actions recommended for immediate review")

        # Risk level
        risk_level = "High" if abs(anomaly.magnitude_pct) > 10 else "Medium" if abs(anomaly.magnitude_pct) > 5 else "Low"
        notes.append(f"Risk level: {risk_level}")

        return " | ".join(notes)

    def _generate_analyst_notes(
        self,
        anomaly: AnomalyEvent,
        correlation: CorrelationResult,
        evidence: RetrievedEvidence,
        base_story: StoryOutput
    ) -> str:
        """Generate analyst-specific notes."""
        notes = []

        # Methodological notes
        notes.append(f"Analysis window: {anomaly.window_start} to {anomaly.window_end}")
        notes.append(f"Data points analyzed: {len(correlation.drivers)} drivers, {len(evidence.sources)} evidence sources")

        # Model performance
        if correlation.drivers:
            top_driver_impact = abs(correlation.drivers[0].value)
            notes.append(f"Top driver explanatory power: {top_driver_impact:.1%}")

        # Evidence quality
        if evidence.sources:
            avg_relevance = sum(s.relevance_score for s in evidence.sources) / len(evidence.sources)
            notes.append(f"Average evidence relevance: {avg_relevance:.2f}")

        # Confidence breakdown
        notes.append(f"Overall confidence: {base_story.overall_confidence:.2f}")
        notes.append(f"Escalation triggered: {base_story.escalate_flag}")

        # Limitations
        notes.append("Note: Correlation does not imply causation. Further validation recommended.")

        return " | ".join(notes)

    def _generate_operations_notes(self, structured_actions: List[StructuredAction]) -> str:
        """Generate operations-specific notes."""
        notes = []

        # Immediate actions
        immediate_actions = [a for a in structured_actions if a.confidence in ["High", "Medium"]]
        if immediate_actions:
            notes.append(f"Immediate actions ({len(immediate_actions)}):")
            for i, action in enumerate(immediate_actions[:3]):  # Top 3
                notes.append(f"  {i+1}. {action.action} (Owner: {action.owner})")

        # Monitoring
        notes.append(f"Recommended monitoring: Review effectiveness in next business cycle")

        # Ownership clarity
        owners = list(set(a.owner for a in structured_actions))
        if owners:
            notes.append(f"Action ownership: {', '.join(owners)}")

        return " | ".join(notes)


# Convenience function
def generate_persona_narratives(
    base_story: StoryOutput,
    anomaly: AnomalyEvent,
    correlation: CorrelationResult,
    evidence: RetrievedEvidence
) -> Dict[Persona, PersonaNarrative]:
    """Generate persona-specific narratives from base story."""
    generator = PersonaNarrativeGenerator()
    return generator.generate_persona_narratives(base_story, anomaly, correlation, evidence)