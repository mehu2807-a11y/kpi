"""
anomaly_gate.py — Task 3 of the BusinessIntelligence.ai pipeline (the noise filter)

Role: ML Engineer (Anomaly Detection / Applied Statistics)

Decides, for one (metric, region, date) check, whether an observed deviation
from the baseline forecast is worth acting on ("anomaly") or is ordinary
day-to-day noise ("noise"). Only records this module marks "anomaly" are
allowed to trigger Task 4 (correlate drivers) / Task 5 (retrieve evidence).

Six-step pipeline (mirrors the brief exactly):
    1. normalized_residual()       -- normalized residual
    2. statistical_flag()          -- primary threshold test (~1.5-2x)
    3. MultivariateChecker.score() -- Isolation Forest across correlated metrics
    4. persistence_check()         -- 3+ consecutive periods, OR single-period 3x
    5. severity_score()            -- weighted blend x persistence multiplier
    6. run_gate()                  -- decision + NoiseLog / AnomalyEvent assembly

Two spots in the brief were genuinely ambiguous. Rather than silently pick one,
both are called out here AND in the README:

  * Step 1's formula is explicit: residual = (actual-expected)/(upper-lower),
    i.e. normalized by the FULL interval width. Step 2 then describes the
    threshold as "~1.5-2x the interval HALF-width." Taken literally those two
    lines don't compose (a residual defined on full-width can't be compared
    to a half-width multiple without a factor of 2 somewhere). This module
    implements step 1's formula exactly as written, and applies the "1.5-2x"
    figure directly as the threshold on that residual (default 1.75, fully
    tunable via GateConfig.primary_threshold) -- i.e. it treats "1.5-2x" as
    the intended threshold value, and treats "half-width" as loose phrasing
    rather than a second, conflicting formula to reconcile.

  * Step 5 says severity is "a weighted blend of normalized residual,
    Isolation Forest score, and a persistence multiplier." A multiplier is
    naturally multiplicative, not a third additive term, so this module
    computes severity = (w1*residual_component + w2*multivariate_score) *
    persistence_multiplier, clipped to [0,1]. This also matches the brief's
    core design principle ("if it's noise, the system does nothing"): a
    single-period, moderate deviation gets its severity damped down by a
    sub-1.0 multiplier unless it persists or is extreme, rather than being
    added to blindly.

ARCHITECTURE NOTE: run_gate() returns a (record, internal) tuple. `record` is
exactly the public NoiseLog / AnomalyEvent schema (what gets written to those
tables / handed to Task 4+5). `internal` carries what the ORCHESTRATOR needs
to maintain rolling state across days (today's flag, today's residuals) --
info that a compact NoiseLog row deliberately doesn't carry, but that the
persistence check (step 4) needs on every subsequent day, including days
that resolved as "noise". Keeping it out of `record` keeps the logged schema
exactly as specified instead of overloading it with pipeline plumbing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import IsolationForest


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class MetricCheck:
    """One (date, region, metric) row from MetricsTable + BaselineForecast."""
    date: str
    region: str
    metric: str
    actual_value: float
    expected_value: float
    lower_bound: float
    upper_bound: float


@dataclass
class GateConfig:
    # Step 2 -- primary statistical threshold on the normalized residual.
    # Brief: "start around 1.5-2x ... tune from there." Default = midpoint.
    primary_threshold: float = 1.75

    # Step 4 -- secondary, stricter single-period threshold ("e.g. 3x").
    secondary_threshold: float = 3.0
    min_consecutive: int = 3

    # Step 3 -- Isolation Forest window over correlated-metric residual vectors.
    history_window: int = 60
    min_history_for_multivariate: int = 14
    iso_forest_contamination: float = 0.1
    iso_forest_n_estimators: int = 200
    iso_forest_seed: int = 42

    # Step 5 -- blend weights (should sum to 1.0) and persistence multiplier ladder.
    w_residual: float = 0.5
    w_multivariate: float = 0.5
    persistence_multiplier_none: float = 0.40   # not flagged yesterday, not flagged today
    persistence_multiplier_one: float = 0.55    # flagged 1 consecutive period
    persistence_multiplier_two: float = 0.75    # flagged 2 consecutive periods
    persistence_multiplier_confirmed: float = 1.00  # 3+ periods, OR secondary threshold breach

    # Step 6 -- decision boundary on severity_score.
    severity_threshold: float = 0.5

    def __post_init__(self):
        total = self.w_residual + self.w_multivariate
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"w_residual + w_multivariate must sum to 1.0, got {total}")


@dataclass
class GateInternal:
    """Everything the orchestrator needs to update rolling state, but that
    doesn't belong in the public NoiseLog / AnomalyEvent record."""
    metric: str
    region: str
    flagged_today: bool
    residual: float
    correlated_residuals: dict[str, float]


class EventCounter:
    """Generates evt_00001, evt_00002, ... ids for confirmed anomalies."""
    def __init__(self, start: int = 1):
        self._n = start

    def next_id(self) -> str:
        eid = f"evt_{self._n:05d}"
        self._n += 1
        return eid


