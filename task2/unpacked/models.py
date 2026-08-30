"""
models.py
Two interchangeable per-series forecasters, both exposing
    fit(history_df) -> self
    predict(future_df) -> np.ndarray
so backtest.py and pipeline.py never need model-specific branches.

history_df / future_df columns: date, value (history only), is_holiday, is_promo
"""

import logging

import numpy as np
import pandas as pd
import xgboost as xgb
from prophet import Prophet

from features import FEATURE_COLUMNS, LAGS, build_feature_frame

logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
logging.getLogger("prophet").setLevel(logging.WARNING)


def _holidays_df_from_flags(history_df: pd.DataFrame) -> pd.DataFrame:
    hol_dates = history_df.loc[history_df["is_holiday"] == 1, "date"]
    return pd.DataFrame({"ds": hol_dates, "holiday": "flagged_holiday"})


class ProphetForecaster:
    name = "prophet"

    def __init__(self, interval_width=0.8):
        self.interval_width = interval_width
        self.model = None

    def fit(self, history_df: pd.DataFrame):
        holidays = _holidays_df_from_flags(history_df)
        m = Prophet(
            holidays=holidays if len(holidays) else None,
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
            interval_width=self.interval_width,
        )
        m.add_regressor("is_promo")
        fit_df = history_df.rename(columns={"date": "ds", "value": "y"})[["ds", "y", "is_promo"]]
        m.fit(fit_df)
        self.model = m
        return self

    def predict(self, future_df: pd.DataFrame) -> np.ndarray:
        fut = future_df.rename(columns={"date": "ds"})[["ds", "is_promo"]]
        fc = self.model.predict(fut)
        return fc["yhat"].to_numpy()


class XGBoostForecaster:
    """Recursive multi-step forecaster: lag_1/7/28 + calendar features.
    Forecasting beyond the training history feeds the model's own prior
    predictions back in as lag_1 (and eventually lag_7 / lag_28)."""

    name = "xgboost"

    def __init__(self, **xgb_params):
        params = dict(n_estimators=300, max_depth=4, learning_rate=0.05,
                       subsample=0.8, colsample_bytree=0.8, reg_lambda=1.0)
        params.update(xgb_params)
        self.params = params
        self.model = None
        self._history = None

    def fit(self, history_df: pd.DataFrame):
        feat = build_feature_frame(history_df)
        feat = feat.dropna(subset=[f"lag_{l}" for l in LAGS])
        X, y = feat[FEATURE_COLUMNS], feat["value"]
        self.model = xgb.XGBRegressor(**self.params)
        self.model.fit(X, y)
        self._history = history_df[["date", "value", "is_holiday", "is_promo"]].copy()
        return self

    def predict(self, future_df: pd.DataFrame) -> np.ndarray:
        history = self._history.copy()
        preds = []
        for _, row in future_df.sort_values("date").iterrows():
            working = pd.concat([history, pd.DataFrame([{
                "date": row["date"], "value": np.nan,
                "is_holiday": row["is_holiday"], "is_promo": row["is_promo"],
            }])], ignore_index=True)
            feat_row = build_feature_frame(working).iloc[[-1]]
            yhat = float(self.model.predict(feat_row[FEATURE_COLUMNS])[0])
            preds.append(yhat)
            history = pd.concat([history, pd.DataFrame([{
                "date": row["date"], "value": yhat,
                "is_holiday": row["is_holiday"], "is_promo": row["is_promo"],
            }])], ignore_index=True)
        return np.array(preds)


MODEL_REGISTRY = {"prophet": ProphetForecaster, "xgboost": XGBoostForecaster}
