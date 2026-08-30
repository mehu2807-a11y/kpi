"""
text_features.py
Step 4 of the ingest pipeline: sentiment scoring + entity extraction on
unstructured text (support tickets/reviews, news articles), so it becomes
usable structured data (per the brief: "store the sentiment score as its
own feature row").

Approach: gazetteer/dictionary matching for entities, and a small
hand-built lexicon for sentiment -- a deliberate MVP choice, not an
oversight:
  - No model download needed, so this runs anywhere, offline, with zero
    setup -- this sandbox has no network access, and the brief wants every
    module buildable "the same day."
  - We already own the canonical product/region vocabulary (config.py), so
    gazetteer matching is *more* precise for those two tag types than a
    generic NER model would be out of the box.

Swap-in path for production: replace `extract_entities` with a spaCy /
transformer NER pipeline (needed once you want to catch open-vocabulary
entities, e.g. a brand-new competitor nobody's added to the gazetteer yet),
and replace `score_sentiment` with VADER or a fine-tuned classifier. Both
are isolated behind a plain (text) -> (score | tags) interface specifically
so that swap is a one-file change with no ripple into join.py or storage.py.
"""
from __future__ import annotations

import re

from . import config

_WORD_RE = re.compile(r"[A-Za-z']+")


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def score_sentiment(text: str) -> float:
    """
    Lexicon score in [-1, 1], 0.0 for neutral/no-signal text. Includes basic
    negation handling (flips polarity of a sentiment word directly preceded
    by a negation token) so "not great" doesn't score as positive.
    """
    if not text:
        return 0.0
    tokens = _tokenize(text)
    pos, neg = 0, 0
    for i, tok in enumerate(tokens):
        negated = i > 0 and tokens[i - 1] in config.NEGATIONS
        if tok in config.POSITIVE_WORDS:
            neg += 1 if negated else 0
            pos += 0 if negated else 1
        elif tok in config.NEGATIVE_WORDS:
            pos += 1 if negated else 0
            neg += 0 if negated else 1
    total = pos + neg
    if total == 0:
        return 0.0
    return round((pos - neg) / total, 3)


def extract_entities(text: str) -> dict:
    """
    Gazetteer match against known competitors, our own products, and our
    regions. Regions go in `region_tags`; competitors AND product mentions
    both go in `entity_tags` (matching the brief's own example, which tags
    a competitor name as an entity_tag).
    """
    if not text:
        return {"region_tags": [], "entity_tags": []}
    lower_haystack = text.lower()

    region_tags = sorted({r for r in config.REGION_GAZETTEER if r.lower() in lower_haystack})
    entity_tags = sorted({
        e for e in (config.COMPETITOR_GAZETTEER + config.PRODUCT_GAZETTEER)
        if e.lower() in lower_haystack
    })
    return {"region_tags": region_tags, "entity_tags": entity_tags}


def process_document(doc_id: str, date, source: str, raw_text: str) -> dict:
    """Full step-4 processing for one raw text document -> a DocumentStore row."""
    ents = extract_entities(raw_text)
    return {
        "doc_id": doc_id,
        "date": date,
        "source": source,
        "region_tags": ents["region_tags"],
        "entity_tags": ents["entity_tags"],
        "sentiment_score": score_sentiment(raw_text),
        "raw_text": raw_text,
    }
