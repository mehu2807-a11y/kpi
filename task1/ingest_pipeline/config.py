"""
config.py
Canonical reference data for the ingest & time-align pipeline.

In production this would live in a managed reference-data table (or a small
config service) so new aliases can be added without a code deploy. It's
inlined here to keep the module runnable standalone against the "agreed
sample schema" the brief calls for.
"""
from __future__ import annotations

# --- Target normalization settings ------------------------------------------

TARGET_TIMEZONE = "UTC"
TARGET_GRANULARITY = "D"  # daily -- recommended by the brief for revenue-type metrics

# --- Region canonicalization --------------------------------------------------
# Raw spelling/casing/abbreviation -> canonical tag. Matching is
# case-insensitive and whitespace/underscore-normalized (see normalize.py).
# Canonical tags deliberately mirror the brief's own example ("Region X").

REGION_LOOKUP = {
    "us west": "Region X",       # matches US-West, us_west, US West, ...
    "united states west": "Region X",
    "usw": "Region X",
    "west us": "Region X",

    "us east": "Region Y",       # matches US-East, us_east, US East, ...
    "united states east": "Region Y",
    "use": "Region Y",
    "east us": "Region Y",

    "emea": "Region Z",
    "europe": "Region Z",
    "eu": "Region Z",
    "europe middle east africa": "Region Z",
}

# --- Product canonicalization -------------------------------------------------
# Only two forms per product are needed here (full word, and "prod X") --
# normalize.py's cleaning already collapses '_', '-', and '.' to a space,
# so PROD_A / prod-a / Prod. A / prod_a all resolve to the same "prod a" key.

PRODUCT_LOOKUP = {
    "product a": "Product A",
    "prod a": "Product A",

    "product b": "Product B",
    "prod b": "Product B",

    "product c": "Product C",
    "prod c": "Product C",
}

CANONICAL_REGIONS = sorted(set(REGION_LOOKUP.values()))
CANONICAL_PRODUCTS = sorted(set(PRODUCT_LOOKUP.values()))

# Sentinel for a metric with no product grain in its source table (e.g.
# marketing spend is tracked at (date, region, channel), never per SKU).
# See join.py for why we don't just broadcast the region total onto every
# product instead.
NO_PRODUCT_SENTINEL = "ALL"

# --- Entity gazetteers for lightweight NER ------------------------------------
# Dictionary/gazetteer matching, not a trained NER model. See
# text_features.py docstring for the reasoning and the production swap-in.

COMPETITOR_GAZETTEER = ["CompetitorCo", "RivalWorks"]
PRODUCT_GAZETTEER = CANONICAL_PRODUCTS   # reuse so entity tags line up with MetricsTable's own product values
REGION_GAZETTEER = CANONICAL_REGIONS     # same idea for regions

# --- Minimal sentiment lexicon -------------------------------------------------
# Small, hand-picked lexicon tuned for product/support text. Swap-in path:
# VADER or a fine-tuned classifier once the environment allows the
# dependency -- see text_features.py.

POSITIVE_WORDS = {
    "great", "excellent", "love", "loved", "amazing", "happy", "fast",
    "reliable", "smooth", "easy", "helpful", "responsive", "fixed",
    "improved", "impressed", "solid", "works", "recommend", "pleased",
    "resolved", "quick", "friendly", "seamless", "delight", "delighted",
    "satisfied", "great value",
}

NEGATIVE_WORDS = {
    "broken", "terrible", "bad", "worst", "slow", "delay", "delayed",
    "refund", "disappointed", "disappointing", "frustrated", "frustrating",
    "outage", "bug", "buggy", "crash", "crashed", "fail", "failed",
    "failure", "poor", "issue", "issues", "complaint", "unacceptable",
    "downtime", "error", "unreliable", "angry", "annoyed", "cancel",
    "cancelled", "overpriced", "confusing", "defective", "stuck",
}

NEGATIONS = {"not", "no", "never", "n't", "without", "hardly", "barely"}
