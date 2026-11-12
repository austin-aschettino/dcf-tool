"""Checks of the index-fund model, the disk cache and the Excel export."""

from __future__ import annotations

import io
import math
from dataclasses import replace

import pandas as pd
import pytest

from conftest import make_company, make_fund
from dcf import (
    DCFAssumptions,
    IndexAssumptions,
    company_tables,
    fund_tables,
    implied_index_growth,
    index_scenarios,
    run_dcf,
    run_index_valuation,
    to_xlsx,
)
from dcf import cache


def flat_index(**kw) -> IndexAssumptions:
    base = dict(growth_rate=0.0, terminal_growth=0.0, required_return=0.10, payout=1.0, years=10, fade=False)
    base.update(kw)
    return IndexAssumptions(**base)


def test_no_growth_fund_value_is_earnings_over_rate():
    # Price 100, P/E 20 -> earnings $5. Paying it all out forever at 10% is worth $50.
    r = run_index_valuation(make_fund(price=100, pe=20), flat_index())
    assert r.value_per_share == pytest.approx(50.0)


def test_payout_scales_value():
    f = make_fund(price=100, pe=20)
    full = run_index_valuation(f, flat_index(payout=1.0)).value_per_share
    half = run_index_valuation(f, flat_index(payout=0.5)).value_per_share
    assert half == pytest.approx(full / 2)


def test_fees_lower_value_and_return():
    cheap = run_index_valuation(make_fund(expense=0.0), flat_index())
    pricey = run_index_valuation(make_fund(expense=0.01), flat_index())
    assert pricey.value_per_share < cheap.value_per_share
    assert pricey.implied_return < cheap.implied_return


def test_implied_return_round_trips():
    # With no growth and full payout the implied return is just the earnings yield: 1 / P/E = 5%.
    r = run_index_valuation(make_fund(price=100, pe=20), flat_index())
    assert r.implied_return == pytest.approx(0.05, abs=1e-6)


def test_implied_index_growth_round_trips():
    f = make_fund(price=100, pe=20)
    a = IndexAssumptions(growth_rate=0.05, terminal_growth=0.03, required_return=0.09)
    g = implied_index_growth(f, a)
    assert not math.isnan(g)
    assert run_index_valuation(f, replace(a, growth_rate=g, fade=False)).value_per_share == pytest.approx(100, rel=1e-6)


def test_bond_fund_cannot_be_valued():
    with pytest.raises(ValueError):
        run_index_valuation(make_fund(pe=None), flat_index())
    assert math.isnan(implied_index_growth(make_fund(pe=None), flat_index()))


def test_index_scenarios_are_ordered():
    f = make_fund()
    a = IndexAssumptions(growth_rate=0.06, terminal_growth=0.04, required_return=0.09)
    s = index_scenarios(a)
    vals = [run_index_valuation(f, s[k]).value_per_share for k in ("Pessimistic", "Middle (your settings)", "Optimistic")]
    assert vals[0] < vals[1] < vals[2]


# ---- Disk cache ----------------------------------------------------------------------------

def test_cache_reuses_saved_value():
    calls = []

    def fetch():
        calls.append(1)
        return {"price": 42}

    assert cache.cached("XYZ", fetch) == {"price": 42}
    assert cache.cached("XYZ", fetch) == {"price": 42}
    assert len(calls) == 1                     # second call came from disk
    cache.cached("XYZ", fetch, refresh=True)
    assert len(calls) == 2                     # refresh forces a new download


def test_cache_expires(monkeypatch):
    cache.write("OLD", 1)
    assert cache.read("OLD", max_age_hours=1) == 1
    assert cache.read("OLD", max_age_hours=0) is None


def test_cache_survives_corrupt_file():
    cache.write("BAD", 1)
    cache._path("BAD").write_bytes(b"not a pickle")
    assert cache.read("BAD") is None


# ---- Excel export --------------------------------------------------------------------------

def _sheets(xlsx: bytes):
    return pd.read_excel(io.BytesIO(xlsx), sheet_name=None, index_col=0)


def test_company_excel_report_has_all_sheets():
    c = make_company(fcf=(100, 110, 120), shares=10, price=100)
    a = DCFAssumptions(growth_rate=0.05, terminal_growth=0.025, wacc=0.09)
    sheets = _sheets(to_xlsx(company_tables(c, a, run_dcf(c, a))))
    assert set(sheets) == {"Summary", "Assumptions", "Projection", "Scenarios", "What-if (value per share)", "Past financials"}
    assert sheets["Summary"].loc["Estimated value / share", "Value"] == pytest.approx(run_dcf(c, a).value_per_share)


def test_fund_excel_report_has_holdings():
    f = make_fund(holdings=[("AAA", "A Co", 0.1)], sectors={"Technology": 0.5})
    a = IndexAssumptions(growth_rate=0.06, terminal_growth=0.04, required_return=0.09)
    sheets = _sheets(to_xlsx(fund_tables(f, a, run_index_valuation(f, a))))
    assert {"Summary", "Top holdings", "Sectors"} <= set(sheets)
