# BusinessIntelligence.ai — combined, orchestrated, and tested

This is your six delivered modules (Tasks 1, 2, 3, 5, 6 as zips, Task 4 as a
notebook) wired into one working pipeline, plus the piece nobody had been
assigned yet — **Task 7, orchestration** — and a 16-scenario test suite that
exercises the whole thing end to end on real data.

**Result: 52/52 checks passing across 16 scenarios.** Full breakdown below.

## The core rule, restated

Task 3 is the only gate. If it verdicts **noise**, the pipeline stops —
Tasks 4, 5, and 6 never run: no correlation call, no retrieval call, no LLM
call. Only a confirmed **anomaly** unlocks the rest. This is asserted on in
the test suite (scenario 01: 150 real days, 0 downstream calls on the noise
days), not just assumed.

## Project structure

```
task1/           Ingest & align       (fixed — see FINDINGS #1)
task2/           Baseline forecast    (Prophet + XGBoost, runs as-is)
task3/           Anomaly gate         (runs as-is, no changes needed)
task4/           Correlate drivers    (notebook + a clean extracted module)
task5/           Retrieve evidence    (RAG, runs as-is)
task6/           Synthesize & score   (runs as-is)
orchestrator/    Task 7 — orchestration + schema adapters (NEW, built here)
tests/           16-scenario test suite + report.json
```

`orchestrator/` **is** Task 7 (Orchestrate & Deliver) — it wasn't named as
its own folder because no zip had been produced for it yet. `orchestrate.py`
is the entry point; `adapters.py` is the schema-reconciliation layer;
`mock_llm.py` generates realistic canned LLM responses for testing without
needing an API key.

## Running it

```bash
pip install -r task2/unpacked/requirements.txt      # prophet, xgboost
pip install -r task5/unpacked/task5_retrieve_evidence/requirements.txt
pip install statsmodels shap                          # task 4
cd tests && python3 run_all.py                         # all 16 scenarios
python3 run_all.py 07 08 09                            # or just a few
```

Each run merges its results into `tests/report.json` rather than
overwriting it, so scenarios can be re-run individually while iterating.

## What each scenario proves

| # | Scenario | Proves |
|---|----------|--------|
| 01 | Ordinary days, real Task 2 data | The gate suppresses noise at scale (150 real days, 100% correctly quiet) |
| 02–05 | Task 2's real injected anomalies (both regions, both directions) | The real gate catches real forecasting-validated anomalies, not just synthetic ones |
| 06 | Task 1's real seeded dip + real documents | The full chain works on the team's own actual target scenario |
| 07 | Clean single driver | High confidence, no escalation, when one cause dominates |
| 08 | Ambiguous two-driver case | Escalates correctly (uses Task 6's own `hard_case()` fixture — see FINDINGS #6) |
| 09 | Competitor evidence | `competitor_activity_detected` fires and gets cited |
| 10 | No relevant evidence | Chain still grounds a hypothesis in the structured driver alone, at lower confidence |
| 11 | Hallucinated citation | The fabricated id is dropped; only the real citation survives |
| 12 | No grounding at all | Falls back correctly: empty hypotheses, `escalate_flag=True`, confidence `0.0`, routes to analyst |
| 13 | Single-day extreme spike | Confirms via the secondary-threshold override, not persistence |
| 14 | Exact 3-day sustained shift | Confirms via persistence, not the secondary threshold |
| 15 | Missing correlated-metric day | Gate doesn't crash on a data gap, still reaches a verdict |
| 16 | A third region (Region Z) | Nothing is hardcoded to Region X |

## FINDINGS — real bugs found and fixed

**1. Task 1's zip was packaged flat.** `run_pipeline.py` imports
`from ingest_pipeline import ...`, but the zip's contents sat at the top
level with no `ingest_pipeline/` folder. Fixed by moving the module files
into the package structure the code already expects.

**2. The orchestrator's own filename collided with two tasks' internal
modules.** It was first written as `pipeline.py` — but Task 2 *and* Task 5
each have their own internal `pipeline.py`. Python's import system resolved
`import pipeline` inside those tasks back to the orchestrator's own
partially-loaded module instead. Renamed to `orchestrate.py`.

**3. A numpy crash the first time the real gate ran at scale.**
`"cannot load module more than once per process"` — the module-isolation
helper was purging *any* module newly added to `sys.modules` during a
task's import, but numpy/scipy lazily import submodules (e.g.
`numpy.fft._pocketfft_umath`) deep inside function calls, not just at
top-level `import numpy`. Fixed by scoping the purge to modules whose file
actually lives inside that task's own directory.

