"""
storage.py
Step 5 of the ingest pipeline: persist MetricsTable and DocumentStore so
they're queryable by downstream modules (detect, correlate, retrieve).

Backend: DuckDB if it's installed (the brief's first suggestion, and a
good fit -- embedded, columnar, zero-ops, real SQL), else SQLite (stdlib,
always available) as a same-day fallback so the module never blocks on an
install. This sandbox has no DuckDB and no network access to install it,
so it's running on the SQLite path -- swap point for a real deployment:
point `_connect()` at Postgres instead; every other function here is plain
SQL and backend-agnostic.
"""
from __future__ import annotations

import json

import pandas as pd

try:
    import duckdb
    BACKEND = "duckdb"
except ImportError:
    import sqlite3
    BACKEND = "sqlite"


def _connect(db_path: str):
    if BACKEND == "duckdb":
        return duckdb.connect(db_path)
    return sqlite3.connect(db_path)


def save_metrics_table(df: pd.DataFrame, db_path: str, table: str = "metrics_table") -> None:
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    con = _connect(db_path)
    if BACKEND == "duckdb":
        con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM out")
    else:
        out.to_sql(table, con, if_exists="replace", index=False)
    con.close()


def save_document_store(df: pd.DataFrame, db_path: str, table: str = "document_store") -> None:
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    # JSON-encode array-typed columns for portability across both backends
    # (SQLite has no native array/list column type; DuckDB does, but we
    # keep one code path rather than branching storage logic on backend).
    out["region_tags"] = out["region_tags"].apply(json.dumps)
    out["entity_tags"] = out["entity_tags"].apply(json.dumps)
    con = _connect(db_path)
    if BACKEND == "duckdb":
        con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM out")
    else:
        out.to_sql(table, con, if_exists="replace", index=False)
    con.close()


def query(db_path: str, sql: str) -> pd.DataFrame:
    """Run arbitrary SQL against either backend and get a DataFrame back --
    this is the "queryable" part of the brief's requirement."""
    con = _connect(db_path)
    result = con.execute(sql).fetchdf() if BACKEND == "duckdb" else pd.read_sql_query(sql, con)
    con.close()
    return result


def sample_rows(db_path: str, table: str, n: int = 5) -> list[dict]:
    """Fetch `n` rows shaped exactly like the brief's JSON examples
    (array fields as real Python lists, not JSON strings)."""
    df = query(db_path, f"SELECT * FROM {table} LIMIT {n}")
    for col in ("region_tags", "entity_tags"):
        if col in df.columns:
            df[col] = df[col].apply(json.loads)
    return df.to_dict(orient="records")
