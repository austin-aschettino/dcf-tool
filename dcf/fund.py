"""Index-fund support: fetch fund data and value the whole index as one company.

A fund has no cash-flow statement of its own, so instead of a company DCF we
treat the index as one giant business:

  earnings per fund share  = price / P/E
  cash paid to owners      = earnings x payout  (dividends + buybacks)
  value                    = cash grown for N years, plus a terminal value,
                             all discounted at the return investors require

We also solve for the *implied return*: the yearly return you'd earn if you
buy at today's price and the growth assumptions come true.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Tuple

import pandas as pd
import yfinance as yf

from .model import EQUITY_RISK_PREMIUM, RISK_FREE_RATE

FUND_TYPES = {"ETF", "MUTUALFUND"}

SECTOR_NAMES = {
    "realestate": "Real estate",
    "consumer_cyclical": "Consumer cyclical",
    "basic_materials": "Basic materials",
    "consumer_defensive": "Consumer defensive",
    "technology": "Technology",
    "communication_services": "Communication services",
    "financial_services": "Financial services",
    "utilities": "Utilities",
    "industrials": "Industrials",
    "energy": "Energy",
    "healthcare": "Healthcare",
}


def is_fund(info: dict) -> bool:
    return (info.get("quoteType") or "").upper() in FUND_TYPES


@dataclass
class FundData:
    ticker: str
    name: str
    fund_type: str                 # "ETF" or "MUTUALFUND"
    category: str
    family: str
    currency: str
    price: float
    pe: Optional[float]            # None for bond funds and other non-equity funds
    dividend_yield: float          # fraction, e.g. 0.0107
    expense_ratio: float           # fraction, e.g. 0.0003
    beta: float
    total_assets: float
    return_3y: Optional[float]
    return_5y: Optional[float]
    holdings: List[Tuple[str, str, float]] = field(default_factory=list)  # (symbol, name, weight)
    sectors: Dict[str, float] = field(default_factory=dict)

    @property
    def can_value(self) -> bool:
        return self.pe is not None and self.pe > 0

    @property
    def earnings_yield(self) -> float:
        return 1 / self.pe if self.can_value else float("nan")

    @property
    def earnings_per_share(self) -> float:
        return self.price / self.pe if self.can_value else float("nan")

    @property
    def top_holdings_weight(self) -> float:
        return sum(w for _, _, w in self.holdings)

    def holdings_table(self) -> pd.DataFrame:
        return pd.DataFrame(self.holdings, columns=["Symbol", "Name", "Weight"])

    def sectors_table(self) -> pd.DataFrame:
        s = pd.Series(self.sectors, name="Weight").sort_values(ascending=False)
        s = s[s > 0]
        return s.rename_axis("Sector").reset_index()


def _num(x) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def fetch_fund(ticker: str, t: Optional[yf.Ticker] = None, info: Optional[dict] = None) -> FundData:
    ticker = ticker.strip().upper()
    t = t or yf.Ticker(ticker)
    info = info if info is not None else (t.info or {})

    fd = None
    try:
        fd = t.funds_data
    except Exception:
        pass

    # P/E: prefer Yahoo's trailing P/E; fall back to the holdings-level figure.
    # (Yahoo stores that one inverted, as an earnings yield, e.g. 0.0413 = P/E 24.2.)
    pe = _num(info.get("trailingPE"))
    if not pe and fd is not None:
        try:
            ey = _num(fd.equity_holdings.loc["Price/Earnings"].iloc[0])
            if ey and 0 < ey < 1:
                pe = 1 / ey
        except Exception:
            pass

    # Expense ratio: the fund-operations figure is a fraction (0.0003); the info
    # field is in percent (0.03), so convert that one.
    expense = None
    if fd is not None:
        try:
            expense = _num(fd.fund_operations.loc["Annual Report Expense Ratio"].iloc[0])
        except Exception:
            pass
    if expense is None:
        pct = _num(info.get("netExpenseRatio"))
        expense = pct / 100 if pct is not None else 0.0

    holdings: List[Tuple[str, str, float]] = []
    sectors: Dict[str, float] = {}
    if fd is not None:
        try:
            th = fd.top_holdings
            for sym, row in th.iterrows():
                holdings.append((str(sym), str(row.get("Name", sym)), float(row.get("Holding Percent", 0.0))))
        except Exception:
            pass
        try:
            sectors = {SECTOR_NAMES.get(k, k.replace("_", " ").title()): float(v) for k, v in (fd.sector_weightings or {}).items()}
        except Exception:
            pass

    price = _num(info.get("regularMarketPrice")) or _num(info.get("navPrice")) or _num(info.get("previousClose"))
    if not price:
        hist = t.history(period="5d")
        if hist.empty:
            raise ValueError(f"No price data found for '{ticker}'.")
        price = float(hist["Close"].iloc[-1])

    return FundData(
        ticker=ticker,
        name=info.get("longName") or info.get("shortName") or ticker,
        fund_type=(info.get("quoteType") or "ETF").upper(),
        category=info.get("category") or "",
        family=info.get("fundFamily") or "",
        currency=info.get("currency") or "USD",
        price=price,
        pe=pe,
        dividend_yield=_num(info.get("yield")) or 0.0,
        expense_ratio=expense,
        beta=_num(info.get("beta3Year")) or 1.0,
        total_assets=_num(info.get("totalAssets")) or 0.0,
        return_3y=_num(info.get("threeYearAverageReturn")),
        return_5y=_num(info.get("fiveYearAverageReturn")),
        holdings=holdings,
        sectors=sectors,
    )


# --------------------------------------------------------------------------- #
# Valuation
# --------------------------------------------------------------------------- #

@dataclass
class IndexAssumptions:
    growth_rate: float       # earnings growth in year 1
    terminal_growth: float   # long-run growth (roughly nominal GDP)
    required_return: float   # return investors demand from this basket of stocks
    payout: float = 0.85     # share of earnings returned to owners (dividends + buybacks)
    years: int = 10
    fade: bool = True


@dataclass
class IndexResult:
    assumptions: IndexAssumptions
    expense_ratio: float
    base_earnings: float
    growth_path: List[float]
    earnings: List[float]
    cash: List[float]
    discount_factors: List[float]
    pv_cash: List[float]
    terminal_value: float
    pv_terminal_value: float
    value_per_share: float
    price: float
    implied_return: float    # yearly return at today's price, after fees

    @property
    def upside(self) -> float:
        return self.value_per_share / self.price - 1 if self.price else float("nan")

    @property
    def terminal_share(self) -> float:
        return self.pv_terminal_value / self.value_per_share if self.value_per_share else float("nan")

    def projection_table(self) -> pd.DataFrame:
        n = len(self.cash)
        return pd.DataFrame(
            {
                "Growth": self.growth_path,
                "Earnings / share": self.earnings,
                "Cash to owners": self.cash,
                "Discount factor": self.discount_factors,
                "PV of cash": self.pv_cash,
            },
            index=[f"Year {i}" for i in range(1, n + 1)],
        )


def default_index_assumptions(f: FundData) -> IndexAssumptions:
    req = RISK_FREE_RATE + f.beta * EQUITY_RISK_PREMIUM
    return IndexAssumptions(
        growth_rate=0.06,
        terminal_growth=0.04,
        required_return=round(min(max(req, 0.06), 0.14), 4),
    )


def _value(f: FundData, a: IndexAssumptions, discount: float) -> Tuple[float, dict]:
    """Value per fund share when cash is discounted at `discount` (already incl. fees)."""
    e = f.earnings_per_share
    growth, earnings, cash, dfs, pvs = [], [], [], [], []
    for i in range(1, a.years + 1):
        if a.fade and a.years > 1:
            g = a.growth_rate + (a.terminal_growth - a.growth_rate) * (i - 1) / (a.years - 1)
        else:
            g = a.growth_rate
        e *= 1 + g
        c = e * a.payout
        df = 1 / (1 + discount) ** i
        growth.append(g)
        earnings.append(e)
        cash.append(c)
        dfs.append(df)
        pvs.append(c * df)
    tv = cash[-1] * (1 + a.terminal_growth) / (discount - a.terminal_growth)
    pv_tv = tv * dfs[-1]
    parts = dict(growth=growth, earnings=earnings, cash=cash, dfs=dfs, pvs=pvs, tv=tv, pv_tv=pv_tv)
    return sum(pvs) + pv_tv, parts


def implied_return(f: FundData, a: IndexAssumptions) -> float:
    """Yearly return (after fees) that makes the model's value equal today's price."""
    lo, hi = a.terminal_growth + 1e-4, 1.0
    if _value(f, a, lo)[0] < f.price:
        return float("nan")  # even a near-zero discount can't justify the price
    for _ in range(100):
        mid = (lo + hi) / 2
        if _value(f, a, mid)[0] > f.price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2 - f.expense_ratio


def run_index_valuation(f: FundData, a: IndexAssumptions) -> IndexResult:
    if not f.can_value:
        raise ValueError(f"{f.ticker} has no P/E ratio (for example, a bond fund), so it can't be valued this way.")
    # Fees come out of what the investor earns, so the fund must earn the
    # required return *plus* its expense ratio to satisfy the investor.
    discount = a.required_return + f.expense_ratio
    if discount <= a.terminal_growth:
        raise ValueError("Required return must be greater than terminal growth.")
    value, p = _value(f, a, discount)
    return IndexResult(
        assumptions=a,
        expense_ratio=f.expense_ratio,
        base_earnings=f.earnings_per_share,
        growth_path=p["growth"],
        earnings=p["earnings"],
        cash=p["cash"],
        discount_factors=p["dfs"],
        pv_cash=p["pvs"],
        terminal_value=p["tv"],
        pv_terminal_value=p["pv_tv"],
        value_per_share=value,
        price=f.price,
        implied_return=implied_return(f, a),
    )


def implied_index_growth(f: FundData, a: IndexAssumptions, lo: float = -0.5, hi: float = 1.0) -> float:
    """Reverse valuation: the steady yearly earnings growth (no fading) that justifies today's price."""
    if not f.can_value or not f.price:
        return float("nan")
    discount = a.required_return + f.expense_ratio
    if discount <= a.terminal_growth:
        return float("nan")

    def value(g: float) -> float:
        return _value(f, replace(a, growth_rate=g, fade=False), discount)[0]

    if value(lo) > f.price or value(hi) < f.price:
        return float("nan")
    for _ in range(100):
        mid = (lo + hi) / 2
        if value(mid) < f.price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def index_scenarios(a: IndexAssumptions) -> Dict[str, IndexAssumptions]:
    from .model import make_scenarios  # local import keeps module load order simple
    return make_scenarios(a, rate_field="required_return", growth_step=0.02)


def index_sensitivity(
    f: FundData,
    a: IndexAssumptions,
    r_step: float = 0.01,
    tg_step: float = 0.005,
    n: int = 2,
) -> pd.DataFrame:
    """Value per share across required return (rows) x terminal growth (columns)."""
    rs = [a.required_return + r_step * k for k in range(-n, n + 1)]
    tgs = [a.terminal_growth + tg_step * k for k in range(-n, n + 1)]
    data = {}
    for tg in tgs:
        col = []
        for r in rs:
            if r + f.expense_ratio <= tg:
                col.append(float("nan"))
            else:
                col.append(run_index_valuation(f, replace(a, required_return=r, terminal_growth=tg)).value_per_share)
        data[f"{tg:.1%}"] = col
    return pd.DataFrame(data, index=[f"{r:.1%}" for r in rs])
