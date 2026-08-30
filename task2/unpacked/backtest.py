"""
backtest.py
Rolling-window, out-of-sample backtest: fit on an expanding window ("window
N"), forecast the block immediately following it ("N+1"), slide the origin
forward, repeat. This is what makes the reported MAPE -- and the residual
pool used to size the forecast interval -- reflect real historical error
instead of an in-sample fit.
"""

import numpy as np
import pandas as pd


def rolling_backtest(history_df, model_cls, initial_train_days, horizon, stride, model_kwargs=None):
    """Returns (per_point_result_df, mape_percent).

    history_df: full series (date, value, is_holiday, is_promo), sorted or not.
    model_cls: a Forecaster class (ProphetForecaster / XGBoostForecaster) --
        a fresh instance is fit for every fold, so nothing leaks across folds.
    initial_train_days: size of the first training window (the backtest
        region is everything after this).
    horizon: days forecast per fold.
    stride: days the origin advances between folds (<= horizon means
        overlapping folds; > horizon skips some days to save compute).
    """
    model_kwargs = model_kwargs or {}
    df = history_df.sort_values("date").reset_index(drop=True)
    n = len(df)
    origin = initial_train_days
    records = []
    while origin + horizon <= n:
        train = df.iloc[:origin]
        test = df.iloc[origin:origin + horizon]
        model = model_cls(**model_kwargs)
        model.fit(train)
        preds = model.predict(test[["date", "is_holiday", "is_promo"]])
        for d, actual, pred in zip(test["date"], test["value"], preds):
            records.append((d, float(actual), float(pred)))
        origin += stride

    result = pd.DataFrame(records, columns=["date", "actual", "pred"])
    result["residual"] = result["actual"] - result["pred"]
    result["ape"] = (result["residual"].abs() / result["actual"].abs()).replace([np.inf], np.nan)
    mape = float(result["ape"].mean() * 100) if len(result) else float("nan")
    return result, mape
