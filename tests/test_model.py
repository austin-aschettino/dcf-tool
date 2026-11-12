"""Checks of the stock DCF math against answers worked out by hand."""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from conftest import make_company
from dcf import (
    DCFAssumptions,
    base_cash,
    check_company,
    company_scenarios,
    implied_growth,
    make_scenarios,
    run_dcf,
    sensitivity_table,
)


def flat(wacc=0.10, years=5, **kw) -> DCFAssumptions:
    return DCFAssumptions(growth_rate=0.0, terminal_growth=0.0, wacc=wacc, years=years, **kw)


def test_no_growth_perpetuity_equals_cash_over_rate():
    # $100 a year forever at 10% is worth $100 / 0.10 = $1,000, whatever the forecast length.
    c = make_company(fcf=(100, 100, 100), shares=1)
    for years in (3, 5, 10):
        r = run_dcf(c, flat(years=years))
        assert r.enterprise_value == pytest.approx(1000.0)
        assert r.value_per_share == pytest.approx(1000.0)


def test_gordon_growth_with_constant_growth():
    # Constant 3% growth at 10%: value = CF1 / (r - g) = 103 / 0.07.
    c = make_company(fcf=(100, 100, 100), shares=1)
    a = DCFAssumptions(growth_rate=0.03, terminal_growth=0.03, wacc=0.10, years=5, fade=False)
    assert run_dcf(c, a).enterprise_value == pytest.approx(103 / 0.07)


def test_discount_factors_and_present_values():
    c = make_company(fcf=(100, 100, 100))
    r = run_dcf(c, flat(years=3))
    assert r.discount_factors == pytest.approx([1 / 1.1, 1 / 1.1 ** 2, 1 / 1.1 ** 3])
    assert r.pv_fcf == pytest.approx([100 / 1.1, 100 / 1.1 ** 2, 100 / 1.1 ** 3])


def test_growth_fades_linearly_to_terminal():
    c = make_company()
    a = DCFAssumptions(growth_rate=0.10, terminal_growth=0.02, wacc=0.09, years=5, fade=True)
    assert run_dcf(c, a).growth_path == pytest.approx([0.10, 0.08, 0.06, 0.04, 0.02])


def test_net_debt_is_subtracted_per_share():
    c = make_company(fcf=(100, 100, 100), shares=10, debt=300, cash=100)
    r = run_dcf(c, flat())
    assert r.equity_value == pytest.approx(1000 - 200)
    assert r.value_per_share == pytest.approx(80.0)


def test_wacc_must_exceed_terminal_growth():
    with pytest.raises(ValueError):
        run_dcf(make_company(), DCFAssumptions(growth_rate=0.05, terminal_growth=0.10, wacc=0.08))


def test_base_cash_average_vs_latest():
    c = make_company(fcf=(50, 100, 120, 150))
    assert base_cash(c, "avg3") == pytest.approx((100 + 120 + 150) / 3)
    assert base_cash(c, "latest") == pytest.approx(150)


def test_implied_growth_round_trips():
    c = make_company(fcf=(100, 100, 100), shares=1, price=1500)
    a = DCFAssumptions(growth_rate=0.05, terminal_growth=0.02, wacc=0.09)
    g = implied_growth(c, a)
    assert not math.isnan(g)
    assert run_dcf(c, replace(a, growth_rate=g, fade=False)).value_per_share == pytest.approx(1500, rel=1e-6)


def test_implied_growth_nan_when_price_unreachable():
    c = make_company(fcf=(100, 100, 100), shares=1, price=1e12)
    assert math.isnan(implied_growth(c, flat()))


def test_sensitivity_centre_matches_base_case():
    c = make_company(fcf=(100, 110, 120), shares=10)
    a = DCFAssumptions(growth_rate=0.06, terminal_growth=0.025, wacc=0.09)
    grid = sensitivity_table(c, a)
    assert grid.iat[2, 2] == pytest.approx(run_dcf(c, a).value_per_share)
    # Higher discount rate -> lower value; higher growth -> higher value.
    assert grid.iat[0, 2] > grid.iat[4, 2]
    assert grid.iat[2, 4] > grid.iat[2, 0]


def test_scenarios_are_ordered():
    c = make_company(fcf=(100, 110, 120), shares=10)
    a = DCFAssumptions(growth_rate=0.06, terminal_growth=0.025, wacc=0.09)
    s = make_scenarios(a)
    values = [run_dcf(c, s[k]).value_per_share for k in ("Pessimistic", "Middle (your settings)", "Optimistic")]
    assert values[0] < values[1] < values[2]
    table = company_scenarios(c, a)
    assert list(table.index) == ["Pessimistic", "Middle (your settings)", "Optimistic"]


# ---- Banks and other financial companies --------------------------------------------------

def test_banks_use_cash_returned_and_skip_debt():
    bank = make_company(
        fcf=(-500, 900, -300), shares=1, debt=10_000, cash=0,
        sector="Financial Services", industry="Banks - Diversified",
        dividends=(40, 40, 40), buybacks=(60, 60, 60),
    )
    assert bank.is_financial
    r = run_dcf(bank, flat())
    assert r.method == "payout"
    assert r.base_fcf == pytest.approx(100)        # dividends + buybacks, not the wild FCF
    assert r.net_debt == 0                          # bank debt is not subtracted
    assert r.value_per_share == pytest.approx(1000)


def test_payment_networks_are_not_treated_as_banks():
    visa = make_company(sector="Financial Services", industry="Credit Services")
    assert not visa.is_financial


def test_bank_gets_explanatory_warning():
    bank = make_company(sector="Financial Services", industry="Banks - Regional",
                        dividends=(10, 10, 10), buybacks=(5, 5, 5))
    blocking, warnings = check_company(bank)
    assert blocking is None
    assert any("dividends + buybacks" in w for w in warnings)


# ---- Cash-burning and uneven companies -----------------------------------------------------

def test_negative_cash_flow_blocks_valuation():
    blocking, _ = check_company(make_company(fcf=(-100, -50, -20)))
    assert blocking and "negative" in blocking


def test_some_negative_years_warn_but_do_not_block():
    blocking, warnings = check_company(make_company(fcf=(-50, 200, 250)))
    assert blocking is None
    assert any("negative" in w for w in warnings)


def test_volatile_cash_flow_warns():
    blocking, warnings = check_company(make_company(fcf=(10, 300, 40)))
    assert blocking is None
    assert any("swung" in w for w in warnings)


def test_steady_company_has_no_warnings():
    assert check_company(make_company(fcf=(100, 105, 110))) == (None, [])


def test_implied_growth_nan_for_cash_burning_company():
    c = make_company(fcf=(-100, -50, -20), price=10)
    assert math.isnan(implied_growth(c, flat()))
