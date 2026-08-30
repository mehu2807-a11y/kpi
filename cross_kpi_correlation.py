"""
cross_kpi_correlation.py — scans all KPIs for concurrent anomalies.

After Task 3 confirms an anomaly on metric X, this module runs a
lightweight residual check on all OTHER tracked KPIs in the same window,
detecting cascade patterns (e.g., inventory drop → revenue drop 2d later).

All logic is deterministic (trailing mean/std baseline, z-score).
"""
from dataclasses import dataclass
from typing import List
import pandas as pd
import numpy as np

@dataclass
class ConcurrentAnomaly:
    kpi_id: str
    metric_name: str
    direction: str
    residual: float
    lag_days_to_primary: int
    severity: float

@dataclass
class CrossKPICascade:
    primary_kpi: str
    primary_date: str
    concurrent_anomalies: List[ConcurrentAnomaly]
    cascade_pattern: str
    analysis_method: str = "deterministic_z_score"

def detect_cascade(
    primary_gate_record: dict,          
    metrics_df: pd.DataFrame,           
    kpi_ids: list[str],                 
    window_days: int = 7,               
    residual_threshold: float = 1.5,    
    history_window: int = 30,           
) -> CrossKPICascade:
    primary_metric = primary_gate_record.get('metric_name', primary_gate_record.get('metric'))
    region = primary_gate_record.get('region')
    primary_date_str = primary_gate_record.get('date')
    primary_date = pd.Timestamp(primary_date_str)
    
    start_hist = primary_date - pd.Timedelta(days=window_days + history_window)
    end_window = primary_date + pd.Timedelta(days=window_days)
    
    df = metrics_df.copy()
    df['date_dt'] = pd.to_datetime(df['date'])
    
    anomalies = []
    
    for kpi in kpi_ids:
        if kpi == primary_metric:
            continue
            
        kpi_df = df[(df['region'] == region) & (df.get('metric_name', df.columns[0] if 'metric_name' not in df.columns else df['metric_name']) == kpi)].copy()
        if kpi_df.empty:
            continue
            
        kpi_df = kpi_df.sort_values('date_dt')
        
        hist_df = kpi_df[(kpi_df['date_dt'] >= start_hist) & (kpi_df['date_dt'] < primary_date - pd.Timedelta(days=window_days))]
        if hist_df.empty:
            continue
            
        mean_val = hist_df['value'].mean()
        std_val = hist_df['value'].std()
        if pd.isna(std_val) or std_val == 0:
            std_val = 1.0
            
        window_df = kpi_df[(kpi_df['date_dt'] >= primary_date - pd.Timedelta(days=window_days)) & (kpi_df['date_dt'] <= end_window)]
        if window_df.empty:
            continue
            
        window_df['z_score'] = (window_df['value'] - mean_val) / std_val
        
        max_abs_z = window_df['z_score'].abs().max()
        if max_abs_z > residual_threshold:
            max_idx = window_df['z_score'].abs().idxmax()
            best_row = window_df.loc[max_idx]
            z_val = best_row['z_score']
            lag = (best_row['date_dt'] - primary_date).days
            
            anomalies.append(ConcurrentAnomaly(
                kpi_id=kpi,
                metric_name=kpi,
                direction="above_expected" if z_val > 0 else "below_expected",
                residual=float(z_val),
                lag_days_to_primary=int(lag),
                severity=float(max_abs_z)
            ))
            
    if not anomalies:
        pattern = "none"
    elif any(a.lag_days_to_primary < -1 for a in anomalies):
        pattern = "leading"
    elif all(a.lag_days_to_primary > 1 for a in anomalies):
        pattern = "lagging"
    else:
        pattern = "simultaneous"
        
    return CrossKPICascade(
        primary_kpi=primary_metric,
        primary_date=primary_date_str,
        concurrent_anomalies=anomalies,
        cascade_pattern=pattern
    )

if __name__ == '__main__':
    import pandas as pd
    import numpy as np
    rng = np.random.default_rng(42)
    dates = pd.date_range('2026-01-01', periods=50, freq='D')
    rows = []
    for d in dates:
        t = (d - dates[0]).days
        inv_shock = 0.3 if t >= 40 else 1.0
        rev_shock = 0.5 if t >= 43 else 1.0  # revenue drops 3 days after inventory
        rows.append({'date': d.date().isoformat(), 'region': 'Region X', 'product': 'Product A',
                     'metric_name': 'revenue', 'value': float(5000 * rev_shock + rng.normal(0, 50))})
        rows.append({'date': d.date().isoformat(), 'region': 'Region X', 'product': 'Product A',
                     'metric_name': 'inventory_level', 'value': float(1200 * inv_shock + rng.normal(0, 20))})
    df = pd.DataFrame(rows)
    gate_record = {'metric_name': 'revenue', 'region': 'Region X', 'date': '2026-02-13', 'metric': 'revenue'}
    result = detect_cascade(gate_record, df, ['revenue', 'inventory_level'])
    print(f'Pattern: {result.cascade_pattern}, concurrent: {len(result.concurrent_anomalies)}')
