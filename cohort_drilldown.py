"""
cohort_drilldown.py — decomposes a confirmed anomaly across cohort dimensions.

After Task 3 confirms an anomaly, automatically decomposes it across
product × channel × segment. Uses only deterministic arithmetic:
  contribution_pct = cohort_delta / total_delta
where cohort_delta = sum(actual - expected) for rows matching that cohort.

Turns "Region X is down" into
"Region X is down, entirely driven by Product A's enterprise channel."
"""
from dataclasses import dataclass
from typing import List
import pandas as pd

@dataclass
class CohortContribution:
    cohort_key: str
    cohort_value: str
    actual_sum: float
    expected_sum: float
    delta: float
    contribution_pct: float

@dataclass
class CohortDrilldown:
    dimension: str
    total_delta: float
    top_cohort: CohortContribution
    all_cohorts: List[CohortContribution]
    concentration_index: float
    analysis_method: str = "deterministic_arithmetic"

def decompose(
    anomaly_event: dict,
    metrics_df: pd.DataFrame,
    dimension: str = "product",
    window_days: int = 7,
) -> CohortDrilldown:
    if dimension not in metrics_df.columns:
        return CohortDrilldown(dimension=dimension, total_delta=0.0, top_cohort=None, all_cohorts=[], concentration_index=0.0)
        
    metric_name = anomaly_event.get('metric_name', anomaly_event.get('metric'))
    region = anomaly_event.get('region')
    anomaly_date = pd.Timestamp(anomaly_event.get('date'))
    start_date = anomaly_date - pd.Timedelta(days=window_days)
    end_date = anomaly_date + pd.Timedelta(days=window_days)
    
    df = metrics_df.copy()
    df['date_dt'] = pd.to_datetime(df['date'])
    
    mask = (
        (df['region'] == region) & 
        (df.get('metric_name', df.columns[0] if 'metric_name' not in df.columns else df['metric_name']) == metric_name) &
        (df['date_dt'] >= start_date) & 
        (df['date_dt'] <= end_date)
    )
    window_df = df[mask].copy()
    
    if window_df.empty:
        return CohortDrilldown(dimension=dimension, total_delta=0.0, top_cohort=None, all_cohorts=[], concentration_index=0.0)
        
    if 'expected_value' not in window_df.columns:
        window_df = window_df.sort_values('date_dt')
        window_df['expected_value'] = window_df.groupby(dimension)['value'].transform(lambda x: x.rolling(14, min_periods=1).mean().shift(1).fillna(x))
        
    window_df['delta'] = window_df['value'] - window_df['expected_value']
    
    cohort_sums = window_df.groupby(dimension).agg(
        actual_sum=('value', 'sum'),
        expected_sum=('expected_value', 'sum'),
        delta=('delta', 'sum')
    ).reset_index()
    
    total_delta = cohort_sums['delta'].sum()
    
    cohorts = []
    for _, row in cohort_sums.iterrows():
        pct = row['delta'] / total_delta if total_delta != 0 else 0.0
        cohorts.append(CohortContribution(
            cohort_key=dimension,
            cohort_value=str(row[dimension]),
            actual_sum=float(row['actual_sum']),
            expected_sum=float(row['expected_sum']),
            delta=float(row['delta']),
            contribution_pct=float(pct)
        ))
        
    cohorts.sort(key=lambda x: abs(x.delta), reverse=True)
    
    if total_delta == 0:
        hhi = 0.0
    else:
        hhi = sum((c.contribution_pct * 100) ** 2 for c in cohorts) / 10000.0
        
    top = cohorts[0] if cohorts else None
    
    return CohortDrilldown(
        dimension=dimension,
        total_delta=float(total_delta),
        top_cohort=top,
        all_cohorts=cohorts,
        concentration_index=float(hhi)
    )

if __name__ == '__main__':
    import pandas as pd
    from datetime import date, timedelta
    dates = pd.date_range('2026-07-01', periods=20, freq='D')
    rows = []
    for d in dates:
        for prod in ['Product A', 'Product B']:
            mult = 0.5 if prod == 'Product A' and d >= pd.Timestamp('2026-07-15') else 1.0
            rows.append({'date': d.date().isoformat(), 'region': 'Region X', 'product': prod,
                        'metric_name': 'revenue', 'value': 1000 * mult, 'expected_value': 1000.0})
    df = pd.DataFrame(rows)
    gate_record = {'metric_name': 'revenue', 'region': 'Region X', 'date': '2026-07-17'}
    drill = decompose(gate_record, df, dimension='product')
    if drill.top_cohort:
        print(f'Top cohort: {drill.top_cohort.cohort_value} ({drill.top_cohort.contribution_pct:.0%})')
