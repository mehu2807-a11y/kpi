"""
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
