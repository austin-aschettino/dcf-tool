"""Fair value by several methods (a "football field"), instead of one model number.

Professionals rarely trust a single discounted-cash-flow figure. They show a range from each
method side by side, with today's price drawn across them. This module builds those ranges:

- the cash-flow model on reported free cash flow (the app's main model);
- the same model on *underlying* cash flow, which counts only the spending needed to maintain
  the business (approximated by depreciation), not spending on growth;
- what the share would cost if priced like similar companies;
- analysts' 12-month price targets;
- the last 12 months' trading range (context only, not a fair-value estimate).
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .data import CompanyData
from .model import DCFAssumptions, base_cash, default_base, make_scenarios, run_dcf

TRADING_DAYS_1Y = 252


@dataclass
class Method:
    name: str
    low: float
    mid: float
    high: float
    kind: str            # "model", "peers", "analysts" or "market"
    note: str = ""
    counts: bool = True  # part of the fair-value range (the trading range is context only)


def _ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def underlying_cash_flow(c: CompanyData) -> List[float]:
    """Operating cash flow minus maintenance spending, year by year ("owner earnings").

    Maintenance spending is estimated as depreciation (what wears out each year), capped at the
    actual capital spending. Years without the figures are NaN.
    """
    out = []
    deps = getattr(c, "depreciation", None) or []   # missing on data saved by older app versions
    for i in range(len(c.years)):
        ocf = c.operating_cash_flow[i] if i < len(c.operating_cash_flow) else float("nan")
        capex = abs(c.capex[i]) if i < len(c.capex) and _ok(c.capex[i]) else float("nan")
        dep = deps[i] if i < len(deps) else float("nan")
        if not (_ok(ocf) and _ok(capex) and _ok(dep)):
            out.append(float("nan"))
        else:
            out.append(ocf - min(capex, dep))
    return out


def has_underlying(c: CompanyData) -> bool:
    """True when underlying cash flow can be measured and differs noticeably from free cash flow."""
    if c.is_financial:
        return False
    pairs = [(u, f) for u, f in zip(underlying_cash_flow(c), c.free_cash_flow) if _ok(u) and _ok(f)]
    if not pairs:
        return False
    u, f = sum(p[0] for p in pairs), sum(p[1] for p in pairs)
    return u > 0 and abs(u - f) > 0.10 * max(abs(f), 1.0)


def model_range(c: CompanyData, a: DCFAssumptions) -> Optional[Tuple[float, float, float]]:
    """(pessimistic, your settings, optimistic) value per share; None if the cash flow is negative."""
    if base_cash(c, a.base) <= 0:
        return None
    vals = {name: run_dcf(c, s).value_per_share for name, s in make_scenarios(a).items()}
    mid = vals["Middle (your settings)"]
    lo, hi = min(vals.values()), max(vals.values())
    return max(lo, 0.0), mid, hi


def fair_value_methods(c: CompanyData, a: DCFAssumptions, peer_prices: Optional[Dict[str, float]] = None,
                       history: Optional[pd.Series] = None, distorted: bool = False) -> List[Method]:
    """Every method that can be computed for this company, in display order."""
    methods: List[Method] = []
    cash_name = "cash returned to shareholders" if c.is_financial else "free cash flow"
    r = model_range(c, a)
    if r:
        methods.append(Method(
            f"Cash-flow model ({cash_name})", *r, kind="model",
            note=("probably too low here: see the note above" if distorted else
                  "your sidebar settings; the bar runs from the pessimistic to the optimistic scenario"),
        ))
    if has_underlying(c):
        cu = replace(c, free_cash_flow=underlying_cash_flow(c))
        # Its own starting point: the latest year if underlying cash flow has been growing.
        r2 = model_range(cu, replace(a, base=default_base(cu)))
        if r2:
            methods.append(Method(
                "Cash-flow model (underlying cash flow)", *r2, kind="model",
                note="counts only the spending needed to maintain the business, not spending on growth",
            ))
    vals = [v for v in (peer_prices or {}).values() if _ok(v) and v > 0]
    if vals:
        methods.append(Method(
            "Priced like similar companies", min(vals), statistics.median(vals), max(vals), kind="peers",
            note="P/E, EV/EBITDA and cash-flow yield of similar large companies",
        ))
    if c.has_analyst_targets:
        methods.append(Method(
            "Analysts' 12-month targets", c.target_low, c.target_mean, c.target_high, kind="analysts",
            note=f"{c.analyst_count} analysts" if c.analyst_count else "",
        ))
    if history is not None and not history.empty:
        last = history.iloc[-TRADING_DAYS_1Y:]
        methods.append(Method(
            "Traded over the last 12 months", float(last.min()), float(last.iloc[-1]), float(last.max()),
            kind="market", note="where the price has actually been: context, not a fair value", counts=False,
        ))
    return methods


def fair_value_band(methods: List[Method]) -> Optional[Tuple[float, float, float]]:
    """(low, middle, high) that most methods agree on.

    Uses each method's central value. With four or more methods the single highest and lowest are
    dropped, so one method thrown off by unusual figures can't stretch the range on its own.
    """
    counted = [m for m in methods if m.counts and _ok(m.mid) and m.mid > 0]
    if not counted:
        return None
    if len(counted) == 1:
        m = counted[0]
        return m.low, m.mid, m.high
    mids = sorted(m.mid for m in counted)
    lo, hi = (mids[1], mids[-2]) if len(mids) >= 4 else (mids[0], mids[-1])
    return lo, statistics.median(mids), hi


def price_position(price: float, band: Tuple[float, float, float]) -> str:
    """'below', 'within' or 'above' the fair-value range."""
    lo, _, hi = band
    if price < lo:
        return "below"
    if price > hi:
        return "above"
    return "within"
