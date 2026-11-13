"""Price outlook: where the share price could reasonably be in 1, 3 or 5 years.

Three separate lenses, because "expected price" can mean different things:

1. Typical swings (volatility). Starting from today's price, assume the stock earns
   its required return on average, less the dividends it pays out (which leave the
   price), and spreads out the way it has over the last year. In a log-normal model
   that gives a "likely" range (about 2 in 3 outcomes, +/-1 standard deviation) and
   a "wide" range (about 19 in 20, +/-1.96 standard deviations).

2. Model fair value. Today's pessimistic / middle / optimistic estimates, grown to
   the horizon at the required return less the dividend yield. Comparing that with
   today's price shows the upside or downside *if the price ends up at fair value*.

3. Analysts' 12-month price targets (low / average / high), when Yahoo has them.

None of these is a prediction; they are ranges and reference points.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from .data import CompanyData
from .fund import FundData, IndexAssumptions, index_scenarios, run_index_valuation
from .model import DCFAssumptions, base_cash, cost_of_equity, make_scenarios, run_dcf

TRADING_DAYS = 252
Z_LIKELY = 1.0     # +/-1 standard deviation: about 68% ("2 in 3")
Z_WIDE = 1.96      # +/-1.96 standard deviations: about 95% ("19 in 20")


# --------------------------------------------------------------------------- #
# Building blocks
# --------------------------------------------------------------------------- #

def annual_volatility(prices: pd.Series, lookback_days: int = TRADING_DAYS) -> float:
    """Annualised volatility of daily log returns over the last `lookback_days`; NaN if too little data."""
    if prices is None or len(prices) < 30:
        return float("nan")
    p = pd.Series(prices).dropna().astype(float)
    p = p[p > 0].iloc[-(lookback_days + 1):]
    if len(p) < 30:
        return float("nan")
    daily = (p / p.shift(1)).dropna().map(math.log)
    return float(daily.std(ddof=1) * math.sqrt(TRADING_DAYS))


def expected_price(price: float, expected_return: float, dividend_yield: float, years: float) -> float:
    """Price after `years` if it grows at the expected return minus the dividends paid out."""
    return price * (1 + expected_return - dividend_yield) ** years


def price_range(center: float, sigma: float, years: float, z: float) -> tuple:
    """Low/high of a log-normal band around `center`."""
    if math.isnan(sigma) or years <= 0:
        return (float("nan"), float("nan"))
    spread = z * sigma * math.sqrt(years)
    return (center * math.exp(-spread), center * math.exp(spread))


def yearly_return(price_now: float, price_then: float, years: float, dividend_yield: float = 0.0) -> float:
    """Average yearly return to go from price_now to price_then, plus dividends received."""
    if not price_now or price_then is None or math.isnan(price_then) or price_then <= 0 or years <= 0:
        return float("nan")
    return (price_then / price_now) ** (1 / years) - 1 + dividend_yield


def cone_path(price: float, expected_return: float, dividend_yield: float, sigma: float,
              years: float, start: Optional[pd.Timestamp] = None, points_per_year: int = 12) -> pd.DataFrame:
    """Month-by-month centre line and likely/wide bands, for drawing the fan chart."""
    start = pd.Timestamp(start or pd.Timestamp.today().normalize())
    n = max(int(round(years * points_per_year)), 1)
    rows = []
    for i in range(n + 1):
        t = years * i / n
        c = expected_price(price, expected_return, dividend_yield, t)
        lo1, hi1 = price_range(c, sigma, t, Z_LIKELY) if t > 0 else (c, c)
        lo2, hi2 = price_range(c, sigma, t, Z_WIDE) if t > 0 else (c, c)
        rows.append({"date": start + pd.DateOffset(days=int(round(t * 365.25))), "center": c,
                     "likely_low": lo1, "likely_high": hi1, "wide_low": lo2, "wide_high": hi2})
    return pd.DataFrame(rows).set_index("date")


# --------------------------------------------------------------------------- #
# The outlook itself
# --------------------------------------------------------------------------- #

@dataclass
class PriceOutlook:
    years: int
    price: float
    expected_return: float            # yearly return the stock is assumed to earn on average
    dividend_yield: float
    volatility: float                 # annualised; NaN if no price history
    center: float                     # expected price at the horizon
    likely: tuple                     # (low, high), about 2 in 3 outcomes
    wide: tuple                       # (low, high), about 19 in 20 outcomes
    fair_today: Dict[str, float] = field(default_factory=dict)    # scenario -> value today
    fair_future: Dict[str, float] = field(default_factory=dict)   # scenario -> value at horizon
    analysts: Optional[dict] = None   # low / mean / high / count / recommendation (12-month)

    @property
    def has_volatility(self) -> bool:
        return not math.isnan(self.volatility)

    def change(self, p: float) -> float:
        return p / self.price - 1 if self.price and p is not None and not math.isnan(p) else float("nan")

    def table(self) -> pd.DataFrame:
        """Every upside/downside figure in one table."""
        rows: List[dict] = []

        def add(group: str, label: str, p: float, years: float) -> None:
            rows.append({
                "Lens": group,
                "Outcome": label,
                "Price": p,
                "Change vs. today": self.change(p),
                "Yearly return incl. dividends": yearly_return(self.price, p, years, self.dividend_yield),
            })

        y = self.years
        if self.has_volatility:
            add("Typical swings", "Wide range: low (1 in 40 chance of lower)", self.wide[0], y)
            add("Typical swings", "Likely range: low", self.likely[0], y)
            add("Typical swings", "Middle", self.center, y)
            add("Typical swings", "Likely range: high", self.likely[1], y)
            add("Typical swings", "Wide range: high (1 in 40 chance of higher)", self.wide[1], y)
        for name, p in self.fair_future.items():
            add("Model fair value", name, p, y)
        if self.analysts:
            for key, label in (("low", "Lowest target"), ("mean", "Average target"), ("high", "Highest target")):
                add("Analysts (12-month)", label, self.analysts[key], 1)
        return pd.DataFrame(rows).set_index(["Lens", "Outcome"])


def build_outlook(price: float, expected_return: float, dividend_yield: float, prices: Optional[pd.Series],
                  years: int, fair_today: Optional[Dict[str, float]] = None,
                  analysts: Optional[dict] = None) -> PriceOutlook:
    sigma = annual_volatility(prices) if prices is not None else float("nan")
    center = expected_price(price, expected_return, dividend_yield, years)
    fair_today = fair_today or {}
    fair_future = {k: expected_price(v, expected_return, dividend_yield, years)
                   for k, v in fair_today.items() if v is not None and not math.isnan(v) and v > 0}
    return PriceOutlook(
        years=years,
        price=price,
        expected_return=expected_return,
        dividend_yield=dividend_yield,
        volatility=sigma,
        center=center,
        likely=price_range(center, sigma, years, Z_LIKELY),
        wide=price_range(center, sigma, years, Z_WIDE),
        fair_today={k: v for k, v in fair_today.items() if k in fair_future},
        fair_future=fair_future,
        analysts=analysts,
    )


def company_outlook(c: CompanyData, a: DCFAssumptions, prices: Optional[pd.Series], years: int) -> PriceOutlook:
    # A share's value grows at the return shareholders demand (cost of equity), not the WACC.
    ke = min(max(cost_of_equity(c), 0.04), 0.15)
    fair: Dict[str, float] = {}
    if base_cash(c, a.base) > 0:
        for name, s in make_scenarios(a).items():
            try:
                fair[name] = run_dcf(c, s).value_per_share
            except ValueError:
                pass
    analysts = None
    if c.has_analyst_targets:
        analysts = {"low": c.target_low, "mean": c.target_mean, "high": c.target_high,
                    "count": c.analyst_count, "recommendation": c.recommendation}
    return build_outlook(c.price, ke, c.dividend_yield, prices, years, fair, analysts)


def fund_outlook(f: FundData, a: IndexAssumptions, prices: Optional[pd.Series], years: int) -> PriceOutlook:
    fair: Dict[str, float] = {}
    if f.can_value:
        for name, s in index_scenarios(a).items():
            try:
                fair[name] = run_index_valuation(f, s).value_per_share
            except ValueError:
                pass
    # Investors keep the required return minus the fund's fee.
    return build_outlook(f.price, a.required_return - f.expense_ratio, f.dividend_yield, prices, years, fair)
