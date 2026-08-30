"""
multi_industry_templates.py — KPI set templates for multiple industries.

Three industry flavors using the same KPIContract interface:
  - RETAIL (current default — maps to existing KPI IDs)
  - SAAS (MRR, Churn, Active Seats, CAC, NRR)
  - FINANCE (NIM, NPL Ratio, AUM, Trading Volume, Cost-to-Income)

Usage:
  from multi_industry_templates import get_contract, INDUSTRIES
  contract = get_contract('saas')
  print(contract.kpis.keys())
"""

from kpi_contract import (
    KPIDefinition, 
    KPIContract, 
    AggregationType, 
    DataSource, 
    AccessLevel,
    create_default_kpi_contract
)

def create_saas_contract() -> KPIContract:
    contract = KPIContract(version="1.0.0", last_updated="2026-08-30")
    
    contract.add_kpi(KPIDefinition(
        kpi_id="mrr",
        name="Monthly Recurring Revenue",
        description="MRR",
        formula="SUM(subscriptions.mrr)",
        data_sources=[DataSource.SALES_DB],
        aggregation=AggregationType.SUM,
        refresh_cadence="daily",
        grain="day",
        threshold_warning=0.05,
        threshold_critical=0.10,
        business_owner="CRO",
        technical_owner="Data",
        lineage=["churn_rate", "new_seats"],
        access_level=AccessLevel.EXECUTIVE,
        tags=["revenue"]
    ))

    contract.add_kpi(KPIDefinition(
        kpi_id="churn_rate",
        name="Monthly Churn Rate",
        description="Churn",
        formula="churned_mrr / start_mrr",
        data_sources=[DataSource.SALES_DB],
        aggregation=AggregationType.MEAN,
        refresh_cadence="daily",
        grain="day",
        threshold_warning=0.02,
        threshold_critical=0.05,
        business_owner="VP CS",
        technical_owner="Data",
        access_level=AccessLevel.MANAGER,
        tags=["retention"]
    ))
    
    contract.add_kpi(KPIDefinition(
        kpi_id="active_seats",
        name="Active Seats",
        description="Active Seats",
        formula="COUNT(DISTINCT user.seat_id WHERE active)",
        data_sources=[DataSource.SALES_DB],
        aggregation=AggregationType.SUM,
        refresh_cadence="daily",
        grain="day",
        threshold_warning=0.05,
        threshold_critical=0.10,
        business_owner="VP Product",
        technical_owner="Data",
        access_level=AccessLevel.TEAM,
        tags=["engagement"]
    ))

    contract.add_kpi(KPIDefinition(
        kpi_id="cac",
        name="Customer Acquisition Cost",
        description="CAC",
        formula="sales_marketing_spend / new_customers",
        data_sources=[DataSource.MARKETING_DB],
        aggregation=AggregationType.MEAN,
        refresh_cadence="weekly",
        grain="week",
        threshold_warning=0.10,
        threshold_critical=0.20,
        business_owner="CMO",
        technical_owner="Data",
        access_level=AccessLevel.MANAGER,
        tags=["marketing"]
    ))

    contract.add_kpi(KPIDefinition(
        kpi_id="nrr",
        name="Net Revenue Retention",
        description="NRR",
        formula="(start_mrr + expansion - contraction - churn) / start_mrr",
        data_sources=[DataSource.SALES_DB],
        aggregation=AggregationType.MEAN,
        refresh_cadence="monthly",
        grain="month",
        threshold_warning=0.02,
        threshold_critical=0.05,
        business_owner="CRO",
        technical_owner="Data",
        access_level=AccessLevel.EXECUTIVE,
        tags=["retention", "revenue"]
    ))

    return contract

