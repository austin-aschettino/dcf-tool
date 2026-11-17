"""Business quality scorecard and comparison with similar companies.

The DCF asks "is it cheap?". These answer two other questions beginners should ask:
"is it a good business?" and "how is it priced next to its peers?"
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Dict, List, Optional

from .data import CompanyData
from .model import historical_cagr

STRONG, OK, WEAK, NA = "Strong", "OK", "Weak", "n/a"
POINTS = {STRONG: 2, OK: 1, WEAK: 0}


def _ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def _f(c, name: str) -> Optional[float]:
    """A ratio from the company data, or None if missing.

    Read with getattr so company data saved by an older version of the app (before these
    ratios existed) shows "n/a" instead of crashing.
    """
    return getattr(c, name, None)


@dataclass
class Check:
    name: str
    value: str          # formatted figure, e.g. "21.3%"
    grade: str          # Strong / OK / Weak / n/a
    meaning: str        # what the figure says, in plain English
    rule: str           # the thresholds used


def _grade(x: Optional[float], strong: float, ok: float, higher_is_better: bool = True) -> str:
    if not _ok(x):
        return NA
    if higher_is_better:
        return STRONG if x >= strong else OK if x >= ok else WEAK
    return STRONG if x <= strong else OK if x <= ok else WEAK


def _pct(x: Optional[float]) -> str:
    return "n/a" if not _ok(x) else f"{x:.1%}"


def fcf_margin(c: CompanyData) -> Optional[float]:
    """Average free cash flow as a share of average sales."""
    pairs = [(f, r) for f, r in zip(c.free_cash_flow, c.revenue) if _ok(f) and _ok(r)]
    if not pairs or sum(r for _, r in pairs) <= 0:
        return None
    return sum(f for f, _ in pairs) / sum(r for _, r in pairs)


def cash_consistency(values: List[float]) -> Optional[float]:
    """0-1: how steady the yearly cash has been (1 = perfectly steady, 0 = a year below zero)."""
    vals = [v for v in values if _ok(v)]
    if len(vals) < 2:
        return None
    if min(vals) <= 0:
        return 0.0
    mean = statistics.mean(vals)
    return max(0.0, 1 - statistics.pstdev(vals) / mean)


def net_debt_to_ebitda(c: CompanyData) -> Optional[float]:
    if not _ok(_f(c, "ebitda")) or _f(c, "ebitda") <= 0:
        return None
    return c.net_debt / _f(c, "ebitda")


def scorecard(c: CompanyData) -> List[Check]:
    """Five or six plain-English checks of business quality."""
    growth = historical_cagr(c.revenue)
    cash_name = "Cash returned to owners" if c.is_financial else "Free cash flow"
    steady = cash_consistency(c.valuation_cash_flow)
    checks: List[Check] = []
    if c.is_financial:
        checks += [
            Check("Return on equity", _pct(_f(c, "return_on_equity")), _grade(_f(c, "return_on_equity"), 0.12, 0.08),
                  "Profit each year for every $1 shareholders have in the business. The key measure for a bank.",
                  "Strong ≥ 12% · OK ≥ 8%"),
            Check("Return on assets", _pct(_f(c, "return_on_assets")), _grade(_f(c, "return_on_assets"), 0.012, 0.008),
                  "Profit for every $1 of loans and other assets. Banks earn thin margins on huge balance sheets.",
                  "Strong ≥ 1.2% · OK ≥ 0.8%"),
        ]
    else:
        nd = net_debt_to_ebitda(c)
        if _ok(nd):
            debt_value = "No net debt (more cash than debt)" if nd <= 0 else f"{nd:.1f}× yearly earnings (EBITDA)"
        else:
            debt_value = "n/a"
        checks += [
            Check("Operating margin", _pct(_f(c, "operating_margin")), _grade(_f(c, "operating_margin"), 0.20, 0.10),
                  "Of every $1 of sales, how much is left after running the business. High margins often mean "
                  "pricing power.", "Strong ≥ 20% · OK ≥ 10%"),
            Check("Free cash flow margin", _pct(fcf_margin(c)), _grade(fcf_margin(c), 0.15, 0.05),
                  "Of every $1 of sales, how much ends up as spare cash for owners after investing in the business.",
                  "Strong ≥ 15% · OK ≥ 5%"),
            Check("Return on assets", _pct(_f(c, "return_on_assets")), _grade(_f(c, "return_on_assets"), 0.10, 0.05),
                  "Profit for every $1 the company has invested in buildings, equipment, stock and so on.",
                  "Strong ≥ 10% · OK ≥ 5%"),
            Check("Debt load", debt_value, _grade(nd, 1.0, 3.0, higher_is_better=False),
                  "Debt minus cash, compared with a year's earnings before interest, tax and depreciation. "
                  "Lower = safer if business turns bad.", "Strong ≤ 1× · OK ≤ 3×"),
        ]
    checks += [
        Check("Sales growth", _pct(growth) + " a year" if _ok(growth) else "n/a", _grade(growth, 0.08, 0.03),
              "How fast sales grew over the last few years.", "Strong ≥ 8% · OK ≥ 3%"),
        Check(f"{cash_name}: consistency", "n/a" if steady is None else f"{steady:.0%} steady",
              _grade(steady, 0.75, 0.5),
              "Whether the cash has been reliable year after year. Steady cash makes a valuation more trustworthy; "
              "a negative year scores 0%.", "Strong ≥ 75% · OK ≥ 50%"),
    ]
    return checks


def overall(checks: List[Check]) -> tuple:
    """(label, colour, score 0-1) across the checks that could be graded."""
    graded = [POINTS[ch.grade] for ch in checks if ch.grade in POINTS]
    if not graded:
        return "Not enough data", "neutral", float("nan")
    score = sum(graded) / (2 * len(graded))
    if score >= 0.7:
        return "High-quality business", "green", score
    if score >= 0.4:
        return "Average quality", "neutral", score
    return "Below-average quality", "red", score


# --------------------------------------------------------------------------- #
# Similar companies
# --------------------------------------------------------------------------- #

# Large, well-known companies for each kind of business, matched by words in Yahoo's industry name.
INDUSTRY_PEERS = [
    (("auto parts",), ["AZO", "ORLY", "GPC", "AAP", "LKQ"]),
    (("semiconductor",), ["NVDA", "AMD", "AVGO", "QCOM", "TXN", "INTC"]),
    (("software",), ["MSFT", "ORCL", "ADBE", "CRM", "NOW", "INTU"]),
    (("internet content",), ["GOOGL", "META", "PINS", "SNAP"]),
    (("internet retail",), ["AMZN", "EBAY", "ETSY", "CHWY"]),
    (("consumer electronics",), ["AAPL", "SONY", "HPQ", "DELL"]),
    (("computer hardware",), ["DELL", "HPQ", "HPE", "NTAP"]),
    (("auto manufacturers",), ["TSLA", "GM", "F", "TM", "STLA"]),
    (("banks",), ["JPM", "BAC", "WFC", "C", "USB", "PNC"]),
    (("credit services",), ["V", "MA", "AXP", "PYPL", "COF"]),
    (("capital markets",), ["GS", "MS", "SCHW", "RJF"]),
    (("insurance",), ["PGR", "TRV", "ALL", "CB", "AIG"]),
    (("beverages - non-alcoholic", "beverages—non-alcoholic"), ["KO", "PEP", "KDP", "MNST"]),
    (("discount stores",), ["COST", "WMT", "TGT", "DG", "DLTR", "BJ"]),
    (("drug manufacturers",), ["LLY", "JNJ", "MRK", "ABBV", "PFE", "BMY"]),
    (("medical devices",), ["ABT", "MDT", "SYK", "BSX", "EW"]),
    (("healthcare plans",), ["UNH", "CVS", "CI", "ELV", "HUM"]),
    (("footwear",), ["NKE", "DECK", "SKX", "CROX"]),
    (("home improvement",), ["HD", "LOW"]),
    (("restaurants",), ["MCD", "SBUX", "CMG", "YUM", "DRI"]),
    (("household",), ["PG", "CL", "KMB", "CHD", "CLX"]),
    (("tobacco",), ["PM", "MO", "BTI"]),
    (("packaged foods", "confectioners"), ["MDLZ", "GIS", "HSY", "KHC", "K"]),
    (("oil & gas integrated",), ["XOM", "CVX", "SHEL", "BP", "TTE"]),
    (("oil & gas e&p",), ["COP", "EOG", "OXY", "DVN"]),
    (("entertainment",), ["DIS", "NFLX", "WBD", "PARA"]),
    (("telecom",), ["T", "VZ", "TMUS", "CMCSA"]),
    (("aerospace",), ["RTX", "LMT", "BA", "GE", "GD", "NOC"]),
    (("integrated freight",), ["UPS", "FDX", "EXPD"]),
    (("railroads",), ["UNP", "CSX", "NSC", "CNI"]),
    (("farm & heavy", "construction machinery"), ["CAT", "DE", "PCAR", "CMI"]),
    (("conglomerates",), ["HON", "MMM", "GE", "ITW"]),
    (("apparel retail",), ["TJX", "ROST", "BURL", "GPS"]),
    (("specialty retail",), ["TJX", "ULTA", "BBY", "TSCO"]),
    (("travel services", "lodging"), ["BKNG", "EXPE", "MAR", "HLT", "ABNB"]),
    (("utilities",), ["NEE", "DUK", "SO", "D", "AEP"]),
    (("biotechnology",), ["AMGN", "GILD", "VRTX", "REGN", "BIIB"]),
    (("information technology services",), ["IBM", "ACN", "CTSH", "IT"]),
    (("communication equipment",), ["CSCO", "MSI", "ANET", "JNPR"]),
]
SECTOR_PEERS = {
    "Technology": ["AAPL", "MSFT", "NVDA", "ORCL", "CSCO", "IBM"],
    "Consumer Cyclical": ["AMZN", "HD", "MCD", "NKE", "TSLA", "BKNG"],
    "Consumer Defensive": ["WMT", "COST", "PG", "KO", "PEP"],
    "Healthcare": ["JNJ", "UNH", "LLY", "MRK", "ABT"],
    "Financial Services": ["JPM", "BAC", "V", "MA", "GS"],
    "Communication Services": ["GOOGL", "META", "NFLX", "DIS", "T"],
    "Industrials": ["GE", "CAT", "HON", "UPS", "RTX"],
    "Energy": ["XOM", "CVX", "COP", "EOG"],
    "Utilities": ["NEE", "DUK", "SO", "AEP"],
    "Basic Materials": ["LIN", "SHW", "APD", "NEM"],
    "Real Estate": ["PLD", "AMT", "O", "SPG"],
}


def peer_tickers(c: CompanyData, limit: int = 5) -> List[str]:
    """Up to `limit` similar large companies (same industry if known, else same sector)."""
    ind = (c.industry or "").lower()
    peers: List[str] = []
    for words, tickers in INDUSTRY_PEERS:
        if any(w in ind for w in words):
            peers = tickers
            break
    if not peers:
        peers = SECTOR_PEERS.get(c.sector, [])
    return [t for t in peers if t.upper() != c.ticker.upper()][:limit]


def fcf_yield(c: CompanyData) -> Optional[float]:
    """Average free cash flow (or cash returned, for banks) as a share of the company's market value."""
    vals = [v for v in c.valuation_cash_flow[-3:] if _ok(v)]
    if not vals or not c.market_cap:
        return None
    return statistics.mean(vals) / c.market_cap


