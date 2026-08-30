"""
synthetic_data.py — day-one test data for the anomaly gate (Task 3)

The brief's input spec for Task 3 explicitly asks for this: "synthetic
series with some hand-injected real anomalies and some random noise, so you
can measure your own detector's precision/recall before real data exists" --
i.e. before Task 1 (ingest) and Task 2 (baseline forecast) are done.

Design:
  * A "clean" underlying signal is generated first (weekly seasonality +
    slow trend + realistic multiplicative noise), for FOUR correlated
    metrics per region: traffic -> units_sold -> revenue, plus a mostly-
    independent avg_order_value. This is what "would have happened" with no
    incident.
  * The baseline forecast (expected_value / lower_bound / upper_bound) is a
    trailing rolling mean +/- 2 sigma, computed from the CLEAN signal only.
    This stands in for whatever model Task 2 ships -- swap it out later,
    nothing else here or in anomaly_gate.py needs to change. Computing it
    from the clean signal (not the contaminated actuals) avoids the baseline
    chasing its own tail when an anomaly is injected, which would make this
    a test of the forecaster rather than of the gate.
  * The "actual" series is the clean series with three kinds of labeled
    events injected, to exercise all three of the gate's decision pathways:

      - "shock"              : one day, large (50-65%), coordinated across
                                traffic/units_sold/revenue. Should clear the
                                step-4 secondary threshold (3x) on its own
                                and fire on day 1. TRUE anomaly.
      - "sustained"           : five consecutive days, moderate (12-22%),
                                coordinated across traffic/units_sold/revenue.
                                Shouldn't clear the secondary threshold alone;
                                should accumulate via the step-4 persistence
                                pathway. TRUE anomaly (every day in the window).
      - "single_metric_noise" : one day, moderate (15-28%), REVENUE ONLY --
                                traffic/units_sold/avg_order_value stay on
                                their clean values. No multivariate
                                corroboration and no persistence. Should be
                                suppressed as noise even though the univariate
                                residual alone may clear the step-2 primary
                                threshold. NOT a true anomaly -- this is
                                exactly the case the gate exists to catch.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

METRICS = ["revenue", "units_sold", "traffic", "avg_order_value"]
REGIONS = ["Region X", "Region Y", "Region Z"]


def _weekday_factor(dow: int) -> float:
    # dow: 0=Mon .. 6=Sun -- modest weekend lift, typical of a retail-like business
    return {0: 0.95, 1: 0.95, 2: 0.97, 3: 1.00, 4: 1.08, 5: 1.15, 6: 1.05}[dow]


def _generate_region_series(region: str, start: date, n_days: int, seed: int):
    rng = np.random.default_rng(seed)
    dates = [start + timedelta(days=i) for i in range(n_days)]

    base_traffic = rng.uniform(8000, 12000)
    trend = rng.uniform(-0.0003, 0.0006)
    conversion_rate = rng.uniform(0.04, 0.07)
    base_aov = rng.uniform(35, 65)

    clean = {m: np.zeros(n_days) for m in METRICS}
    for i, d in enumerate(dates):
        season = _weekday_factor(d.weekday())
        traffic = base_traffic * season * (1 + trend * i) * (1 + rng.normal(0, 0.04))
        units = traffic * conversion_rate * (1 + rng.normal(0, 0.05))
        aov = base_aov * (1 + rng.normal(0, 0.03))
        revenue = units * aov * (1 + rng.normal(0, 0.02))
        clean["traffic"][i] = traffic
        clean["units_sold"][i] = units
        clean["avg_order_value"][i] = aov
        clean["revenue"][i] = revenue

    actual = {m: clean[m].copy() for m in METRICS}
    labels = ["none"] * n_days  # "none" | "shock" | "sustained" | "single_metric_noise"

    burn_in = 30  # need enough trailing history before any injected event
    tail_guard = 6  # keep sustained windows fully inside the series
    candidates = list(range(burn_in, n_days - tail_guard))
    rng.shuffle(candidates)
    cursor = 0

    def reserve(i: int, span: int = 1) -> bool:
        return all(labels[j] == "none" for j in range(i, i + span))

    def claim(i: int, span: int, label: str) -> None:
        for j in range(i, i + span):
            labels[j] = label

    # 3 single-day shocks: large, coordinated, meant to clear the secondary
    # threshold unaided (tests the step-4 single-period override pathway).
    placed = 0
    while placed < 3 and cursor < len(candidates):
        i = candidates[cursor]; cursor += 1
        if reserve(i):
            down = rng.random() < 0.7
            factor = rng.uniform(0.20, 0.35) if down else rng.uniform(1.70, 2.00)
            for m in ("traffic", "units_sold", "revenue"):
                actual[m][i] = clean[m][i] * factor * (1 + rng.normal(0, 0.02))
            claim(i, 1, "shock")
            placed += 1

    # 2 sustained 5-day windows: moderate, coordinated, meant to stay under
    # the secondary threshold and be caught via persistence (step 4).
    placed = 0
    while placed < 2 and cursor < len(candidates):
        i = candidates[cursor]; cursor += 1
        if reserve(i, 5):
            down = rng.random() < 0.7
            factor = rng.uniform(0.72, 0.85) if down else rng.uniform(1.15, 1.30)
            for j in range(i, i + 5):
                for m in ("traffic", "units_sold", "revenue"):
                    actual[m][j] = clean[m][j] * factor * (1 + rng.normal(0, 0.02))
            claim(i, 5, "sustained")
            placed += 1

    # 4 single-metric noise blips: moderate, REVENUE ONLY, no multivariate
    # corroboration, no persistence. Ground truth = NOT a true anomaly.
    placed = 0
    while placed < 4 and cursor < len(candidates):
        i = candidates[cursor]; cursor += 1
        if reserve(i):
            down = rng.random() < 0.5
            factor = rng.uniform(0.68, 0.85) if down else rng.uniform(1.15, 1.32)
            actual["revenue"][i] = clean["revenue"][i] * factor
            claim(i, 1, "single_metric_noise")
            placed += 1

    return dates, clean, actual, labels


def _rolling_baseline(clean_values: np.ndarray, dates: list[date], window_days: int = 42, z: float = 2.0):
    """
    Day-of-week-aware trailing mean +/- z*std, computed from the CLEAN series
    (no leakage into the anomaly window, no contamination from injected
    events). A plain rolling mean/std over raw values would treat normal
    weekday-vs-weekend seasonality (see _weekday_factor) as noise and produce
    artificially wide bounds, which would understate every injected
    anomaly's normalized residual. Real forecasters handle seasonality; this
    is a simple stand-in for whatever Task 2 ships -- swap it out later,
    nothing else here or in anomaly_gate.py needs to change.
    """
    n = len(clean_values)
    expected = np.full(n, np.nan)
    lower = np.full(n, np.nan)
    upper = np.full(n, np.nan)
    weekdays = np.array([d.weekday() for d in dates])

    for i in range(n):
        start = max(0, i - window_days)
        hist_vals = clean_values[start:i]
        hist_wd = weekdays[start:i]
        if len(hist_vals) < 14:
            continue

        overall_mean = hist_vals.mean()
        wd_factor = {}
        for wd in range(7):
            wd_vals = hist_vals[hist_wd == wd]
            wd_factor[wd] = (wd_vals.mean() / overall_mean) if len(wd_vals) >= 2 else 1.0

        deseasonalized = hist_vals / np.array([wd_factor[w] for w in hist_wd])
        deseas_mean = deseasonalized.mean()
        deseas_std = max(deseasonalized.std(ddof=1), 1e-6)

        today_factor = wd_factor[weekdays[i]]
        expected[i] = deseas_mean * today_factor
        lower[i] = expected[i] - z * deseas_std * today_factor
        upper[i] = expected[i] + z * deseas_std * today_factor

    return expected, lower, upper


def generate_dataset(n_days: int = 180, start: date = date(2026, 1, 21), seed: int = 7) -> pd.DataFrame:
    rows = []
    for r_i, region in enumerate(REGIONS):
        dates, clean, actual, labels = _generate_region_series(region, start, n_days, seed=seed + r_i)
        baselines = {m: _rolling_baseline(clean[m], dates) for m in METRICS}
        for i, d in enumerate(dates):
            expected0 = baselines[METRICS[0]][0][i]
            if np.isnan(expected0):
                continue  # still in burn-in for the rolling baseline
            for m in METRICS:
                expected, lower, upper = baselines[m][0][i], baselines[m][1][i], baselines[m][2][i]
                rows.append({
                    "date": d.isoformat(),
                    "region": region,
                    "metric": m,
                    "actual_value": round(float(actual[m][i]), 2),
                    "expected_value": round(float(expected), 2),
                    "lower_bound": round(float(lower), 2),
                    "upper_bound": round(float(upper), 2),
                    "is_true_anomaly": labels[i] in ("shock", "sustained"),
                    "anomaly_type": labels[i],
                })
    return pd.DataFrame(rows)


def generate_long_history(
    n_days: int = 730,
    start: date = date(2024, 8, 1),
    seed: int = 7,
    inject_anomalies: bool = True,
) -> pd.DataFrame:
    """
    Generates 2 years of realistic history (default 730 days) by calling
    generate_dataset() with the given parameters.
    
    With 2 years of history, Task 2's Prophet model can be run for real
    everywhere, not just in the scenarios that use trailing-mean baselines.
    
    Returns the same DataFrame shape as generate_dataset(): columns
    date, region, metric, actual_value, expected_value, lower_bound,
    upper_bound, is_true_anomaly, anomaly_type.
    """
    return generate_dataset(n_days=n_days, start=start, seed=seed)


def generate_sparse_history(
    n_days: int = 30,
    start: date | None = None,
    seed: int = 99,
    regions: list[str] | None = None,
    metrics: list[str] | None = None,
) -> pd.DataFrame:
    """
    Generates a short-history dataset simulating a newly launched KPI or
    product — only n_days of history available. Use this to exercise
    Task 2's cold-start path and Task 3's 'skipped_insufficient_history'
    multivariate check path.
    
    Uses generate_dataset() but with n_days=30 and no injected anomalies
    (not enough history to distinguish anomaly from noise).
    """
    _regions = regions or REGIONS[:1]  # just one region for a new product
    _metrics = metrics or METRICS
    _start = start or (date.today() - timedelta(days=n_days))
    
    # Temporarily override REGIONS for generation
    rows = []
    for r_i, region in enumerate(_regions):
        dates_list, clean, actual, labels = _generate_region_series(region, _start, n_days, seed=seed + r_i)
        baselines = {m: _rolling_baseline(clean[m], dates_list) for m in _metrics}
        for i, d in enumerate(dates_list):
            expected0 = baselines[_metrics[0]][0][i]
            if np.isnan(expected0):
                continue
            for m in _metrics:
                expected_v, lower_v, upper_v = baselines[m][0][i], baselines[m][1][i], baselines[m][2][i]
                rows.append({
                    'date': d.isoformat(), 'region': region, 'metric': m,
                    'actual_value': round(float(actual[m][i]), 2),
                    'expected_value': round(float(expected_v), 2),
                    'lower_bound': round(float(lower_v), 2),
                    'upper_bound': round(float(upper_v), 2),
                    'is_true_anomaly': False,
                    'anomaly_type': 'none',
                })
    return pd.DataFrame(rows)


if __name__ == '__main__':
    print('Generating 2-year history...')
    df_long = generate_long_history()
    print(f'  Long history: {df_long.shape}, date range: {df_long["date"].min()} to {df_long["date"].max()}')
    print('Generating sparse history...')
    df_sparse = generate_sparse_history()
    print(f'  Sparse history: {df_sparse.shape}, date range: {df_sparse["date"].min()} to {df_sparse["date"].max()}')
    print('Both passed.')
