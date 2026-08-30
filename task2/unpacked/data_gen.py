"""
data_gen.py
Synthetic daily, retail-shaped dataset for developing and validating the
Baseline Forecast module ahead of Task 1 (Ingest & Align) shipping real
MetricsTable data.

Why synthetic rather than pulling an arbitrary public CSV: this way the
data-generating process (trend + weekly seasonality + yearly seasonality +
holiday effects + promo effects + noise + a couple of injected one-off
anomalies) is known, so we can check the pipeline actually recovers the
right signal -- not just that it runs. Column names match a real
MetricsTable extract (date, region, product, metric_name, value,
is_holiday, is_promo), so swapping in real data later is a one-function
change (see `load_series` in pipeline.py).
"""

import numpy as np
import pandas as pd

START = "2023-01-01"
END = "2025-12-31"


def _holiday_dates(dates: pd.DatetimeIndex) -> pd.DataFrame:
    """(ds, holiday) rows for the date range -- drives both the is_holiday
    flag column and the holidays dataframe Prophet is fed."""
    years = sorted(dates.year.unique())
    rows = []
    for y in years:
        rows.append((pd.Timestamp(y, 1, 1), "new_years_day"))
        rows.append((pd.Timestamp(y, 7, 4), "summer_sale_day"))
        nov1 = pd.Timestamp(y, 11, 1)
        first_thu = nov1 + pd.Timedelta(days=(3 - nov1.dayofweek) % 7)
        fourth_thu = first_thu + pd.Timedelta(weeks=3)
        black_friday = fourth_thu + pd.Timedelta(days=1)
        for offset, name in [(-1, "thanksgiving"), (0, "black_friday"), (1, "black_friday_weekend")]:
            rows.append((black_friday + pd.Timedelta(days=offset), name))
        rows.append((pd.Timestamp(y, 12, 25), "christmas"))
    hdf = pd.DataFrame(rows, columns=["ds", "holiday"])
    hdf = hdf[(hdf.ds >= dates.min()) & (hdf.ds <= dates.max())].reset_index(drop=True)
    return hdf


def _promo_windows(dates: pd.DatetimeIndex, rng: np.random.Generator,
                    n_promos=5, min_len=3, max_len=7) -> np.ndarray:
    """Scatter n_promos non-overlapping promo windows across the range."""
    promo_flag = pd.Series(0, index=range(len(dates)))
    n_days = len(dates)
    attempts, placed = 0, 0
    while placed < n_promos and attempts < 300:
        attempts += 1
        start_idx = rng.integers(30, n_days - 30)
        length = int(rng.integers(min_len, max_len + 1))
        if promo_flag.iloc[start_idx:start_idx + length].sum() == 0:
            promo_flag.iloc[start_idx:start_idx + length] = 1
            placed += 1
    return promo_flag.values


def make_series(region, product, metric_name, seed, base_level, growth_rate,
                 weekly_amp, yearly_amp, noise_std, holiday_boost, promo_boost,
                 anomalies=None):
    """One synthetic (metric, region, product) daily series over [START, END]."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range(START, END, freq="D")
    t = np.arange(len(dates))

    # trend with a mild mid-series growth-rate change, so Prophet's
    # changepoint detection actually has something to do
    changepoint = int(len(dates) * 0.55)
    trend = base_level + growth_rate * t
    trend[changepoint:] += (growth_rate * 1.8) * (t[changepoint:] - changepoint)

    dow = dates.dayofweek
    weekly = weekly_amp * np.where(dow >= 5, 1.0, -0.35) * base_level / 100

    doy = dates.dayofyear
    # peaks ~mid-November (holiday shopping run-up), trough ~mid-Feb
    yearly = yearly_amp * base_level / 100 * np.sin(2 * np.pi * (doy - 45) / 365.25 + np.pi)

    hdf = _holiday_dates(dates)
    is_holiday = dates.isin(hdf.ds).astype(int)
    holiday_effect = is_holiday * base_level * holiday_boost

    promo_flag = _promo_windows(dates, rng)
    promo_effect = promo_flag * base_level * promo_boost

    noise = rng.normal(0, noise_std, len(dates)) * base_level

    value = trend + weekly + yearly + holiday_effect + promo_effect + noise
    value = np.maximum(value, base_level * 0.1)

    df = pd.DataFrame({
        "date": dates,
        "region": region,
        "product": product,
        "metric_name": metric_name,
        "value": value,
        "is_holiday": is_holiday,
        "is_promo": promo_flag,
    })
    df["_anomaly_label"] = pd.Series([None] * len(df), dtype="object")

    # inject genuine one-off anomalies -- NOT flagged as holiday/promo, so
    # the model has no feature signal for them. Used later purely as a
    # sanity check that the interval would actually catch a real deviation.
    for (days_before_end, multiplier, label) in (anomalies or []):
        idx = len(df) - 1 - days_before_end
        df.loc[idx, "value"] = max(df.loc[idx, "value"] * multiplier, 1.0)
        df.loc[idx, "_anomaly_label"] = label

    return df


SERIES_CONFIG = [
    dict(region="Region X", product="Product A", metric_name="revenue", seed=1,
         base_level=3000, growth_rate=1.6, weekly_amp=1.1, yearly_amp=14,
         noise_std=0.035, holiday_boost=0.55, promo_boost=0.22,
         heavy_external_drivers=True,
         anomalies=[(140, 0.62, "supply_disruption"), (60, 1.55, "viral_moment")]),
    dict(region="Region Y", product="Product B", metric_name="revenue", seed=2,
         base_level=1800, growth_rate=0.9, weekly_amp=0.8, yearly_amp=10,
         noise_std=0.045, holiday_boost=0.40, promo_boost=0.30,
         heavy_external_drivers=True,
         anomalies=[(200, 0.55, "logistics_outage"), (95, 1.50, "regional_event_spike")]),
    dict(region="Region X", product="Product A", metric_name="units_sold", seed=3,
         base_level=450, growth_rate=0.12, weekly_amp=1.3, yearly_amp=8,
         noise_std=0.05, holiday_boost=0.35, promo_boost=0.25,
         heavy_external_drivers=False,
         anomalies=[]),
]


def build_all() -> pd.DataFrame:
    frames = []
    for cfg in SERIES_CONFIG:
        cfg = dict(cfg)
        cfg.pop("heavy_external_drivers")
        frames.append(make_series(**cfg))
    return pd.concat(frames, ignore_index=True)


if __name__ == "__main__":
    d = build_all()
    print(d.shape)
    print(d.groupby(["metric_name", "region", "product"]).size())
    print(d.head())
