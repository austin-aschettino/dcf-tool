"""Probability view: run the valuation thousands of times with assumptions drawn around yours.

Instead of one estimate (or three scenarios), this gives a range of values and the share of
outcomes in which today's price is justified. The maths is the same as `run_dcf` and the fund
model, done for many assumption sets at once with numpy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np

from .data import CompanyData
from .fund import FundData, IndexAssumptions
from .model import DCFAssumptions, base_cash

# How far each assumption is allowed to wander (one standard deviation), by uncertainty level.
UNCERTAINTY = {
    "Low":    dict(growth=0.015, rate=0.005, terminal=0.0025),
    "Medium": dict(growth=0.03, rate=0.01, terminal=0.005),
    "High":   dict(growth=0.05, rate=0.015, terminal=0.0075),
}
MIN_SPREAD = 0.01   # the discount rate is kept at least 1 point above long-term growth


@dataclass
class Simulation:
    values: np.ndarray          # value per share in each simulated outcome
    price: float

    @property
    def prob_above_price(self) -> float:
        """Share of outcomes where the value is at least today's price."""
        return float(np.mean(self.values >= self.price))

    def percentile(self, q: float) -> float:
        return float(np.percentile(self.values, q))

    @property
    def median(self) -> float:
        return self.percentile(50)

    def summary(self) -> Dict[str, float]:
        return {f"p{q}": self.percentile(q) for q in (5, 25, 50, 75, 95)}


def _present_value(start: float, years: int, g, tg, r, fade: bool) -> np.ndarray:
    """Value today of a cash stream starting at `start`, for arrays of growth g, long-term growth tg and rate r."""
    g, tg, r = (np.asarray(x, dtype=float) for x in (g, tg, r))
    total = np.zeros_like(g)
    cash = np.full_like(g, start)
    for i in range(1, years + 1):
        gi = g + (tg - g) * (i - 1) / (years - 1) if fade and years > 1 else g
        cash = cash * (1 + gi)
        total += cash / (1 + r) ** i
    terminal = cash * (1 + tg) / (r - tg) / (1 + r) ** years
    return total + terminal


def _draw(n: int, seed: int, centre: tuple, level: str):
    sd = UNCERTAINTY[level]
    rng = np.random.default_rng(seed)
    g = rng.normal(centre[0], sd["growth"], n)
    tg = np.clip(rng.normal(centre[1], sd["terminal"], n), 0.0, None)
    r = rng.normal(centre[2], sd["rate"], n)
    r = np.maximum(r, tg + MIN_SPREAD)
    return g, tg, r


def simulate_company(c: CompanyData, a: DCFAssumptions, n: int = 5000, level: str = "Medium",
                     seed: int = 7) -> Simulation:
    g, tg, r = _draw(n, seed, (a.growth_rate, a.terminal_growth, a.wacc), level)
    ev = _present_value(base_cash(c, a.base), a.years, g, tg, r, a.fade)
    net_debt = 0.0 if c.is_financial else c.net_debt
    return Simulation(values=(ev - net_debt) / c.shares_outstanding, price=c.price)


def simulate_fund(f: FundData, a: IndexAssumptions, n: int = 5000, level: str = "Medium",
                  seed: int = 7) -> Simulation:
    g, tg, r = _draw(n, seed, (a.growth_rate, a.terminal_growth, a.required_return + f.expense_ratio), level)
    values = _present_value(f.earnings_per_share * a.payout, a.years, g, tg, r, a.fade)
    return Simulation(values=values, price=f.price)
