"""Checks of the newer features: SEC statements, quality scorecard, peers, probability view, portfolio."""

from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np
import pytest

from conftest import make_company, make_fund
from dcf import DCFAssumptions, IndexAssumptions, data, run_dcf, run_index_valuation
from dcf import montecarlo, portfolio, quality


# ---- SEC statements --------------------------------------------------------------------------

SEC_SNAPSHOT = {
    "years": ["2023", "2024"], "period_end": "2024-12-31",
    "revenue": [1000.0, 1100.0], "operating_cash_flow": [150.0, 170.0], "capex": [-30.0, -40.0],
    "free_cash_flow": [120.0, 130.0], "dividends_paid": [10.0, 12.0], "buybacks": [5.0, 6.0],
    "shares": 100.0, "total_debt": 50.0, "cash": 20.0, "interest_expense": 3.0, "tax": 25.0, "pretax": 100.0,
}
INFO = {"currentPrice": 20.0, "sharesOutstanding": 101.0, "totalDebt": 80.0, "totalCash": 30.0,
        "sector": "Technology", "industry": "Software", "longName": "Test Co", "operatingMargins": 0.2}


def test_sec_statements_are_used_when_available(monkeypatch):
    monkeypatch.setattr(data, "_sec_statements", lambda ticker, financial: dict(SEC_SNAPSHOT))
    fake = SimpleNamespace(growth_estimates=None)
    c = data.fetch_company("TEST", t=fake, info=INFO)
    assert c.statements_source == "SEC EDGAR"
    assert c.free_cash_flow == [120.0, 130.0] and c.years == ["2023", "2024"]
    assert c.tax_rate == pytest.approx(0.25)
    # Price, shares, debt and cash come from Yahoo (debt includes leases, cash includes investments).
    assert (c.price, c.shares_outstanding, c.total_debt, c.cash) == (20.0, 101.0, 80.0, 30.0)
    assert c.operating_margin == 0.2


def test_sec_balance_sheet_is_a_fallback_only(monkeypatch):
    monkeypatch.setattr(data, "_sec_statements", lambda ticker, financial: dict(SEC_SNAPSHOT))
    info = {k: v for k, v in INFO.items() if k not in ("totalDebt", "totalCash", "sharesOutstanding")}
    c = data.fetch_company("TEST", t=SimpleNamespace(growth_estimates=None), info=info)
    assert (c.total_debt, c.cash, c.shares_outstanding) == (50.0, 20.0, 100.0)


# ---- Quality scorecard ----------------------------------------------------------------------

def test_scorecard_grades_a_strong_business():
    c = make_company(fcf=(200.0, 220.0, 240.0), operating_margin=0.30, return_on_assets=0.15, ebitda=500.0)
    c.revenue = [1000.0, 1100.0, 1210.0]
    grades = {ch.name: ch.grade for ch in quality.scorecard(c)}
    assert grades["Operating margin"] == "Strong"
    assert grades["Free cash flow margin"] == "Strong"      # ~20% of sales
    assert grades["Debt load"] == "Strong"                   # no net debt
    assert grades["Sales growth"] == "Strong"                # 10% a year
    assert quality.overall(quality.scorecard(c))[1] == "green"


def test_scorecard_flags_weak_points_and_missing_data():
    c = make_company(fcf=(50.0, -20.0, 40.0), debt=3000.0, ebitda=500.0, operating_margin=0.04)
    grades = {ch.name: ch.grade for ch in quality.scorecard(c)}
    assert grades["Debt load"] == "Weak"                     # 6x EBITDA
    assert grades["Free cash flow: consistency"] == "Weak"   # a negative year
    assert grades["Return on assets"] == "n/a"
    assert quality.cash_consistency([100, 100, 100]) == 1.0


def test_banks_get_bank_checks():
    bank = make_company(sector="Financial Services", industry="Banks - Diversified",
                        dividends=(10, 10, 10), buybacks=(5, 5, 5), return_on_equity=0.15)
    names = [ch.name for ch in quality.scorecard(bank)]
    assert "Return on equity" in names and "Debt load" not in names


# ---- Similar companies -----------------------------------------------------------------------

def test_peer_lists():
    c = make_company(industry="Auto Parts", sector="Consumer Cyclical")
    c.ticker = "AZO"
    assert quality.peer_tickers(c)[0] == "ORLY" and "AZO" not in quality.peer_tickers(c)
    other = make_company(industry="Something New", sector="Energy")
    assert quality.peer_tickers(other) == ["XOM", "CVX", "COP", "EOG"]
    assert quality.peer_tickers(make_company(industry="?", sector="?")) == []


def test_implied_prices_from_peer_medians():
    c = make_company(price=10.0, shares=100.0, fcf=(100.0, 100.0, 100.0), pe=20.0, ebitda=200.0, debt=100.0)
    med = {"P/E": 25.0, "Forward P/E": None, "EV/EBITDA": 8.0, "Cash flow yield": 0.05}
    out = quality.implied_prices(c, med)
    assert out["At peers' P/E"] == pytest.approx(12.5)                    # earnings $0.50 x 25
    assert out["At peers' EV/EBITDA"] == pytest.approx((200 * 8 - 100) / 100)
    assert out["At peers' cash flow yield"] == pytest.approx(20.0)        # $1/share cash at a 5% yield
    meds = quality.peer_medians([make_company(pe=10.0), make_company(pe=30.0), make_company(pe=None)])
    assert meds["P/E"] == 20.0


# ---- Probability view ------------------------------------------------------------------------

