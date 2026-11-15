"""Core DCF math: discount rate, cash-flow projection, terminal value, per-share value.

Two flavours share the same engine:

* Ordinary companies: discount free cash flow at the WACC, then subtract net debt.
* Banks, insurers and brokers (see CompanyData.is_financial): their free cash flow
  is meaningless, so we discount the cash they actually return to shareholders
  (dividends + buybacks) at the cost of equity. That cash already belongs to
  shareholders, so no debt is subtracted.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .data import CompanyData

RISK_FREE_RATE = 0.043       # ~10y US Treasury
# Extra yearly return investors demand for owning stocks instead of Treasuries. 4.5% is in line with
# recent market-implied estimates; the older 5.5% made most large companies look overpriced. Tested in
# the backtest: see README "Backtest".
EQUITY_RISK_PREMIUM = 0.045
FORECAST_YEARS = 10          # years forecast one by one before the long-term rate takes over

GROWTH_FLOOR, GROWTH_CAP = -0.05, 0.20


@dataclass
class DCFAssumptions:
    growth_rate: float         # cash-flow growth in year 1
    terminal_growth: float     # perpetual growth after the projection period
    wacc: float                # discount rate (cost of equity for financial companies)
    years: int = 5             # projection period
    fade: bool = True          # linearly fade growth toward terminal growth
    base: str = "avg3"         # starting cash flow: "avg3" (3-year average) or "latest"


@dataclass
class DCFResult:
    assumptions: DCFAssumptions
    method: str                # "fcf" (free cash flow) or "payout" (cash returned to shareholders)
    base_fcf: float
    projected_fcf: List[float]
    growth_path: List[float]
    discount_factors: List[float]
    pv_fcf: List[float]
    terminal_value: float
    pv_terminal_value: float
    enterprise_value: float
    net_debt: float            # 0 for the payout method
    equity_value: float
    shares: float
    value_per_share: float
    price: float

    @property
    def upside(self) -> float:
        return self.value_per_share / self.price - 1 if self.price else float("nan")

    @property
    def terminal_share(self) -> float:
        return self.pv_terminal_value / self.enterprise_value if self.enterprise_value else float("nan")

    def projection_table(self) -> pd.DataFrame:
        n = len(self.projected_fcf)
        return pd.DataFrame(
            {
                "Growth": self.growth_path,
                "FCF": self.projected_fcf,
                "Discount factor": self.discount_factors,
                "PV of FCF": self.pv_fcf,
            },
            index=[f"Year {i}" for i in range(1, n + 1)],
        )


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #

def historical_cagr(values: Sequence[float]) -> float:
    """CAGR between the first and last positive values; NaN if not computable."""
    vals = [v for v in values if v is not None and not math.isnan(v)]
    if len(vals) < 2 or vals[0] <= 0 or vals[-1] <= 0:
        return float("nan")
    return (vals[-1] / vals[0]) ** (1 / (len(vals) - 1)) - 1


def cost_of_equity(c: CompanyData, rf: float = RISK_FREE_RATE, erp: float = EQUITY_RISK_PREMIUM) -> float:
    """CAPM: the return shareholders demand = risk-free rate + beta x equity risk premium."""
    return rf + c.beta * erp


def compute_wacc(c: CompanyData, rf: float = RISK_FREE_RATE, erp: float = EQUITY_RISK_PREMIUM) -> float:
    ke = cost_of_equity(c, rf, erp)
    pre_tax_cost_debt = c.interest_expense / c.total_debt if c.total_debt > 0 else rf
    pre_tax_cost_debt = min(max(pre_tax_cost_debt, rf * 0.5), 0.15)
    cost_debt = pre_tax_cost_debt * (1 - c.tax_rate)
    e, d = max(c.market_cap, 0.0), max(c.total_debt, 0.0)
    if e + d == 0:
        return ke
    return e / (e + d) * ke + d / (e + d) * cost_debt


def historical_growth(c: CompanyData) -> float:
    g = historical_cagr(c.revenue)
    if math.isnan(g):
        g = historical_cagr(c.valuation_cash_flow)
    return 0.05 if math.isnan(g) else g


def default_growth(c: CompanyData, source: str = "analyst") -> Tuple[float, str]:
    """Starting growth rate and a short description of where it came from."""
    if source == "analyst" and c.analyst_growth is not None:
        g, label = c.analyst_growth, "analysts' forecast of next year's earnings growth"
    else:
        g, label = historical_growth(c), "the company's past sales growth"
    return min(max(g, GROWTH_FLOOR), GROWTH_CAP), label


def default_discount_rate(c: CompanyData) -> float:
    rate = cost_of_equity(c) if c.is_financial else compute_wacc(c)
    return min(max(rate, 0.06), 0.15)


def default_base(c: CompanyData) -> str:
    """Start from the latest year when cash flow has been growing (the 3-year average would lag it),
    otherwise from the 3-year average (which smooths out a single bad or lucky year)."""
    return "latest" if base_cash(c, "latest") > base_cash(c, "avg3") else "avg3"


def default_assumptions(c: CompanyData, growth_source: str = "analyst", base: Optional[str] = None) -> DCFAssumptions:
    """Reasonable starting assumptions derived from the company's own data."""
    g, _ = default_growth(c, growth_source)
    return DCFAssumptions(
        growth_rate=round(g, 4),
        terminal_growth=0.025,
        wacc=round(default_discount_rate(c), 4),
        years=FORECAST_YEARS,
        base=base or default_base(c),
    )


