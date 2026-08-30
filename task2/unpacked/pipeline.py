"""
pipeline.py
Runs the Baseline Forecast module for one (metric, region, product) series:
fit Prophet (+ XGBoost when the metric is configured as driver-heavy),
backtest both with rolling_backtest, pick the better one -- or ensemble if
they're close -- calibrate the interval from backtest residuals, and emit
forward forecast rows in the exact BaselineForecast schema plus a
per-series accuracy report.

NOTE on column access: this module deliberately uses bracket notation
(df['product']) everywhere rather than attribute access (df.product),
because 'product' collides with pandas' own DataFrame.product() method --
attribute access silently returns the method instead of raising, which
is an easy way to end up filtering on the wrong thing.
"""

import numpy as np
import pandas as pd

from backtest import rolling_backtest
from models import ProphetForecaster, XGBoostForecaster

INITIAL_TRAIN_DAYS = 735       # ~2 years before the backtest region starts (735, not 730,
                                # so Prophet's own "need >=2yr for yearly seasonality" check is
                                # comfortably satisfied instead of warning on every fold)
BACKTEST_HORIZON = 14          # days forecast per backtest fold
BACKTEST_STRIDE = 14           # == horizon -> contiguous, non-overlapping folds covering
                                # essentially the whole holdout region (not just samples of it)
FORECAST_HORIZON = 30          # days of forward BaselineForecast rows to emit
INTERVAL_LOW_Q, INTERVAL_HIGH_Q = 0.10, 0.90   # ~80% interval from backtest residuals
ENSEMBLE_MARGIN = 0.10         # MAPEs within 10% relative of each other -> ensemble instead of picking one
FUTURE_PROMO_DAYS = (5, 10)    # schedule one known future promo window, to show the regressor working


def load_series(all_data: pd.DataFrame, region: str, product: str, metric_name: str) -> pd.DataFrame:
    """Pulls one series out of the long-format table. This is the one
    function to change to point at real MetricsTable output instead of
    the synthetic dev set -- same expected columns either way."""
    mask = ((all_data["region"] == region) &
            (all_data["product"] == product) &
            (all_data["metric_name"] == metric_name))
    return all_data.loc[mask].sort_values("date").reset_index(drop=True)


def run_series(df: pd.DataFrame, heavy_external_drivers: bool) -> dict:
    region = df["region"].iloc[0]
    product = df["product"].iloc[0]
    metric = df["metric_name"].iloc[0]

    candidates = {"prophet": ProphetForecaster}
    if heavy_external_drivers:
        candidates["xgboost"] = XGBoostForecaster

    backtests = {}
    for name, cls in candidates.items():
        bt_df, mape = rolling_backtest(df, cls, INITIAL_TRAIN_DAYS, BACKTEST_HORIZON, BACKTEST_STRIDE)
        backtests[name] = {"result": bt_df, "mape": mape}

    if len(backtests) == 1:
        chosen = next(iter(backtests))
    else:
        m_prophet, m_xgb = backtests["prophet"]["mape"], backtests["xgboost"]["mape"]
        rel_gap = abs(m_prophet - m_xgb) / min(m_prophet, m_xgb)
        chosen = "ensemble" if rel_gap < ENSEMBLE_MARGIN else min(backtests, key=lambda k: backtests[k]["mape"])

    # refit every needed model on the FULL history for the actual forward forecast
    fitted = {name: cls().fit(df) for name, cls in candidates.items()}

    last_date = df["date"].max()
    future_dates = pd.date_range(last_date + pd.Timedelta(days=1), periods=FORECAST_HORIZON, freq="D")
    future_df = pd.DataFrame({"date": future_dates})
    future_df["is_holiday"] = 0  # production would look this up from a forward holiday calendar
    future_df["is_promo"] = 0
    lo, hi = FUTURE_PROMO_DAYS
    future_df.loc[(future_df.index >= lo) & (future_df.index < hi), "is_promo"] = 1

    point_forecasts = {name: model.predict(future_df[["date", "is_holiday", "is_promo"]])
                        for name, model in fitted.items()}

    if chosen == "ensemble":
        expected = np.mean([point_forecasts["prophet"], point_forecasts["xgboost"]], axis=0)
        resid_pool = np.concatenate([backtests["prophet"]["result"]["residual"].to_numpy(),
                                      backtests["xgboost"]["result"]["residual"].to_numpy()])
        used_mape = float(np.mean([backtests["prophet"]["mape"], backtests["xgboost"]["mape"]]))
    else:
        expected = point_forecasts[chosen]
        resid_pool = backtests[chosen]["result"]["residual"].to_numpy()
        used_mape = backtests[chosen]["mape"]

    q_lo, q_hi = np.quantile(resid_pool, [INTERVAL_LOW_Q, INTERVAL_HIGH_Q])
    lower = expected + q_lo
    upper = expected + q_hi

    forecast_rows = pd.DataFrame({
        "date": future_dates.strftime("%Y-%m-%d"),
        "region": region,
        "product": product,
        "metric_name": metric,
        "expected_value": np.round(expected, 2),
        "lower_bound": np.round(lower, 2),
        "upper_bound": np.round(upper, 2),
        "model_used": chosen,
    })

    accuracy_report = {
        "region": region, "product": product, "metric_name": metric,
        "chosen_model": chosen,
        "chosen_model_mape_pct": round(used_mape, 3),
        "per_model_mape_pct": {k: round(v["mape"], 3) for k, v in backtests.items()},
        "n_backtest_points": {k: int(len(v["result"])) for k, v in backtests.items()},
        "interval_residual_quantiles_used": [float(round(q_lo, 2)), float(round(q_hi, 2))],
    }

    diagnostics = {"backtests": backtests, "future_df": future_df, "point_forecasts": point_forecasts}
    return {"forecast_rows": forecast_rows, "accuracy_report": accuracy_report, "diagnostics": diagnostics}
