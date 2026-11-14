"""Checks of the reverse DCF: each implied number, plugged back in, should reproduce today's price."""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from conftest import make_company, make_fund
from dcf import (
    DCFAssumptions,
    IndexAssumptions,
    demand_level,
    fund_implied_growth_grid,
    fund_needed_path,
    growth_benchmarks,
    implied_discount_rate,
    implied_growth,
    implied_growth_grid,
    implied_index_growth,
    needed_path,
    reference_growth,
    run_dcf,
    run_index_valuation,
)


def test_implied_discount_rate_reproduces_the_price():
    c = make_company(fcf=(100.0, 100.0, 100.0), price=12.0, shares=100.0)
    a = DCFAssumptions(growth_rate=0.05, terminal_growth=0.02, wacc=0.09, years=5)
    r = implied_discount_rate(c, a)
    assert run_dcf(c, replace(a, wacc=r)).value_per_share == pytest.approx(c.price, rel=1e-6)


def test_no_growth_forever_gives_the_cash_yield():
    # $100 a year forever with no growth, priced at $1,000 in total -> a 10% return.
    c = make_company(fcf=(100.0, 100.0, 100.0), price=10.0, shares=100.0)
    a = DCFAssumptions(growth_rate=0.0, terminal_growth=0.0, wacc=0.08, years=5, fade=False)
    assert implied_discount_rate(c, a) == pytest.approx(0.10, abs=1e-6)


def test_implied_rate_is_nan_without_positive_cash():
    c = make_company(fcf=(-10.0, -10.0, -10.0))
    assert math.isnan(implied_discount_rate(c, DCFAssumptions(0.05, 0.02, 0.09)))


def test_growth_grid_matches_single_calculation_and_moves_the_right_way():
    c = make_company(price=15.0)
    a = DCFAssumptions(growth_rate=0.05, terminal_growth=0.02, wacc=0.09, years=5)
    grid = implied_growth_grid(c, a, [0.08, 0.09, 0.10], [5, 10])
    assert grid.loc[0.09, 5] == pytest.approx(implied_growth(c, a))
    assert grid.loc[0.08, 5] < grid.loc[0.09, 5] < grid.loc[0.10, 5]   # higher return -> more growth needed
    assert grid.loc[0.09, 10] < grid.loc[0.09, 5]                       # longer runway -> less growth a year


def test_needed_path_grows_steadily_at_the_implied_rate():
    c = make_company(price=15.0)
    a = DCFAssumptions(growth_rate=0.05, terminal_growth=0.02, wacc=0.09, years=5)
    g = implied_growth(c, a)
    path = needed_path(c, a, g)
    assert len(path) == 5
    assert path[0] == pytest.approx(100 * (1 + g)) and path[-1] == pytest.approx(100 * (1 + g) ** 5)
    assert needed_path(c, a, float("nan")) == []


def test_fund_reverse_pieces():
    f = make_fund(price=100.0, pe=20.0)
    a = IndexAssumptions(growth_rate=0.06, terminal_growth=0.04, required_return=0.09)
    g = implied_index_growth(f, a)
    grid = fund_implied_growth_grid(f, a, [0.08, 0.09], [10, 20])
    assert grid.loc[0.09, 10] == pytest.approx(g)
    path = fund_needed_path(f, a, g)
    assert path[0] == pytest.approx(f.earnings_per_share * (1 + g))
    # Plugging the implied growth back in reproduces the price.
    assert run_index_valuation(f, replace(a, growth_rate=g, fade=False)).value_per_share == pytest.approx(100.0, rel=1e-6)


def test_benchmarks_and_yardstick():
    c = make_company(analyst_growth=0.10)
    c.revenue = [100.0, 110.0, 121.0]            # 10% a year
    b = growth_benchmarks(c)
    assert b["Past sales growth"] == pytest.approx(0.10)
    assert b["Analysts' forecast (next year)"] == 0.10
    assert reference_growth(c) == pytest.approx(0.10)
    c.analyst_growth = 0.20
    assert reference_growth(c) == pytest.approx(0.15)   # average of the two


def test_demand_levels():
    assert demand_level(0.03, 0.10)[1] == "green"
    assert demand_level(0.10, 0.10)[1] == "orange"
    assert demand_level(0.14, 0.10)[0] == "Demanding expectations"
    assert demand_level(0.25, 0.20)[0] == "Very demanding expectations"
    assert demand_level(float("nan"), 0.10)[1] == "orange"
    assert "long-run average" in demand_level(0.05, float("nan"))[2]
