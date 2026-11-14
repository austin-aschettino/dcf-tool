"""Portfolio view: combine the valuation of each holding into one picture.

Each holding is valued with its default assumptions. The portfolio's expected return is the
value-weighted average of each holding's "return priced in": the yearly return you'd earn
buying at today's price if the default assumptions come true.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple, Union

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
