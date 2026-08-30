# Task 5 — Retrieve unstructured evidence (RAG)

Role: AI/ML Engineer (NLP & Retrieval). Implements the module as specced in the
project brief: given an `AnomalyEvent` + Task 4's `CorrelationResult`, retrieve
and rank supporting evidence from the `DocumentStore`, and separately flag any
competitor activity in that evidence.

Runs standalone against a hand-picked 18-document sample store, so it's
buildable and testable before Task 1 (ingest & embed) and Task 4 (correlate
drivers) exist — per the brief's "day-one start" input.

## Run it

```bash
pip install -r requirements.txt
python demo.py              # end-to-end run, prints RetrievedEvidence JSON
python test_retrieval.py    # precision/recall checks (or: pytest test_retrieval.py)
```

Both were just run against this exact code: `demo.py` returns 8/8 relevant
evidence items for the mock anomaly (no off-topic doc — the bike-lane and
employee-onboarding sample docs, which pass the date/region filters but are
topically unrelated — makes it into the top 8), and all 4 checks in
`test_retrieval.py` pass, including that every known-competitor document in
the anomaly's date/region window is surfaced in `competitor_documents`, and
that out-of-window/out-of-region documents never leak into either output.

## File layout

| File | Process step | Purpose |
|---|---|---|
| `schemas.py` | — | `AnomalyEvent`, `CorrelationResult`, `DocumentRecord`, `RetrievedEvidenceItem`, `RetrievalOutput` |
| `sample_data.py` | — | 18-doc day-one `DocumentStore` stand-in (10 relevant, 8 deliberately not) |
| `query_builder.py` | 1 | Builds the retrieval query from the anomaly + top drivers |
| `vector_index.py` | 2 | Metadata-filtered semantic search |
| `bm25_search.py` | 3 | Metadata-filtered keyword search for named entities |
| `rerank.py` | 4 | Merge + recency/relevance weighted rerank |
| `pipeline.py` | 5 | `retrieve_evidence()` — orchestrates 1–4 and does competitor tagging |
| `demo.py` | — | Runnable example with a mock anomaly + correlation result |
| `test_retrieval.py` | — | Precision/recall checks against hand-labelled sample docs |

## Assumptions worth flagging to the rest of the team

**`CorrelationResult`'s shape (Task 4's output) is inferred, not specced.**
Task 5's brief only says "used to enrich the retrieval query" and references
"top drivers." `schemas.py` assumes a `top_drivers: List[DriverSignal]` list,
where each driver has a `name`, `category` (`"competitor"` / `"market"` /
`"pricing"` / `"internal_ops"` / …), a `correlation_strength`, and an optional
named `entity`. Only `query_builder.py` and `pipeline.py`'s entity-term
selection touch this shape — reconciling it with Task 4's real output once
it exists is a small, contained change.

**"Known competitors" is a separate registry from what Task 4 flagged.**
`retrieve_evidence()` takes a `known_competitors` list distinct from
`correlation.competitor_entities()`. The idea: Task 4's correlated entity
drives a *targeted* BM25 query (process step 3), but the competitor-tagging
question in step 5 ("did a known competitor show up in the evidence at all")
should check against the company's full competitor registry, not just
whatever one entity Task 4 happened to statistically correlate for this
particular anomaly. In production `known_competitors` would likely come from
a shared config/reference table rather than being passed in by the caller
each time.

**Competitor surfacing isn't limited to the reranked top-K.** Step 5 says to
"surface any result where entity_tags includes a known competitor." Read
literally against the *whole* document store, that would flag ancient,
unrelated mentions of a competitor's name forever. Instead, `pipeline.py`
surfaces competitor-tagged docs from the same date/region-filtered candidate
pool used for retrieval (already scoped to this anomaly), but independent of
whether the reranker's top-K cutoff kept them in `evidence` — so a competitor
mention can't silently disappear just because three other documents scored
higher.

**Tag priority is competitor > internal > market.** A support ticket that
names a known competitor is tagged `"competitor"`, not `"internal"` — that's
the more useful signal for the inter-company question the brief calls out.

## What's a placeholder for Task 1's real vector index

This sandbox has no network path to a model hub, so `vector_index.py` embeds
with **TF-IDF + cosine similarity** rather than a real dense embedding model.
It validated well against the hand-labelled sample set (see numbers above),
but it's a bag-of-words stand-in, not a production embedding model.

The module is written so this is a one-file swap: `VectorIndex.__init__`
builds whatever representation it wants from the documents, and `.search()`
returns `ScoredDoc` objects — nothing in `pipeline.py`, `rerank.py`, or the
tests cares how the score was computed. When Task 1 ships its real
embedding-based index (OpenAI / Cohere / a local sentence-transformer, likely
backed by FAISS or pgvector), point `VectorIndex` at it and everything
downstream keeps working unchanged.

Similarly, `rerank.py` implements the brief's "simple recency + relevance
weighted score" option behind a `Reranker`-shaped interface, with a
`CrossEncoderReranker` stub showing where the brief's other option (a real
cross-encoder rerank) would slot in later.

## Output shape

`retrieve_evidence(...)` returns a `RetrievalOutput` with:

- `evidence: List[RetrievedEvidenceItem]` — the reranked top-K, matching the
  brief's `RetrievedEvidence` JSON shape exactly (`doc_id`, `date`, `source`,
  `relevance_score`, `tag`, `snippet_ref`).
- `competitor_activity_detected: bool`
- `competitor_documents: List[RetrievedEvidenceItem]` — the specific matching
  documents backing that flag.
