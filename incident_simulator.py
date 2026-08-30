"""
incident_simulator.py — standalone CLI incident generator.

Generates complete demo scenarios on demand: synthetic metrics data,
ground-truth anomaly event, and LLM-generated or templated document
store (news/ticket copy).

Usage:
  python incident_simulator.py --scenario competitor_promo
  python incident_simulator.py --scenario supply_shock --region "Region Y" --llm mock
  python incident_simulator.py --scenario viral_spike --days 120 --output ./output
  python incident_simulator.py --list-scenarios

Outputs (all in --output directory):
  region_wide.csv          — Task 4's input shape
  document_store.json      — Task 5's input shape
  anomaly_ground_truth.json — ground truth for evaluation
  gate_baseline.csv        — Task 3's input shape
"""

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'tests'))

from scenarios import build_region_wide_and_gate_series, build_document_store

SCENARIOS = {
    'competitor_promo': {
        'description': 'Competitor runs a flash sale pulling share in overlapping markets',
        'driver': 'marketing_spend',  # marketing cut to match competitor prices
        'shock_pct': -0.18,
        'driver_step_pct': 0.0,
        'driver_lag_days': 5,
        'document_templates': [
            {
                'source': 'news',
                'raw_text': 'CompetitorCo launches aggressive summer promotion with 20% discount on core products in {region}, attracting price-sensitive customers away from established players.',
                'sentiment_score': -0.4,
                'entity_tags': ['CompetitorCo', 'promotion'],
            },
            {
                'source': 'support_ticket',
                'raw_text': 'Multiple customers in {region} citing competitor pricing as reason for switching. Ticket volume up 35% this week.',
                'sentiment_score': -0.6,
                'entity_tags': ['pricing', 'customer_churn'],
            },
        ]
    },
    'supply_shock': {
        'description': 'Warehouse stockout cuts fulfillable demand for a sustained period',
        'driver': 'inventory_level',
        'shock_pct': -0.25,
        'driver_step_pct': -0.70,
        'driver_lag_days': 3,
        'document_templates': [
            {
                'source': 'internal_ops',
                'raw_text': 'Critical SKU stockout in {region} warehouse. Fulfillment rate dropped to 30%. Restock ETA: 5-7 business days.',
                'sentiment_score': -0.7,
                'entity_tags': ['inventory', 'stockout', 'fulfillment'],
            },
            {
                'source': 'support_ticket',
                'raw_text': 'Order cancellations in {region} due to out-of-stock notifications. Customer satisfaction scores declining.',
                'sentiment_score': -0.5,
                'entity_tags': ['cancellation', 'out_of_stock'],
            },
        ]
    },
    'price_increase': {
        'description': 'A price increase on a flagship SKU reduces demand with a lag',
        'driver': 'avg_price',
        'shock_pct': -0.20,
        'driver_step_pct': 0.15,
        'driver_lag_days': 7,
        'document_templates': [
            {
                'source': 'internal_pricing',
                'raw_text': 'Pricing committee approved 15% list-price increase on Product A effective this week in {region}. Expected demand elasticity: -1.2.',
                'sentiment_score': 0.0,
                'entity_tags': ['pricing', 'Product A'],
            },
        ]
    },
    'marketing_cut': {
        'description': 'Budget cut eliminates paid media, demand erodes within weeks',
        'driver': 'marketing_spend',
        'shock_pct': -0.15,
        'driver_step_pct': 0.0,  # handled specially: spend cut to 35%
        'driver_lag_days': 10,
        'document_templates': [
            {
                'source': 'internal_finance',
                'raw_text': 'Q3 marketing budget reduced by 65% in {region} as part of cost optimization. Paid search and display campaigns paused.',
                'sentiment_score': -0.2,
                'entity_tags': ['marketing', 'budget_cut'],
            },
        ]
    },
    'viral_spike': {
        'description': 'Viral social media mention drives unexpected demand surge',
        'driver': 'marketing_spend',
        'shock_pct': 0.45,  # positive shock
        'driver_step_pct': 0.0,
        'driver_lag_days': 2,
        'document_templates': [
            {
                'source': 'social_media',
                'raw_text': 'Product went viral on social media in {region}. #ProductA trending with 50k+ mentions in 24 hours. Organic demand spike observed.',
                'sentiment_score': 0.8,
                'entity_tags': ['viral', 'social_media', 'Product A'],
            },
        ]
    },
    'new_product_launch': {
        'description': 'Newly launched product with only 30 days history — sparse history scenario',
        'driver': None,
        'shock_pct': -0.10,
        'driver_step_pct': 0.0,
        'driver_lag_days': 0,
        'sparse_history': True,
        'document_templates': [
            {
                'source': 'internal_launch',
                'raw_text': 'New product launched in {region} last month. Limited historical data available — baseline forecasts may be unreliable.',
                'sentiment_score': 0.3,
                'entity_tags': ['new_product', 'launch'],
            },
        ]
    },
}

