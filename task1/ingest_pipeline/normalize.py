"""
normalize.py
Steps 1 & 2 of the ingest pipeline: normalize every timestamp to one
granularity/timezone, and standardize region/product naming via a lookup
table (config.REGION_LOOKUP / config.PRODUCT_LOOKUP).
"""
from __future__ import annotations

import re

import pandas as pd

from . import config


def _clean_key(raw) -> str:
    """Lowercase and collapse whitespace/underscore/hyphen/period runs to a
    single space, so 'PROD_A', 'prod-a', and 'Prod. A' all normalize to the
    same lookup key regardless of which separator a given source system
    happens to use."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return ""
    s = str(raw).strip().lower()
    s = re.sub(r"[\s_.\-]+", " ", s)
    return s.strip()


def canonicalize_region(raw_region) -> str:
    key = _clean_key(raw_region)
    if key in config.REGION_LOOKUP:
        return config.REGION_LOOKUP[key]
    if raw_region in config.CANONICAL_REGIONS:
        return raw_region
    return f"UNMAPPED:{raw_region}"


def canonicalize_product(raw_product) -> str:
    key = _clean_key(raw_product)
    if key in config.PRODUCT_LOOKUP:
        return config.PRODUCT_LOOKUP[key]
    if raw_product in config.CANONICAL_PRODUCTS:
        return raw_product
    return f"UNMAPPED:{raw_product}"


def standardize_regions(df: pd.DataFrame, col: str = "region") -> pd.DataFrame:
    out = df.copy()
    out[col] = out[col].map(canonicalize_region)
    n_unmapped = out[col].astype(str).str.startswith("UNMAPPED:").sum()
    if n_unmapped:
        print(f"[standardize_regions] WARNING: {n_unmapped} rows had a region with no lookup entry -- "
              f"flagged as UNMAPPED rather than silently dropped or guessed.")
    return out


def standardize_products(df: pd.DataFrame, col: str = "product") -> pd.DataFrame:
    out = df.copy()
    out[col] = out[col].map(canonicalize_product)
    n_unmapped = out[col].astype(str).str.startswith("UNMAPPED:").sum()
    if n_unmapped:
        print(f"[standardize_products] WARNING: {n_unmapped} rows had a product with no lookup entry -- "
              f"flagged as UNMAPPED rather than silently dropped or guessed.")
    return out


def normalize_timestamps(df: pd.DataFrame, date_col: str = "date", source_tz: str | None = None) -> pd.DataFrame:
    """
    Parse `date_col`, localize/convert to config.TARGET_TIMEZONE, and floor
    to config.TARGET_GRANULARITY (daily by default), matching the brief's
    step 1: "one granularity ... and one timezone."

    source_tz: pass this if the source system's timestamps are known to be
    naive-local in a specific zone, so we localize correctly before
    converting. If left as None, naive timestamps are assumed to already be
    UTC -- a safe default for daily-grain business data with no
    time-of-day component (true for every table in this module's sample
    schema), but flip it per-source once a table's real source timezone is
    confirmed.
    """
    out = df.copy()
    ts = pd.to_datetime(out[date_col], errors="coerce")

    if ts.dt.tz is None:
        if source_tz:
            ts = ts.dt.tz_localize(source_tz, ambiguous="infer", nonexistent="shift_forward")
            ts = ts.dt.tz_convert(config.TARGET_TIMEZONE)
        else:
            ts = ts.dt.tz_localize(config.TARGET_TIMEZONE)
    else:
        ts = ts.dt.tz_convert(config.TARGET_TIMEZONE)

    floored = ts.dt.floor(config.TARGET_GRANULARITY)
    out[date_col] = pd.to_datetime(floored.dt.date)

    n_bad = out[date_col].isna().sum()
    if n_bad:
        # Surfaced rather than silently dropped -- route to a dead-letter
        # table for follow-up in a real deployment.
        print(f"[normalize_timestamps] WARNING: {n_bad} unparseable timestamps in '{date_col}'")
    return out
