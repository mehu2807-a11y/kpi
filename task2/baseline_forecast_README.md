# Baseline Forecast — module implementation

Role: ML Engineer / Data Scientist (Forecasting), for BusinessIntelligence.ai.
Produces `BaselineForecast` rows for the Anomaly Gate module (Task 3), plus a
per-series backtest accuracy report so Task 3 knows how much to trust each
interval.

## Quick start

```
pip install -r requirements.txt
python3 run.py                 # fits + backtests + forecasts all series, writes outputs/
python3 plot_diagnostics.py    # reads outputs/ pickles, writes a sanity-check chart
```

`run.py` prints per-series MAPE and an anomaly sanity check, and writes:
- `outputs/baseline_forecast.json` — the `BaselineForecast` rows
- `outputs/backtest_accuracy_report.json` — per-series MAPE report
- `outputs/_dev_data.pkl`, `outputs/_diagnostics.pkl` — cached so the plot script doesn't refit

## Files

| File | Purpose |
|---|---|
| `data_gen.py` | Synthetic dev/validation dataset (see below) |
| `features.py` | Calendar + lag feature engineering (XGBoost only) |
| `models.py` | `ProphetForecaster` / `XGBoostForecaster`, common `fit`/`predict` interface |
| `backtest.py` | Rolling-window out-of-sample backtest harness |
| `pipeline.py` | Per-series orchestration: backtest both candidates, select/ensemble, calibrate interval, emit rows |
| `run.py` | Entry point — runs all series, writes outputs, anomaly sanity check |
| `plot_diagnostics.py` | Renders `outputs/baseline_forecast_diagnostic.png` |

## Dev dataset — and why it's synthetic, not a pulled-in public CSV

`data_gen.py` builds 3 years of daily data for three `(metric, region, product)`
series, with a **known** data-generating process: trend (with a mid-series
growth-rate change), weekly seasonality, yearly seasonality, holiday effects,
promo effects, realistic noise, and — separately — a couple of **injected,
unflagged one-off anomalies** per revenue series.

Reasoning: the point of a day-one dev set is to check the pipeline recovers
the right signal, not just that it runs without errors. A real public retail
dataset (Kaggle's Store Item Demand / Rossmann-style sets are the closest
shape) doesn't come with ground truth for "how much of this is trend vs.
seasonality vs. holiday effect," so there's nothing to check the fit against.
Known synthetic components + injected anomalies gave a concrete pass/fail
test (see "Validation" below) that an arbitrary CSV wouldn't have.

Column names (`date, region, product, metric_name, value, is_holiday,
is_promo`) match what a real `MetricsTable` extract looks like per the brief,
so switching to real data is a one-function change: point `load_series()` in
`pipeline.py` at the real table instead of the synthetic frame `run.py`
builds. Everything downstream is unchanged.

Two of the three series (`revenue` in both regions) are marked
`heavy_external_drivers=True` and get both models; `units_sold` is marked
`False` and gets Prophet only — this flag is exactly the "for metrics with
heavier external drivers, also fit XGBoost" branch from the brief, and in a
real system would be a config call per metric rather than hardcoded.

## Modeling

- **Prophet**: fit per series with `yearly_seasonality` and `weekly_seasonality`
  on, holidays passed via a `holidays` dataframe built from the `is_holiday`
  flag, and `is_promo` added as a regressor (`add_regressor`).
- **XGBoost**: `lag_1 / lag_7 / lag_28` + day-of-week, month, sin/cos of
  day-of-year (so trees have a smooth yearly-cycle signal without needing a
  year of lag depth), `is_holiday`, `is_promo`. Forecasting beyond the
  training history is done **recursively** — each step's prediction becomes
  the next step's `lag_1`, and so on for `lag_7`/`lag_28` once far enough out.

## Backtest protocol