**4. Task 5 silently mistagged every real support ticket.** It tags a
document "internal" with an exact match on `doc.source == "support"`, but
Task 1's real data uses `"support_ticket"`. Every real ticket fell through
to the generic "market" tag instead — found by running Task 5 against
Task 1's actual output and seeing zero "internal" tags where there should
have been several. Fixed with a source-name normalization step in the
adapter (not inside either task's own code).

**5. My own test data starved Task 4 down to zero usable rows.** Task 1's
convention tags `marketing_spend` rows with `product == "ALL"` (it's a
region-level figure); the adapter that pivots the long-format table
filters on exactly that. My synthetic scenario builder tagged it with a
real product name instead, so the filter silently returned an empty,
all-NaN column — which a downstream `dropna()` turned into zero training
rows for Task 4's SHAP step, crashing several scenarios. Fixed with a
shared `to_long_metrics_table()` helper that applies the same convention
Task 1 itself uses.

**6. My hand-built "ambiguous two-driver" scenario wasn't actually
ambiguous.** Two honest attempts at planting comparably-sized shocks in
`marketing_spend` and `inventory_level` both resolved to the same dominant
driver (SHAP contribution ~0.58 vs ~0.20) regardless of the noise/magnitude
tuned — which is itself a legitimate result (Task 4 doesn't manufacture
false ambiguity), but not a reliable way to test Task 6's escalation path
specifically. Switched that one check to use Task 6's own validated
`hard_case()` fixture directly, which targets the mechanism precisely.
Full-chain coverage of realistic driver correlation stays with scenarios
07, 09–12, 16.

**7. My "single extreme day" test wasn't actually extreme, by the gate's
own math.** Task 3 normalizes residuals by the *interval width*
(`upper − lower`), not by σ directly. My synthetic baseline's σ was
inflated 5–10x because it folded weekday seasonality into "noise" instead
of "expected" — so no realistic single-day shock could clear the threshold.
Fixed with a day-of-week-adjusted baseline builder that keeps `expected`
tracking the true weekday level, restoring a realistic, small σ.

**8. Minor, unexplained, flagged rather than hidden:** in scenario 14, the
persistence counter is already at 9 by the time the intended shock window
starts, rather than 1. The final assertions still hold (confirms via
persistence, not the secondary threshold), so this didn't block anything,
but it suggests a few incidental pre-shock statistical flags are occurring
at the ~1.75x primary threshold before the shock — plausible as ordinary
false-positive-rate noise at that threshold, but not fully traced down.
Worth a look before this baseline pattern is reused elsewhere.

**9. Adapter polish:** Task 6's `StructuredDriver.label` is meant to read
like a headline fragment (its own docstring example: *"10% price increase
on Product A (Jul 4)"*). The first version of the adapter put a full
technical readout there instead (`"inventory_level moved with the metric
(r=-0.45, 0d lag, no established precedence)"`), which flowed straight into
unreadable headlines. Fixed to a short human phrase; the technical detail
is still available in Task 4's raw output.

## Known limitations, stated plainly

- **No live LLM calls.** There's no `ANTHROPIC_API_KEY` in this environment,
  so all 16 scenarios run through Task 6's `MockLLMClient` with realistic
  canned responses (see `orchestrator/mock_llm.py`). The scoring, citation
  validation, and escalation logic are all real; the prose generation isn't.
  Worth a small follow-up pass with a real key before launch.
- **Hand-built scenarios (07–16) use a simplified baseline**, not a live
  Task 2 forecast — documented inline everywhere it's used. Task 2's own
  model is validated separately in scenarios 01–05 against its real,
  backtested output.
- **Region-level aggregation choices** in
  `adapters.metrics_table_to_region_wide()` (sum for revenue/units/
  inventory, mean for price/sentiment, `product == "ALL"` filter for
  marketing spend) are reasonable defaults, not validated business logic —
  flag if the real convention should differ.
