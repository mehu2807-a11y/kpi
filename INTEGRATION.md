# Integrating the dashboard with real data

`dashboard.html` is currently wired to a hardcoded `DATA` object at the top
of its `<script>` tag — five KPIs, one with a full anomaly story attached,
shaped exactly like the real `/analyze` response. This doc is the path from
that mockup to a dashboard reading real numbers.

## The three integration points

```
Your systems  →  Task 1 (ingest)  →  Orchestrator  →  app.py (/analyze)  →  dashboard.html
```

### 1. Get your real data into Task 1's shape

Task 1 expects a long-format table: `(date, region, product, metric_name, value)`,
plus a document store: `(doc_id, date, source, region_tags, entity_tags,
sentiment_score, raw_text)`. Right now both are populated by
`task1/ingest_pipeline/sample_data.py` — synthetic data, regenerated every
run. To use real data, replace that module's output with a real extract:

- Point `task1/ingest_pipeline/storage.py` at your actual warehouse (it
  already falls back cleanly between DuckDB and SQLite — swap in a real
  connection string).
- Whatever your source system calls things, normalize into the five metric
  names `kpi_contract.py` already knows: `revenue_total`, `units_sold`,
  `avg_price`, `marketing_spend`, `inventory_level` — or add new
  `KPIDefinition` entries there for anything else you're tracking.
- Keep the `product == "ALL"` convention for anything that's genuinely
  region-level (not product-level), like marketing spend — the adapter
  layer filters on that exact string.

### 2. Run the pipeline for real, on a schedule

`orchestrator/orchestrate.py`'s `run_end_to_end()` is the function a
scheduler would call — once per metric, per region, per day (see the
"Using it on your own data" section of `BusinessIntelligenceAI_README.md`
for the exact call). It already does the right thing on its own: if Task 3
verdicts noise, it returns immediately and nothing downstream runs.

### 3. Point the dashboard at `/analyze` instead of the mock object

`app.py` is the real HTTP layer already sitting in front of Task 6.
Today it's a manual tester (pick a backend, pick easy/hard, hit go) — the
missing piece is a route that runs the *whole* pipeline (Tasks 1-6, gated
by Task 3) rather than just Task 6 on a fixed test case. Two ways to close
that gap, smallest first:

**A. Minimal — reuse `/analyze` as-is.** Have your scheduler call
`orchestrate.run_end_to_end(...)` directly (not through Flask), and when it
returns a real anomaly, POST that `StoryOutput` + KPI value into a small
new Flask route, e.g. `/kpis/live`, that the dashboard polls instead of
using the hardcoded `DATA` object. This is the fastest path to a real demo.

**B. Complete — one route per KPI card.** Add `GET /kpis` (current value +
delta + noise/anomaly status for all five KPIs, from Task 1/3's real
output) and keep `POST /analyze` for the story detail, called only when a
card's status is `"anomaly"`. This matches how the dashboard is already
structured — one card triggers one story fetch, exactly like clicking a
card in `dashboard.html` today.

In `dashboard.html`, replace the `DATA` constant and the two `render*()`
calls at the bottom with:

```javascript
async function loadKpis() {
  const kpis = await fetch('/kpis').then(r => r.json());
  // merge into DATA, calling /analyze per anomaly card as needed
  renderGrid(); renderDetail();
}
loadKpis();
```

The rest of the file — cards, persona tabs, hypothesis list, structured
actions table, telemetry strip — needs no changes; it already renders
whatever shape `/analyze` returns, because that's what it was built against.

## Running everything together

```bash
cd project
pip install -r requirements.txt          # now includes flask + flask-cors
python3 app.py                           # backend, http://localhost:5000
# open dashboard.html directly in a browser for the presentation view,
# or serve it from Flask once you've wired the /kpis route above
```

See `BusinessIntelligenceAI_README.md` for the test suite and the
programmatic `orchestrate.run_end_to_end()` usage example.
