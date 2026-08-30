"""
Task-1-shaped sample DocumentStore: a hand-picked set of 18 articles /
support tickets for day-one development and precision testing, before
the real Task 1 (ingest & embed) and Task 4 (correlate drivers) exist.

Built around one mock anomaly: EU-West weekly_revenue, down 18.4%,
2026-07-10 to 2026-07-17 (see demo.py / test_retrieval.py). Ten of the
eighteen are genuinely relevant to that investigation (competitor
activity, market conditions, or internal signals); the rest are
deliberately irrelevant -- either outside the anomaly's date/region
window, or topically unrelated despite passing the metadata filters --
so retrieval *precision* can be checked, not just recall.
"""
from __future__ import annotations

from datetime import date

from schemas import DocumentRecord

KNOWN_COMPETITORS = ["Northwind Retail", "Solstice Mart", "Acme Commerce"]

ALL_DOCUMENTS = [
    DocumentRecord(
        doc_id="news_1001",
        date=date(2026, 7, 12),
        source="Reuters",
        title="Northwind Retail Launches Aggressive Price Cuts Across Western Europe",
        text=(
            "Northwind Retail said Friday it is cutting prices by up to 25% on core "
            "grocery and household categories across its Western Europe stores, a move "
            "analysts called a direct challenge to rivals in the region. The retailer "
            "framed the discounts as a summer promotion, but pricing analysts said the "
            "depth and breadth of the price cuts point to a longer campaign for market "
            "share. Competing chains in the EU-West region reported early signs of "
            "customer traffic shifting toward Northwind Retail outlets."
        ),
        region_tags=["EU-West"],
        entity_tags=["Northwind Retail"],
    ),
    DocumentRecord(
        doc_id="news_1002",
        date=date(2026, 7, 9),
        source="TechMarket Daily",
        title="Northwind Retail Announces 20% Off Summer Promotion in EU-West Stores",
        text=(
            "Northwind Retail confirmed a region-wide summer discount campaign offering "
            "20% off across most product lines in its EU-West stores, running through "
            "the end of July. Marketing materials describe price as the campaign's "
            "central message, undercutting typical seasonal discount depth by several "
            "percentage points. Shoppers interviewed outside a Northwind Retail location "
            "said the lower price was the main reason for their visit."
        ),
        region_tags=["EU-West"],
        entity_tags=["Northwind Retail"],
    ),
    DocumentRecord(
        doc_id="news_1003",
        date=date(2026, 7, 11),
        source="PR Newswire",
        title="Northwind Retail Opens New EU-West Distribution Center",
        text=(
            "Northwind Retail opened a new regional distribution center in EU-West this "
            "week, a facility executives say will cut delivery times and let stores "
            "restock discounted inventory faster during the retailer's ongoing price "
            "promotion. The expansion adds warehouse capacity specifically to support "
            "the chain's recent round of price cuts in the region."
        ),
        region_tags=["EU-West"],
        entity_tags=["Northwind Retail"],
    ),
    DocumentRecord(
        doc_id="news_1004",
        date=date(2026, 7, 17),
        source="Reuters",
        title="Analysts Flag Northwind Retail's Aggressive European Expansion",
        text=(
            "Equity analysts covering the retail sector said Northwind Retail's recent "
            "combination of price cuts, a new EU-West distribution center, and expanded "
            "marketing spend amounts to a coordinated push for market share across "
            "Europe. Several analysts warned that competitors' revenue in EU-West and "
            "EU-East could see near-term pressure if the price campaign continues into "
            "the autumn."
        ),
        region_tags=["EU-West", "EU-East"],
        entity_tags=["Northwind Retail"],
    ),
    DocumentRecord(
        doc_id="news_1005",
        date=date(2026, 7, 14),
        source="Reuters",
        title="EU Consumer Confidence Index Dips Slightly in July",
        text=(
            "The regional consumer confidence index for EU-West and EU-East edged down "
            "in July, according to new data, with survey respondents citing tighter "
            "household budgets and more price-conscious shopping habits. Economists "
            "said the dip is modest but could translate into lower discretionary "
            "spending and softer retail sales across the bloc in the near term."
        ),
        region_tags=["EU-West", "EU-East"],
        entity_tags=[],
    ),
    DocumentRecord(
        doc_id="news_1006",
        date=date(2026, 7, 15),
        source="Bloomberg",
        title="Shipping Carrier Strikes Disrupt European Logistics",
        text=(
            "A wave of carrier strikes across major European ports has delayed "
            "shipments and disrupted restocking schedules for retailers operating in "
            "EU-West and EU-East, logistics data shows. Some retailers have reported "
            "empty shelves and delayed promotions as a result, while others have "
            "shifted deliveries to alternate routes at higher cost, squeezing margins "
            "and sales across the sector."
        ),
        region_tags=["EU-West", "EU-East"],
        entity_tags=[],
    ),
    DocumentRecord(
        doc_id="news_1007",
        date=date(2026, 7, 8),
        source="Reuters",
        title="Heatwave Slows Foot Traffic in EU-West Retail Corridors",
        text=(
            "An unusual mid-July heatwave across EU-West has kept shoppers away from "
            "outdoor retail corridors and shopping streets, according to local "
            "foot-traffic sensors, with some retailers reporting a double-digit drop in "
            "in-store visits and in-store sales over the past week. Store managers said "
            "online orders ticked up slightly but not enough to offset the decline in "
            "walk-in customers."
        ),
        region_tags=["EU-West"],
        entity_tags=[],
    ),
    DocumentRecord(
        doc_id="news_1008",
        date=date(2026, 1, 22),
        source="MarketWatch",
        title="Northwind Retail Q4 Earnings Beat Expectations",
        text=(
            "Northwind Retail reported fourth-quarter earnings ahead of analyst "
            "estimates, driven by strong holiday-season demand and disciplined cost "
            "control across its store network. The company's chief financial officer "
            "said margins held up despite a competitive pricing environment during the "
            "holidays, and reaffirmed full-year revenue guidance."
        ),
        region_tags=["EU-West"],
        entity_tags=["Northwind Retail"],
    ),
    DocumentRecord(
        doc_id="news_1009",
        date=date(2026, 7, 13),
        source="Reuters",
        title="Solstice Mart Expands into Southeast Asia",
        text=(
            "Solstice Mart announced plans to open its first stores in Southeast Asia "
            "next year, marking the retailer's first expansion outside its core "
            "markets. Executives said the move reflects strong demand signals from the "
            "region and will be funded through existing cash reserves rather than new "
            "debt."
        ),
        region_tags=["APAC"],
        entity_tags=["Solstice Mart"],
    ),
    DocumentRecord(
        doc_id="news_1010",
        date=date(2026, 5, 2),
        source="TechCrunch",
        title="Acme Commerce Raises Series C Funding",
        text=(
            "Acme Commerce, a US-East focused e-commerce platform, announced a new "
            "Series C funding round led by a group of growth investors. The company "
            "said the capital will go toward warehouse automation and expanding its "
            "same-day delivery footprint in major US-East metro areas."
        ),
        region_tags=["US-East"],
        entity_tags=["Acme Commerce"],
    ),
    DocumentRecord(
        doc_id="news_1011",
        date=date(2025, 11, 30),
        source="Local Times",
        title="Northwind Retail Opens Flagship Store in EU-West",
        text=(
            "Northwind Retail celebrated the opening of a new flagship store in "
            "EU-West this week, its largest location in the region to date. The store "
            "features an expanded grocery section and a dedicated area for the "
            "retailer's private-label product lines, part of a broader push to grow "
            "its footprint in the market."
        ),
        region_tags=["EU-West"],
        entity_tags=["Northwind Retail"],
    ),
    DocumentRecord(
        doc_id="news_1012",
        date=date(2026, 7, 13),
        source="Reuters",
        title="EU-West City Council Approves New Bike Lane Network",
        text=(
            "The EU-West city council voted this week to approve a new protected bike "
            "lane network connecting several neighborhoods to the downtown core. "
            "Construction is expected to begin next spring, with officials citing "
            "rising cyclist commuter numbers and a broader push to reduce car traffic "
            "in the city center."
        ),
        region_tags=["EU-West"],
        entity_tags=[],
    ),
    DocumentRecord(
        doc_id="ticket_2001",
        date=date(2026, 7, 10),
        source="support",
        title="Customers report cheaper prices at Northwind Retail, EU-West",
        text=(
            "Multiple support tickets this week from EU-West shoppers mention "
            "comparing price with Northwind Retail before requesting a discount or "
            "canceling an order. One customer wrote that a nearly identical basket of "
            "goods was noticeably cheaper at a nearby Northwind Retail location. "
            "Support agents flagged the pattern as worth escalating to the pricing "
            "team."
        ),
        region_tags=["EU-West"],
        entity_tags=["Northwind Retail"],
    ),
    DocumentRecord(
        doc_id="ticket_2002",
        date=date(2026, 7, 11),
        source="support",
        title="Spike in cart abandonment complaints, EU-West checkout flow",
        text=(
            "Support has seen a rise in tickets from EU-West customers abandoning "
            "their cart at the final checkout step, several citing final price as the "
            "reason without naming a specific competitor. Engineering confirmed no "
            "checkout bugs were deployed this week, suggesting the complaints reflect "
            "price sensitivity and lower sales conversion rather than a technical "
            "issue."
        ),
        region_tags=["EU-West"],
        entity_tags=[],
    ),
    DocumentRecord(
        doc_id="ticket_2003",
        date=date(2026, 7, 16),
        source="support",
        title="Refund requests spike, EU-West, customers cite Northwind pricing",
        text=(
            "Refund and cancellation requests from EU-West customers rose sharply this "
            "week, with a recurring theme in the ticket text: shoppers say they found "
            "the same items for less at Northwind Retail after already placing an "
            "order. Support leadership asked for this pattern to be surfaced to the "
            "pricing and retention teams."
        ),
        region_tags=["EU-West"],
        entity_tags=["Northwind Retail"],
    ),
    DocumentRecord(
        doc_id="ticket_2004",
        date=date(2026, 3, 2),
        source="support",
        title="Login page outage reported by EU-West users",
        text=(
            "Several EU-West users reported being unable to log into their accounts "
            "for roughly 40 minutes this morning due to an authentication service "
            "outage. The issue was resolved after a service restart, and the incident "
            "has been logged for a post-mortem review by the platform team."
        ),
        region_tags=["EU-West"],
        entity_tags=[],
    ),
    DocumentRecord(
        doc_id="ticket_2005",
        date=date(2026, 7, 1),
        source="support",
        title="Feature request: dark mode for mobile app",
        text=(
            "A customer submitted a feature request asking for a dark mode option in "
            "the mobile app, citing eye strain during nighttime use. Several other "
            "customers upvoted the same request in the following days. Product has "
            "added it to the mobile backlog for consideration."
        ),
        region_tags=[],
        entity_tags=[],
    ),
    DocumentRecord(
        doc_id="ticket_2006",
        date=date(2026, 7, 15),
        source="support",
        title="Employee onboarding checklist question, EU-West office",
        text=(
            "A new hire in the EU-West office submitted a support ticket asking where "
            "to find the internal onboarding checklist and benefits enrollment portal. "
            "HR responded with links to the internal wiki and scheduled a welcome call "
            "for later in the week."
        ),
        region_tags=["EU-West"],
        entity_tags=[],
    ),
]
