"""
backtest_thresholds.py — systematic threshold calibration for Task 3.

Sweeps primary_threshold and secondary_threshold across a labeled
dataset to find the Pareto-optimal setting. Replaces the current
'start around 1.5-2x, tune from there' guidance with calibrated numbers.

Usage:
  python backtest_thresholds.py           # full sweep, may take ~2 min
  python backtest_thresholds.py --quick   # single default pair, for CI
  python backtest_thresholds.py --days 365  # use 1 year of history
"""

import argparse
import json
import sys
import time
from pathlib import Path
from itertools import product as iterproduct

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'task3'))

def evaluate_thresholds(
    df: pd.DataFrame,           # labeled dataset from generate_dataset()
    primary_threshold: float,
    secondary_threshold: float,
    metric: str = 'revenue',
    region: str = 'Region X',
) -> dict:
    """
    Runs Task 3's run_gate() across a labeled series with the given thresholds.
    Returns precision, recall, F1, and false alarm rate.
    
    True positives: verdict==anomaly AND is_true_anomaly==True
    False positives: verdict==anomaly AND is_true_anomaly==False  
    False negatives: verdict==noise AND is_true_anomaly==True
    True negatives: verdict==noise AND is_true_anomaly==False
    """
    from anomaly_gate import (
        GateConfig, EventCounter, RegionHistory, MetricCheck, run_gate
    )
    
    series = df[
        (df['region'] == region) &
        (df['metric'] == metric)
    ].sort_values('date').reset_index(drop=True)
    
    if len(series) == 0:
        return {'error': 'no_data'}
    
    config = GateConfig(
        primary_threshold=primary_threshold,
        secondary_threshold=secondary_threshold,
    )
    history = RegionHistory()
    counter = EventCounter()
    
    tp = fp = fn = tn = 0
    
    # Get correlated metrics for the same region
    other_metrics = df[
        (df['region'] == region) &
        (df['metric'] != metric)
    ]
    
    for _, row in series.iterrows():
        date_str = row['date']
        correlated = [
            MetricCheck(
                date=date_str, region=region, metric=m_row['metric'],
                actual_value=float(m_row['actual_value']),
                expected_value=float(m_row['expected_value']),
                lower_bound=float(m_row['lower_bound']),
                upper_bound=float(m_row['upper_bound']),
            )
            for _, m_row in other_metrics[other_metrics['date'] == date_str].iterrows()
        ]
        
        check = MetricCheck(
            date=date_str, region=region, metric=metric,
            actual_value=float(row['actual_value']),
            expected_value=float(row['expected_value']),
            lower_bound=float(row['lower_bound']),
            upper_bound=float(row['upper_bound']),
        )
        
        try:
            record, internal = run_gate(check, correlated, history, config, counter)
            history.push(internal)
        except Exception:
            history.push(type('FakeInternal', (), {'metric': metric, 'region': region, 'flagged_today': False, 'residual': 0.0, 'correlated_residuals': {}})())
            continue
        
        predicted_anomaly = record['verdict'] == 'anomaly'
        true_anomaly = bool(row['is_true_anomaly'])
        
        if predicted_anomaly and true_anomaly:     tp += 1
        elif predicted_anomaly and not true_anomaly: fp += 1
        elif not predicted_anomaly and true_anomaly:  fn += 1
        else:                                          tn += 1
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    far       = fp / (fp + tn) if (fp + tn) > 0 else 0.0  # false alarm rate
    
    return {
        'primary_threshold': primary_threshold,
        'secondary_threshold': secondary_threshold,
        'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
        'precision': round(precision, 4),
        'recall': round(recall, 4),
        'f1': round(f1, 4),
        'false_alarm_rate': round(far, 4),
        'total_days': len(series),
        'true_anomaly_days': tp + fn,
    }