def model_caveats(c: CompanyData, a: DCFAssumptions) -> List[Tuple[str, str]]:
    """Known situations where this simple model is likely to understate the value: (short label, explanation).

    They don't change the estimate; they tell the reader when to take a low estimate with a pinch of salt.
    """
    out: List[Tuple[str, str]] = []
    if not c.is_financial and c.operating_cash_flow and c.capex:
        ocf, capex = c.operating_cash_flow[-1], abs(c.capex[-1] or 0.0)
        if ocf and ocf > 0 and not math.isnan(ocf) and capex / ocf >= 0.5:
            out.append((
                "heavy investment",
                f"{c.name} spent {capex / ocf:.0%} of last year's operating cash flow on new buildings, equipment "
                "and the like. Free cash flow counts all of it as a cost, including spending that should produce "
                "growth later, so the estimate is probably too low while the company is in a building phase.",
            ))
    series = [v for v in c.valuation_cash_flow if v is not None and not math.isnan(v)]
    if len(series) >= 2:
        peak, latest = max(series[:-1]), series[-1]
        if peak > 0 and latest < 0.6 * peak:
            what = "cash returned to shareholders" if c.is_financial else "free cash flow"
            out.append((
                "recent dip in cash flow",
                f"Its {what} fell from about {_money(peak)} to {_money(latest)} in the latest year. If that drop is "
                "temporary (a one-off payment, a big project, a bad year), the estimate built on it is too low.",
            ))
    if a.wacc >= 0.149 or c.beta >= 1.8:
        out.append((
            "very volatile stock",
            f"Its share price has swung a lot (beta {c.beta:.2f}), so the model asks for a {a.wacc:.1%} yearly "
            "return, at or near the highest it allows. Many analysts would use a lower rate for a large, "
            "established company, which would raise the estimate.",
        ))
    return out


def _money(x: float) -> str:
    for unit, div in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if abs(x) >= div:
            return f"${x / div:,.1f}{unit}"
    return f"${x:,.0f}"


def base_cash(c: CompanyData, base: str = "avg3") -> float:
    """Starting cash flow: the latest year, or the average of the last up-to-3 years."""
    series = [v for v in c.valuation_cash_flow if v is not None and not math.isnan(v)]
    if not series:
        return 0.0
    if base == "latest":
        return series[-1]
    recent = series[-3:]
    return sum(recent) / len(recent)


def check_company(c: CompanyData, base: str = "avg3") -> Tuple[Optional[str], List[str]]:
    """Return (blocking_problem, warnings) about how reliable a valuation of this company is.

    A blocking problem means the model can't produce a meaningful number at all.
    """
    warnings: List[str] = []
    label = "cash returned to shareholders" if c.is_financial else "free cash flow"
    series = [v for v in c.valuation_cash_flow if v is not None and not math.isnan(v)]

    if c.is_financial:
        warnings.append(
            f"{c.name} is a financial company ({c.industry or c.sector}). For banks, insurers and brokers, "
            "\"free cash flow\" mixes in customer deposits, loans and premiums, so it can't be used. "
            "This valuation uses the cash the company returns to shareholders (dividends + buybacks) instead."
        )

    if not series:
        return f"Yahoo Finance has no {label} history for {c.name}, so it can't be valued.", warnings

    start = base_cash(c, base)
    if start <= 0:
        return (
            f"{c.name}'s starting {label} is negative or zero ({start / 1e9:,.2f}B), meaning it currently "
            "spends more cash than it brings in. A DCF values a company from the cash it produces, so it "
            "can't give a meaningful number here. Companies like this are usually valued on future "
            "expectations, such as sales growth or a path to profitability, rather than today's cash.",
            warnings,
        )

    negatives = sum(1 for v in series if v < 0)
    if negatives:
        warnings.append(
            f"{c.name} had negative {label} in {negatives} of the last {len(series)} years. "
            "Treat the estimate with extra caution."
        )
    elif len(series) >= 3:
        mean = statistics.mean(series)
        spread = statistics.pstdev(series) / mean if mean else 0
        if spread > 0.4:
            warnings.append(
                f"{c.name}'s {label} has swung a lot from year to year, so the starting point "
                "(and the estimate) is less reliable than usual."
            )
    return None, warnings


