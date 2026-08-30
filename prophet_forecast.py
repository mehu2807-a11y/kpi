"""
prophet_forecast.py — Real Prophet-based baseline forecast.

Drops in as a replacement for the trailing-mean stand-in used in
kpis_endpoint.py._trailing_baseline(). Uses Facebook Prophet for
proper trend + seasonality decomposition.

Performance: Prophet fits take ~20-40s each. Results are cached to disk
(prophet_cache.json, TTL=6h) so subsequent /kpis calls are instant.
A background thread precomputes caches on server startup.

Falls back gracefully to trailing mean if Prophet unavailable or < 60 days.
"""

from __future__ import annotations
import hashlib
import json
import math
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

try:
    from prophet import Prophet
    import pandas as pd
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False

# ── Cache ──────────────────────────────────────────────────────────────────
_CACHE_FILE = Path(__file__).parent / "prophet_cache.json"
_CACHE_TTL_SECONDS = 6 * 3600  # 6 hours
_cache_lock = threading.Lock()


def _cache_key(dates: list[str], horizon_days: int) -> str:
    sig = f"{dates[0]}|{dates[-1]}|{len(dates)}|{horizon_days}"
    return hashlib.md5(sig.encode()).hexdigest()


def _load_cache() -> dict:
    try:
        if _CACHE_FILE.exists():
            with open(_CACHE_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_cache(cache: dict):
    try:
        with open(_CACHE_FILE, "w") as f:
            json.dump(cache, f)
    except Exception:
        pass


def _get_cached(key: str) -> dict | None:
    with _cache_lock:
        cache = _load_cache()
        entry = cache.get(key)
        if entry and time.time() - entry.get("ts", 0) < _CACHE_TTL_SECONDS:
            return entry["result"]
    return None


def _set_cached(key: str, result: dict):
    with _cache_lock:
        cache = _load_cache()
        cache[key] = {"ts": time.time(), "result": result}
        _save_cache(cache)


# ── Core dataclass ─────────────────────────────────────────────────────────
@dataclass
class ProphetForecastResult:
    expected: float
    lower: float
    upper: float
    trend: float
    seasonal: float
    method: str


# ── Trailing mean fallback ─────────────────────────────────────────────────
def _trailing_mean(values: list[float]) -> ProphetForecastResult:
    recent = values[-30:] if len(values) >= 30 else values
    if not recent:
        return ProphetForecastResult(0.0, 0.0, 0.0, 0.0, 0.0, "trailing_mean_fallback")
    mean = sum(recent) / len(recent)
    std = math.sqrt(sum((v - mean) ** 2 for v in recent) / max(len(recent) - 1, 1))
    return ProphetForecastResult(
        expected=mean, lower=mean - 2 * std, upper=mean + 2 * std,
        trend=mean, seasonal=0.0, method="trailing_mean_fallback"
    )


# ── Main function ──────────────────────────────────────────────────────────
def forecast_next(
    dates: list[str],
    values: list[float],
    horizon_days: int = 1,
    interval_width: float = 0.80,
    use_cache: bool = True,
    sync_fit: bool = False,
) -> ProphetForecastResult:
    """
    Fit Prophet on (dates, values) and return the point forecast + CI
    for `horizon_days` ahead. Results are cached to disk (TTL=6h).

    If sync_fit=False and cache misses, falls back to trailing mean instantly 
    to avoid blocking web requests. Background thread uses sync_fit=True.
    """
    if not PROPHET_AVAILABLE or len(dates) < 60:
        return _trailing_mean(values)

    key = _cache_key(dates, horizon_days)
    if use_cache:
        cached = _get_cached(key)
        if cached:
            return ProphetForecastResult(**cached)

    if not sync_fit:
        return _trailing_mean(values)

    try:
        df = pd.DataFrame({"ds": pd.to_datetime(dates), "y": values})
        yearly = len(dates) >= 365
        m = Prophet(
            interval_width=interval_width,
            daily_seasonality=False,
            weekly_seasonality=True,
            yearly_seasonality=yearly,
            # Quiet Stan output
            stan_backend="CMDSTANPY",
        )
        import logging
        logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
        m.fit(df)
        future = m.make_future_dataframe(periods=horizon_days)
        forecast = m.predict(future)
        last = forecast.iloc[-1]
        result = ProphetForecastResult(
            expected=float(last["yhat"]),
            lower=float(last["yhat_lower"]),
            upper=float(last["yhat_upper"]),
            trend=float(last["trend"]),
            seasonal=float(last.get("additive_terms", 0.0)),
            method="prophet",
        )
        if use_cache:
            _set_cached(key, {
                "expected": result.expected, "lower": result.lower,
                "upper": result.upper, "trend": result.trend,
                "seasonal": result.seasonal, "method": result.method,
            })
        return result
    except Exception:
        return _trailing_mean(values)


def _fallback_forecast_series(dates: list[str], values: list[float], horizon_days: int) -> dict:
    from datetime import datetime, timedelta
    future_dates: list[str] = []
    if dates:
        last_dt = datetime.fromisoformat(dates[-1][:10])
        future_dates = [
            (last_dt + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(1, horizon_days + 1)
        ]
    all_dates = dates + future_dates
    m = sum(values) / len(values) if values else 0.0
    s = math.sqrt(sum((v - m) ** 2 for v in values) / max(len(values) - 1, 1))
    return {
        "dates": all_dates,
        "expected": [m] * len(all_dates),
        "lower": [m - 2 * s] * len(all_dates),
        "upper": [m + 2 * s] * len(all_dates),
        "trend": [m] * len(all_dates),
        "method": "trailing_mean_fallback",
    }

def get_forecast_series(
    dates: list[str],
    values: list[float],
    interval_width: float = 0.80,
    use_cache: bool = True,
    sync_fit: bool = False,
) -> dict:
    """
    Returns full in-sample + 7-day-ahead forecast as lists.
    Used by /kpis/<kpi_id>/history for sparkline enrichment.
    """
    horizon_days = 7
    if not PROPHET_AVAILABLE or len(dates) < 60:
        return _fallback_forecast_series(dates, values, horizon_days)

    key = _cache_key(dates, 1000 + horizon_days)  # distinct key from forecast_next
    if use_cache:
        cached = _get_cached(key)
        if cached:
            return cached

    if not sync_fit:
        return _fallback_forecast_series(dates, values, horizon_days)

    try:
        df = pd.DataFrame({"ds": pd.to_datetime(dates), "y": values})
        yearly = len(dates) >= 365
        m = Prophet(
            interval_width=interval_width,
            daily_seasonality=False,
            weekly_seasonality=True,
            yearly_seasonality=yearly,
        )
        import logging
        logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
        m.fit(df)
        future = m.make_future_dataframe(periods=horizon_days)
        forecast = m.predict(future)
        result = {
            "dates": forecast["ds"].dt.strftime("%Y-%m-%d").tolist(),
            "expected": [round(v, 2) for v in forecast["yhat"].tolist()],
            "lower": [round(v, 2) for v in forecast["yhat_lower"].tolist()],
            "upper": [round(v, 2) for v in forecast["yhat_upper"].tolist()],
            "trend": [round(v, 2) for v in forecast["trend"].tolist()],
            "method": "prophet",
        }
        if use_cache:
            _set_cached(key, result)
        return result
    except Exception as e:
        return {"error": str(e), "method": "prophet_failed"}


# ── Background precompute ──────────────────────────────────────────────────
def warm_cache_in_background(kpi_series: dict[str, tuple[list[str], list[float]]]):
    """
    Call this at app startup with {kpi_id: (dates, values)} to pre-fit
    Prophet for all KPIs in a background thread. Subsequent /kpis calls
    will hit the disk cache and return instantly.
    """
    def _worker():
        for kpi_id, (dates, values) in kpi_series.items():
            try:
                key = _cache_key(dates, 1)
                existing = _get_cached(key)
                if existing:
                    continue  # already cached, skip
                forecast_next(dates, values, horizon_days=1, use_cache=True, sync_fit=True)
            except Exception:
                pass

    t = threading.Thread(target=_worker, daemon=True, name="prophet-warm")
    t.start()
    return t


if __name__ == "__main__":
    from datetime import date, timedelta
    import random
    random.seed(42)
    dates = [(date(2024, 8, 1) + timedelta(days=i)).isoformat() for i in range(400)]
    values = [1000 + 50 * math.sin(i * 2 * math.pi / 7) + random.gauss(0, 20) for i in range(400)]
    print("Testing prophet (no cache)...")
    r = forecast_next(dates, values, use_cache=False, sync_fit=True)
    print(f"Method: {r.method}, expected: {r.expected:.1f}, CI: [{r.lower:.1f}, {r.upper:.1f}]")
    print("Testing again (should use cache)...")
    r2 = forecast_next(dates, values)
    print(f"Method: {r2.method}, expected: {r2.expected:.1f} (from cache)")
