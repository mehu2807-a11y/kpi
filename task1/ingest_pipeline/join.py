"""
join.py
Step 3 of the ingest pipeline: join the structured tables into one wide
table on (date, region, product), then reshape to the long/EAV MetricsTable
format the brief's output spec requires: {date, region, product,
metric_name, value}.

Reshape note -- joining is naturally a *wide* operation (each source table
contributes columns); MetricsTable is a *long* table (one row per metric).
We build wide internally, then melt. That's the standard pattern, and it's
also how step 3's "one wide metrics table" instruction and the brief's long
-format JSON output example are both literally true, just at different
points in the same function.

Grain note -- marketing spend: the source table is (date, region, channel,
spend) with NO product column (see the brief's own schema). Broadcasting
the region's daily total onto every product row would silently multiply
true spend the moment anyone sums marketing_spend across products for a
region. Instead we keep the source grain and emit those rows with
product="ALL" (config.NO_PRODUCT_SENTINEL) -- "applies to the region as a
whole," not to one SKU. Downstream modules should branch on that sentinel
rather than assume every row is product-specific.

avg_price note: computed primarily as revenue / units_sold from the sales
table (the real transacted average price, discounts included). Where a
(date, region, product) has no sales that day but pricing_history still has
a price on file, we fall back to that list price, so avg_price has broader
day-to-day coverage for later trend/anomaly work.
"""
from __future__ import annotations

import pandas as pd

from . import config

METRIC_COLUMNS = ["revenue", "units_sold", "avg_price", "inventory_level", "marketing_spend"]
KEY = ["date", "region", "product"]


def build_wide_table(
    sales: pd.DataFrame,
    pricing_history: pd.DataFrame,
    inventory: pd.DataFrame,
    marketing_spend: pd.DataFrame,
) -> pd.DataFrame:
    wide = sales[KEY + ["units_sold", "revenue"]].copy()

    sales_price = sales[KEY + ["revenue", "units_sold"]].copy()
    sales_price["avg_price_sales"] = sales_price["revenue"] / sales_price["units_sold"].replace(0, pd.NA)
    wide = wide.merge(sales_price[KEY + ["avg_price_sales"]], on=KEY, how="left")

    price_list = pricing_history.rename(columns={"list_price": "avg_price_list"})[KEY + ["avg_price_list"]]
    wide = wide.merge(price_list, on=KEY, how="outer")
    wide["avg_price"] = wide["avg_price_sales"].combine_first(wide["avg_price_list"])
    wide = wide.drop(columns=["avg_price_sales", "avg_price_list"])

    inv = inventory.rename(columns={"stock_level": "inventory_level"})[KEY + ["inventory_level"]]
    wide = wide.merge(inv, on=KEY, how="outer")
    # NaN in revenue/units_sold after these outer merges is expected and
    # meaningful: "no sales activity recorded that day," not zero and not
    # an ingestion error. We deliberately do NOT fillna(0) here -- coercing
    # to zero would tell a downstream anomaly detector that demand hit
    # exactly zero, which is a much stronger (and usually false) claim.

    mkt = (
        marketing_spend.groupby(["date", "region"], as_index=False)["spend"]
        .sum()
        .rename(columns={"spend": "marketing_spend"})
    )
    mkt["product"] = config.NO_PRODUCT_SENTINEL

    return pd.concat([wide, mkt], ignore_index=True, sort=False)


def melt_to_metrics_table(wide: pd.DataFrame) -> pd.DataFrame:
    present = [c for c in METRIC_COLUMNS if c in wide.columns]
    long_df = wide.melt(id_vars=KEY, value_vars=present, var_name="metric_name", value_name="value")
    long_df = long_df.dropna(subset=["value"]).reset_index(drop=True)
    long_df["value"] = long_df["value"].astype(float).round(4)  # tidy up float-division noise (e.g. avg_price)
    return long_df


def add_complaint_sentiment_metric(metrics_long: pd.DataFrame, document_store: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate per-document sentiment into a (date, region, product) metric
    cell, for documents where NER found enough to attribute them: at least
    one region tag AND at least one of our own product tags. Documents that
    only mention a competitor, or don't name a specific region/product,
    stay in DocumentStore (still useful for retrieval later) but aren't
    averaged into a metric cell they can't be confidently attributed to.
    """
    rows = []
    for doc in document_store.itertuples(index=False):
        products_mentioned = [e for e in doc.entity_tags if e in config.CANONICAL_PRODUCTS]
        for region in doc.region_tags:
            for product in products_mentioned:
                rows.append({"date": doc.date, "region": region, "product": product,
                              "sentiment_score": doc.sentiment_score})

    if not rows:
        return metrics_long

    agg = (
        pd.DataFrame(rows)
        .groupby(KEY, as_index=False)["sentiment_score"]
        .mean()
        .rename(columns={"sentiment_score": "value"})
    )
    agg["metric_name"] = "complaint_sentiment_score"
    agg = agg[KEY + ["metric_name", "value"]]

    return pd.concat([metrics_long, agg], ignore_index=True)
