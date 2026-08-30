import os
import re

def write_file(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

# 1. data_quality_gate.py
dq_content = '''"""
data_quality_gate.py — runs BEFORE Task 3's run_gate().

Checks performed (all deterministic, no LLM):
  1. Missing days: gap in date sequence > max_gap_days
  2. Duplicate rows: same (date, region, metric) > 1 row  
  3. Stale feed: latest record is > max_staleness_days old
  4. Flat-line: last N values all identical (silent freeze)
  5. Implausible value: value outside [0, 10 * rolling_mean]

Returns DataQualityReport. If report.skipped_gate=True, orchestrator
should short-circuit before Task 3 and log the data issue.
"""
from dataclasses import dataclass
from typing import List
from datetime import datetime

@dataclass
class DataQualityIssue:
    check_name: str
    severity: str
    detail: str

@dataclass
class DataQualityReport:
    passed: bool
    skipped_gate: bool
    issues: List[DataQualityIssue]
    series_length: int
    latest_date: str
    staleness_days: int

@dataclass
class DataQualityConfig:
    max_gap_days: int = 1
    max_staleness_days: int = 3
    flatline_window: int = 5
    implausible_multiplier: float = 10.0
    min_series_length: int = 7

def check_series(dates: list[str], values: list[float], metric: str, region: str,
                 config: DataQualityConfig = None, as_of_date: str = None) -> DataQualityReport:
    if config is None:
        config = DataQualityConfig()
    if as_of_date is None:
        as_of_date = datetime.now().date().isoformat()
    
    issues = []
    
    if not dates:
        issues.append(DataQualityIssue("empty_series", "error", "No data provided"))
        return DataQualityReport(passed=False, skipped_gate=True, issues=issues, series_length=0, latest_date=as_of_date, staleness_days=0)
    
    # Missing days & duplicates
    parsed_dates = [datetime.fromisoformat(d).date() for d in dates]
    for i in range(1, len(parsed_dates)):
        diff = (parsed_dates[i] - parsed_dates[i-1]).days
        if diff == 0:
            issues.append(DataQualityIssue("duplicate_rows", "error", f"Duplicate date found: {dates[i]}"))
        elif diff > config.max_gap_days:
            issues.append(DataQualityIssue("missing_days", "error", f"Gap of {diff} days ending at {dates[i]}"))
            
    # Staleness
    latest = parsed_dates[-1]
    as_of = datetime.fromisoformat(as_of_date).date()
    staleness = (as_of - latest).days
    if staleness > config.max_staleness_days:
        issues.append(DataQualityIssue("stale_feed", "error", f"Latest data is {staleness} days old"))
        
    # Flat-line
    if len(values) >= config.flatline_window:
        last_n = values[-config.flatline_window:]
        if max(last_n) - min(last_n) < 1e-9:
            issues.append(DataQualityIssue("flatline", "error", f"Last {config.flatline_window} values are identical"))
            
    # Implausible value
    if len(values) >= config.min_series_length:
        first_80_idx = max(1, int(len(values) * 0.8))
        rolling_mean = sum(values[:first_80_idx]) / first_80_idx
        for i, val in enumerate(values):
            if val < 0 or val > config.implausible_multiplier * rolling_mean:
                issues.append(DataQualityIssue("implausible_value", "warning", f"Value {val} at index {i} is outside plausibility range"))
                break

    skipped_gate = any(i.severity == 'error' for i in issues)
    passed = not skipped_gate
    
    return DataQualityReport(passed=passed, skipped_gate=skipped_gate, issues=issues, series_length=len(dates), latest_date=dates[-1], staleness_days=staleness)

if __name__ == '__main__':
    from datetime import date, timedelta
    import json
    
    dates = [(date(2026,1,1) + timedelta(days=i)).isoformat() for i in range(30)]
    values = [100.0 + i*0.5 for i in range(30)]
    report = check_series(dates, values, 'revenue', 'Region X')
    
    print(json.dumps({'passed': report.passed, 'issues': [{'check': i.check_name, 'severity': i.severity} for i in report.issues]}, indent=2))
'''
write_file('d:/project/data_quality_gate.py', dq_content)

# 2. cohort_drilldown.py
cohort_content = '''"""
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
'''
write_file('d:/project/cohort_drilldown.py', cohort_content)

# 3. cross_kpi_correlation.py
cross_kpi_content = '''"""
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
'''
write_file('d:/project/cross_kpi_correlation.py', cross_kpi_content)

# 4. early_warning.py
early_warning_content = '''"""
early_warning.py — leading-indicator / early-warning layer.

Watches the RATE OF CHANGE of severity scores across rolling windows,
not just hard thresholds. Flags "trending toward anomaly" 1-2 days
before Task 3 formally confirms one.

All logic is deterministic: linear regression slope over trailing
severity scores.
"""
from dataclasses import dataclass
from typing import List
import numpy as np

@dataclass
class EarlyWarningConfig:
    slope_threshold: float = 0.05
    severity_floor: float = 0.25
    slope_window_days: int = 5
    severity_threshold: float = 0.50

@dataclass
class EarlyWarning:
    metric: str
    region: str
    current_severity: float
    slope: float
    days_to_likely_anomaly: float
    confidence: str
    triggered_at: str

def check_severity_trend(
    metric: str,
    region: str,
    severity_history: list[float],   
    dates: list[str],                
    config: EarlyWarningConfig = None,
) -> EarlyWarning | None:
    if config is None:
        config = EarlyWarningConfig()
        
    if len(severity_history) < config.slope_window_days:
        return None
        
    recent_sev = severity_history[-config.slope_window_days:]
    current_severity = recent_sev[-1]
    
    if current_severity >= config.severity_threshold:
        return None
    if current_severity < config.severity_floor:
        return None
        
    x = np.arange(config.slope_window_days)
    y = np.array(recent_sev)
    slope, intercept = np.polyfit(x, y, 1)
    
    if slope < config.slope_threshold:
        return None
        
    days = (config.severity_threshold - current_severity) / slope
    
    if slope > 2 * config.slope_threshold and days < 2:
        confidence = "high"
    elif days < 4:
        confidence = "medium"
    else:
        confidence = "low"
        
    return EarlyWarning(
        metric=metric,
        region=region,
        current_severity=float(current_severity),
        slope=float(slope),
        days_to_likely_anomaly=float(days),
        confidence=confidence,
        triggered_at=dates[-1]
    )

def scan_all_regions(
    severity_histories: dict[tuple[str,str], list[float]],  
    dates_per_key: dict[tuple[str,str], list[str]],
    config: EarlyWarningConfig = None,
) -> list[EarlyWarning]:
    warnings = []
    for (metric, region), sev_hist in severity_histories.items():
        dates = dates_per_key.get((metric, region), [])
        if not dates:
            continue
        w = check_severity_trend(metric, region, sev_hist, dates, config)
        if w is not None:
            warnings.append(w)
    return warnings
'''
write_file('d:/project/early_warning.py', early_warning_content)

# 5. peer_benchmarking.py
peer_benchmark_content = '''"""
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
    pass
'''
write_file('d:/project/peer_benchmarking.py', peer_benchmark_content)

# 6. causal_graph.py
causal_content = '''"""
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
'''
write_file('d:/project/causal_graph.py', causal_content)

# 7. orchestrate.py
with open('d:/project/orchestrator/orchestrate.py', 'r', encoding='utf-8') as f:
    orch = f.read()

orch = orch.replace('''import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict
import time

import numpy as np
import pandas as pd''', '''import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict
import time

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from data_quality_gate import check_series as dq_check_series, DataQualityConfig
from cohort_drilldown import decompose as cohort_decompose
from cross_kpi_correlation import detect_cascade
from early_warning import scan_all_regions as ew_scan, EarlyWarningConfig
from peer_benchmarking import benchmark as peer_benchmark
from causal_graph import rank_drivers_by_causal_proximity''')

orch = orch.replace('''    error_stage: Optional[str] = None
    error_message: Optional[str] = None''', '''    error_stage: Optional[str] = None
    error_message: Optional[str] = None
    data_quality_report: Optional[object] = None     # DataQualityReport
    cohort_drilldown: Optional[object] = None        # CohortDrilldown
    cross_kpi_cascade: Optional[object] = None       # CrossKPICascade
    peer_benchmark: Optional[object] = None          # PeerBenchmark
    causal_rankings: Optional[list] = None           # list[CausalRanking]''')

orch = orch.replace('''        task4_drivers, task4_precedent = T4.correlate_drivers(t4_anomaly, region_wide, historical_log)
        result.task4_drivers = task4_drivers
        result.task4_precedent = task4_precedent''', '''        task4_drivers, task4_precedent = T4.correlate_drivers(t4_anomaly, region_wide, historical_log)
        result.task4_drivers = task4_drivers
        result.task4_precedent = task4_precedent

        # --- Causal Graph Re-ranking ---
        try:
            result.causal_rankings = rank_drivers_by_causal_proximity(
                task4_drivers, canonical.metric
            )
        except Exception:
            pass

        try:
            result.cohort_drilldown = cohort_decompose(record, metrics_table, dimension='product')
        except Exception:
            pass

        try:
            all_kpi_ids = [canonical.metric, 'revenue', 'units_sold', 'avg_price', 'marketing_spend', 'inventory_level']
            result.cross_kpi_cascade = detect_cascade(record, metrics_table, all_kpi_ids)
        except Exception:
            pass

        try:
            result.peer_benchmark = peer_benchmark(record, metrics_table)
        except Exception:
            pass''')

orch = orch.replace('''    record, internal = T3.run_gate(check, correlated_checks, history, gate_config, event_counter)''', '''    # --- Data Quality Gate (runs before Task 3) ---
    try:
        dates_list = list(metrics_table[
            (metrics_table['region'] == check.region) &
            (metrics_table.get('metric_name', metrics_table.columns[0]) == check.metric)
        ].sort_values('date')['date'].astype(str))
        values_list = list(metrics_table[
            (metrics_table['region'] == check.region) &
            (metrics_table.get('metric_name', metrics_table.columns[0]) == check.metric)
        ].sort_values('date')['value'].astype(float))
        dq_report = dq_check_series(dates_list, values_list, check.metric, check.region)
        if dq_report.skipped_gate:
            result = PipelineResult(gate_record={'metric': check.metric, 'region': check.region, 'date': check.date, 'verdict': 'data_quality_fail'}, verdict='data_quality_fail', stopped_at_gate=True)
            result.data_quality_report = dq_report
            return result
    except Exception:
        pass  # data quality gate is best-effort; never block the pipeline on its own failure

    record, internal = T3.run_gate(check, correlated_checks, history, gate_config, event_counter)''')

write_file('d:/project/orchestrator/orchestrate.py', orch)

# 8. kpi_contract.py
with open('d:/project/kpi_contract.py', 'r', encoding='utf-8') as f:
    kpi_lines = f.readlines()

new_kpi = []
for line in kpi_lines:
    if "lineage: List[str] = field(default_factory=list)" in line:
        new_kpi.append(line)
        new_kpi.append("    upstream_drivers: List[str] = field(default_factory=list)\n")
        new_kpi.append("    refresh_lag_hours: int = 24\n")
    elif 'kpi_id="revenue_total"' in line:
        new_kpi.append(line)
    elif 'tags=["revenue", "financial", "top-line"]' in line:
        new_kpi.append(line.replace(')', ',\n        upstream_drivers=["avg_price", "units_sold", "marketing_spend"],\n        refresh_lag_hours=24\n    )'))
    elif 'tags=["volume", "sales", "operational"]' in line:
        new_kpi.append(line.replace(')', ',\n        upstream_drivers=["avg_price", "inventory_level", "marketing_spend"],\n        refresh_lag_hours=24\n    )'))
    elif 'tags=["pricing", "financial", "margin"]' in line:
        new_kpi.append(line.replace(')', ',\n        upstream_drivers=[],\n        refresh_lag_hours=24\n    )'))
    elif 'tags=["marketing", "expense", "investment"]' in line:
        new_kpi.append(line.replace(')', ',\n        upstream_drivers=[],\n        refresh_lag_hours=168\n    )'))
    elif 'tags=["inventory", "operations", "supply-chain"]' in line:
        new_kpi.append(line.replace(')', ',\n        upstream_drivers=[],\n        refresh_lag_hours=24\n    )'))
    else:
        new_kpi.append(line)

write_file('d:/project/kpi_contract.py', "".join(new_kpi))
