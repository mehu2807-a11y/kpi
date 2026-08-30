"""
peer_benchmarking.py — relative/peer benchmarking.

Compares a flagged region's metric movement against all peer regions
in the same time window. A drop that's happening everywhere is a
market-wide story; a drop in one region only is a local one.

All logic deterministic: z-score of this region's residual relative
to the cross-region distribution.
"""
from dataclasses import dataclass
from typing import Dict
import pandas as pd
import numpy as np

@dataclass
class PeerBenchmark:
    primary_region: str
    metric: str
    date: str
    this_residual: float
    peer_median: float
    peer_std: float
    z_score: float
    classification: str
    peer_residuals: Dict[str, float]
    analysis_method: str = "deterministic_z_score"

def benchmark(
    gate_record: dict,              
    metrics_df: pd.DataFrame,       
    window_days: int = 7,           
    history_window: int = 30,       
    regional_z_threshold: float = 1.5,
    outlier_z_threshold: float = 2.5,
) -> PeerBenchmark:
    metric = gate_record.get('metric_name', gate_record.get('metric'))
    primary_region = gate_record.get('region')
    primary_date_str = gate_record.get('date')
    primary_date = pd.Timestamp(primary_date_str)
    
    start_hist = primary_date - pd.Timedelta(days=window_days + history_window)
    end_window = primary_date + pd.Timedelta(days=window_days)
    
    df = metrics_df.copy()
    df['date_dt'] = pd.to_datetime(df['date'])
    
    metric_df = df[df.get('metric_name', df.columns[0] if 'metric_name' not in df.columns else df['metric_name']) == metric].copy()
    
    regions = metric_df['region'].unique()
    
    residuals = {}
    for r in regions:
        r_df = metric_df[metric_df['region'] == r].sort_values('date_dt')
        hist_df = r_df[(r_df['date_dt'] >= start_hist) & (r_df['date_dt'] < primary_date - pd.Timedelta(days=window_days))]
        window_df = r_df[(r_df['date_dt'] >= primary_date - pd.Timedelta(days=window_days)) & (r_df['date_dt'] <= end_window)]
        
        if hist_df.empty or window_df.empty:
            continue
            
        mean_val = hist_df['value'].mean()
        std_val = hist_df['value'].std()
        if pd.isna(std_val) or std_val == 0:
            std_val = 1.0
            
        window_z = (window_df['value'] - mean_val) / std_val
        residuals[r] = window_z.mean()
        
    if len(residuals) < 2 or primary_region not in residuals:
        return PeerBenchmark(
            primary_region=primary_region,
            metric=metric,
            date=primary_date_str,
            this_residual=residuals.get(primary_region, 0.0),
            peer_median=0.0,
            peer_std=0.0,
            z_score=0.0,
            classification="insufficient_peers",
            peer_residuals=residuals
        )
        
    this_residual = residuals[primary_region]
    all_res = list(residuals.values())
    peer_median = float(np.median(all_res))
    peer_std = float(np.std(all_res))
    if peer_std == 0:
        peer_std = 1.0
        
    z_score = (this_residual - peer_median) / peer_std
    
    abs_z = abs(z_score)
    if abs_z < regional_z_threshold:
        classification = "market_wide"
    elif abs_z < outlier_z_threshold:
        classification = "regional"
    else:
        classification = "outlier"
        
    return PeerBenchmark(
        primary_region=primary_region,
        metric=metric,
        date=primary_date_str,
        this_residual=float(this_residual),
        peer_median=peer_median,
        peer_std=peer_std,
        z_score=float(z_score),
        classification=classification,
        peer_residuals=residuals
    )

if __name__ == '__main__':
    import pandas as pd
    import numpy as np
    rng = np.random.default_rng(0)
    dates = pd.date_range('2026-01-01', periods=50, freq='D')
    rows = []
    for d in dates:
        t = (d - dates[0]).days
        for region, shock in [('Region X', 0.5 if t >= 43 else 1.0),
                               ('Region Y', 1.0), ('Region Z', 1.0)]:
            rows.append({'date': d.date().isoformat(), 'region': region,
                         'metric_name': 'revenue', 'product': 'Product A',
                         'value': float(5000 * shock + rng.normal(0, 50))})
    df = pd.DataFrame(rows)
    gate_record = {'metric_name': 'revenue', 'region': 'Region X', 'date': '2026-02-13'}
    result = benchmark(gate_record, df)
    print(f'Classification: {result.classification}')
    print(f'Z-score: {result.z_score:.2f}')
    print(f'Peer residuals: { {k: round(v, 2) for k, v in result.peer_residuals.items()} }')