Rolling-origin, out-of-sample, non-overlapping 14-day folds: train on
everything before the fold, predict the 14 days after it, slide the origin
forward 14 days, repeat — covering essentially the whole ~1-year holdout
region (the first ~2 years are reserved as the initial training window, so
there's a full seasonal cycle to learn from before backtesting starts).
Model is refit from scratch every fold; nothing from a fold's test window
ever informs an earlier or later fold.

This produces two things per series/model, both out-of-sample:
1. **MAPE** — averaged over every backtest point — that's the accuracy report.
2. A **pool of residuals** (`actual - predicted`), whose 10th/90th percentiles
   become `lower_bound`/`upper_bound` for the real forecast. This is the
   direct implementation of "interval width reflects real historical error,
   not an in-sample fit" — the final bounds come from backtest residuals,
   not from Prophet's own (partly in-sample) uncertainty interval.

**Selection rule**: per series, if only Prophet applies, use it. If both
apply, compare backtest MAPE; if they're within 10% relative of each other,
ensemble (average the two point forecasts, pool both residual sets for the
interval); otherwise take whichever backtested better.

## Validation

All three series currently select **Prophet** — its explicit trend +
Fourier-seasonality decomposition is a close structural match for this
synthetic DGP (2.2–3.3% backtest MAPE vs. 5.2–6.2% for XGBoost, which is
working from lag features alone). That's a property of *this* dataset, not
a bias in the pipeline — the ensemble branch is exercised by the same
`abs(mape_a - mape_b) / min(...) < 0.10` check regardless of which series
trips it, and a real revenue series with choppier, less smooth external
drivers (competitor actions, macro shocks) is exactly the case where
XGBoost's flexibility should start winning backtests and get selected.

Anomaly sanity check (`run.py` output) — each injected, unflagged anomaly
correctly falls outside its calibrated interval:

```
supply_disruption  (Region X, -44%): actual 3387 vs band [5341, 5645]  -> outside
viral_moment       (Region X, +55%): actual 9782 vs band [6216, 6520]  -> outside
logistics_outage   (Region Y, -45%): actual 1566 vs band [2834, 3064]  -> outside
regional_event_spike (Region Y,+50%): actual 5109 vs band [3352, 3582] -> outside
```

`outputs/baseline_forecast_diagnostic.png` shows this visually for both
revenue series: actual vs. the out-of-sample backtest band, the injected
anomalies breaking well outside it, ordinary holiday/promo bumps staying
inside it, and the forward 30-day forecast (with a visible step up during
the one scheduled future promo window used to confirm the regressor is
actually doing something).

## Output schema

`baseline_forecast.json` — one row per `(date, region, product, metric_name)`
in the 30-day forecast horizon:

```json
{"date": "2026-01-01", "region": "Region X", "product": "Product A",
 "metric_name": "revenue", "expected_value": 6467.64,
 "lower_bound": 6320.37, "upper_bound": 6624.26, "model_used": "prophet"}
```

`backtest_accuracy_report.json` — one entry per series:

```json
{"region": "Region X", "product": "Product A", "metric_name": "revenue",
 "chosen_model": "prophet", "chosen_model_mape_pct": 2.22,
 "per_model_mape_pct": {"prophet": 2.22, "xgboost": 5.19},
 "n_backtest_points": {"prophet": 350, "xgboost": 350},
 "interval_residual_quantiles_used": [-147.28, 156.62]}
```

`chosen_model_mape_pct` is the number Task 3 should read as "how much to
trust this series' interval" — e.g. widen its own tolerance, or discount an
alert, for a series with a materially higher MAPE than its peers.

## Tuning knobs (all at the top of `pipeline.py`)

- `INITIAL_TRAIN_DAYS` / `BACKTEST_HORIZON` / `BACKTEST_STRIDE` — backtest
  window size, fold length, and fold spacing. Current settings (735 / 14 / 14)
  give full contiguous coverage of the holdout region in ~25s total for all
  3 series on this sandbox; a production run against real MetricsTable data
  and many more series would likely want daily or weekly refit cadence and
  more compute, not this coarser 14-day-block version.
- `INTERVAL_LOW_Q` / `INTERVAL_HIGH_Q` — currently 10th/90th percentile
  (~80% interval, matching Prophet's own default). Narrower for a more
  sensitive downstream gate, wider for fewer false alarms.
- `ENSEMBLE_MARGIN` — how close two models' MAPE must be to ensemble instead
  of picking the better one.
- `FORECAST_HORIZON` — currently 30 days.

## Known limitations

- Dev/validation only — real accuracy depends on real `MetricsTable` data
  once Task 1 ships; `load_series()` is the single integration point.
- XGBoost's recursive forecasting compounds error over the horizon (each
  step's noise becomes the next step's `lag_1`); fine at 14–30 days, would
  need capping or a direct multi-step model at longer horizons.
- Future `is_holiday` is currently hardcoded to 0 in the forecast window —
  a real run should look this up from a forward holiday calendar the same
  way `is_promo` would come from a forward promo calendar.
- No hyperparameter tuning on the XGBoost side (sensible defaults only);
  worth a real search once it's winning backtests on real data.
