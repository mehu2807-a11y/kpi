"""
sample_data.py
Synthetic raw inputs standing in for real source exports, since none were
provided with the task. This is demo/test scaffolding only -- not pipeline
"logic" (steps 1-5 live in normalize.py / text_features.py / join.py /
storage.py). Swap this module out once real exports are wired up; every
other module depends only on the *column shapes* generated here (the raw
schema named in the brief), never on this file.

Deliberately messy, matching "no fixed schema yet" in the brief:
  - region/product spelled inconsistently across tables (and across rows)
  - sales has random missing (date, region, product) combos -- real gaps
  - pricing_history is sparser than sales (real price lists don't move
    daily), which exercises join.py's avg_price fallback path
  - marketing_spend has no product column, by design -- see join.py
  - a real anomaly (not just noise) is seeded into the last 3 days of
    Region X / Product A -- a sales dip paired with a cluster of negative
    support tickets -- so the output this module produces is something a
    later anomaly/correlation module could plausibly act on. Task 1 stops
    at ingest & align; nothing here *detects* the dip.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

import pandas as pd

random.seed(42)

N_DAYS = 30
START_DATE = date(2026, 6, 15)
DATES = [START_DATE + timedelta(days=i) for i in range(N_DAYS)]

REGION_RAW_VARIANTS = {
    "Region X": ["US-West", "United States - West", "USW", "us_west", "West US"],
    "Region Y": ["US-East", "United States - East", "USE", "us_east", "East US"],
    "Region Z": ["EMEA", "Europe", "EU"],
}
PRODUCT_RAW_VARIANTS = {
    "Product A": ["Product A", "product a", "PROD_A", "Prod. A", "prod-a"],
    "Product B": ["Product B", "product b", "PROD_B", "Prod. B", "prod-b"],
    "Product C": ["Product C", "product c", "PROD_C", "Prod. C", "prod-c"],
}
CHANNELS = ["search", "social", "email"]

BASE_UNITS = {
    ("Region X", "Product A"): 1400, ("Region X", "Product B"): 700, ("Region X", "Product C"): 500,
    ("Region Y", "Product A"): 900, ("Region Y", "Product B"): 1100, ("Region Y", "Product C"): 400,
    ("Region Z", "Product A"): 600, ("Region Z", "Product B"): 500, ("Region Z", "Product C"): 950,
}
BASE_PRICE = {"Product A": 55.0, "Product B": 82.0, "Product C": 36.0}

ANOMALY_REGION, ANOMALY_PRODUCT = "Region X", "Product A"
ANOMALY_START = START_DATE + timedelta(days=N_DAYS - 3)  # last 3 days of the window


def _raw_region(canonical: str) -> str:
    return random.choice(REGION_RAW_VARIANTS[canonical])


def _raw_product(canonical: str) -> str:
    return random.choice(PRODUCT_RAW_VARIANTS[canonical])


def _gen_sales() -> pd.DataFrame:
    rows = []
    for d in DATES:
        for (region, product), base in BASE_UNITS.items():
            if random.random() < 0.08:
                continue  # simulate a genuine reporting gap
            units = base + random.randint(-int(base * 0.12), int(base * 0.12))
            if region == ANOMALY_REGION and product == ANOMALY_PRODUCT and d >= ANOMALY_START:
                units = int(units * random.uniform(0.35, 0.5))  # the real anomaly, not noise
            price = BASE_PRICE[product] * random.uniform(0.97, 1.03)
            revenue = round(units * price, 2)
            rows.append({
                "date": d.isoformat(),
                "region": _raw_region(region),
                "product": _raw_product(product),
                "units_sold": units,
                "revenue": revenue,
                "unit_price": round(price, 2),
            })
    return pd.DataFrame(rows)


def _gen_pricing_history() -> pd.DataFrame:
    """Schema not specified in the brief -- inferred as (date, region, product,
    list_price). See join.py for how this feeds avg_price."""
    rows = []
    for i, d in enumerate(DATES):
        if i % 3 != 0:
            continue  # price lists don't move daily
        for (region, product) in BASE_UNITS.keys():
            price = BASE_PRICE[product] * random.uniform(0.98, 1.05)
            rows.append({
                "date": d.isoformat(),
                "region": _raw_region(region),
                "product": _raw_product(product),
                "list_price": round(price, 2),
            })
    return pd.DataFrame(rows)


def _gen_inventory() -> pd.DataFrame:
    rows = []
    stock = {k: v * 6.0 for k, v in BASE_UNITS.items()}
    for d in DATES:
        for key in BASE_UNITS.keys():
            region, product = key
            stock[key] -= BASE_UNITS[key] * random.uniform(0.85, 1.05)
            if stock[key] < BASE_UNITS[key]:
                stock[key] += BASE_UNITS[key] * random.uniform(4, 6)  # restock event
            rows.append({
                "date": d.isoformat(),
                "region": _raw_region(region),
                "product": _raw_product(product),
                "stock_level": max(int(stock[key]), 0),
            })
    return pd.DataFrame(rows)


def _gen_marketing_spend() -> pd.DataFrame:
    """No product column -- matches the brief's schema exactly: (date, region, channel, spend)."""
    rows = []
    for d in DATES:
        for region in REGION_RAW_VARIANTS.keys():
            for channel in CHANNELS:
                spend = random.uniform(800, 4000)
                rows.append({
                    "date": d.isoformat(),
                    "region": _raw_region(region),
                    "channel": channel,
                    "spend": round(spend, 2),
                })
    return pd.DataFrame(rows)