# --------------------------------------------------------------------------- #
# Valuation
# --------------------------------------------------------------------------- #

def run_dcf(c: CompanyData, a: DCFAssumptions) -> DCFResult:
    if a.wacc <= a.terminal_growth:
        raise ValueError("WACC must be greater than terminal growth.")

    payout = c.is_financial
    fcf0 = base_cash(c, a.base)
    growth, fcfs, dfs, pvs = [], [], [], []
    fcf = fcf0
    for i in range(1, a.years + 1):
        if a.fade and a.years > 1:
            g = a.growth_rate + (a.terminal_growth - a.growth_rate) * (i - 1) / (a.years - 1)
        else:
            g = a.growth_rate
        fcf *= 1 + g
        df = 1 / (1 + a.wacc) ** i
        growth.append(g)
        fcfs.append(fcf)
        dfs.append(df)
        pvs.append(fcf * df)

    tv = fcfs[-1] * (1 + a.terminal_growth) / (a.wacc - a.terminal_growth)
    pv_tv = tv * dfs[-1]
    ev = sum(pvs) + pv_tv
    net_debt = 0.0 if payout else c.net_debt
    equity = ev - net_debt
    per_share = equity / c.shares_outstanding

    return DCFResult(
        assumptions=a,
        method="payout" if payout else "fcf",
        base_fcf=fcf0,
        projected_fcf=fcfs,
        growth_path=growth,
        discount_factors=dfs,
        pv_fcf=pvs,
        terminal_value=tv,
        pv_terminal_value=pv_tv,
        enterprise_value=ev,
        net_debt=net_debt,
        equity_value=equity,
        shares=c.shares_outstanding,
        value_per_share=per_share,
        price=c.price,
    )


def implied_growth(c: CompanyData, a: DCFAssumptions, lo: float = -0.5, hi: float = 1.0) -> float:
    """Reverse DCF: the steady yearly growth rate that makes the estimate equal today's price.

    Growth is held at that rate for every forecast year (no fading), then drops to
    the long-term rate, which makes the answer easy to read: "cash flow would need
    to grow X% a year for N years". Discount rate, long-term growth and years stay
    as in `a`. Returns NaN when no growth rate in [lo, hi] can justify the price.
    """
    if not c.price or base_cash(c, a.base) <= 0 or a.wacc <= a.terminal_growth:
        return float("nan")

    def value(g: float) -> float:
        return run_dcf(c, replace(a, growth_rate=g, fade=False)).value_per_share

    if value(lo) > c.price or value(hi) < c.price:
        return float("nan")
    for _ in range(100):
        mid = (lo + hi) / 2
        if value(mid) < c.price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def make_scenarios(a, rate_field: str = "wacc", growth_step: float = 0.03,
                   terminal_step: float = 0.005, rate_step: float = 0.01) -> Dict[str, object]:
    """Pessimistic / middle / optimistic versions of a set of assumptions.

    Works for both DCFAssumptions (rate_field="wacc") and IndexAssumptions
    (rate_field="required_return").
    """
    rate = getattr(a, rate_field)
    bear_tg = max(a.terminal_growth - terminal_step, 0.0)
    bull_tg = a.terminal_growth + terminal_step
    bear = replace(a, growth_rate=a.growth_rate - growth_step, terminal_growth=bear_tg,
                   **{rate_field: rate + rate_step})
    bull = replace(a, growth_rate=a.growth_rate + growth_step, terminal_growth=bull_tg,
                   **{rate_field: max(rate - rate_step, bull_tg + 0.01)})
    return {"Pessimistic": bear, "Middle (your settings)": a, "Optimistic": bull}


def sensitivity_table(
    c: CompanyData,
    a: DCFAssumptions,
    wacc_step: float = 0.01,
    tg_step: float = 0.005,
    n: int = 2,
) -> pd.DataFrame:
    """Value per share across a grid of WACC (rows) x terminal growth (columns)."""
    waccs = [a.wacc + wacc_step * k for k in range(-n, n + 1)]
    tgs = [a.terminal_growth + tg_step * k for k in range(-n, n + 1)]
    data = {}
    for tg in tgs:
        col = []
        for w in waccs:
            if w <= tg:
                col.append(float("nan"))
            else:
                col.append(run_dcf(c, replace(a, wacc=w, terminal_growth=tg)).value_per_share)
        data[f"{tg:.1%}"] = col
    return pd.DataFrame(data, index=[f"{w:.1%}" for w in waccs])
