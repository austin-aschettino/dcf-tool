"""Checks of the fair-value methods ("football field") and the range most methods agree on."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from conftest import make_company
from dcf import DCFAssumptions
from dcf.fairvalue import (Method, fair_value_band, fair_value_methods, has_underlying, model_range,
                           price_position, underlying_cash_flow)


def investing_company():
    """Operating cash 100 a year; capex 70 of which only 20 is maintenance (depreciation)."""
    c = make_company(fcf=(30.0, 30.0, 30.0))
    c.operating_cash_flow = [100.0, 100.0, 100.0]
    c.capex = [-70.0, -70.0, -70.0]
    c.depreciation = [20.0, 20.0, 20.0]
    return c


def test_underlying_cash_flow_counts_only_maintenance_spending():
    c = investing_company()
    assert underlying_cash_flow(c) == [80.0, 80.0, 80.0]      # 100 - min(70, 20)
    assert has_underlying(c)
    # Maintenance can't exceed what was actually spent.
    c.depreciation = [90.0, 90.0, 90.0]
    assert underlying_cash_flow(c) == [30.0, 30.0, 30.0]
    # Missing depreciation -> not available; banks never get it.
    c.depreciation = []
    assert all(math.isnan(v) for v in underlying_cash_flow(c)) and not has_underlying(c)
    bank = make_company(sector="Financial Services", industry="Banks - Diversified")
    assert not has_underlying(bank)


def test_methods_and_their_order():
    c = investing_company()
    c.target_low, c.target_mean, c.target_high, c.analyst_count = 8.0, 12.0, 15.0, 20
    a = DCFAssumptions(growth_rate=0.05, terminal_growth=0.02, wacc=0.09, years=10)
    hist = pd.Series([9.0, 11.0, 10.0], index=pd.date_range("2026-01-01", periods=3))
    ms = fair_value_methods(c, a, {"At peers' P/E": 14.0, "At peers' EV/EBITDA": 10.0}, hist)
    assert [m.kind for m in ms] == ["model", "model", "peers", "analysts", "market"]
    reported, underlying = ms[0], ms[1]
    assert reported.low <= reported.mid <= reported.high
    assert underlying.mid > reported.mid                      # growth spending no longer counted as a cost
    assert ms[2].low == 10.0 and ms[2].high == 14.0 and ms[2].mid == 12.0
    assert not ms[4].counts                                   # the trading range is context only


def test_negative_cash_flow_skips_the_model_but_keeps_other_methods():
    c = make_company(fcf=(-10.0, -10.0, -10.0))
    c.target_low, c.target_mean, c.target_high = 5.0, 8.0, 12.0
    ms = fair_value_methods(c, DCFAssumptions(0.05, 0.02, 0.09), {"At peers' P/E": 9.0})
    assert [m.kind for m in ms] == ["peers", "analysts"]
    assert model_range(c, DCFAssumptions(0.05, 0.02, 0.09)) is None


def test_band_drops_the_extremes_when_there_are_enough_methods():
    m = lambda mid: Method("x", mid * 0.8, mid, mid * 1.2, "model")
    assert fair_value_band([m(30), m(100), m(140), m(300)]) == (100, 120, 140)   # 30 and 300 left out
    assert fair_value_band([m(50), m(100), m(150)]) == (50, 100, 150)
    assert fair_value_band([m(100)]) == (80, 100, 120)                           # one method: its own range
    context = Method("traded", 1, 500, 900, "market", counts=False)
    assert fair_value_band([context]) is None


def test_price_position():
    band = (100.0, 120.0, 140.0)
    assert price_position(90, band) == "below"
    assert price_position(120, band) == "within"
    assert price_position(150, band) == "above"


def test_data_saved_before_a_field_existed_still_loads():
    """The live-app crash: company data cached before 'depreciation' existed, restored into newer code."""
    import pickle
    from types import SimpleNamespace

    c = make_company()
    del c.__dict__["depreciation"], c.__dict__["forward_pe"]   # what an older version saved
    restored = pickle.loads(pickle.dumps(c))                     # how the cache brings it back
    assert restored.depreciation == [] and restored.forward_pe is None
    assert fair_value_methods(restored, DCFAssumptions(0.05, 0.02, 0.09))[0].kind == "model"   # no crash

    # An object with no such attribute at all (an older class still in memory) is handled too.
    bare = SimpleNamespace(**{k: v for k, v in c.__dict__.items()})
    assert all(math.isnan(v) for v in underlying_cash_flow(bare))


def test_fund_data_also_fills_missing_fields():
    import pickle
    from conftest import make_fund
    f = make_fund()
    del f.__dict__["holdings"]
    assert pickle.loads(pickle.dumps(f)).holdings == []
