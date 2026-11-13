"""Checks of the backtest: point-in-time SEC data, split handling, grouping and summary maths."""

from __future__ import annotations

import pandas as pd
import pytest

from dcf import sec
from dcf.backtest import assign_groups, estimate_beta, forward_return, summarize, value_on


def fact(val, end, filed, start=None, form="10-K"):
    e = {"val": val, "end": end, "filed": filed, "form": form, "accn": f"acc-{filed}"}
    if start:
        e["start"] = start
    return e


def facts(**tags):
    return {"facts": {"us-gaap": {t: {"units": {"USD": v}} for t, v in tags.items()}}}


# ---- Point-in-time SEC extraction ------------------------------------------------------------

def test_only_filings_known_at_the_date_are_used():
    f = facts(NetCashProvidedByUsedInOperatingActivities=[
        fact(100, "2019-12-31", "2020-02-15", "2019-01-01"),
        fact(120, "2020-12-31", "2021-02-15", "2020-01-01"),
    ])
    tag = sec.TAGS["ocf"]
    assert sec.annual_values(f, tag, "2020-06-01") == {"2019-12-31": 100}
    assert sec.annual_values(f, tag, "2021-06-01") == {"2019-12-31": 100, "2020-12-31": 120}


def test_restatements_count_only_after_they_are_filed():
    f = facts(NetCashProvidedByUsedInOperatingActivities=[
        fact(100, "2019-12-31", "2020-02-15", "2019-01-01"),
        fact(90, "2019-12-31", "2021-02-15", "2019-01-01"),   # restated in next year's report
    ])
    tag = sec.TAGS["ocf"]
    assert sec.annual_values(f, tag, "2020-06-01")["2019-12-31"] == 100
    assert sec.annual_values(f, tag, "2021-06-01")["2019-12-31"] == 90


def test_quarters_and_quarterly_reports_are_ignored():
    f = facts(NetCashProvidedByUsedInOperatingActivities=[
        fact(30, "2020-03-31", "2020-05-01", "2020-01-01", form="10-Q"),
        fact(30, "2020-03-31", "2021-02-15", "2020-01-01"),          # a quarter inside a 10-K
        fact(120, "2020-12-31", "2021-02-15", "2020-01-01"),
    ])
    assert sec.annual_values(f, sec.TAGS["ocf"], "2021-06-01") == {"2020-12-31": 120}


def test_earlier_tags_take_priority():
    f = facts(Revenues=[fact(500, "2020-12-31", "2021-02-01", "2020-01-01")],
              SalesRevenueNet=[fact(480, "2020-12-31", "2021-02-01", "2020-01-01"),
                               fact(450, "2019-12-31", "2020-02-01", "2019-01-01")])
    assert sec.annual_values(f, sec.TAGS["revenue"], "2021-06-01") == {"2020-12-31": 500, "2019-12-31": 450}


def test_share_classes_from_one_filing_are_added():
    f = {"facts": {"dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
        {"val": 300, "end": "2021-01-20", "filed": "2021-02-01", "accn": "a1", "form": "10-K"},
        {"val": 50, "end": "2021-01-20", "filed": "2021-02-01", "accn": "a1", "form": "10-K"},
        {"val": 340, "end": "2021-04-20", "filed": "2021-05-01", "accn": "a2", "form": "10-Q"},
    ]}}}}}
    assert sec.shares_outstanding(f, "2021-03-01") == 350
    assert sec.shares_outstanding(f, "2021-06-01") == 340


def test_bank_industry_codes():
    assert sec.sic_to_sector(6021)[1] == "Banks"
    assert sec.sic_to_sector(6311)[1] == "Insurance"
    assert sec.sic_to_sector(3571) == ("", "")


# ---- Prices -----------------------------------------------------------------------------------

def test_forward_return_and_future_dates():
    idx = pd.bdate_range("2020-01-01", "2021-06-30")
    adj = pd.Series(100.0, index=idx)
    adj.loc["2021-01-01":] = 110.0
    assert forward_return(adj, pd.Timestamp("2020-03-02")) == pytest.approx(0.10)
    assert forward_return(adj, pd.Timestamp("2021-03-01")) is None   # a year later hasn't happened yet


def test_value_on_uses_last_trading_day():
    s = pd.Series([1.0, 2.0], index=pd.to_datetime(["2020-03-27", "2020-03-30"]))
    assert value_on(s, pd.Timestamp("2020-04-01")) == 2.0
    assert value_on(s, pd.Timestamp("2020-05-01")) is None   # too stale


def test_beta_of_a_stock_that_moves_twice_as_much():
    idx = pd.bdate_range("2018-01-01", "2020-04-01")
    rng = pd.Series(range(len(idx)), index=idx)
    market = 100 * (1 + 0.01 * ((rng % 7) - 3) / 3).cumprod()
    stock = 100 * (1 + 2 * market.pct_change().fillna(0)).cumprod()
    assert estimate_beta(stock, market, pd.Timestamp("2020-04-01")) == pytest.approx(2.0, abs=0.05)


