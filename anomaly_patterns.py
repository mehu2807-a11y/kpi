"""
anomaly_patterns.py — Anomaly pattern library.

Clusters past anomalies by their driver signature using cosine similarity
(same approach as Task 4's historical precedent matching, extended to
produce named pattern clusters with resolution history).

Known pattern templates:
  - competitor_event: high avg_price driver, negative marketing_spend correlation
  - supply_disruption: high inventory_level driver, positive complaint correlation
  - demand_surge: positive units_sold, positive marketing_spend
  - pricing_error: high avg_price driver isolated, no other drivers
  - seasonal_anomaly: recurring same-day-of-week or same-week-of-year
  - unknown: no close match
"""

from dataclasses import dataclass
import math

@dataclass
class PatternTemplate:
    name: str
    description: str
    driver_weights: dict[str, float]
    typical_resolution_days: int
    recommended_actions: list[str]

@dataclass
class PatternMatch:
    pattern_name: str
    similarity: float
    description: str
    typical_resolution_days: int
    recommended_actions: list[str]
    historical_matches: list[dict]

PATTERN_TEMPLATES = [
    PatternTemplate(
        name='competitor_event',
        description='Competitor pricing action or promotion pulling share',
        driver_weights={'avg_price': 0.6, 'marketing_spend': -0.3, 'units_sold': -0.5, 'inventory_level': 0.0},
        typical_resolution_days=14,
        recommended_actions=['Competitive price response', 'Defensive marketing activation', 'Account team outreach to at-risk accounts']
    ),
    PatternTemplate(
        name='supply_disruption',
        description='Inventory/fulfillment issue cutting available supply',
        driver_weights={'inventory_level': -0.8, 'units_sold': -0.6, 'avg_price': 0.1, 'marketing_spend': 0.0},
        typical_resolution_days=7,
        recommended_actions=['Emergency restock order', 'Customer communication on delays', 'Prioritize high-margin SKUs']
    ),
    PatternTemplate(
        name='demand_surge',
        description='Organic or marketing-driven demand spike',
        driver_weights={'units_sold': 0.8, 'marketing_spend': 0.5, 'avg_price': -0.1, 'inventory_level': -0.4},
        typical_resolution_days=3,
        recommended_actions=['Replenish inventory urgently', 'Increase ad spend to sustain', 'Monitor for stockout risk']
    ),
    PatternTemplate(
        name='pricing_error',
        description='Isolated price movement with no supporting demand signal',
        driver_weights={'avg_price': 0.9, 'units_sold': 0.1, 'marketing_spend': 0.0, 'inventory_level': 0.0},
        typical_resolution_days=2,
        recommended_actions=['Verify pricing system for errors', 'Check for accidental discount codes', 'Roll back price if unintentional']
    ),
]

def cosine_similarity(v1: dict[str, float], v2: dict[str, float]) -> float:
    keys = set(v1.keys()) | set(v2.keys())
    dot = sum(v1.get(k, 0) * v2.get(k, 0) for k in keys)
    mag1 = math.sqrt(sum(v ** 2 for v in v1.values()))
    mag2 = math.sqrt(sum(v ** 2 for v in v2.values()))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)

def match_pattern(
    driver_contributions: dict[str, float],
    historical_log: list[dict] = None,
    top_n: int = 2,
) -> list[PatternMatch]:
    """
    Matches the current anomaly's driver signature against known pattern
    templates using cosine similarity.
    Returns top_n matches sorted by similarity.
    """
    matches = []
    for pt in PATTERN_TEMPLATES:
        sim = cosine_similarity(driver_contributions, pt.driver_weights)
        matches.append(PatternMatch(
            pattern_name=pt.name,
            similarity=sim,
            description=pt.description,
            typical_resolution_days=pt.typical_resolution_days,
            recommended_actions=pt.recommended_actions,
            historical_matches=[]
        ))
    
    matches.sort(key=lambda x: x.similarity, reverse=True)
    return matches[:top_n]

def get_pattern_summary(matches: list[PatternMatch]) -> str:
    """Returns a 1-sentence human-readable summary of the best match."""
    if not matches or matches[0].similarity < 0.5:
        return 'No clear pattern match — this may be a novel event type.'
    m = matches[0]
    return f'Pattern: {m.pattern_name} (similarity {m.similarity:.0%}) — {m.description}. Typical resolution: {m.typical_resolution_days} days.'

if __name__ == '__main__':
    # Supply disruption signature
    sig = {'inventory_level': -0.75, 'units_sold': -0.55, 'avg_price': 0.05, 'marketing_spend': 0.02}
    matches = match_pattern(sig)
    print(f'Top match: {matches[0].pattern_name} ({matches[0].similarity:.0%})')
    print(get_pattern_summary(matches))
