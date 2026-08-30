"""
Tests for Task 6's deterministic logic (citation resolution, confidence
scoring, disagreement detection) plus one end-to-end smoke test per mock
case. No network access required -- MockLLMClient stands in for the real
Anthropic call.

    python -m unittest test_synthesize.py -v
"""

import unittest
import sys
from pathlib import Path

# Ensure the task6 directory is in sys.path to import the correct schemas
TASK6_DIR = Path(__file__).parent
if str(TASK6_DIR) not in sys.path:
    sys.path.insert(0, str(TASK6_DIR))

from schemas import (
    StructuredDriver, CorrelationResult,
    EvidenceSource, RetrievedEvidence, Hypothesis,
)
from scoring import resolve_citations, score_hypothesis, detect_disagreement
from llm_client import MockLLMClient
from synthesize import synthesize
from mock_data import easy_case, hard_case
from demo import EASY_LLM_RESPONSE, HARD_LLM_RESPONSE


class TestCitationResolution(unittest.TestCase):
    def setUp(self):
        self.correlation = CorrelationResult(
            anomaly_id="a1",
            drivers=[StructuredDriver("avg_price", "price up", "correlation", -0.8, 1)],
        )
        self.evidence = RetrievedEvidence(
            anomaly_id="a1",
            sources=[EvidenceSource("news_001", "t", "s", "Pub", "2026-01-01", 0.9, 1)],
        )

    def test_valid_citations_resolve(self):
        resolved = resolve_citations(
            ["CorrelationResult.avg_price", "news_001"], self.correlation, self.evidence,
        )
        self.assertEqual(resolved.driver_ids, ["avg_price"])
        self.assertEqual(resolved.source_ids, ["news_001"])
        self.assertEqual(resolved.unresolved, [])

    def test_hallucinated_citation_is_dropped(self):
        resolved = resolve_citations(
            ["CorrelationResult.avg_price", "news_999_does_not_exist"],
            self.correlation, self.evidence,
        )
        self.assertEqual(resolved.unresolved, ["news_999_does_not_exist"])
        self.assertEqual(resolved.source_ids, [])


class TestScoring(unittest.TestCase):
    def test_confidence_bounded_zero_to_one(self):
        correlation = CorrelationResult("a1", [StructuredDriver("d1", "x", "shap", 5.0, 1)])
        evidence = RetrievedEvidence("a1", [EvidenceSource("s1", "t", "s", "P", "2026-01-01", 0.9, 1)])
        confidence, _ = score_hypothesis(["CorrelationResult.d1", "s1"], correlation, evidence)
        self.assertGreaterEqual(confidence, 0.0)
        self.assertLessEqual(confidence, 1.0)

    def test_uncited_hypothesis_scores_zero(self):
        correlation = CorrelationResult("a1", [StructuredDriver("d1", "x", "shap", 5.0, 1)])
        evidence = RetrievedEvidence("a1", [])
        confidence, resolved = score_hypothesis([], correlation, evidence)
        self.assertEqual(confidence, 0.0)

    def test_more_independent_sources_scores_higher(self):
        correlation = CorrelationResult("a1", [])
        evidence = RetrievedEvidence("a1", [
            EvidenceSource("s1", "t", "s", "Pub A", "2026-01-01", 0.9, 1),
            EvidenceSource("s2", "t", "s", "Pub B", "2026-01-01", 0.8, 2),
        ])
        one_source, _ = score_hypothesis(["s1"], correlation, evidence)
        two_sources, _ = score_hypothesis(["s1", "s2"], correlation, evidence)
        self.assertGreater(two_sources, one_source)

    def test_same_publisher_twice_does_not_double_count(self):
        # two source_ids, same publisher -- should score the same as citing
        # just one of them, since "independent" means distinct publishers
        correlation = CorrelationResult("a1", [])
        evidence = RetrievedEvidence("a1", [
            EvidenceSource("s1", "t", "s", "Same Pub", "2026-01-01", 0.9, 1),
            EvidenceSource("s2", "t", "s", "Same Pub", "2026-01-01", 0.8, 2),
        ])
        one_source, _ = score_hypothesis(["s1"], correlation, evidence)
        both_same_pub, _ = score_hypothesis(["s1", "s2"], correlation, evidence)
        self.assertEqual(one_source, both_same_pub)