def multiples(c: CompanyData) -> Dict[str, Optional[float]]:
    return {
        "P/E": c.pe if _ok(c.pe) and c.pe > 0 else None,
        "Forward P/E": _f(c, "forward_pe") if _ok(_f(c, "forward_pe")) and _f(c, "forward_pe") > 0 else None,
        "EV/EBITDA": _f(c, "ev_to_ebitda") if _ok(_f(c, "ev_to_ebitda")) and _f(c, "ev_to_ebitda") > 0 else None,
        "Cash flow yield": fcf_yield(c),
        "Operating margin": _f(c, "operating_margin"),
        "Sales growth": historical_cagr(c.revenue),
    }


def _median(values) -> Optional[float]:
    vals = [v for v in values if _ok(v)]
    return statistics.median(vals) if vals else None


# Outside these, a multiple is almost certainly a data problem (accounts in another currency, a one-off),
# not a real valuation: such a peer is shown flagged but left out of the median.
PLAUSIBLE = {"P/E": (0, 300), "Forward P/E": (0, 300), "EV/EBITDA": (0, 150),
             "Cash flow yield": (-0.5, 0.5), "Operating margin": (-1.0, 1.0)}


def implausible(m: Dict[str, Optional[float]]) -> List[str]:
    """Names of the multiples outside a believable range."""
    return [k for k, (lo, hi) in PLAUSIBLE.items() if _ok(m.get(k)) and not lo <= m[k] <= hi]


