"""
Task 5 process step 1: build the retrieval query from the anomaly
description + top drivers from Task 4, e.g.

  "EU-West weekly revenue decline Northwind Retail price cut
   EU-West logistics disruption July 2026"
"""
from __future__ import annotations

from typing import List

from schemas import AnomalyEvent, CorrelationResult


def build_query(anomaly: AnomalyEvent, correlation: CorrelationResult, max_drivers: int = 3) -> str:
    sign = "decline" if anomaly.direction == "down" else "increase"
    month_year = anomaly.window_start.strftime("%B %Y")

    top_drivers = sorted(
        correlation.top_drivers, key=lambda d: d.correlation_strength, reverse=True
    )[:max_drivers]
    driver_terms = [d.name for d in top_drivers]

    parts = [anomaly.region, anomaly.metric.replace("_", " "), sign, *driver_terms, month_year]
    return " ".join(parts)


def competitor_entity_terms(correlation: CorrelationResult) -> List[str]:
    """Named entities to run through the exact-match BM25 pass (process step 3)."""
    return correlation.competitor_entities()
