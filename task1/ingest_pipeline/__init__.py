"""
ingest_pipeline
Task 1 -- Ingest & time-align (Data Engineer role).

Turns messy, un-joined raw exports into two queryable outputs:
  - MetricsTable    : {date, region, product, metric_name, value}   (long/EAV)
  - DocumentStore   : {doc_id, date, source, region_tags[], entity_tags[],
                        sentiment_score, raw_text}

See README.md for the full module map, assumptions, and how to swap
placeholder pieces (sentiment/NER, storage backend) for production-grade
ones later.
"""
