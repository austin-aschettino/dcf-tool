"""Portfolio view: combine the valuation of each holding into one picture.

Each holding is valued with its default assumptions. The portfolio's expected return is the
value-weighted average of each holding's "return priced in": the yearly return you'd earn
buying at today's price if the default assumptions come true.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from .data import CompanyData
from .fund import FundData, default_index_assumptions, implied_index_growth, run_index_valuation
from .model import check_company, default_assumptions, implied_growth, run_dcf
from .reverse import LONG_RUN_EARNINGS_GROWTH, demand_level, implied_discount_rate, reference_growth

EXAMPLE = "VOO:5000,AAPL:2000,KO:1500,MSFT:1500"


def parse_holdings(text: str) -> List[Tuple[str, float]]:
    """'VOO:5000,AAPL:2000' -> [('VOO', 5000.0), ('AAPL', 2000.0)]; bad parts are skipped."""
    out: Dict[str, float] = {}
    for part in (text or "").split(","):
        if ":" not in part:
            continue
        t, amt = part.split(":", 1)
        t = t.strip().upper()
        try:
            v = float(amt)
        except ValueError:
            continue
        if t and v > 0:
            out[t] = out.get(t, 0.0) + v
    return list(out.items())


def format_holdings(holdings: List[Tuple[str, float]]) -> str:
    return ",".join(f"{t}:{v:g}" for t, v in holdings)


def _nan(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def holding_row(ticker: str, amount: float, data: Union[CompanyData, FundData]) -> dict:
    """One holding's valuation summary."""
    row = {"Ticker": ticker, "Amount": amount, "Name": data.name, "Price": data.price,
           "Value / share": float("nan"), "Gap vs. price": float("nan"),
           "Expected return": float("nan"), "Growth priced in": float("nan"),
           "Expectations": "Can't value", "Colour": "grey", "Sector mix": {}}
    if isinstance(data, FundData):
        row["Type"] = "Fund"
        row["Sector mix"] = dict(data.sectors) if data.sectors else {"Fund (sectors unknown)": 1.0}
        if data.can_value:
            a = default_index_assumptions(data)
            r = run_index_valuation(data, a)
            g = implied_index_growth(data, a)
            head, colour, _ = demand_level(g, LONG_RUN_EARNINGS_GROWTH, "the fund")
            row.update({"Value / share": r.value_per_share, "Gap vs. price": r.upside,
                        "Expected return": r.implied_return, "Growth priced in": g,
                        "Expectations": head.replace(" expectations", "").replace("Expectations ", ""),
                        "Colour": colour})
        return row
    row["Type"] = "Bank / insurer" if data.is_financial else "Stock"
    row["Sector mix"] = {data.sector or "Unknown": 1.0}
    blocking, _ = check_company(data)
    if blocking:
        return row
    a = default_assumptions(data)
    r = run_dcf(data, a)
    g = implied_growth(data, a)
    head, colour, _ = demand_level(g, reference_growth(data), "the company")
    row.update({"Value / share": r.value_per_share, "Gap vs. price": r.upside,
                "Expected return": implied_discount_rate(data, a), "Growth priced in": g,
                "Expectations": head.replace(" expectations", "").replace("Expectations ", ""),
                "Colour": colour})
    return row


def weighted(rows: List[dict], field: str) -> Optional[float]:
    """Amount-weighted average of a field over the holdings that have it."""
    pairs = [(r["Amount"], r[field]) for r in rows if not _nan(r[field])]
    total = sum(a for a, _ in pairs)
    return sum(a * v for a, v in pairs) / total if total else None


def sector_mix(rows: List[dict]) -> pd.Series:
    """Dollars in each sector, looking through funds to the sectors they hold."""
    mix: Dict[str, float] = {}
    for r in rows:
        weights = r["Sector mix"]
        total = sum(weights.values()) or 1.0
        for sector, w in weights.items():
            name = sector.strip().capitalize() if sector else "Unknown"
            mix[name] = mix.get(name, 0.0) + r["Amount"] * w / total
    return pd.Series(mix).sort_values(ascending=False)


# --------------------------------------------------------------------------- #
# Future value
# --------------------------------------------------------------------------- #

TRADING_DAYS = 252


def portfolio_volatility(prices: Dict[str, pd.Series], weights: Dict[str, float],
                         days: int = 3 * TRADING_DAYS) -> Optional[float]:
    """How much the whole portfolio's value has swung in a typical year (standard deviation of yearly return).

    Uses the holdings' daily price moves over the last `days` trading days, combined with their weights,
    so holdings that move together count more than ones that offset each other.
    """
    moves = {t: s.pct_change(fill_method=None) for t, s in prices.items()
             if t in weights and s is not None and len(s) > 60}
    if not moves:
        return None
    rets = pd.DataFrame(moves).iloc[-days:].dropna(how="all").fillna(0.0)
    if len(rets) < 60:
        return None
    w = np.array([weights[t] for t in rets.columns], dtype=float)
    w = w / w.sum()
    daily = (rets * w).sum(axis=1).to_numpy()   # weighted daily move of the whole portfolio
    return float(np.std(daily, ddof=1) * np.sqrt(TRADING_DAYS))


def project_value(start: float, monthly: float, years: int, annual_return: float, volatility: float,
                  n: int = 4000, seed: int = 11) -> pd.DataFrame:
    """Simulate the portfolio month by month and summarise each year.

    Each month the value grows by a random return (on average `annual_return` a year, swinging by
    `volatility` a year) and then `monthly` is added. Returns one row per year (0 = today) with the
    10th/25th/50th/75th/90th percentiles, the steady-return path and the total money put in.
    """
    months = years * 12
    mean_m = (1 + annual_return) ** (1 / 12) - 1
    sd = max(volatility, 0.0) / np.sqrt(12)
    rng = np.random.default_rng(seed)
    # Log-normal monthly growth whose average equals the requested return.
    growth = np.exp(rng.normal(np.log1p(mean_m) - sd ** 2 / 2, sd, size=(n, months)))
    value = np.full(n, float(start))
    steady = float(start)
    rows = [dict(year=0, p10=start, p25=start, p50=start, p75=start, p90=start, steady=start, put_in=start)]
    for m in range(1, months + 1):
        value = value * growth[:, m - 1] + monthly
        steady = steady * (1 + mean_m) + monthly
        if m % 12 == 0:
            q = np.percentile(value, [10, 25, 50, 75, 90])
            rows.append(dict(year=m // 12, p10=q[0], p25=q[1], p50=q[2], p75=q[3], p90=q[4],
                             steady=steady, put_in=start + monthly * m))
    return pd.DataFrame(rows).set_index("year")