def create_finance_contract() -> KPIContract:
    contract = KPIContract(version="1.0.0", last_updated="2026-08-30")
    
    contract.add_kpi(KPIDefinition(
        kpi_id="nim",
        name="Net Interest Margin",
        description="NIM",
        formula="(interest_income - interest_expense) / avg_earning_assets",
        data_sources=[DataSource.EXTERNAL_FEED],
        aggregation=AggregationType.MEAN,
        refresh_cadence="daily",
        grain="day",
        threshold_warning=0.05,
        threshold_critical=0.10,
        business_owner="CFO",
        technical_owner="Data",
        access_level=AccessLevel.RESTRICTED,
        tags=["margin"]
    ))

    contract.add_kpi(KPIDefinition(
        kpi_id="npl_ratio",
        name="Non-Performing Loan Ratio",
        description="NPL Ratio",
        formula="npl_balance / total_loan_book",
        data_sources=[DataSource.EXTERNAL_FEED],
        aggregation=AggregationType.MEAN,
        refresh_cadence="daily",
        grain="day",
        threshold_warning=0.10,
        threshold_critical=0.20,
        business_owner="CRO",
        technical_owner="Data",
        access_level=AccessLevel.EXECUTIVE,
        tags=["risk"]
    ))
    
    contract.add_kpi(KPIDefinition(
        kpi_id="aum",
        name="Assets Under Management",
        description="AUM",
        formula="SUM(portfolio.market_value)",
        data_sources=[DataSource.EXTERNAL_FEED],
        aggregation=AggregationType.SUM,
        refresh_cadence="daily",
        grain="day",
        threshold_warning=0.05,
        threshold_critical=0.10,
        business_owner="VP Wealth",
        technical_owner="Data",
        access_level=AccessLevel.RESTRICTED,
        tags=["assets"]
    ))

    contract.add_kpi(KPIDefinition(
        kpi_id="daily_trading_volume",
        name="Daily Trading Volume",
        description="Daily Trading Volume",
        formula="SUM(trades.notional_value)",
        data_sources=[DataSource.EXTERNAL_FEED],
        aggregation=AggregationType.SUM,
        refresh_cadence="daily",
        grain="day",
        threshold_warning=0.10,
        threshold_critical=0.20,
        business_owner="VP Trading",
        technical_owner="Data",
        access_level=AccessLevel.MANAGER,
        tags=["volume"]
    ))

    contract.add_kpi(KPIDefinition(
        kpi_id="cost_to_income",
        name="Cost-to-Income Ratio",
        description="Cost-to-Income Ratio",
        formula="operating_costs / operating_income",
        data_sources=[DataSource.EXTERNAL_FEED],
        aggregation=AggregationType.MEAN,
        refresh_cadence="monthly",
        grain="month",
        threshold_warning=0.05,
        threshold_critical=0.10,
        business_owner="CFO",
        technical_owner="Data",
        access_level=AccessLevel.EXECUTIVE,
        tags=["efficiency"]
    ))

    return contract

def create_retail_contract() -> KPIContract:
    return create_default_kpi_contract()

INDUSTRIES = {
    'retail': {'label': 'Retail', 'contract_fn': create_retail_contract, 'kpi_names': ['Total Revenue', 'Units Sold', 'Avg Price', 'Marketing Spend', 'Inventory Level']},
    'saas': {'label': 'SaaS', 'contract_fn': create_saas_contract, 'kpi_names': ['MRR', 'Churn Rate', 'Active Seats', 'CAC', 'NRR']},
    'finance': {'label': 'Finance', 'contract_fn': create_finance_contract, 'kpi_names': ['NIM', 'NPL Ratio', 'AUM', 'Trading Volume', 'Cost-to-Income']},
}

def get_contract(industry: str = 'retail') -> KPIContract:
    """Get the KPI contract for a given industry."""
    if industry not in INDUSTRIES:
        raise ValueError(f'Unknown industry {industry!r}. Options: {list(INDUSTRIES)}')
    return INDUSTRIES[industry]['contract_fn']()

if __name__ == '__main__':
    for industry in ['retail', 'saas', 'finance']:
        contract = get_contract(industry)
        print(f'{industry}: {list(contract.kpis.keys())}')