def peer_medians(peers: List[CompanyData]) -> Dict[str, Optional[float]]:
    rows = [multiples(p) for p in peers]
    rows = [r for r in rows if not implausible(r)] or rows   # keep at least something to compare with
    keys = rows[0].keys() if rows else []
    return {k: _median(r[k] for r in rows) for k in keys}


def implied_prices(c: CompanyData, med: Dict[str, Optional[float]]) -> Dict[str, float]:
    """Share price if this company were valued like the typical similar company, by each measure."""
    out: Dict[str, float] = {}
    if _ok(med.get("P/E")) and _ok(c.pe) and c.pe > 0:
        out["At peers' P/E"] = c.price / c.pe * med["P/E"]
    if _ok(med.get("Forward P/E")) and _ok(_f(c, "forward_pe")) and _f(c, "forward_pe") > 0:
        out["At peers' forward P/E"] = c.price / _f(c, "forward_pe") * med["Forward P/E"]
    if _ok(med.get("EV/EBITDA")) and _ok(_f(c, "ebitda")) and _f(c, "ebitda") > 0 and not c.is_financial:
        out["At peers' EV/EBITDA"] = (_f(c, "ebitda") * med["EV/EBITDA"] - c.net_debt) / c.shares_outstanding
    y = fcf_yield(c)
    if _ok(med.get("Cash flow yield")) and med["Cash flow yield"] > 0 and _ok(y) and y > 0:
        out["At peers' cash flow yield"] = c.price * y / med["Cash flow yield"]
    return {k: v for k, v in out.items() if v > 0}