# ---- Grouping and summary ------------------------------------------------------------------

def make_signals():
    rows = []
    for year, rets in [(2018, [0.30, 0.20, 0.10, 0.00, -0.05, -0.10]), (2019, [0.05, 0.10, 0.0, 0.15, 0.2, 0.1])]:
        for i, r in enumerate(rets):
            rows.append({"year": year, "ticker": f"S{i}", "upside": 0.5 - 0.2 * i, "fwd_1y": r,
                         "excluded": "", "benchmark_fwd_1y": 0.08})
    rows.append({"year": 2018, "ticker": "BURN", "upside": None, "fwd_1y": 0.5, "excluded": "negative cash flow",
                 "benchmark_fwd_1y": 0.08})
    return pd.DataFrame(rows)


def test_groups_are_equal_sized_and_cheapest_first():
    g = assign_groups(make_signals())
    y = g[g["year"] == 2018]
    assert y.loc[y["ticker"] == "S0", "group"].iloc[0] == 0
    assert y.loc[y["ticker"] == "S5", "group"].iloc[0] == 2
    assert y["group"].value_counts().tolist() == [2, 2, 2]
    assert pd.isna(y.loc[y["ticker"] == "BURN", "group"].iloc[0])   # excluded stocks get no group


def test_summary_maths():
    s = summarize(make_signals())
    y18 = s.yearly[0]
    assert y18["Cheapest third"] == pytest.approx(0.25)
    assert y18["Most expensive third"] == pytest.approx(-0.075)
    assert y18["rank_correlation"] == pytest.approx(1.0)        # perfectly ordered in 2018
    assert s.yearly[1]["rank_correlation"] < 0                  # reversed-ish in 2019
    assert s.cheap_beat_expensive == 1
    assert s.growth_of_1["Cheapest third"] == pytest.approx(1.25 * 1.075)
    assert s.avg_return["S&P 500 (SPY)"] == pytest.approx(0.08)


# ---- Data-quality safeguards -------------------------------------------------------------

def test_histories_from_two_sec_ids_are_combined():
    old = facts(NetCashProvidedByUsedInOperatingActivities=[fact(100, "2017-12-31", "2018-02-01", "2017-01-01")])
    new = facts(NetCashProvidedByUsedInOperatingActivities=[fact(130, "2020-12-31", "2021-02-01", "2020-01-01")])
    merged = sec.merge_facts([old, new])
    assert sec.annual_values(merged, sec.TAGS["ocf"], "2021-06-01") == {"2017-12-31": 100, "2020-12-31": 130}


def test_share_count_resists_bad_figures():
    pick = sec.pick_share_count
    # Mastercard: the cover page lists one share class; diluted and basic agree on the real total.
    assert pick(cover=122e6, diluted=1101e6, basic=1095e6, balance_sheet=None) == 1095e6   # the middle value
    # Only two figures that disagree: trust the one that isn't the cover page.
    assert pick(cover=122e6, diluted=1101e6, basic=None, balance_sheet=None) == 1101e6
    # McDonald's: diluted tagged in millions (721.9) is mis-scaled and ignored.
    assert pick(cover=714e6, diluted=721.9, basic=None, balance_sheet=None) == 714e6
    # Normal case: two figures that agree are averaged.
    assert pick(cover=100e6, diluted=101e6, basic=None, balance_sheet=None) == pytest.approx(100.5e6)
    assert pick(None, None, None, None) is None
    assert pick(cover=5.0, diluted=None, basic=None, balance_sheet=None) is None


def test_lone_sparse_cover_page_share_count_is_not_trusted():
    usd = lambda v, end, start: fact(v, end, "2021-02-01", start)
    f = facts(
        NetCashProvidedByUsedInOperatingActivities=[usd(100, "2019-12-31", "2019-01-01"), usd(110, "2020-12-31", "2020-01-01")],
        PaymentsToAcquirePropertyPlantAndEquipment=[usd(10, "2019-12-31", "2019-01-01"), usd(10, "2020-12-31", "2020-01-01")],
    )
    f["facts"]["dei"] = {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
        {"val": 469e6, "end": "2021-01-20", "filed": "2021-02-01", "accn": "a1", "form": "10-K"}]}}}
    assert sec.snapshot(f, "2021-06-01") is None          # only 1 cover entry ever and nothing to check it against
    f["facts"]["dei"]["EntityCommonStockSharesOutstanding"]["units"]["shares"] = [
        {"val": 469e6, "end": f"20{y}-01-20", "filed": f"20{y}-02-01", "accn": f"a{y}", "form": "10-K"} for y in range(10, 22)]
    assert sec.snapshot(f, "2021-06-01")["shares"] == 469e6   # a regular filer's cover page is fine
