"""
whatif_simulator.py — Counterfactual / What-If analysis.

Answers: "If avg_price hadn't increased by 15%, how much of the
revenue drop would be explained?"

Uses the causal graph (causal_graph.py) to trace which fraction of
the total observed delta is attributable to a specific driver change.
All deterministic arithmetic — no LLM.

Also supports forward simulation: "If I cut price by 5%, what happens
to revenue in the next 7 days?"
"""

from dataclasses import dataclass

@dataclass
class WhatIfResult:
    scenario: str
    driver: str
    driver_counterfactual_pct: float
    original_delta_pct: float
    explained_delta_pct: float
    unexplained_delta_pct: float
    causal_chain: list[str]
    method: str = "causal_arithmetic"

@dataclass
class ForwardSimResult:
    driver: str
    driver_change_pct: float
    predicted_kpi_change_pct: float
    predicted_kpi_value: float
    current_kpi_value: float
    elasticity_used: float
    causal_chain: list[str]
    confidence: str

DEFAULT_ELASTICITIES = {
    ('avg_price', 'revenue'): -1.2,      # 10% price up → 12% revenue change (non-linear via units)
    ('avg_price', 'units_sold'): -1.5,   # price elasticity of demand
    ('marketing_spend', 'revenue'): 0.4, # marketing ROI
    ('marketing_spend', 'units_sold'): 0.5,
    ('inventory_level', 'units_sold'): 0.3,  # stockout effect
    ('inventory_level', 'revenue'): 0.3,
    ('units_sold', 'revenue'): 1.0,
}

def explain_counterfactual(
    driver: str,
    driver_actual_change_pct: float,
    target_kpi: str,
    total_observed_delta_pct: float,
) -> WhatIfResult:
    """How much of the observed delta does this driver explain?"""
    # Normalize KPI id aliases (e.g. revenue_total → revenue)
    _KPI_ALIAS = {'revenue_total': 'revenue', 'units_sold': 'units_sold',
                  'avg_price': 'avg_price', 'marketing_spend': 'marketing_spend',
                  'inventory_level': 'inventory_level'}
    target_norm = _KPI_ALIAS.get(target_kpi, target_kpi)
    elasticity = DEFAULT_ELASTICITIES.get((driver, target_norm),
                 DEFAULT_ELASTICITIES.get((driver, target_kpi), 0.0))
    explained_delta = driver_actual_change_pct * elasticity
    unexplained = total_observed_delta_pct - explained_delta
    
    return WhatIfResult(
        scenario=f"Counterfactual: what if {driver} had not changed by {driver_actual_change_pct:.1%}?",
        driver=driver,
        driver_counterfactual_pct=driver_actual_change_pct,
        original_delta_pct=total_observed_delta_pct,
        explained_delta_pct=explained_delta,
        unexplained_delta_pct=unexplained,
        causal_chain=[f"{driver} → {target_kpi} (elasticity {elasticity})"]
    )

def simulate_forward(
    driver: str,
    driver_change_pct: float,
    target_kpi: str,
    current_kpi_value: float,
    elasticities: dict = None,
) -> ForwardSimResult:
    """If I change this driver by X%, what happens to the KPI?"""
    if elasticities is None:
        elasticities = DEFAULT_ELASTICITIES
        
    _KPI_ALIAS = {'revenue_total': 'revenue', 'units_sold': 'units_sold',
                  'avg_price': 'avg_price', 'marketing_spend': 'marketing_spend',
                  'inventory_level': 'inventory_level'}
    target_norm = _KPI_ALIAS.get(target_kpi, target_kpi)
    elasticity = elasticities.get((driver, target_norm),
                 elasticities.get((driver, target_kpi), 0.0))
    predicted_change = driver_change_pct * elasticity
    new_value = current_kpi_value * (1 + predicted_change)
    
    return ForwardSimResult(
        driver=driver,
        driver_change_pct=driver_change_pct,
        predicted_kpi_change_pct=predicted_change,
        predicted_kpi_value=new_value,
        current_kpi_value=current_kpi_value,
        elasticity_used=elasticity,
        causal_chain=[f"{driver} → {target_kpi} (elasticity {elasticity})"],
        confidence="Medium"
    )

if __name__ == '__main__':
    r = explain_counterfactual('avg_price', +0.15, 'revenue', -0.20)
    print(f'Price increase explains {r.explained_delta_pct:.0%} of revenue drop')
    s = simulate_forward('avg_price', -0.05, 'revenue', current_kpi_value=85000)
    print(f'5% price cut -> revenue changes {s.predicted_kpi_change_pct:+.1%} to {s.predicted_kpi_value:.0f}')
