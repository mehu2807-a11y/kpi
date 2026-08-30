"""
run_pipeline.py
Task 1 -- Ingest & time-align. Entry point.

Runs the full pipeline against the agreed sample schema: raw
structured/unstructured sample data -> normalized, joined MetricsTable +
DocumentStore, persisted and queryable.

    python3 run_pipeline.py

Produces bi_pipeline.db (SQLite in this environment; see
ingest_pipeline/storage.py for the DuckDB swap point) with two tables:
metrics_table and document_store.
"""
from __future__ import annotations

import json

import pandas as pd

from ingest_pipeline import join, normalize, sample_data, storage, text_features

DB_PATH = "bi_pipeline.db"


def run(db_path: str = DB_PATH) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = sample_data.generate_all()

    # --- Steps 1 & 2: normalize timestamps, standardize region/product names
    sales = normalize.standardize_products(normalize.standardize_regions(
        normalize.normalize_timestamps(raw["sales"])))
    pricing = normalize.standardize_products(normalize.standardize_regions(
        normalize.normalize_timestamps(raw["pricing_history"])))
    inventory = normalize.standardize_products(normalize.standardize_regions(
        normalize.normalize_timestamps(raw["inventory"])))
    marketing = normalize.standardize_regions(
        normalize.normalize_timestamps(raw["marketing_spend"]))  # no product column to standardize

    # --- Step 4: sentiment + NER on unstructured text, ahead of the metrics
    # merge below, since complaint_sentiment_score needs it as an input.
    document_store = pd.DataFrame([text_features.process_document(**doc) for doc in raw["documents"]])
    document_store = normalize.normalize_timestamps(document_store)

    # --- Step 3: join structured tables into wide, melt to MetricsTable,
    # then fold in the sentiment-derived metric.
    wide = join.build_wide_table(sales, pricing, inventory, marketing)
    metrics_table = join.melt_to_metrics_table(wide)
    metrics_table = join.add_complaint_sentiment_metric(metrics_table, document_store)
    metrics_table = metrics_table.sort_values(["date", "region", "product", "metric_name"]).reset_index(drop=True)

    # --- Step 5: load both into a queryable store
    storage.save_metrics_table(metrics_table, db_path)
    storage.save_document_store(document_store, db_path)

    return metrics_table, document_store


if __name__ == "__main__":
    metrics_table, document_store = run()

    print(f"backend: {storage.BACKEND}")
    print(f"MetricsTable : {len(metrics_table):,} rows")
    print(f"DocumentStore: {len(document_store):,} rows")

    print(f"\nMetricsTable metric_name counts:")
    print(metrics_table["metric_name"].value_counts().to_string())

    print("\nSample MetricsTable rows:")
    print(json.dumps(storage.sample_rows(DB_PATH, "metrics_table", 5), indent=2, default=str))

    print("\nSample DocumentStore rows:")
    print(json.dumps(storage.sample_rows(DB_PATH, "document_store", 3), indent=2, default=str))

    print("\nQuery demo -- Region X / Product A revenue, last 6 days:")
    demo = storage.query(
        DB_PATH,
        """
        SELECT date, value AS revenue
        FROM metrics_table
        WHERE region = 'Region X' AND product = 'Product A' AND metric_name = 'revenue'
        ORDER BY date DESC LIMIT 6
        """,
    )
    print(demo.to_string(index=False))
