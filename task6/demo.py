"""
Runs Task 6's synthesis pipeline end to end against both brief-mandated mock
cases, using MockLLMClient so this needs no network access or API key.

    python demo.py

EASY_LLM_RESPONSE / HARD_LLM_RESPONSE below stand in for what
AnthropicLLMClient would return for mock_data.easy_case() / hard_case() --
they follow the exact JSON shape requested in llm_client.SYSTEM_PROMPT, and
are also reused by test_synthesize.py's end-to-end tests.
"""

import json
import sys
from pathlib import Path
from dataclasses import asdict

# Ensure the task6 directory is in sys.path to import the correct schemas
TASK6_DIR = Path(__file__).parent
if str(TASK6_DIR) not in sys.path:
    sys.path.insert(0, str(TASK6_DIR))

from mock_data import easy_case, hard_case
from llm_client import MockLLMClient
from synthesize import synthesize


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


def run(label: str, case_fn, canned_response: dict) -> None:
    anomaly, correlation, evidence = case_fn()
    client = MockLLMClient(canned_response)
    story = synthesize(anomaly, correlation, evidence, client)

    print(f"\n{'=' * 72}\n{label}\n{'=' * 72}")
    print(json.dumps(asdict(story), indent=2))


if __name__ == "__main__":
    run("EASY CASE — one dominant, well-corroborated cause", easy_case, EASY_LLM_RESPONSE)
    run("HARD CASE — two plausible causes, conflicting evidence", hard_case, HARD_LLM_RESPONSE)
