"""
Enhanced demo for Task 6 showing the new features:
- Structured action recommendations (driver → lever → action → impact → owner → confidence → monitoring)
- Persona-specific narratives (executive, analyst, operations)
- KPI contract integration
- Detailed telemetry and LLM usage tracking
- Feedback mechanism integration

Run: python demo_enhanced.py
"""

import json
import time
from dataclasses import asdict
from enum import Enum
import sys
from pathlib import Path

# Add project root and task6 directory to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TASK6_DIR = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(TASK6_DIR) not in sys.path:
    sys.path.insert(0, str(TASK6_DIR))

from mock_data import easy_case, hard_case
from llm_client import MockLLMClient
from synthesize import synthesize_enhanced
from feedback_manager import FeedbackManager, FeedbackType, FeedbackValue


def pretty_print_structured_action(action) -> str:
    """Format a structured action for display."""
    return (
        f"  {action.driver} -> {action.controllable_leverage} -> {action.action} -> "
        f"{action.expected_impact} -> {action.owner} -> {action.confidence} -> {action.monitoring_plan}"
    )


def pretty_print_persona_narrative(persona: str, narrative) -> str:
    """Format a persona narrative for display."""
    lines = [
        f"  Persona: {persona.upper()}",
        f"  Headline: {narrative.headline}",
        f"  Explanation: {narrative.explanation}",
        f"  Confidence: {narrative.overall_confidence:.2f}",
        f"  Escalate: {narrative.escalate_flag}",
    ]

    if narrative.structured_actions:
        lines.append("  Structured Actions:")
        for action in narrative.structured_actions:
            lines.append(f"    {pretty_print_structured_action(action)}")

    if narrative.persona_specific_notes:
        lines.append(f"  Notes: {narrative.persona_specific_notes}")

    return "\n".join(lines)


def demo_feedback_integration():
    """Demonstrate how feedback can be collected and used."""
    print("\n" + "=" * 72)
    print("FEEDBACK MANAGEMENT DEMO")
    print("=" * 72)

    # Simulate collecting some feedback
    fb_manager = FeedbackManager()

    # Add some sample feedback
    fb_manager.add_feedback(
        FeedbackType.ACTION_RELEVANCE,
        FeedbackValue.GOOD,
        "The pricing action was very helpful and led to a quick win",
        anomaly_id="anom_001",
        provider_role="business_user",
        provider_id="sales_manager_001"
    )

    fb_manager.add_feedback(
        FeedbackType.ACTION_RELEVANCE,
        FeedbackValue.POOR,
        "The marketing action was too generic and didn't consider our budget constraints",
        anomaly_id="anom_002",
        provider_role="analyst",
        provider_id="analyst_002"
    )

    fb_manager.add_feedback(
        FeedbackType.NARRATIVE_CLARITY,
        FeedbackValue.EXCELLENT,
        "Executive summary was perfect for my morning briefing",
        anomaly_id="anom_001",
        persona="executive",
        provider_role="executive",
        provider_id="cmo_001"
    )

    # Show feedback summary
    action_summary = fb_manager.get_feedback_summary(FeedbackType.ACTION_RELEVANCE)
    print(f"Action Feedback Summary:")
    print(f"  Total: {action_summary.total_count} | Avg Score: {action_summary.average_score:.1f} | Trend: {action_summary.recent_trend}")

    narrative_summary = fb_manager.get_feedback_summary(FeedbackType.NARRATIVE_CLARITY)
    print(f"Narrative Feedback Summary:")
    print(f"  Total: {narrative_summary.total_count} | Avg Score: {narrative_summary.average_score:.1f} | Trend: {narrative_summary.recent_trend}")

    # Show insights for improvement
    insights = fb_manager.get_actionability_insights()
    if insights:
        print("Improvement Insights:")
        for insight in insights:
            print(f"  • {insight}")
    else:
        print("No improvement insights at this time.")