def test_simulation_without_uncertainty_matches_the_dcf(monkeypatch):
    monkeypatch.setitem(montecarlo.UNCERTAINTY, "None", dict(growth=0.0, rate=0.0, terminal=0.0))
    c = make_company(price=12.0)
    a = DCFAssumptions(growth_rate=0.05, terminal_growth=0.02, wacc=0.09, years=5)
    sim = montecarlo.simulate_company(c, a, n=50, level="None")
    assert np.allclose(sim.values, run_dcf(c, a).value_per_share)
    f = make_fund(expense=0.001)
    fa = IndexAssumptions(growth_rate=0.06, terminal_growth=0.04, required_return=0.09)
    assert np.allclose(montecarlo.simulate_fund(f, fa, n=20, level="None").values,
                       run_index_valuation(f, fa).value_per_share)


def test_simulation_summary_and_probability():
    c = make_company(price=12.0)
    a = DCFAssumptions(growth_rate=0.05, terminal_growth=0.02, wacc=0.09, years=5)
    sim = montecarlo.simulate_company(c, a, n=4000)
    q = sim.summary()
    assert q["p5"] < q["p25"] < q["p50"] < q["p75"] < q["p95"]
    assert 0.0 < sim.prob_above_price < 1.0
    # Same seed, same answer; a much lower price is justified far more often.
    assert montecarlo.simulate_company(c, a, n=4000).prob_above_price == sim.prob_above_price
    cheap = make_company(price=3.0)
    assert montecarlo.simulate_company(cheap, a, n=4000).prob_above_price > 0.95


# ---- Portfolio ---------------------------------------------------------------------------------

def test_holdings_text_round_trip():
    h = portfolio.parse_holdings("voo:5000, AAPL:2000,bad,KO:-5,VOO:1000,MSFT:x")
    assert h == [("VOO", 6000.0), ("AAPL", 2000.0)]
    assert portfolio.parse_holdings(portfolio.format_holdings(h)) == h


def test_portfolio_maths():
    stock = make_company(price=12.0, sector="Technology")
    fund = make_fund(sectors={"Technology": 0.3, "Healthcare": 0.7})
    rows = [portfolio.holding_row("TEST", 1000.0, stock), portfolio.holding_row("FUND", 3000.0, fund)]
    assert rows[1]["Type"] == "Fund" and not math.isnan(rows[1]["Expected return"])
    exp = portfolio.weighted(rows, "Expected return")
    assert exp == pytest.approx((1000 * rows[0]["Expected return"] + 3000 * rows[1]["Expected return"]) / 4000)
    mix = portfolio.sector_mix(rows)
    assert mix["Technology"] == pytest.approx(1000 + 900) and mix["Healthcare"] == pytest.approx(2100)


def test_unvaluable_holding_is_kept_but_not_averaged():
    burner = make_company(fcf=(-5.0, -5.0, -5.0))
    row = portfolio.holding_row("BURN", 500.0, burner)
    assert row["Expectations"] == "Can't value" and math.isnan(row["Expected return"])
    assert portfolio.weighted([row], "Expected return") is None


def test_company_data_from_an_older_app_version_does_not_crash():
    # Company data saved before the ratio fields existed (e.g. while a server still runs older code).
    old = SimpleNamespace(
        ticker="OLD", name="Old Co", price=10.0, pe=15.0, market_cap=1000.0, shares_outstanding=100.0,
        revenue=[100.0, 110.0], free_cash_flow=[10.0, 12.0], valuation_cash_flow=[10.0, 12.0],
        net_debt=0.0, is_financial=False, sector="Technology", industry="Software",
    )
    grades = {ch.name: ch.grade for ch in quality.scorecard(old)}
    assert grades["Operating margin"] == "n/a" and grades["Debt load"] == "n/a"
    m = quality.multiples(old)
    assert m["Forward P/E"] is None and m["EV/EBITDA"] is None and m["P/E"] == 15.0
    assert "At peers' P/E" in quality.implied_prices(old, {"P/E": 20.0})


def test_future_value_without_swings_matches_compound_growth():
    proj = portfolio.project_value(10_000, 100, years=10, annual_return=0.07, volatility=0.0, n=10)
    m = 1.07 ** (1 / 12) - 1
    expected = 10_000 * 1.07 ** 10 + 100 * sum((1 + m) ** k for k in range(120))
    assert proj.loc[10, "p50"] == pytest.approx(expected, rel=1e-9)
    assert proj.loc[10, "steady"] == pytest.approx(expected, rel=1e-9)
    assert proj.loc[10, "put_in"] == 10_000 + 100 * 120
    assert list(proj.index) == list(range(11))


def test_future_value_range_widens_with_swings():
    proj = portfolio.project_value(10_000, 0, years=20, annual_return=0.07, volatility=0.16)
    assert proj.loc[20, "p10"] < proj.loc[20, "p50"] < proj.loc[20, "p90"]
    assert (proj.loc[20, "p90"] - proj.loc[20, "p10"]) > (proj.loc[5, "p90"] - proj.loc[5, "p10"])
    # The average outcome matches the steady path; the middle outcome sits a little below it.
    assert proj.loc[20, "p50"] < proj.loc[20, "steady"]


def test_portfolio_volatility_of_offsetting_holdings():
    import pandas as pd
    idx = pd.bdate_range("2023-01-02", periods=300)
    a = pd.Series(np.cumprod([1.01 if i % 2 else 1 / 1.01 for i in range(300)]), index=idx)
    b = pd.Series(np.cumprod([1 / 1.01 if i % 2 else 1.01 for i in range(300)]), index=idx)
    alone = portfolio.portfolio_volatility({"A": a}, {"A": 1.0})
    mixed = portfolio.portfolio_volatility({"A": a, "B": b}, {"A": 0.5, "B": 0.5})
    assert alone > 0.1 and mixed < alone / 5      # opposite moves largely cancel out
    assert portfolio.portfolio_volatility({}, {"A": 1.0}) is None
