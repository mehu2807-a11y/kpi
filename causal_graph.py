"""
causal_graph.py — lightweight DAG-style causal chain layer.

Builds a directed causal graph from the KPI contract's upstream_drivers
field. Allows reasoning about chains of cause, not just pairwise
correlation: price → demand → revenue.

This is NOT a causal inference engine — it's a knowledge-graph-assisted
ranker that re-scores Task 4's flat correlation list by causal proximity.
"""
from dataclasses import dataclass
from typing import List

@dataclass
class CausalEdge:
    from_kpi: str
    to_kpi: str
    relationship: str

@dataclass
class CausalChain:
    target_kpi: str
    chain: List[str]
    depth: int
    description: str

@dataclass
class CausalRanking:
    driver_id: str
    original_rank: int
    causal_rank: int
    causal_depth: int
    chain: List[str]
    causal_boost: float

DEFAULT_CAUSAL_GRAPH = {
    "revenue": ["avg_price", "units_sold", "marketing_spend"],
    "units_sold": ["avg_price", "inventory_level", "marketing_spend"],
    "avg_price": [],
    "marketing_spend": [],
    "inventory_level": [],
    "revenue_total": ["avg_price", "units_sold", "marketing_spend"],
}

def trace_causal_chain(target_kpi: str, graph: dict = None, max_depth: int = 3) -> list[CausalChain]:
    if graph is None:
        graph = DEFAULT_CAUSAL_GRAPH
        
    chains = []
    
    def dfs(current_kpi, current_chain, depth):
        if depth > 0:
            chains.append(CausalChain(
                target_kpi=target_kpi,
                chain=list(current_chain),
                depth=depth,
                description=" -> ".join(reversed(current_chain))
            ))
            
        if depth == max_depth:
            return
            
        for driver in graph.get(current_kpi, []):
            if driver not in current_chain:
                current_chain.append(driver)
                dfs(driver, current_chain, depth + 1)
                current_chain.pop()
                
    dfs(target_kpi, [target_kpi], 0)
    return chains

def rank_drivers_by_causal_proximity(
    driver_results: list[dict],   
    target_kpi: str,
    graph: dict = None,
) -> list[CausalRanking]:
    if graph is None:
        graph = DEFAULT_CAUSAL_GRAPH
        
    chains = trace_causal_chain(target_kpi, graph)
    
    driver_depths = {}
    driver_chains = {}
    for chain in chains:
        driver = chain.chain[-1]
        if driver not in driver_depths or chain.depth < driver_depths[driver]:
            driver_depths[driver] = chain.depth
            driver_chains[driver] = chain.chain
            
    rankings = []
    for i, res in enumerate(driver_results):
        driver = res.get('driver')
        depth = driver_depths.get(driver, 999)
        if depth == 1:
            boost = 1.0
        elif depth == 2:
            boost = 0.6
        elif depth == 3:
            boost = 0.3
        else:
            boost = 0.1
            
        rankings.append({
            'driver_id': driver,
            'original_rank': i + 1,
            'causal_depth': depth if depth != 999 else -1,
            'chain': driver_chains.get(driver, []),
            'causal_boost': boost,
            'shap_contribution': res.get('shap_contribution', 0.0),
            'score': boost * res.get('shap_contribution', 0.0)
        })
        
    rankings.sort(key=lambda x: x['score'], reverse=True)
    
    final_rankings = []
    for i, r in enumerate(rankings):
        final_rankings.append(CausalRanking(
            driver_id=r['driver_id'],
            original_rank=r['original_rank'],
            causal_rank=i + 1,
            causal_depth=r['causal_depth'],
            chain=r['chain'],
            causal_boost=r['causal_boost']
        ))
        
    return final_rankings

if __name__ == '__main__':
    res = rank_drivers_by_causal_proximity([
        {'driver': 'inventory_level', 'shap_contribution': 0.8},
        {'driver': 'avg_price', 'shap_contribution': 0.5}
    ], 'revenue')
    for r in res:
        print(f"Driver: {r.driver_id}, Rank: {r.causal_rank}, Boost: {r.causal_boost}")