def run_enhanced_demo(label: str, case_fn, canned_response: dict) -> None:
    """Run an enhanced demo showing all new features."""
    anomaly, correlation, evidence = case_fn()
    client = MockLLMClient(canned_response)

    start_time = time.time()
    result = synthesize_enhanced(anomaly, correlation, evidence, client)
    end_time = time.time()

    print(f"\n{'=' * 72}\n{label} (ENHANCED)\n{'=' * 72}")

    # Original story (backward compatibility)
    story = result["original_story"]
    print(f"ORIGINAL STORY (Backward Compatible):")
    print(f"  Headline: {story.headline}")
    print(f"  Explanation: {story.explanation}")
    print(f"  Overall Confidence: {story.overall_confidence:.2f}")
    print(f"  Escalate Flag: {story.escalate_flag}")
    print(f"  Number of Hypotheses: {len(story.hypotheses)}")

    if story.hypotheses:
        print("  Hypotheses:")
        for i, hyp in enumerate(story.hypotheses):
            print(f"    {i+1}. {hyp.cause} (confidence: {hyp.confidence:.2f})")
            print(f"        Citations: {', '.join(hyp.citations)}")
            print(f"        Actions: {', '.join(hyp.actions)}")

    print(f"\n  Original Recommended Actions:")
    for i, action in enumerate(story.recommended_actions):
        print(f"    {i+1}. {action}")

    # Enhanced features
    print(f"\nENHANCED FEATURES:")

    # Structured Actions
    structured_actions = result["structured_actions"]
    if structured_actions:
        print(f"  Structured Actions ({len(structured_actions)}):")
        for action in structured_actions:
            print(f"    {pretty_print_structured_action(action)}")
    else:
        print("  Structured Actions: None generated")

    # Persona-Specific Narratives
    persona_narratives = result["persona_narratives"]
    if persona_narratives:
        print(f"  Persona-Specific Narratives:")
        for persona_enum, narrative in persona_narratives.items():
            persona_name = persona_enum.value if isinstance(persona_enum, Enum) else str(persona_enum)
            print(pretty_print_persona_narrative(persona_name, narrative))
            print()  # Empty line between personas
    else:
        print("  Persona-Specific Narratives: None generated")

    # Relevant KPIs
    relevant_kpis = result["relevant_kpis"]
    if relevant_kpis:
        print(f"  Relevant KPI Definitions ({len(relevant_kpis)}):")
        for kpi in relevant_kpis:
            print(f"    • {kpi.name} ({kpi.kpi_id}): {kpi.description}")
            print(f"      Formula: {kpi.formula} | Owner: {kpi.business_owner} | Access: {kpi.access_level.value}")
    else:
        print("  Relevant KPI Definitions: None found")

    # Telemetry
    telemetry = result["telemetry"]
    if telemetry:
        print(f"  Telemetry & Metrics:")
        print(f"    Processing Latency: {telemetry.get('processing_latency_ms', 0):.2f} ms")
        print(f"    LLM Calls: {telemetry.get('llm_calls', 0)}")
        print(f"    Estimated LLM Tokens: {telemetry.get('llm_total_tokens_estimate', 0)}")
        print(f"    Estimated Cost: ${telemetry.get('estimated_cost_usd', 0):.6f}")
        print(f"    Evidence Quality Score: {telemetry.get('evidence_quality_score', 0):.2f}")
        print(f"    Driver Concentration: {telemetry.get('driver_strength_concentration', 0):.2f}")
        print(f"    Avg Hypothesis Confidence: {telemetry.get('avg_hypothesis_confidence', 0):.2f}")

    # Show total processing time
    print(f"\n  Total Processing Time: {(end_time - start_time)*1000:.2f} ms")


def main():
    """Run the enhanced demo for both test cases."""
    print("BusinessIntelligence.ai - Enhanced Task 6 Demonstration")
    print("Showing new features: structured actions, persona narratives, KPI contracts, telemetry, and feedback")

    run_enhanced_demo("EASY CASE — one dominant, well-corroborated cause", easy_case, EASY_LLM_RESPONSE)
    run_enhanced_demo("HARD CASE — two plausible causes, conflicting evidence", hard_case, HARD_LLM_RESPONSE)

    demo_feedback_integration()

    print(f"\n{'=' * 72}")
    print("DEMO COMPLETE")
    print("The enhanced features address the BusinessIntelligence.ai Round 2 requirements:")
    print("[OK] Structured action recommendations (driver -> lever -> action -> impact -> owner -> confidence -> monitoring)")
    print("[OK] Persona-specific narratives (executive, analyst, operations)")
    print("[OK] KPI semantic contract integration")
    print("[OK] Comprehensive telemetry including LLM usage and cost tracking")
    print("[OK] Feedback mechanism for continuous improvement")
    print("[OK] Backward compatibility maintained with original synthesize function")
    print(f"{'=' * 72}")


# Reuse the mock responses from the original demo
EASY_LLM_RESPONSE = {
    "explanation": (
        "Region X revenue fell 7.5% for the week of July 4-10. The drop lines up closely "
        "with a 10% list-price increase on Product A that took effect July 4, which is also "
        "the strongest structured driver for this anomaly. A competitor promotion in "
        "overlapping markets is a much weaker, secondary signal."
    ),
    "hypotheses": [
        {
            "cause": "10% price increase on Product A, effective July 4, reduced regional demand",
            "citations": ["CorrelationResult.avg_price", "internal_00091", "news_00231"],
            "actions": [
                "Compare Region X's price elasticity for Product A against the assumption used when the increase was approved",
                "Check whether the drop is concentrated in Product A or spread across the regional basket",
            ],
        },
        {
            "cause": "CompetitorCo's summer promotion pulled share in overlapping markets",
            "citations": ["news_00255"],
            "actions": [
                "Confirm CompetitorCo's promotion end date before reversing any price change",
            ],
        },
    ],
}

HARD_LLM_RESPONSE = {
    "explanation": (
        "Region Y signups fell 12% for the week of June 13-19. Two structural drivers are "
        "close in strength: a 3.2x spike in mobile app crash rate and a 40% cut to regional "
        "marketing spend, starting within a day of each other. Evidence supports each "
        "independently, and nothing in the data distinguishes which one dominates."
    ),
    "hypotheses": [
        {
            "cause": "Mobile app crashes drove signup abandonment",
            "citations": ["CorrelationResult.crash_rate", "reviews_00114"],
            "actions": [
                "Pull crash logs for the affected app version and confirm the release date lines up with June 14",
                "Check signup funnel drop-off specifically at the crash-prone screen",
            ],
        },
        {
            "cause": "40% marketing spend cut in Region Y reduced top-of-funnel traffic",
            "citations": ["CorrelationResult.marketing_spend_cut", "internal_00147"],
            "actions": [
                "Compare paid traffic volume in Region Y before and after June 13 against the signup drop timing",
            ],
        },
    ],
}


if __name__ == "__main__":
    main()