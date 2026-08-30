"""
correlate_drivers.py -- library-only extraction from task4_correlate_drivers.ipynb.

The notebook interleaves each function definition with an inline demo call on its
own mock data (standard notebook style: define, then immediately show it working).
This extraction keeps ONLY the reusable definitions -- dataclass, functions, and the
HISTORICAL_INCIDENT_LOG mock constant -- and drops every inline demo/print/assert
block, so importing this module has no side effects and does no wasted computation
(no re-fitting XGBoost, no re-running Granger tests) at import time.

Single entry point Task 7 calls: correlate_drivers(anomaly_event, metrics_df, historical_log).
"""


import json
import os
import warnings
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import pearsonr
from statsmodels.tsa.stattools import grangercausalitytests
import xgboost as xgb
import shap

warnings.filterwarnings("ignore")
np.random.seed(7)
plt.rcParams["figure.facecolor"] = "white"
plt.rcParams["axes.facecolor"] = "white"

CANDIDATE_FEATURES = ["avg_price", "inventory_level", "marketing_spend", "complaint_sentiment_score"]
LAG_GRID_DAYS = (0, 7, 14, 21, 28)


@dataclass
class AnomalyEvent:
    metric: str
    region: str
    window_start: str  # ISO date
    window_end: str     # ISO date
    magnitude: float     # fractional deviation from the expected/forecast value

    def as_dict(self):
        return asdict(self)


def generate_synthetic_metrics_table(region="US-WEST", price_shift_day=80, demand_lag_days=7,
                                      window_len_days=14):
    """Builds a synthetic MetricsTable + the AnomalyEvent it would produce.

    History spans day 0 through the last day of the anomaly window (inclusive) — deliberately no
    lookahead beyond that, so downstream steps can't accidentally cheat with future data.
    """
    effect_start = price_shift_day + demand_lag_days
    window_start_idx = effect_start
    window_end_idx = effect_start + window_len_days - 1
    n_days = window_end_idx + 1

    dates = pd.date_range("2026-01-01", periods=n_days, freq="D")
    day_idx = np.arange(n_days)

    # --- planted driver: a step change in price ---
    avg_price = np.where(day_idx < price_shift_day, 40.0, 46.0).astype(float)
    avg_price += np.random.normal(0, 0.15, n_days)

    # --- revenue: weekly seasonality + noise + the lagged price effect ---
    weekday_factor = np.array([1.05, 1.08, 1.05, 1.02, 1.10, 0.90, 0.80])  # Mon..Sun
    seasonality = weekday_factor[dates.dayofweek]
    baseline = 50_000 * seasonality
    noise = np.random.normal(0, 900, n_days)
    price_effect = np.where(day_idx >= effect_start, -0.20, 0.0)  # -20% demand response
    revenue = baseline * (1 + price_effect) + noise

    # --- decoy 1: inventory — noisy but mean-reverting, no drift, no relation to revenue ---
    inventory_level = np.empty(n_days)
    inventory_level[0] = 12_000
    for t in range(1, n_days):
        inventory_level[t] = 12_000 + 0.85 * (inventory_level[t - 1] - 12_000) + np.random.normal(0, 220)

    # --- decoy 2: marketing spend, campaign bursts (kept clear of the window) ---
    marketing_spend = 2200 + np.random.normal(0, 120, n_days)
    for campaign_start in (10, 45):
        end = min(campaign_start + 4, n_days)
        marketing_spend[campaign_start:end] += 1800

    # --- decoy 3: complaint sentiment — a SYMPTOM starting 1 day into the window, not a lead ---
    complaint_sentiment_score = 0.78 + np.random.normal(0, 0.018, n_days)
    complaint_sentiment_score = np.where(
        day_idx >= window_start_idx + 1, complaint_sentiment_score - 0.07, complaint_sentiment_score
    )
    complaint_sentiment_score = np.clip(complaint_sentiment_score, 0, 1)

    df = pd.DataFrame({
        "date": dates,
        "region": region,
        "revenue": revenue.round(2),
        "avg_price": avg_price.round(2),
        "inventory_level": inventory_level.round(0),
        "marketing_spend": marketing_spend.round(2),
        "complaint_sentiment_score": complaint_sentiment_score.round(3),
    })

    event = AnomalyEvent(
        metric="revenue",
        region=region,
        window_start=dates[window_start_idx].date().isoformat(),
        window_end=dates[window_end_idx].date().isoformat(),
        magnitude=round(float(price_effect[window_start_idx:window_end_idx + 1].mean()), 3),
    )
    return df, event


