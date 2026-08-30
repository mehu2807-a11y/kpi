"""
Hand-crafted mock CorrelationResult / RetrievedEvidence, per the Task 6
brief's instruction to build these for a day-one start ahead of Task 4 / 5:

  - easy_case()  -- one dominant driver, corroborated by two independent
                    sources. Should NOT trigger escalation.
  - hard_case()  -- two structurally close drivers, each corroborated by a
                    single, conflicting source. SHOULD trigger escalation.

Both are consumed by demo.py and test_synthesize.py.
"""

import sys
from pathlib import Path

# Ensure the task6 directory is in sys.path to import the correct schemas
TASK6_DIR = Path(__file__).parent
if str(TASK6_DIR) not in sys.path:
    sys.path.insert(0, str(TASK6_DIR))

from schemas import (
    AnomalyEvent, StructuredDriver, CorrelationResult,
    EvidenceSource, RetrievedEvidence,
)


def easy_case():
    anomaly = AnomalyEvent(
        anomaly_id="anon-2026-07-12-region-x-revenue",
        metric_name="revenue",
        entity="Region X",
        direction="decrease",
        magnitude_pct=7.5,
        baseline_value=2_400_000,
        observed_value=2_220_000,
        window_start="2026-07-04",
        window_end="2026-07-10",
        detected_at="2026-07-11T06:00:00Z",
    )

    correlation = CorrelationResult(
        anomaly_id=anomaly.anomaly_id,
        drivers=[
            StructuredDriver(
                driver_id="avg_price",
                label="10% list-price increase on Product A, effective Jul 4",
                stat_type="correlation",
                value=-0.81,
                rank=1,
            ),
            StructuredDriver(
                driver_id="marketing_spend",
                label="Regional marketing spend, week over week",
                stat_type="correlation",
                value=0.11,
                rank=2,
            ),
        ],
    )

    evidence = RetrievedEvidence(
        anomaly_id=anomaly.anomaly_id,
        sources=[
            EvidenceSource(
                source_id="internal_00091",
                title="Weekly pricing change log",
                snippet=(
                    "Product A list price raised 10% in Region X effective "
                    "July 4, per pricing committee sign-off."
                ),
                publisher="Internal Pricing Ops",
                date="2026-07-04",
                relevance_score=0.95,
                rank=1,
            ),
            EvidenceSource(
                source_id="news_00231",
                title="Regional Business Journal notes retailer price move",
                snippet=(
                    "Regional Business Journal reported the price increase "
                    "and flagged early customer pushback on social media."
                ),
                publisher="Regional Business Journal",
                date="2026-07-06",
                relevance_score=0.83,
                rank=2,
            ),
            EvidenceSource(
                source_id="news_00255",
                title="CompetitorCo launches summer promotion",
                snippet=(
                    "CompetitorCo announced a limited-time discount in "
                    "overlapping markets starting July 3."
                ),
                publisher="TradePress Daily",
                date="2026-07-03",
                relevance_score=0.38,
                rank=3,
            ),
        ],
    )

    return anomaly, correlation, evidence


def hard_case():
    anomaly = AnomalyEvent(
        anomaly_id="anon-2026-06-20-region-y-signups",
        metric_name="signups",
        entity="Region Y",
        direction="decrease",
        magnitude_pct=12.0,
        baseline_value=18_400,
        observed_value=16_190,
        window_start="2026-06-13",
        window_end="2026-06-19",
        detected_at="2026-06-20T06:00:00Z",
    )

    correlation = CorrelationResult(
        anomaly_id=anomaly.anomaly_id,
        drivers=[
            StructuredDriver(
                driver_id="crash_rate",
                label="Mobile app crash rate up 3.2x week over week",
                stat_type="shap",
                value=0.54,
                rank=1,
            ),
            StructuredDriver(
                driver_id="marketing_spend_cut",
                label="Regional marketing spend cut 40% starting Jun 13",
                stat_type="shap",
                value=-0.49,
                rank=2,
            ),
        ],
    )

    evidence = RetrievedEvidence(
        anomaly_id=anomaly.anomaly_id,
        sources=[
            EvidenceSource(
                source_id="reviews_00114",
                title="App store review sentiment digest",
                snippet=(
                    "Spike in one-star reviews citing crashes on launch, "
                    "concentrated in Region Y, starting Jun 14."
                ),
                publisher="App Store Reviews Aggregator",
                date="2026-06-16",
                relevance_score=0.71,
                rank=1,
            ),
            EvidenceSource(
                source_id="internal_00147",
                title="Marketing budget reallocation memo",
                snippet=(
                    "Region Y paid acquisition spend cut 40% starting Jun 13 "
                    "to fund a Region Z launch."
                ),
                publisher="Internal Marketing Ops",
                date="2026-06-12",
                relevance_score=0.69,
                rank=2,
            ),
        ],
    )

    return anomaly, correlation, evidence
