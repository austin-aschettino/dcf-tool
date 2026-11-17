"""Reverse DCF: start from today's price and work out what the market must be assuming.

A normal DCF goes assumptions -> value. A reverse DCF goes price -> assumptions:
"for today's price to be fair, how fast must cash flow grow?" or "if my growth comes
true, what return would I earn buying at today's price?"
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Dict, Iterable, List, Tuple

import pandas as pd

from .data import CompanyData
from .fund import FundData, IndexAssumptions, _value, implied_index_growth
from .model import DCFAssumptions, base_cash, historical_cagr, implied_growth, run_dcf

LONG_RUN_EARNINGS_GROWTH = 0.06   # rough long-run nominal earnings growth of large US companies


def _nan(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def implied_discount_rate(c: CompanyData, a: DCFAssumptions, hi: float = 1.0) -> float:
    """The required return that makes the estimate equal today's price, with the user's growth path.

    Put another way: the yearly return you'd earn buying at today's price if that growth comes true.
    NaN when no rate between long-term growth and 100% works.
    """
    if not c.price or base_cash(c, a.base) <= 0:
        return float("nan")
    lo = a.terminal_growth + 1e-4

    def value(r: float) -> float:
        return run_dcf(c, replace(a, wacc=r)).value_per_share

    if value(lo) < c.price or value(hi) > c.price:
        return float("nan")
    for _ in range(100):            # value falls as the rate rises
        mid = (lo + hi) / 2
        if value(mid) > c.price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def implied_growth_grid(c: CompanyData, a: DCFAssumptions, rates: Iterable[float],
                        years: Iterable[int]) -> pd.DataFrame:
    """Growth priced in for each required return (rows) and forecast length (columns)."""
    years = list(years)
    rows = {}
    for r in rates:
        rows[r] = [implied_growth(c, replace(a, wacc=r, years=n)) if r > a.terminal_growth else float("nan")
                   for n in years]
    return pd.DataFrame.from_dict(rows, orient="index", columns=years)


def fund_implied_growth_grid(f: FundData, a: IndexAssumptions, rates: Iterable[float],
                             years: Iterable[int]) -> pd.DataFrame:
    years = list(years)
    rows = {r: [implied_index_growth(f, replace(a, required_return=r, years=n)) for n in years] for r in rates}
    return pd.DataFrame.from_dict(rows, orient="index", columns=years)


def needed_path(c: CompanyData, a: DCFAssumptions, g: float) -> List[float]:
    """Yearly cash flow the company would have to produce, growing steadily at `g`."""
    if _nan(g):
        return []
    return run_dcf(c, replace(a, growth_rate=g, fade=False)).projected_fcf


def fund_needed_path(f: FundData, a: IndexAssumptions, g: float) -> List[float]:
    """Earnings per fund share needed each year, growing steadily at `g`."""
    if _nan(g):
        return []
    return _value(f, replace(a, growth_rate=g, fade=False), a.required_return + f.expense_ratio)[1]["earnings"]


def growth_benchmarks(c: CompanyData) -> Dict[str, float]:
    """Reality checks to compare the growth priced in against (missing ones are left out)."""
    out = {
        "Past sales growth": historical_cagr(c.revenue),
        ("Past cash returned growth" if c.is_financial else "Past free cash flow growth"):
            historical_cagr(c.valuation_cash_flow),
        "Analysts' forecast (next year)": c.analyst_growth,
    }
    return {k: v for k, v in out.items() if not _nan(v)}


def reference_growth(c: CompanyData) -> float:
    """A single yardstick for realistic growth: the average of past sales growth and analysts' forecast.

    Cash-flow growth is only used when neither exists, because it swings a lot from year to year.
    """
    picks = [v for v in (historical_cagr(c.revenue), c.analyst_growth) if not _nan(v)]
    if not picks:
        fcf = historical_cagr(c.valuation_cash_flow)
        return float("nan") if _nan(fcf) else fcf
    return sum(picks) / len(picks)


def demand_level(g: float, reference: float, what: str = "the company") -> Tuple[str, str, str]:
    """(headline, colour, explanation) for how demanding the growth priced in is.

    `reference` is the best evidence of what's realistic (e.g. past growth or analysts' forecast).
    Colour is green / neutral / red, matching the verdict cards (neutral = no colour).
    """
    if _nan(g):
        return ("Can't work out what's priced in", "neutral",
                "No growth rate in a sensible range makes the estimate match today's price with these settings.")
    if _nan(reference):
        reference = LONG_RUN_EARNINGS_GROWTH
        ref_words = f"the long-run average for large companies (about {reference:.0%})"
    else:
        ref_words = f"{what}'s track record and forecasts (about {reference:.1%})"
    gap = g - reference
    if g > 0.20 or gap > 0.08:
        return ("Very demanding expectations", "red",
                f"The price assumes {g:.1%} growth a year, far above {ref_words}. Few companies keep up growth "
                "like that for years, so the price leaves little room for disappointment.")
    if gap > 0.02:
        return ("Demanding expectations", "red",
                f"The price assumes {g:.1%} growth a year, above {ref_words}. It needs things to go better "
                "than they have been.")
    if gap >= -0.02:
        return ("Expectations in line with the record", "neutral",
                f"The price assumes {g:.1%} growth a year, close to {ref_words}. The market is roughly "
                "betting on more of the same.")
    return ("Modest expectations", "green",
            f"The price assumes only {g:.1%} growth a year, below {ref_words}. If growth holds up, today's "
            "price asks for less than the record suggests.")
