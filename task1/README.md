# Task 1 — Ingest & time-align

**Role:** Data Engineer · **Pipeline stage:** `detect` (feeds the anomaly-gate module)

Turns the messy, un-joined raw exports into two queryable outputs, exactly per spec:

- **`MetricsTable`** — `{date, region, product, metric_name, value}` (long/EAV format)
- **`DocumentStore`** — `{doc_id, date, source, region_tags[], entity_tags[], sentiment_score, raw_text}`

## Run it

```bash
python3 run_pipeline.py
```

No arguments, no setup. It generates the sample raw data, runs the full pipeline, writes
`bi_pipeline.db`, and prints row counts + a few sample rows in the exact output shape.

```python
from ingest_pipeline import storage
storage.query("bi_pipeline.db", "SELECT * FROM metrics_table WHERE region='Region X' LIMIT 10")
```

## Module map (mirrors the brief's 5 process steps)

| File | Step | Does |
|---|---|---|
| `ingest_pipeline/normalize.py` | 1, 2 | Timestamp → one timezone/granularity; region/product → canonical tag via lookup table |
| `ingest_pipeline/text_features.py` | 4 | Sentiment score + entity/region extraction on raw text |
| `ingest_pipeline/join.py` | 3 (+ tail of 4) | Structured tables → wide → melted to `MetricsTable`; folds in the sentiment-derived metric |
| `ingest_pipeline/storage.py` | 5 | Persists both tables to a queryable DB |
| `ingest_pipeline/config.py` | — | Canonical lookup tables, entity gazetteers, sentiment lexicon (the reference data steps 1/2/4 run against) |
| `ingest_pipeline/sample_data.py` | — | Synthetic raw inputs (see below) |
| `run_pipeline.py` | — | Orchestrates 1→5 in dependency order, entry point |

Execution order in `run_pipeline.py` is 1, 2, 4, 3, 5 rather than the brief's listed 1–5: step 3's
output needs `complaint_sentiment_score`, which only exists once step 4 has run. Each module still
maps 1:1 to a brief step; only the orchestrator's call order differs from the numbering.

## No file was uploaded, so this ships against sample data

There's no `uploaded_files` in this task, so `sample_data.py` generates synthetic raw exports that
match the brief's schema exactly — inconsistent region/product spellings, ~8% random gaps in sales,
a sparser pricing-history table, and marketing spend with no product column (all deliberate, see
below). It also seeds one real anomaly — a demand dip in the last 3 days for Region X / Product A,
paired with a cluster of negative support tickets right where the dip happens — so the output this
module hands off is something a later anomaly/correlation module could plausibly act on. **That's
scene-setting only: Task 1 stops at ingest & align, nothing here detects or explains the dip.**

Swap `sample_data.generate_all()` for real extract loaders whenever source access is ready —
every other module depends only on the column shapes defined here, never on this file.

## Assumptions & judgment calls

The brief didn't fully specify a few things. Here's what was assumed, and why:

1. **`pricing_history` schema wasn't given.** Assumed `(date, region, product, list_price)`.
   `avg_price` is computed primarily as `revenue / units_sold` from sales (the real transacted
   price, discounts included), falling back to `pricing_history.list_price` on days a product had
   pricing on file but no recorded sales. This gives `avg_price` broader day-to-day coverage
   without ever overriding an actual transacted price.

2. **`marketing_spend` has no product column** (`date, region, channel, spend` — matches the
   brief exactly). Broadcasting the region's daily total onto every product row would silently
   multiply true spend the moment anyone sums `marketing_spend` across products for a region.
   Instead, those rows keep the source grain and use `product = "ALL"` as an explicit sentinel
   ("applies to the region as a whole, not one SKU") rather than a number that looks product-level
   but isn't. **Downstream modules should branch on that sentinel**, not assume every
   `MetricsTable` row is product-specific.

3. **Sentiment + NER use a lexicon/gazetteer, not a trained model.** This sandbox has no network
   access to download spaCy/transformer models, and a hand-rolled lexicon needs zero setup — in
   keeping with the brief's "ready for parallel build, same day" goal. It's also arguably *more*
   precise here: we already own the canonical product/region/competitor vocabulary
   (`config.py`), so exact-match gazetteer tagging won't mis-tag the way a generic off-the-shelf
   NER model sometimes does on domain-specific names. The trade-off: it can't catch an entity
   nobody's added to the gazetteer yet (e.g. a brand-new competitor). Both `score_sentiment()` and
   `extract_entities()` sit behind a plain `text -> score` / `text -> tags` interface in
   `text_features.py` specifically so swapping in VADER or spaCy later is a one-file change.

4. **Storage backend: SQLite, not DuckDB.** The brief suggests either; DuckDB isn't installed in
   this sandbox and there's no network access to add it. `storage.py` auto-detects DuckDB and
   prefers it if present, otherwise falls back to SQLite (stdlib, always available) so the module
   never blocks on an install. Every function is plain SQL — pointing `_connect()` at Postgres
   later is the only change needed for a real deployment.

5. **`complaint_sentiment_score` only covers confidently-attributed documents.** It's only
   computed for `(date, region, product)` where a document's extracted tags include *both* a
   region and one of our own products. A ticket that only names a competitor, or doesn't mention
   a specific region/product, still lands in `DocumentStore` (useful for the retrieval module
   later) but isn't averaged into a metric cell it can't be confidently attributed to.

6. **Missing data stays missing, not zero.** A `(date, region, product)` with no recorded sales
   isn't filled in as `revenue: 0` — that row is simply absent from `MetricsTable` for that
   metric/day. Zero-filling would tell a downstream anomaly detector "demand hit exactly zero,"
   which is a much stronger and usually false claim versus "no data recorded."

## Validation performed

Ran end-to-end against the generated sample data and checked:

- **0** unmapped region/product values (every raw spelling variant resolved to a canonical tag)
- **0** duplicate `(date, region, product, metric_name)` cells in `MetricsTable` (join didn't fan out)
- `marketing_spend` rows use `product = "ALL"` exclusively, never a real product name
- `complaint_sentiment_score` for Region X / Product A goes consistently negative right where the
  seeded anomaly and negative-ticket cluster land — a coherence check, not a correctness guarantee

## Output shapes (for reference)

```json
{"date": "2026-07-14", "region": "Region X", "product": "Product A", "metric_name": "revenue", "value": 84200}
```
```json
{"doc_id": "news_00231", "date": "2026-07-12", "source": "Reuters", "region_tags": ["Region X"], "entity_tags": ["CompetitorCo"], "sentiment_score": -0.4, "raw_text": "..."}
```

`metric_name` takes one of: `revenue`, `units_sold`, `avg_price`, `inventory_level`,
`marketing_spend`, `complaint_sentiment_score`.

## Not in scope here

Detection, correlation, retrieval, scoring, and orchestration are separate modules with their own
task specs not yet provided — this module's only job is handing off a clean, queryable
`MetricsTable` + `DocumentStore` for those to build on.