def _generate_document_text(template: dict, region: str, scenario: str, llm: str = 'mock') -> dict:
    """
    Fills in {region} in template text and optionally uses an LLM to
    generate a varied, realistic version.
    
    llm='mock': just formats the template (instant, no setup needed)
    llm='ollama': calls Ollama to generate varied copy based on the template
    """
    base_text = template['raw_text'].replace('{region}', region)
    
    if llm == 'mock':
        return {**template, 'raw_text': base_text, 'region_tags': [region]}
    
    # Try LLM generation
    try:
        sys.path.insert(0, str(PROJECT_ROOT / 'task6'))
        from ollama_llm import OllamaLLMClient
        client = OllamaLLMClient()
        system = 'You are a business document writer. Write realistic, varied business documents.'
        user = f'Rewrite this business note in a more realistic, varied style (2-3 sentences): {base_text}'
        result = client.complete(system, user)  # plain text, not JSON
        if result and len(result) > 20:
            base_text = result.strip()
    except Exception as e:
        print(f'[llm] Falling back to template text: {e}')
    
    return {**template, 'raw_text': base_text, 'region_tags': [region]}

def generate_scenario(
    scenario_name: str,
    region: str = 'Region X',
    n_days: int = 110,
    output_dir: str = '.',
    llm: str = 'mock',
    seed: int = 42,
) -> dict:
    """
    Generate a full incident scenario and save all output files.
    Returns dict with paths to output files.
    """
    scenario = SCENARIOS[scenario_name]
    os.makedirs(output_dir, exist_ok=True)
    
    shock_start = n_days - 15
    
    region_wide, gate_baseline = build_region_wide_and_gate_series(
        region=region,
        n_days=n_days,
        shock_start_day=shock_start,
        shock_len_days=7,
        shock_pct=scenario['shock_pct'],
        driver=scenario['driver'],
        driver_lag_days=scenario.get('driver_lag_days', 7),
        driver_step_pct=scenario.get('driver_step_pct', 0.15),
        seed=seed,
    )
    
    # Generate document store
    doc_rows = []
    for i, tmpl in enumerate(scenario['document_templates']):
        shock_date = (region_wide['date'].iloc[shock_start]).date() if hasattr(region_wide['date'].iloc[0], 'date') else pd.Timestamp(region_wide['date'].iloc[shock_start]).date()
        doc_date = (shock_date - timedelta(days=i * 2)).isoformat()
        doc = _generate_document_text(tmpl, region, scenario_name, llm)
        doc_rows.append({
            'doc_id': f'{scenario_name}_{i:03d}',
            'date': doc_date,
            **doc,
        })
    
    doc_store = build_document_store(doc_rows)
    
    # Ground truth
    anomaly_date = region_wide['date'].iloc[shock_start]
    anomaly_date_str = anomaly_date.isoformat() if hasattr(anomaly_date, 'isoformat') else str(anomaly_date)[:10]
    ground_truth = {
        'scenario': scenario_name,
        'description': scenario['description'],
        'region': region,
        'metric': 'revenue',
        'anomaly_start_date': anomaly_date_str,
        'true_driver': scenario['driver'],
        'shock_pct': scenario['shock_pct'],
        'driver_lag_days': scenario.get('driver_lag_days', 7),
        'sparse_history': scenario.get('sparse_history', False),
    }
    
    # Save files
    paths = {}
    
    rw_path = os.path.join(output_dir, 'region_wide.csv')
    region_wide.to_csv(rw_path, index=False)
    paths['region_wide'] = rw_path
    
    gb_path = os.path.join(output_dir, 'gate_baseline.csv')
    gate_baseline.to_csv(gb_path, index=False)
    paths['gate_baseline'] = gb_path
    
    ds_path = os.path.join(output_dir, 'document_store.json')
    with open(ds_path, 'w') as f:
        json.dump(doc_store, f, indent=2)
    paths['document_store'] = ds_path
    
    gt_path = os.path.join(output_dir, 'anomaly_ground_truth.json')
    with open(gt_path, 'w') as f:
        json.dump(ground_truth, f, indent=2)
    paths['ground_truth'] = gt_path
    
    print(f'[incident_simulator] Generated scenario: {scenario_name!r}')
    print(f'  Region: {region}, Driver: {scenario["driver"]}, Shock: {scenario["shock_pct"]:+.0%}')
    for name, path in paths.items():
        print(f'  {name}: {path}')
    
    return {'scenario': scenario_name, 'paths': paths, 'ground_truth': ground_truth}

def main():
    parser = argparse.ArgumentParser(description='KPI Incident Simulator')
    parser.add_argument('--scenario', type=str, default='price_increase',
                        choices=list(SCENARIOS.keys()),
                        help='Scenario to simulate')
    parser.add_argument('--region', type=str, default='Region X')
    parser.add_argument('--days', type=int, default=110)
    parser.add_argument('--output', type=str, default='./incident_output')
    parser.add_argument('--llm', type=str, default='mock', choices=['mock', 'ollama'])
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--list-scenarios', action='store_true')
    parser.add_argument('--check', action='store_true', help='Dry run: generate but do not save')
    args = parser.parse_args()
    
    if args.list_scenarios:
        print('Available scenarios:')
        for name, s in SCENARIOS.items():
            print(f'  {name}: {s["description"]}')
        return
    
    if args.check:
        print(f'[check] Would generate: scenario={args.scenario!r}, region={args.region!r}, days={args.days}')
        return
    
    generate_scenario(
        scenario_name=args.scenario,
        region=args.region,
        n_days=args.days,
        output_dir=args.output,
        llm=args.llm,
        seed=args.seed,
    )

if __name__ == '__main__':
    main()
