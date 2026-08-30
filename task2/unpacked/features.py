"""
features.py
Calendar + lag feature engineering for the XGBoost model. Prophet needs
none of this -- it gets (ds, y, is_promo) plus a holidays dataframe,
built directly in models.py.
"""

import numpy as np
import pandas as pd

LAGS = (1, 7, 28)

FEATURE_COLUMNS = ["dow", "month", "doy_sin", "doy_cos", "is_holiday", "is_promo"] + \
                  [f"lag_{l}" for l in LAGS]


def add_calendar_features(df: pd.DataFrame, date_col="date") -> pd.DataFrame:
    out = df.copy()
    d = out[date_col]
    out["dow"] = d.dt.dayofweek
    out["month"] = d.dt.month
    doy = d.dt.dayofyear
    out["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    out["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    return out


def add_lag_features(df: pd.DataFrame, value_col="value", lags=LAGS) -> pd.DataFrame:
    out = df.copy().sort_values("date").reset_index(drop=True)
    for lag in lags:
        out[f"lag_{lag}"] = out[value_col].shift(lag)
    return out


def build_feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    """df needs: date, value, is_holiday, is_promo (value may be NaN for
    the row(s) being predicted -- only its own lag features are unusable,
    which is fine since we never read a lag off the row itself)."""
    out = add_calendar_features(df)
    out = add_lag_features(out)
    return out
