# Task 6 — Synthesize, score confidence, handle ambiguity

Join point for Task 4 (`CorrelationResult`) and Task 5 (`RetrievedEvidence`). Turns
an anomaly plus its structured drivers and retrieved evidence into a cited,
confidence-scored `StoryOutput`.

## Files

| File | Purpose |
|---|---|
| `schemas.py` | `AnomalyEvent`, `StructuredDriver` / `CorrelationResult`, `EvidenceSource` / `RetrievedEvidence`, `Hypothesis`, `StoryOutput` |
| `mock_data.py` | `easy_case()` and `hard_case()` — hand-crafted Task 4/5 mocks for a day-one start |
| `llm_client.py` | Prompt construction, `LLMClient` protocol, `MockLLMClient`, `AnthropicLLMClient` |
| `scoring.py` | Programmatic confidence scoring + disagreement/escalation detection |
| `synthesize.py` | `synthesize(anomaly, correlation, evidence, llm_client) -> StoryOutput` — the orchestration function Task 7 will call |
| `demo.py` | Runs both mock cases end to end, prints the resulting JSON |
| `test_synthesize.py` | Unit + end-to-end tests, stdlib `unittest`, no network needed |

Run it:

```bash
cd task6_synthesize
python demo.py
python -m unittest test_synthesize.py -v
```

## How confidence is computed

The brief's hard rule: **never take the model's self-rating**. The prompt in
`llm_client.py` doesn't even give the model a place to put a confidence number —
it only asks for an explanation, ranked hypotheses (each with citations back to a
`driver_id` or `source_id`), and next-step actions. Confidence is computed
afterward, in `scoring.py`, from three signals per hypothesis:

- **(a) Structured strength** — the cited driver's correlation/SHAP magnitude,
  normalized against the strongest driver for that anomaly.
- **(b) Source support** — count of *independent* (distinct-publisher) cited
  sources, with diminishing returns (1 source → 0.5, 2 → 0.67, 3 → 0.75, ...).
- **(c) Cross-modal agreement** — 1.0 if the hypothesis is backed by both a
  structured driver *and* an independent source, 0.5 if only one modality backs it.

These combine as a weighted sum (weights `STRUCTURED_WEIGHT` / `SOURCE_WEIGHT` /
`AGREEMENT_WEIGHT` at the top of `scoring.py`, currently 0.45 / 0.25 / 0.30),
clipped to `[0, 1]`. They're tunable constants, not derived — worth calibrating
against real Task 4/5 output once it exists rather than trusting the starting values.

**Hallucinated citations are not trusted.** `resolve_citations()` checks every
citation the model produced against the real `driver_id`s and `source_id`s it was
given. Anything that doesn't match is dropped and logged. A hypothesis that ends up
with zero valid citations — a bare assertion — is dropped entirely rather than kept
with a confidence score derived from nothing.

## How escalation works

`detect_disagreement()` sets `escalate_flag = True` on either condition from the
brief (checked independently, either one is sufficient):

1. **Close margin** — the top two hypotheses' confidence scores are within
   `DISAGREEMENT_MARGIN` (0.15) of each other.
2. **Cross-modal mismatch** — the single strongest structured driver and the
   single most-relevant retrieved source back *different* hypotheses. This can fire
   even when the margin is wide — see
   `test_cross_modal_conflict_escalates_despite_wide_margin` in
   `test_synthesize.py` for a case where structured data and the top news source
   flatly point at different causes, and escalation is still correct even though
   one hypothesis's score comfortably beats the other's.

The headline is also templated off the already-computed result rather than drafted
by the model (see the docstring on `_build_headline` in `synthesize.py`) — this
guarantees the headline's confidence language ("most likely driven by..." vs.
"unclear cause...") can never say something the computed score and escalate_flag
contradict.

## The two mock cases

- **`easy_case()`** — Region X revenue down 7.5%. One dominant driver (a July 4
  price increase) corroborated by two independent sources; a much weaker
  competitor-promo driver has only one, low-relevance source. `demo.py` runs this
  through the pipeline and gets `escalate_flag: false`, top confidence ~0.9+.
- **`hard_case()`** — Region Y signups down 12%. Two structurally close drivers
  (app crash rate, marketing spend cut), each backed by exactly one independent,
  non-overlapping source, with no third signal to break the tie. `escalate_flag: true`.

## Wiring in the real pieces

1. **Real Task 4 / Task 5 output**: the field names in `schemas.py` are this
   module's own mock design, since Task 4/5's real schemas hadn't shipped when
   this was written. Reconcile field names against the actual `CorrelationResult`
   / `RetrievedEvidence` the team agrees on — the scoring logic only needs each
   driver to expose an id + a numeric strength, and each source to expose an id +
   a publisher + a relevance score, so it should be a thin adapter, not a rewrite.
2. **Real LLM calls**: `pip install -r requirements.txt`, set `ANTHROPIC_API_KEY`,
   and pass `AnthropicLLMClient()` instead of `MockLLMClient(...)` to `synthesize()`.
   Everything else is unchanged — that's the point of the `LLMClient` protocol.
3. **Task 7 (orchestrate & deliver)**: calls `synthesize(anomaly, correlation,
   evidence, llm_client)` once both upstream tasks resolve for a given
   `anomaly_id`, and reads `escalate_flag` to decide whether the story goes out
   automatically or gets routed to a human first.

## One deliberate deviation from the brief's example JSON

The Process section asks for a "plain-language explanation of what changed" as one
of three things the model produces, but the sample `StoryOutput` JSON in the brief
doesn't show a field for it. `StoryOutput` here includes it as `explanation`
(separate from `headline`, which is the short templated summary line). Easy to drop
if the team wants to match the sample schema exactly instead — flagging it here
since it's a real discrepancy between the brief's prose and its example, not an
assumption I wanted to resolve silently.