def run_sweep(
    df: pd.DataFrame,
    primary_thresholds: list[float] | None = None,
    secondary_thresholds: list[float] | None = None,
    metric: str = 'revenue',
    region: str = 'Region X',
) -> list[dict]:
    """
    Sweeps all (primary, secondary) threshold combinations.
    Returns list of result dicts, sorted by F1 descending.
    """
    p_grid = primary_thresholds or [1.00, 1.25, 1.50, 1.75, 2.00, 2.25, 2.50]
    s_grid = secondary_thresholds or [2.0, 2.5, 3.0, 3.5]
    
    results = []
    total = len(p_grid) * len(s_grid)
    for i, (pt, st) in enumerate(iterproduct(p_grid, s_grid)):
        r = evaluate_thresholds(df, pt, st, metric, region)
        if 'error' not in r:
            results.append(r)
        if (i + 1) % 5 == 0:
            print(f'  Progress: {i+1}/{total}', flush=True)
    
    return sorted(results, key=lambda x: x['f1'], reverse=True)

def find_pareto_optimal(results: list[dict]) -> list[dict]:
    """Returns Pareto-optimal configurations (high F1, low false-alarm rate)."""
    pareto = []
    for r in results:
        dominated = False
        for other in results:
            if other is r:
                continue
            if other['f1'] >= r['f1'] and other['false_alarm_rate'] <= r['false_alarm_rate']:
                dominated = True
                break
        if not dominated:
            pareto.append(r)
    return sorted(pareto, key=lambda x: x['f1'], reverse=True)

def main():
    parser = argparse.ArgumentParser(description='Backtest Task 3 thresholds')
    parser.add_argument('--quick', action='store_true', help='Single default config, for CI')
    parser.add_argument('--days', type=int, default=365, help='Days of synthetic history to generate')
    parser.add_argument('--output', type=str, default='threshold_report.json')
    parser.add_argument('--metric', type=str, default='revenue')
    parser.add_argument('--region', type=str, default='Region X')
    args = parser.parse_args()
    
    sys.path.insert(0, str(PROJECT_ROOT / 'task3'))
    from synthetic_data import generate_dataset
    
    print(f'Generating {args.days}-day labeled dataset...')
    t0 = time.time()
    df = generate_dataset(n_days=args.days)
    print(f'  Dataset: {df.shape[0]} rows, {df["is_true_anomaly"].sum()} true anomaly days, generated in {time.time()-t0:.1f}s')
    
    if args.quick:
        print('Running single threshold pair (quick mode)...')
        result = evaluate_thresholds(df, 1.75, 3.0, args.metric, args.region)
        print(json.dumps(result, indent=2))
        with open(args.output, 'w') as f:
            json.dump({'quick_mode': True, 'results': [result]}, f, indent=2)
        return
    
    print(f'Running full threshold sweep for metric={args.metric!r} region={args.region!r}...')
    t0 = time.time()
    results = run_sweep(df, metric=args.metric, region=args.region)
    print(f'  Sweep complete: {len(results)} configs in {time.time()-t0:.1f}s')
    
    pareto = find_pareto_optimal(results)
    
    print(f'\\nTop 5 by F1:')
    for r in results[:5]:
        print(f'  primary={r["primary_threshold"]} secondary={r["secondary_threshold"]} F1={r["f1"]:.3f} FAR={r["false_alarm_rate"]:.3f}')
    
    print(f'\\nPareto-optimal ({len(pareto)} configs):')
    for r in pareto[:3]:
        print(f'  primary={r["primary_threshold"]} secondary={r["secondary_threshold"]} F1={r["f1"]:.3f} FAR={r["false_alarm_rate"]:.3f}')
    
    if results:
        best = results[0]
        print(f'\\nRecommended thresholds: primary={best["primary_threshold"]}, secondary={best["secondary_threshold"]}')
        print(f'  F1={best["f1"]:.3f}, Precision={best["precision"]:.3f}, Recall={best["recall"]:.3f}, FAR={best["false_alarm_rate"]:.3f}')
    
    report = {
        'generated_at': pd.Timestamp.now().isoformat(),
        'dataset_days': args.days,
        'metric': args.metric,
        'region': args.region,
        'best_config': results[0] if results else None,
        'pareto_optimal': pareto,
        'all_results': results,
    }
    
    with open(args.output, 'w') as f:
        json.dump(report, f, indent=2)
    print(f'\\nFull report written to {args.output}')


if __name__ == '__main__':
    main()
