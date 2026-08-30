"""
scenarios.py -- builds the hand-constructed test scenarios (the ones that
need a specific driver/evidence signature Task 2's real series can't
provide on its own -- ambiguity, competitor evidence, missing evidence,
citation edge cases). Every scenario still runs through the REAL Task 3
gate on a real (baseline_df) series -- nothing here bypasses the gate,
including the "should stay noise" scenarios.

Pattern follows Task 4's own notebook (plant a driver + decoys) and Task 5's
own sample_data.py (mix of relevant/irrelevant, in/out of window docs) --
not an arbitrary new convention.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _weekday_seasonal_baseline(n_days, level=50_000, noise_std=900, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2026-01-01", periods=n_days, freq="D")
    weekday_factor = np.array([1.05, 1.08, 1.05, 1.02, 1.10, 0.90, 0.80])
    seasonality = weekday_factor[dates.dayofweek]
    base = level * seasonality
    noise = rng.normal(0, noise_std, n_days)
    return dates, base, noise


def build_region_wide_and_gate_series(
    *,
    region: str,
    n_days: int = 110,
    shock_start_day: int = 95,
    shock_len_days: int = 14,
    shock_pct: float = -0.20,
    driver: str | None = "avg_price",
    driver_lag_days: int = 7,
    driver_step_pct: float = 0.15,
    seed: int = 1,
):
    """
    Returns (region_wide_df, gate_baseline_df):
      region_wide_df -- date, revenue, avg_price, inventory_level,
                         marketing_spend, complaint_sentiment_score
                         (Task 4's exact input shape).
      gate_baseline_df -- date, actual_value, expected_value, lower_bound,
                         upper_bound (Task 3's exact input shape), built
                         from a trailing-mean/std baseline over the
                         PRE-SHOCK history -- this stands in for a live
                         Task 2 forecast for scenarios that need a specific
                         planted driver signature Task 2's own validated
                         dataset doesn't happen to contain. Documented
                         substitution, not a hidden one: Task 2's real
                         model is already validated separately (see
                         scenarios 1-5, which use Task 2's actual output).
    """
    rng = np.random.default_rng(seed)
    dates, base_revenue, noise = _weekday_seasonal_baseline(n_days, seed=seed)
    day_idx = np.arange(n_days)

    revenue = base_revenue + noise
    shock_end_day = shock_start_day + shock_len_days - 1
    in_shock = (day_idx >= shock_start_day) & (day_idx <= shock_end_day)
    revenue = np.where(in_shock, revenue * (1 + shock_pct), revenue)

    avg_price = 40.0 + rng.normal(0, 0.15, n_days)
    inventory_level = np.empty(n_days)
    inventory_level[0] = 12_000
    for t in range(1, n_days):
        inventory_level[t] = 12_000 + 0.85 * (inventory_level[t - 1] - 12_000) + rng.normal(0, 220)
    marketing_spend = 2200 + rng.normal(0, 120, n_days)
    complaint_sentiment_score = np.clip(0.78 + rng.normal(0, 0.018, n_days), 0, 1)

    if driver == "avg_price":
        step_day = shock_start_day - driver_lag_days
        avg_price = np.where(day_idx >= step_day, avg_price + avg_price.mean() * driver_step_pct, avg_price)
    elif driver == "marketing_spend":
        step_day = shock_start_day - driver_lag_days
        marketing_spend = np.where(day_idx >= step_day, marketing_spend * 0.35, marketing_spend)  # spend CUT
    elif driver == "inventory_level":
        step_day = shock_start_day - driver_lag_days
        inventory_level = np.where(day_idx >= step_day, inventory_level * 0.25, inventory_level)
    # driver is None -> pure noise-only candidate columns, no planted structured cause

    region_wide = pd.DataFrame({
        "date": dates, "revenue": revenue.round(2), "avg_price": avg_price.round(2),
        "inventory_level": inventory_level.round(0), "marketing_spend": marketing_spend.round(2),
        "complaint_sentiment_score": complaint_sentiment_score.round(3),
    })

    # gate baseline: trailing 60-day mean/std computed OUT of the shock window,
    # applied flat across history (a deliberately simple stand-in -- see docstring)
    pre_shock = revenue[:shock_start_day]
    mu, sigma = pre_shock[-60:].mean(), pre_shock[-60:].std()
    expected = np.full(n_days, mu)
    lower = expected - 2.5 * sigma
    upper = expected + 2.5 * sigma
    gate_baseline = pd.DataFrame({
        "date": dates, "actual_value": revenue, "expected_value": expected,
        "lower_bound": lower, "upper_bound": upper,
    })
    return region_wide, gate_baseline


def build_document_store(rows: list[dict]) -> list[dict]:
    """rows: list of partial dicts; fills in defaults matching Task 1's real
    DocumentStore schema exactly (doc_id, date, source, region_tags,
    entity_tags, sentiment_score, raw_text)."""
    out = []
    for i, r in enumerate(rows):
        out.append({
            "doc_id": r.get("doc_id", f"gen_doc_{i:04d}"),
            "date": r["date"],
            "source": r["source"],
            "region_tags": r.get("region_tags", []),
            "entity_tags": r.get("entity_tags", []),
            "sentiment_score": r.get("sentiment_score", 0.0),
            "raw_text": r["raw_text"],
        })
    return out


def build_day_of_week_adjusted_gate_series(*, n_days=110, shock_start_day=95, shock_len_days=1,
                                            shock_pct=-0.55, noise_std_frac=0.01, seed=1):
    """
    A gate_baseline (date, actual_value, expected_value, lower_bound,
    upper_bound) where `expected_value` tracks the SAME weekday pattern the
    actuals follow -- unlike build_region_wide_and_gate_series()'s flat mean,
    which leaves weekday seasonality sitting inside the residual and inflates
    sigma to ~5-10x a real forecast's residual spread. That inflation makes
    Task 3's secondary_threshold (3x the interval's normalized width) all but
    unreachable by any realistic single-day shock -- discovered when
    scenario 13's intended single-day override path never fired despite a
    -55% shock (see FINDINGS in the project README). This builder keeps
    `expected` at each day's true weekday level, so sigma reflects only
    genuine (small, tunable) noise, the way a working forecast's residual
    would -- restoring the ability to test the secondary-threshold path at
    all with a realistic shock size.
    """
    rng = np.random.default_rng(seed)
    dates, base_revenue, _ = _weekday_seasonal_baseline(n_days, noise_std=0, seed=seed)
    noise = rng.normal(0, base_revenue.mean() * noise_std_frac, n_days)
    actual = base_revenue + noise
    day_idx = np.arange(n_days)
    shock_end_day = shock_start_day + shock_len_days - 1
    in_shock = (day_idx >= shock_start_day) & (day_idx <= shock_end_day)
    actual = np.where(in_shock, actual * (1 + shock_pct), actual)

    sigma = noise[: shock_start_day].std() or (base_revenue.mean() * noise_std_frac)
    expected = base_revenue
    lower = expected - 2.5 * sigma
    upper = expected + 2.5 * sigma
    return pd.DataFrame({"date": dates, "actual_value": actual, "expected_value": expected,
                          "lower_bound": lower, "upper_bound": upper})


def to_long_metrics_table(region_wide_df: pd.DataFrame, region: str, product: str) -> pd.DataFrame:
    """Melts a (date + metric columns) wide frame into Task 1's real
    long-format MetricsTable shape (date, region, product, metric_name,
    value) -- crucially tagging marketing_spend rows with product == "ALL",
    matching Task 1's own convention (marketing spend is region-level, not
    product-level). Skipping this is an easy mistake to make and a bad one:
    adapters.metrics_table_to_region_wide() filters marketing_spend on
    product == "ALL" specifically, so any other product tag silently comes
    back as an all-NaN column instead of an error -- which starves Task 4's
    dropna()'d training set down to zero rows several steps downstream. This
    exact bug was hit and fixed while building this test suite (see FINDINGS
    in the project README for the full trace).
    """
    long = region_wide_df.assign(region=region, product=product).melt(
        id_vars=["date", "region", "product"], var_name="metric_name", value_name="value")
    is_marketing = long["metric_name"] == "marketing_spend"
    long.loc[is_marketing, "product"] = "ALL"
    return long