class JsonlLog:
    """Minimal append-only JSONL sink, standing in for NoiseLog / AnomalyEvents tables."""
    def __init__(self, path: str):
        self.path = path
        self._fh = open(path, "a")

    def write(self, record: dict) -> None:
        self._fh.write(json.dumps(record) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


class RegionHistory:
    """
    Rolling state for one region: trailing normalized residuals per metric
    (feeds the multivariate check's history window) and trailing flagged_today
    booleans per metric (feeds the persistence check). Owned by the caller,
    one instance per region, updated once per day via `.push(internal)` using
    the GateInternal returned by run_gate.
    """
    def __init__(self, max_history: int = 120):
        self.max_history = max_history
        self.residuals: dict[str, list[float]] = {}
        self.flags: dict[str, list[bool]] = {}

    def residual_history(self) -> dict[str, list[float]]:
        return self.residuals

    def flag_history(self, metric: str) -> list[bool]:
        return self.flags.get(metric, [])

    def push(self, internal: GateInternal) -> None:
        # primary metric: record both its residual and its flag
        self._push_residual(internal.metric, internal.residual)
        self._push_flag(internal.metric, internal.flagged_today)
        # correlated metrics: record residuals only (no independent gate ran for them)
        for m, r in internal.correlated_residuals.items():
            self._push_residual(m, r)

    def _push_residual(self, metric: str, value: float) -> None:
        lst = self.residuals.setdefault(metric, [])
        lst.append(value)
        if len(lst) > self.max_history:
            del lst[: len(lst) - self.max_history]

    def _push_flag(self, metric: str, value: bool) -> None:
        lst = self.flags.setdefault(metric, [])
        lst.append(value)
        if len(lst) > self.max_history:
            del lst[: len(lst) - self.max_history]


# ---------------------------------------------------------------------------
# Step 1 -- normalized residual
# ---------------------------------------------------------------------------

def normalized_residual(check: MetricCheck) -> float:
    width = check.upper_bound - check.lower_bound
    if width <= 0:
        raise ValueError(
            f"Non-positive interval width for {check.metric}/{check.region}/{check.date} "
            f"(lower={check.lower_bound}, upper={check.upper_bound})"
        )
    return (check.actual_value - check.expected_value) / width


# ---------------------------------------------------------------------------
# Step 2 -- statistical test
# ---------------------------------------------------------------------------

def statistical_flag(residual: float, threshold: float) -> bool:
    return abs(residual) > threshold


# ---------------------------------------------------------------------------
# Step 3 -- multivariate check (Isolation Forest across correlated metrics)
# ---------------------------------------------------------------------------

class MultivariateChecker:
    """
    Fits an Isolation Forest on trailing normalized-residual vectors (one
    vector per day, one dimension per metric) for a region, then scores
    today's vector against that recent history.
    """
    def __init__(self, config: GateConfig):
        self.config = config

    def score(self, history_vectors: np.ndarray, today_vector: np.ndarray):
        """
        history_vectors : shape (n_days, n_metrics), trailing days, NOT incl. today.
        today_vector    : shape (n_metrics,)

        Returns (is_outlier: bool, outlier_score: float in [0,1], status: str)
        outlier_score is scaled relative to the fitting window's own score
        distribution (0 = as normal as the most typical recent day, 1 = as
        unusual as the most unusual recent day or worse).
        """
        n_days = history_vectors.shape[0]
        if n_days < self.config.min_history_for_multivariate:
            return False, 0.0, "skipped_insufficient_history"

        window = history_vectors[-self.config.history_window:]

        model = IsolationForest(
            contamination=self.config.iso_forest_contamination,
            random_state=self.config.iso_forest_seed,
            n_estimators=self.config.iso_forest_n_estimators,
        )
        model.fit(window)

        today = today_vector.reshape(1, -1)
        is_outlier = bool(model.predict(today)[0] == -1)

        window_scores = -model.score_samples(window)
        today_score = -model.score_samples(today)[0]
        lo, hi = window_scores.min(), window_scores.max()
        if hi > lo:
            outlier_score = float(np.clip((today_score - lo) / (hi - lo), 0.0, 1.0))
        else:
            outlier_score = 0.0

        return is_outlier, outlier_score, "ok"


# ---------------------------------------------------------------------------
# Step 4 -- persistence check
# ---------------------------------------------------------------------------

def persistence_check(flag_history: list[bool], flagged_today: bool, residual: float,
                       config: GateConfig):
    """
    flag_history : prior days' (statistical OR multivariate) flags for this
                   (region, metric), oldest..newest, NOT including today.
    Returns (persistence_multiplier, consecutive_periods, secondary_threshold_breach)
    """
    consecutive = 1 if flagged_today else 0
    if flagged_today:
        for prior in reversed(flag_history):
            if prior:
                consecutive += 1
            else:
                break

    secondary_breach = abs(residual) >= config.secondary_threshold
    confirmed = consecutive >= config.min_consecutive or secondary_breach

    if confirmed:
        multiplier = config.persistence_multiplier_confirmed
    elif consecutive == 2:
        multiplier = config.persistence_multiplier_two
    elif consecutive == 1:
        multiplier = config.persistence_multiplier_one
    else:
        multiplier = config.persistence_multiplier_none

    return multiplier, consecutive, secondary_breach


# ---------------------------------------------------------------------------
# Step 5 -- severity score
# ---------------------------------------------------------------------------

def severity_score(residual: float, multivariate_score: float,
                    persistence_multiplier: float, config: GateConfig) -> float:
    residual_component = float(np.clip(abs(residual) / config.secondary_threshold, 0.0, 1.0))
    blend = config.w_residual * residual_component + config.w_multivariate * multivariate_score
    return float(np.clip(blend * persistence_multiplier, 0.0, 1.0))


# ---------------------------------------------------------------------------
# Step 6 -- decision + output assembly
# ---------------------------------------------------------------------------

def run_gate(
    check: MetricCheck,
    correlated_checks: list[MetricCheck],
    history: RegionHistory,
    config: GateConfig,
    event_counter: EventCounter,
) -> tuple[dict, GateInternal]:
    """
    check              : today's primary-metric MetricCheck (e.g. metric="revenue").
    correlated_checks  : today's MetricCheck for each correlated metric, same date/region.
    history            : this region's RegionHistory, containing every prior day
                          UP TO BUT NOT INCLUDING today (caller pushes today's
                          GateInternal onto it AFTER calling run_gate).
    """
    residual = normalized_residual(check)
    stat_flag = statistical_flag(residual, config.primary_threshold)

    all_today = {c.metric: c for c in ([check] + correlated_checks)}
    metric_order = sorted(all_today.keys())
    today_vector = np.array([normalized_residual(all_today[m]) for m in metric_order])

    residual_hist = history.residual_history()
    history_len = min((len(residual_hist.get(m, [])) for m in metric_order), default=0)
    if history_len > 0:
        history_matrix = np.array([
            [residual_hist[m][i] for m in metric_order]
            for i in range(history_len)
        ])
    else:
        history_matrix = np.empty((0, len(metric_order)))

    # Exclude previously-flagged days from the Isolation Forest's reference
    # window. Without this, a persisting anomaly's own earlier days get
    # pushed into history and start defining a new "normal" for itself,
    # fading the multivariate signal out right when persistence (step 4)
    # needs it most. flag_hist is this metric's own flagged_today history,
    # pushed in lockstep with residual_hist by RegionHistory.push(), so the
    # indices line up 1:1 with history_matrix's rows.
    flag_hist_for_mask = history.flag_history(check.metric)
    clean_rows = [
        i for i in range(history_len)
        if i >= len(flag_hist_for_mask) or not flag_hist_for_mask[i]
    ]
    fit_matrix = history_matrix[clean_rows] if clean_rows else history_matrix[0:0]

    checker = MultivariateChecker(config)
    mv_flag, mv_score, mv_status = checker.score(fit_matrix, today_vector)
    mv_fit_rows = len(clean_rows)

    flagged_today = stat_flag or mv_flag
    flag_hist = history.flag_history(check.metric)
    persistence_multiplier, consecutive, secondary_breach = persistence_check(
        flag_hist, flagged_today, residual, config
    )

    severity = severity_score(residual, mv_score, persistence_multiplier, config)
    verdict = "anomaly" if severity >= config.severity_threshold else "noise"

    internal = GateInternal(
        metric=check.metric,
        region=check.region,
        flagged_today=flagged_today,
        residual=residual,
        correlated_residuals={c.metric: normalized_residual(c) for c in correlated_checks},
    )

    if verdict == "noise":
        record = {
            "date": check.date,
            "region": check.region,
            "metric": check.metric,
            "residual": round(residual, 4),
            "severity_score": round(severity, 4),
            "verdict": "noise",
        }
        return record, internal

    direction = "below_expected" if (check.actual_value - check.expected_value) < 0 else "above_expected"
    record = {
        "event_id": event_counter.next_id(),
        "metric_name": check.metric,
        "region": check.region,
        "date": check.date,
        "actual_value": check.actual_value,
        "expected_value": check.expected_value,
        "lower_bound": check.lower_bound,
        "upper_bound": check.upper_bound,
        "residual": round(residual, 4),
        "direction": direction,
        "severity_score": round(severity, 4),
        "verdict": "anomaly",
        "detection": {
            "statistical_flag": stat_flag,
            "multivariate_flag": mv_flag,
            "multivariate_status": mv_status,
            "multivariate_score": round(mv_score, 4),
            "multivariate_fit_rows": mv_fit_rows,
            "consecutive_flagged_periods": consecutive,
            "secondary_threshold_breach": secondary_breach,
            "persistence_multiplier": persistence_multiplier,
        },
        "correlated_metrics": [
            {
                "metric": c.metric,
                "actual_value": c.actual_value,
                "expected_value": c.expected_value,
                "residual": round(normalized_residual(c), 4),
            }
            for c in correlated_checks
        ],
    }
    return record, internal
