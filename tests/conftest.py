"""Shared test fixtures: small made-up companies and funds with answers we can check by hand."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dcf import CompanyData, FundData  # noqa: E402


def make_company(fcf=(100.0, 100.0, 100.0), price=10.0, shares=100.0, debt=0.0, cash=0.0,
                 sector="Technology", industry="Software", dividends=None, buybacks=None, **kw) -> CompanyData:
    n = len(fcf)
    return CompanyData(
        ticker="TEST",
        name="Test Co",
        currency="USD",
        price=price,
        shares_outstanding=shares,
        market_cap=price * shares,
        beta=1.0,
        total_debt=debt,
        cash=cash,
        tax_rate=0.2,
        interest_expense=0.0,
        years=[str(2020 + i) for i in range(n)],
        revenue=[1000.0] * n,
        operating_cash_flow=list(fcf),
        capex=[0.0] * n,
        free_cash_flow=list(fcf),
        dividends_paid=list(dividends) if dividends is not None else [0.0] * n,
        buybacks=list(buybacks) if buybacks is not None else [0.0] * n,
        sector=sector,
        industry=industry,
        **kw,
    )


def make_fund(price=100.0, pe=20.0, expense=0.0, **kw) -> FundData:
    return FundData(
        ticker="FUND",
        name="Test Fund",
        fund_type="ETF",
        category="Large Blend",
        family="Test",
        currency="USD",
        price=price,
        pe=pe,
        dividend_yield=0.015,
        expense_ratio=expense,
        beta=1.0,
        total_assets=1e9,
        return_3y=None,
        return_5y=None,
        **kw,
    )


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    """Point the disk cache at a temporary folder so tests never touch real data."""
    from dcf import cache

    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path / "cache")