_TICKET_TEMPLATES_NEG = [
    "Really disappointed with {product} in {region} -- it crashed twice this week and support was slow to respond.",
    "{product} has been unreliable lately. Getting frequent errors and considering a refund.",
    "Frustrated customer here: {product} shipment to {region} was delayed again. This is a poor experience.",
    "The latest {product} update is buggy. It crashed on startup, had to cancel my order.",
    "Outage on {product} today in {region}, very poor communication from support.",
]
_TICKET_TEMPLATES_POS = [
    "Just wanted to say {product} has been great this month -- fast, reliable, and support was helpful.",
    "Love {product}! Smooth experience end to end in {region}.",
    "{product} support team resolved my issue quickly. Impressed with how responsive they were.",
    "Excellent value with {product}, works exactly as expected in {region}.",
]
_TICKET_TEMPLATES_NEUTRAL = [
    "Question about {product} billing cycle for my account in {region}.",
    "Requesting an invoice copy for a recent {product} purchase.",
    "Is there a warranty extension available for {product}?",
]
_NEWS_TEMPLATES = [
    "CompetitorCo announced a price cut across its {region} lineup, undercutting rivals ahead of the quarter.",
    "RivalWorks is expanding its {region} distribution network, adding new retail partnerships.",
    "Industry report: demand in {region} softened slightly this month amid broader economic uncertainty.",
    "CompetitorCo faced backlash in {region} after a widely reported service outage last week.",
    "RivalWorks launched a marketing campaign targeting {region} customers directly.",
]


def _gen_documents() -> list[dict]:
    docs = []
    doc_i = 0

    for d in DATES:
        for _ in range(random.randint(1, 2)):
            region = random.choice(list(REGION_RAW_VARIANTS.keys()))
            product = random.choice(list(PRODUCT_RAW_VARIANTS.keys()))
            template = random.choice(_TICKET_TEMPLATES_NEG + _TICKET_TEMPLATES_POS + _TICKET_TEMPLATES_NEUTRAL)
            doc_i += 1
            docs.append({
                "doc_id": f"ticket_{doc_i:05d}",
                "date": d.isoformat(),
                "source": "support_ticket",
                "raw_text": template.format(product=product, region=region),
            })
        if random.random() < 0.4:
            region = random.choice(list(REGION_RAW_VARIANTS.keys()))
            template = random.choice(_NEWS_TEMPLATES)
            doc_i += 1
            docs.append({
                "doc_id": f"news_{doc_i:05d}",
                "date": d.isoformat(),
                "source": random.choice(["Reuters", "Bloomberg", "TechDaily"]),
                "raw_text": template.format(region=region),
            })

    # Seeded cluster: negative tickets about the real anomaly, concentrated
    # right where the sales dip happens -- so the output plausibly supports
    # a later correlate/root-cause module (not built here).
    for d in [d for d in DATES if d >= ANOMALY_START]:
        for _ in range(random.randint(3, 5)):
            template = random.choice(_TICKET_TEMPLATES_NEG)
            doc_i += 1
            docs.append({
                "doc_id": f"ticket_{doc_i:05d}",
                "date": d.isoformat(),
                "source": "support_ticket",
                "raw_text": template.format(product=ANOMALY_PRODUCT, region=ANOMALY_REGION),
            })

    return docs


def generate_all() -> dict:
    return {
        "sales": _gen_sales(),
        "pricing_history": _gen_pricing_history(),
        "inventory": _gen_inventory(),
        "marketing_spend": _gen_marketing_spend(),
        "documents": _gen_documents(),
    }