def compute_cross_correlations(df, metric_col, feature_cols, window_end, lags=LAG_GRID_DAYS):
    indexed = df.set_index("date").sort_index()
    indexed = indexed.loc[:window_end]
    metric = indexed[metric_col]

    results = []
    for feature in feature_cols:
        scored_lags = []
        for lag in lags:
            shifted = indexed[feature].shift(lag)  # shifted[d] = feature value `lag` days before d
            paired = pd.concat([metric, shifted], axis=1).dropna()
            if len(paired) < 10:
                continue
            r, _ = pearsonr(paired.iloc[:, 0], paired.iloc[:, 1])
            scored_lags.append((lag, round(float(r), 4)))
        if not scored_lags:
            continue
        best_lag, best_r = max(scored_lags, key=lambda pair: abs(pair[1]))
        results.append({
            "driver": feature,
            "correlation": round(float(best_r), 3),
            "lag_days": int(best_lag),
            "_all_lags": scored_lags,
        })
    return sorted(results, key=lambda r: abs(r["correlation"]), reverse=True)


def run_granger_test(df, metric_col, feature_col, maxlag=4, alpha=0.05):
    weekly = df.set_index("date")[[metric_col, feature_col]].resample("W").mean().dropna()
    if len(weekly) < maxlag + 3:
        return {"tested": False, "reason": "insufficient history after weekly resampling"}
    try:
        test_result = grangercausalitytests(weekly[[metric_col, feature_col]].values, maxlag=maxlag, verbose=False)
    except Exception as exc:
        return {"tested": False, "reason": f"test failed: {exc}"}
    p_values = {lag: round(test_result[lag][0]["ssr_ftest"][1], 4) for lag in test_result}
    best_lag = min(p_values, key=p_values.get)
    return {
        "tested": True,
        "best_lag_weeks": best_lag,
        "p_value": p_values[best_lag],
        "precedence": bool(p_values[best_lag] < alpha),
    }


def train_and_explain(df, metric_col, feature_cols, lag_by_feature, window_start, window_end):
    indexed = df.set_index("date").sort_index()
    model_df = pd.DataFrame(index=indexed.index)
    model_df[metric_col] = indexed[metric_col]

    aligned_cols = []
    for feature in feature_cols:
        lag = lag_by_feature.get(feature, 0)
        col = f"{feature}__lag{lag}"
        model_df[col] = indexed[feature].shift(lag)
        aligned_cols.append(col)

    model_df = model_df.dropna()
    X, y = model_df[aligned_cols], model_df[metric_col]

    model = xgb.XGBRegressor(
        n_estimators=250, max_depth=3, learning_rate=0.05,
        subsample=0.85, colsample_bytree=0.9, random_state=7,
    )
    model.fit(X, y)

    explainer = shap.TreeExplainer(model)
    shap_values = pd.DataFrame(explainer.shap_values(X), columns=aligned_cols, index=X.index)

    window_shap = shap_values.loc[window_start:window_end]
    mean_abs = window_shap.abs().mean().astype("float64")  # SHAP returns float32; upcast before rounding
    total = mean_abs.sum()
    normalized = (mean_abs / total) if total > 0 else mean_abs * 0

    contribution_by_feature = {
        feature: round(float(normalized[f"{feature}__lag{lag_by_feature.get(feature, 0)}"]), 3)
        for feature in feature_cols
    }
    return contribution_by_feature, model, shap_values