class TestDisagreementDetection(unittest.TestCase):
    def test_close_margin_triggers_escalation(self):
        hyps = [Hypothesis("A", 0.60, ["x"], []), Hypothesis("B", 0.52, ["y"], [])]
        self.assertTrue(detect_disagreement(hyps, CorrelationResult("a1", []), RetrievedEvidence("a1", [])))

    def test_single_hypothesis_never_escalates(self):
        hyps = [Hypothesis("A", 0.60, ["x"], [])]
        self.assertFalse(detect_disagreement(hyps, CorrelationResult("a1", []), RetrievedEvidence("a1", [])))

    def test_wide_margin_no_cross_modal_conflict_does_not_escalate(self):
        hyps = [
            Hypothesis("A", 0.90, ["CorrelationResult.driver_a", "source_a"], []),
            Hypothesis("B", 0.30, ["CorrelationResult.driver_b", "source_b"], []),
        ]
        correlation = CorrelationResult("a1", [
            StructuredDriver("driver_a", "x", "shap", 0.9, 1),
            StructuredDriver("driver_b", "y", "shap", 0.2, 2),
        ])
        evidence = RetrievedEvidence("a1", [
            EvidenceSource("source_a", "t", "s", "P1", "2026-01-01", 0.95, 1),
            EvidenceSource("source_b", "t", "s", "P2", "2026-01-01", 0.40, 2),
        ])
        self.assertFalse(detect_disagreement(hyps, correlation, evidence))

    def test_cross_modal_conflict_escalates_despite_wide_margin(self):
        # Top structured driver (driver_a, |0.90|) is cited only by hypothesis A.
        # Top evidence source (source_x, relevance 0.95) is cited only by hypothesis B.
        # Structured and unstructured evidence point at *different* hypotheses, so this
        # should escalate even though A's confidence comfortably beats B's.
        hyps = [
            Hypothesis("A", 0.875, ["CorrelationResult.driver_a", "source_y"], []),
            Hypothesis("B", 0.525, ["CorrelationResult.driver_b", "source_x"], []),
        ]
        correlation = CorrelationResult("a1", [
            StructuredDriver("driver_a", "x", "shap", 0.90, 1),
            StructuredDriver("driver_b", "y", "shap", 0.20, 2),
        ])
        evidence = RetrievedEvidence("a1", [
            EvidenceSource("source_x", "t", "s", "P1", "2026-01-01", 0.95, 1),
            EvidenceSource("source_y", "t", "s", "P2", "2026-01-01", 0.40, 2),
        ])
        self.assertTrue(detect_disagreement(hyps, correlation, evidence))


class TestEndToEnd(unittest.TestCase):
    def test_easy_case_does_not_escalate(self):
        anomaly, correlation, evidence = easy_case()
        story = synthesize(anomaly, correlation, evidence, MockLLMClient(EASY_LLM_RESPONSE))
        self.assertFalse(story.escalate_flag)
        self.assertIn("price increase", story.hypotheses[0].cause.lower())
        self.assertGreater(story.hypotheses[0].confidence, story.hypotheses[1].confidence)
        self.assertEqual(story.overall_confidence, story.hypotheses[0].confidence)

    def test_hard_case_escalates(self):
        anomaly, correlation, evidence = hard_case()
        story = synthesize(anomaly, correlation, evidence, MockLLMClient(HARD_LLM_RESPONSE))
        self.assertTrue(story.escalate_flag)
        self.assertEqual(len(story.hypotheses), 2)

    def test_hypothesis_with_hallucinated_citation_only_is_dropped(self):
        anomaly, correlation, evidence = easy_case()
        bad_response = {
            "explanation": "test",
            "hypotheses": [
                {
                    "cause": "Made up cause with no real citation",
                    "citations": ["totally_fabricated_source_id"],
                    "actions": ["n/a"],
                },
                EASY_LLM_RESPONSE["hypotheses"][0],
            ],
        }
        story = synthesize(anomaly, correlation, evidence, MockLLMClient(bad_response))
        causes = [h.cause for h in story.hypotheses]
        self.assertNotIn("Made up cause with no real citation", causes)
        self.assertEqual(len(story.hypotheses), 1)


if __name__ == "__main__":
    unittest.main()
