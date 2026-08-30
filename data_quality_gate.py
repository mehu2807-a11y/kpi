"""
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