HISTORICAL_INCIDENT_LOG = [
    {
        "event_id": "evt_00042",
        "date": "2026-03-02",
        "confirmed_cause": "Regional price increase on flagship SKU; demand response lagged about a week.",
        "signature": {"avg_price": 0.71, "inventory_level": 0.06, "marketing_spend": 0.09, "complaint_sentiment_score": 0.14},
    },
    {
        "event_id": "evt_00031",
        "date": "2025-11-18",
        "confirmed_cause": "Competitor flash sale drew volume away during a paid-media pause.",
        "signature": {"avg_price": 0.05, "inventory_level": 0.12, "marketing_spend": 0.68, "complaint_sentiment_score": 0.15},
    },
    {
        "event_id": "evt_00025",
        "date": "2025-09-07",
        "confirmed_cause": "Warehouse stockout on the top SKU cut fulfillable demand for five days.",
        "signature": {"avg_price": 0.08, "inventory_level": 0.74, "marketing_spend": 0.06, "complaint_sentiment_score": 0.12},
    },
]


def cosine_similarity(vec_a: dict, vec_b: dict, keys):
    a = np.array([vec_a[k] for k in keys], dtype=float)
    b = np.array([vec_b[k] for k in keys], dtype=float)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom else 0.0


def query_historical_precedent(current_signature, log, keys=CANDIDATE_FEATURES, threshold=0.85):
    if not log:
        return None
    scored = [(incident, cosine_similarity(current_signature, incident["signature"], keys)) for incident in log]
    best_incident, best_score = max(scored, key=lambda pair: pair[1])
    if best_score < threshold:
        return None
    return {
        "matched_event_id": best_incident["event_id"],
        "date": best_incident["date"],
        "confirmed_cause": best_incident["confirmed_cause"],
        "confidence": round(best_score, 3),
    }


def correlate_drivers(anomaly_event: AnomalyEvent, metrics_df: pd.DataFrame, historical_log: list,
                       candidate_features=CANDIDATE_FEATURES, lags=LAG_GRID_DAYS, top_n_granger=2):
    metric_col = anomaly_event.metric
    w_start, w_end = anomaly_event.window_start, anomaly_event.window_end

    corr = compute_cross_correlations(metrics_df, metric_col, candidate_features, w_end, lags)
    top_ids = {r["driver"] for r in corr[:top_n_granger]}
    for r in corr:
        if r["driver"] in top_ids:
            g = run_granger_test(metrics_df, metric_col, r["driver"])
            r["precedence"] = bool(g.get("precedence", False))
        else:
            r["precedence"] = False

    lag_by_feature = {r["driver"]: r["lag_days"] for r in corr}
    shap_contribution, _, _ = train_and_explain(metrics_df, metric_col, candidate_features, lag_by_feature, w_start, w_end)
    for r in corr:
        r["shap_contribution"] = shap_contribution.get(r["driver"], 0.0)

    correlation_result = [
        {"driver": r["driver"], "correlation": r["correlation"], "lag_days": r["lag_days"],
         "shap_contribution": r["shap_contribution"], "precedence": r["precedence"]}
        for r in sorted(corr, key=lambda r: r["shap_contribution"], reverse=True)
    ]
    precedent = query_historical_precedent(shap_contribution, historical_log)
    return correlation_result, precedent


def load_precedent_log(path: str = 'historical_precedent_log.jsonl') -> list[dict]:
    """
    Reads the persisted historical precedent log written by scheduler.py
    and merges it with HISTORICAL_INCIDENT_LOG.
    
    Each line in the JSONL must have: event_id, date, confirmed_cause, signature.
    Returns combined list (disk records first, then hardcoded fallback for any
    event_ids not already in the disk records).
    
    If file doesn't exist, returns HISTORICAL_INCIDENT_LOG unchanged.
    """
    if not os.path.exists(path):
        return list(HISTORICAL_INCIDENT_LOG)
    
    disk_records = []
    existing_ids = set()
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                if 'event_id' in record and 'signature' in record:
                    disk_records.append(record)
                    existing_ids.add(record['event_id'])
    except Exception:
        pass
    
    # Merge: disk records + hardcoded fallback for IDs not in disk
    fallback = [r for r in HISTORICAL_INCIDENT_LOG if r['event_id'] not in existing_ids]
    return disk_records + fallback


def append_incident_to_log(incident: dict, path: str = 'historical_precedent_log.jsonl') -> None:
    """
    Appends a new confirmed incident to the persistent JSONL log.
    incident must have: event_id, date, confirmed_cause, signature (dict of driver_id -> float contribution).
    Called by scheduler.py when an anomaly is confirmed and labeled.
    """
    with open(path, 'a') as f:
        f.write(json.dumps(incident) + '\n')
