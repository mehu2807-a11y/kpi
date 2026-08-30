"""
KPI Contract - Lightweight semantic contract covering KPI definitions,
calculations, drivers, thresholds, lineage and access restrictions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Literal
from enum import Enum


class AggregationType(Enum):
    SUM = "sum"
    MEAN = "mean"
    LATEST = "latest"


class DataSource(Enum):
    SALES_DB = "sales_db"
    MARKETING_DB = "marketing_db"
    INVENTORY_SYSTEM = "inventory_system"
    EXTERNAL_FEED = "external_feed"
    MANUAL_ENTRY = "manual_entry"


class AccessLevel(Enum):
    PUBLIC = "public"
    TEAM = "team"
    MANAGER = "manager"
    EXECUTIVE = "executive"
    RESTRICTED = "restricted"


@dataclass
class KPIDefinition:
    """Defines a KPI including its calculation, data sources, and metadata."""
    kpi_id: str
    name: str
    description: str
    formula: str  # Human-readable or SQL-like expression
    data_sources: List[DataSource]
    aggregation: AggregationType
    refresh_cadence: str  # e.g., "daily", "hourly", "real-time"
    grain: str  # e.g., "day", "week", "month", "region", "product"
    threshold_warning: float  # Percentage change that triggers warning
    threshold_critical: float  # Percentage change that triggers alert
    business_owner: str
    technical_owner: str
    lineage: List[str] = field(default_factory=list)  # Upstream/downstream dependencies
    upstream_drivers: List[str] = field(default_factory=list)
    refresh_lag_hours: int = 24
    access_level: AccessLevel = AccessLevel.TEAM
    tags: List[str] = field(default_factory=list)  # e.g., ["revenue", "growth", "financial"]


@dataclass
class KPIContract:
    """Container for all KPI definitions in the system."""
    kpis: Dict[str, KPIDefinition] = field(default_factory=dict)
    version: str = "1.0.0"
    last_updated: str = ""

    def add_kpi(self, kpi: KPIDefinition):
        """Add or update a KPI definition."""
        self.kpis[kpi.kpi_id] = kpi

    def get_kpi(self, kpi_id: str) -> Optional[KPIDefinition]:
        """Retrieve a KPI definition by ID."""
        return self.kpis.get(kpi_id)

    def get_kpis_by_tag(self, tag: str) -> List[KPIDefinition]:
        """Get all KPIs with a specific tag."""
        return [kpi for kpi in self.kpis.values() if tag in kpi.tags]

    def get_kpis_by_owner(self, owner: str) -> List[KPIDefinition]:
        """Get all KPIs owned by a specific person/team."""
        return [kpi for kpi in self.kpis.values() if kpi.business_owner == owner or kpi.technical_owner == owner]


# Default KPI contracts for BusinessIntelligence.ai
def create_default_kpi_contract() -> KPIContract:
    """Create a default set of KPI definitions for demonstration."""
    contract = KPIContract(
        version="1.0.0",
        last_updated="2026-08-27"
    )

    # Revenue KPI
    revenue_kpi = KPIDefinition(
        kpi_id="revenue_total",
        name="Total Revenue",
        description="Total gross revenue from all sales channels",
        formula="SUM(sales.amount)",
        data_sources=[DataSource.SALES_DB],
        aggregation=AggregationType.SUM,
        refresh_cadence="daily",
        grain="day",
        threshold_warning=0.05,  # 5% change
        threshold_critical=0.15,  # 15% change
        business_owner="VP of Sales",
        technical_owner="Data Engineering Team",
        lineage=["sales.transactions", "product.catalog"],
        access_level=AccessLevel.MANAGER,
        tags=["revenue", "financial", "top-line"],
        upstream_drivers=["avg_price", "units_sold", "marketing_spend"],
        refresh_lag_hours=24
    )

    # Units Sold KPI
    units_kpi = KPIDefinition(
        kpi_id="units_sold",
        name="Units Sold",
        description="Total number of units sold",
        formula="SUM(sales.quantity)",
        data_sources=[DataSource.SALES_DB],
        aggregation=AggregationType.SUM,
        refresh_cadence="daily",
        grain="day",
        threshold_warning=0.08,
        threshold_critical=0.20,
        business_owner="VP of Sales",
        technical_owner="Data Engineering Team",
        lineage=["sales.transactions"],
        access_level=AccessLevel.MANAGER,
        tags=["volume", "sales", "operational"],
        upstream_drivers=["avg_price", "inventory_level", "marketing_spend"],
        refresh_lag_hours=24
    )

    # Average Price KPI
    avg_price_kpi = KPIDefinition(
        kpi_id="avg_price",
        name="Average Selling Price",
        description="Average price per unit sold",
        formula="AVG(sales.amount / sales.quantity)",
        data_sources=[DataSource.SALES_DB],
        aggregation=AggregationType.MEAN,
        refresh_cadence="daily",
        grain="day",
        threshold_warning=0.03,
        threshold_critical=0.08,
        business_owner="VP of Pricing",
        technical_owner="Analytics Team",
        lineage=["sales.transactions", "product.catalog"],
        access_level=AccessLevel.TEAM,
        tags=["pricing", "financial", "margin"],
        upstream_drivers=[],
        refresh_lag_hours=24
    )

    # Marketing Spend KPI
    marketing_spend_kpi = KPIDefinition(
        kpi_id="marketing_spend",
        name="Marketing Spend",
        description="Total marketing expenditure",
        formula="SUM(marketing.cost)",
        data_sources=[DataSource.MARKETING_DB],
        aggregation=AggregationType.SUM,
        refresh_cadence="weekly",
        grain="week",
        threshold_warning=0.10,
        threshold_critical=0.25,
        business_owner="CMO",
        technical_owner="Marketing Analytics",
        lineage=["marketing.campaigns", "finance.ledger"],
        access_level=AccessLevel.MANAGER,
        tags=["marketing", "expense", "investment"],
        upstream_drivers=[],
        refresh_lag_hours=168
    )

    # Inventory Level KPI
    inventory_kpi = KPIDefinition(
        kpi_id="inventory_level",
        name="Inventory Level",
        description="Total units in inventory",
        formula="SUM(inventory.quantity_on_hand)",
        data_sources=[DataSource.INVENTORY_SYSTEM],
        aggregation=AggregationType.SUM,
        refresh_cadence="daily",
        grain="day",
        threshold_warning=-0.10,  # Negative for inventory (low is bad)
        threshold_critical=-0.25,
        business_owner="VP of Operations",
        technical_owner="Supply Chain Team",
        lineage=["inventory.system", "procurement.orders"],
        access_level=AccessLevel.TEAM,
        tags=["inventory", "operations", "supply-chain"],
        upstream_drivers=[],
        refresh_lag_hours=24
    )

    # Add all KPIs to contract
    for kpi in [revenue_kpi, units_kpi, avg_price_kpi, marketing_spend_kpi, inventory_kpi]:
        contract.add_kpi(kpi)

    return contract


# Global contract instance
DEFAULT_KPI_CONTRACT = create_default_kpi_contract()