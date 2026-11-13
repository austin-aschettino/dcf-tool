"""Checks of the price-outlook math (typical swings, future fair value, analyst targets)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from conftest import make_company, make_fund
from dcf import DCFAssumptions, IndexAssumptions, annual_volatility, build_outlook, company_outlook, cone_path, fund_outlook
from dcf.outlook import Z_LIKELY, Z_WIDE, expected_price, price_range, yearly_return


def series_with_daily_vol(daily_sigma: float, days: int = 260, seed: int = 1) -> pd.Series:
    rng = np.random.default_rng(seed)
    logs = rng.normal(0.0, daily_sigma, days)
    return pd.Series(100 * np.exp(np.cumsum(logs)), index=pd.bdate_range("2025-01-01", periods=days))


def test_volatility_of_a_steady_price_is_zero():
    s = pd.Series([100 * 1.001 ** i for i in range(300)])
    assert annual_volatility(s) == pytest.approx(0.0, abs=1e-9)


def test_volatility_matches_the_noise_that_went_in():
    # 1.26% a day is about 20% a year (x sqrt(252)). Use the whole long series so sampling noise is small.
    vol = annual_volatility(series_with_daily_vol(0.0126, days=2000), lookback_days=1999)
    assert vol == pytest.approx(0.20, abs=0.01)


def test_volatility_needs_enough_data():
    assert math.isnan(annual_volatility(pd.Series([100.0, 101.0, 99.0])))


def test_expected_price_grows_at_return_less_dividends():
    assert expected_price(100, 0.10, 0.02, 1) == pytest.approx(108)
    assert expected_price(100, 0.10, 0.0, 2) == pytest.approx(121)


def test_ranges_are_symmetric_in_log_terms_and_widen_with_time():
    lo, hi = price_range(100, 0.2, 1, Z_LIKELY)
    assert lo * hi == pytest.approx(100 * 100)
    assert hi == pytest.approx(100 * math.exp(0.2))
    lo5, hi5 = price_range(100, 0.2, 5, Z_LIKELY)
    assert lo5 < lo and hi5 > hi
    wlo, whi = price_range(100, 0.2, 1, Z_WIDE)
    assert wlo < lo and whi > hi


def test_yearly_return_includes_dividends():
    assert yearly_return(100, 121, 2) == pytest.approx(0.10)
    assert yearly_return(100, 110, 1, dividend_yield=0.02) == pytest.approx(0.12)


def test_build_outlook_ties_together():
    o = build_outlook(price=100, expected_return=0.09, dividend_yield=0.01, prices=series_with_daily_vol(0.0126),
                      years=3, fair_today={"Pessimistic": 80, "Middle (your settings)": 100, "Optimistic": 130})
    assert o.center == pytest.approx(100 * 1.08 ** 3)
    assert o.fair_future["Middle (your settings)"] == pytest.approx(o.center)  # fair value == price -> same path
    assert o.fair_future["Pessimistic"] < o.fair_future["Optimistic"]
    assert o.wide[0] < o.likely[0] < o.center < o.likely[1] < o.wide[1]
    t = o.table()
    assert ("Model fair value", "Optimistic") in t.index
    assert t.loc[("Typical swings", "Middle"), "Change vs. today"] == pytest.approx(1.08 ** 3 - 1)


def test_outlook_without_price_history_still_gives_fair_values():
    o = build_outlook(100, 0.09, 0.0, None, 1, {"Middle (your settings)": 90})
    assert not o.has_volatility
    assert o.fair_future["Middle (your settings)"] == pytest.approx(90 * 1.09)
    assert "Typical swings" not in o.table().index.get_level_values(0)


def test_company_outlook_includes_analyst_targets():
    c = make_company(fcf=(100, 110, 120), shares=10, price=100, dividend_rate=2.0,
                     target_low=80, target_mean=110, target_high=150, analyst_count=12, recommendation="buy")
    a = DCFAssumptions(growth_rate=0.05, terminal_growth=0.025, wacc=0.09)
    o = company_outlook(c, a, series_with_daily_vol(0.0126), years=1)
    assert c.dividend_yield == pytest.approx(0.02)
    assert o.analysts["mean"] == 110
    assert o.table().loc[("Analysts (12-month)", "Average target"), "Change vs. today"] == pytest.approx(0.10)
    assert set(o.fair_future) == {"Pessimistic", "Middle (your settings)", "Optimistic"}


def test_cash_burning_company_gets_swings_but_no_fair_value():
    c = make_company(fcf=(-100, -50, -20), price=50)
    o = company_outlook(c, DCFAssumptions(growth_rate=0.05, terminal_growth=0.025, wacc=0.09),
                        series_with_daily_vol(0.02), years=1)
    assert o.fair_future == {}
    assert o.has_volatility


def test_fund_outlook_and_bond_fund():
    a = IndexAssumptions(growth_rate=0.06, terminal_growth=0.04, required_return=0.09)
    o = fund_outlook(make_fund(expense=0.001), a, series_with_daily_vol(0.01), years=5)
    assert o.expected_return == pytest.approx(0.089)
    assert len(o.fair_future) == 3
    bond = fund_outlook(make_fund(pe=None), a, series_with_daily_vol(0.003), years=1)
    assert bond.fair_future == {} and bond.has_volatility


def test_cone_path_starts_at_price_and_ends_at_horizon():
    path = cone_path(100, 0.1, 0.0, 0.2, 2, start=pd.Timestamp("2026-01-01"))
    assert path.iloc[0]["center"] == pytest.approx(100)
    assert path.iloc[0]["wide_low"] == pytest.approx(100)
    assert path.iloc[-1]["center"] == pytest.approx(121)
    assert path.index[-1].year == 2028
