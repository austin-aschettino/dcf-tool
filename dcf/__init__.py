"""A small valuation toolkit for stocks (DCF) and index funds (whole-index model)."""

from __future__ import annotations

from .data import CompanyData, fetch_company, is_financial_industry
from .fund import (
    FundData,
    IndexAssumptions,
    IndexResult,
    default_index_assumptions,
    fetch_fund,
    implied_index_growth,
    index_scenarios,
    index_sensitivity,
    is_fund,
    run_index_valuation,
)
from .loader import data_age_hours, load, price_history
from .model import (
    DCFAssumptions,
    DCFResult,
    base_cash,
    check_company,
    cost_of_equity,
    default_assumptions,
    default_growth,
    implied_growth,
    make_scenarios,
    run_dcf,
    sensitivity_table,
)
from .report import company_scenarios, company_tables, fund_scenarios, fund_tables, to_xlsx
from .outlook import (
    PriceOutlook,
    annual_volatility,
    build_outlook,
    company_outlook,
    cone_path,
    fund_outlook,
)
from .reverse import (
    LONG_RUN_EARNINGS_GROWTH,
    demand_level,
    fund_implied_growth_grid,
    fund_needed_path,
    growth_benchmarks,
    implied_discount_rate,
    implied_growth_grid,
    needed_path,
    reference_growth,
)

__all__ = [
    "load", "price_history", "data_age_hours",
    "CompanyData", "fetch_company", "is_financial_industry",
    "DCFAssumptions", "DCFResult", "default_assumptions", "default_growth", "base_cash",
    "check_company", "cost_of_equity", "run_dcf", "implied_growth", "make_scenarios", "sensitivity_table",
    "FundData", "fetch_fund", "is_fund", "IndexAssumptions", "IndexResult", "default_index_assumptions",
    "run_index_valuation", "implied_index_growth", "index_scenarios", "index_sensitivity",
    "company_scenarios", "fund_scenarios", "company_tables", "fund_tables", "to_xlsx",
    "PriceOutlook", "annual_volatility", "build_outlook", "company_outlook", "fund_outlook", "cone_path",
    "implied_discount_rate", "implied_growth_grid", "fund_implied_growth_grid", "needed_path",
    "fund_needed_path", "growth_benchmarks", "demand_level", "reference_growth", "LONG_RUN_EARNINGS_GROWTH",
]
