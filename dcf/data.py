"""Fetch the financial inputs a DCF needs from Yahoo Finance (via yfinance)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd
import yfinance as yf

# Industries where a free-cash-flow DCF doesn't work: for banks, insurers and
# brokers, "cash flow" mixes in customer deposits, loans and premiums, so it
# swings wildly and says little about what owners earn. Payment networks such as
# Visa ("Credit Services") are ordinary businesses and keep the normal DCF.
FINANCIAL_INDUSTRY_WORDS = ("bank", "insurance", "capital markets", "mortgage", "asset management", "reinsurance")


def _row(df: pd.DataFrame, *names: str) -> Optional[pd.Series]:
    """Return the first matching row from a yfinance statement, oldest -> newest."""
    if df is None or df.empty:
        return None
    for name in names:
        if name in df.index:
            s = pd.to_numeric(df.loc[name], errors="coerce").dropna()
            if not s.empty:
                return s.sort_index()
    return None


def _latest(df: pd.DataFrame, *names: str, default: float = 0.0) -> float:
    s = _row(df, *names)
    return float(s.iloc[-1]) if s is not None else default


def _num(x) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def is_financial_industry(sector: str, industry: str) -> bool:
    ind = (industry or "").lower()
    return (sector or "") == "Financial Services" and any(w in ind for w in FINANCIAL_INDUSTRY_WORDS)


@dataclass
class CompanyData:
    ticker: str
    name: str
    currency: str
    price: float
    shares_outstanding: float
    market_cap: float
    beta: float
    total_debt: float
    cash: float
    tax_rate: float
    interest_expense: float
    years: List[str] = field(default_factory=list)
    revenue: List[float] = field(default_factory=list)
    operating_cash_flow: List[float] = field(default_factory=list)
    capex: List[float] = field(default_factory=list)
    free_cash_flow: List[float] = field(default_factory=list)
    dividends_paid: List[float] = field(default_factory=list)   # positive amounts
    buybacks: List[float] = field(default_factory=list)         # positive amounts
    sector: str = ""
    industry: str = ""
    analyst_growth: Optional[float] = None   # analysts' next-year earnings growth estimate
    pe: Optional[float] = None

    @property
    def net_debt(self) -> float:
        return self.total_debt - self.cash

    @property
    def latest_fcf(self) -> float:
        return self.free_cash_flow[-1] if self.free_cash_flow else 0.0

    @property
    def latest_revenue(self) -> float:
        return self.revenue[-1] if self.revenue else 0.0

    @property
    def is_financial(self) -> bool:
        """Banks, insurers and brokers, which are valued from cash returned to shareholders instead."""
        return is_financial_industry(self.sector, self.industry)

    @property
    def cash_returned(self) -> List[float]:
        """Dividends + buybacks each year: what the company actually handed to its owners."""
        out = []
        for d, b in zip(self.dividends_paid, self.buybacks):
            d = 0.0 if d is None or math.isnan(d) else d
            b = 0.0 if b is None or math.isnan(b) else b
            out.append(d + b)
        return out

    @property
    def valuation_cash_flow(self) -> List[float]:
        """The yearly cash series the valuation is built on."""
        return self.cash_returned if self.is_financial else self.free_cash_flow

    def history(self) -> pd.DataFrame:
        data = {
            "Revenue": self.revenue,
            "Operating cash flow": self.operating_cash_flow,
            "Capex": self.capex,
            "Free cash flow": self.free_cash_flow,
        }
        if self.is_financial:
            data["Dividends"] = self.dividends_paid
            data["Buybacks"] = self.buybacks
            data["Cash returned to shareholders"] = self.cash_returned
        return pd.DataFrame(data, index=self.years)


def _analyst_growth(t: yf.Ticker) -> Optional[float]:
    """Analysts' consensus earnings growth for next year ('+1y'), if Yahoo has it."""
    try:
        ge = t.growth_estimates
        if ge is None or ge.empty or "stockTrend" not in ge.columns:
            return None
        for period in ("+1y", "LTG", "0y"):
            if period in ge.index:
                v = _num(ge.loc[period, "stockTrend"])
                if v is not None:
                    return v
    except Exception:
        pass
    return None


def fetch_company(ticker: str, t: Optional[yf.Ticker] = None, info: Optional[dict] = None) -> CompanyData:
    ticker = ticker.strip().upper()
    t = t or yf.Ticker(ticker)

    if info is None:
        info = {}
        try:
            info = t.info or {}
        except Exception:
            pass

    cf = t.cashflow
    inc = t.income_stmt
    bs = t.balance_sheet
    if cf is None or cf.empty:
        raise ValueError(f"No cash-flow data found for '{ticker}'. Check the ticker symbol.")

    ocf = _row(cf, "Operating Cash Flow", "Cash Flow From Continuing Operating Activities")
    capex = _row(cf, "Capital Expenditure", "Purchase Of PPE")
    fcf = _row(cf, "Free Cash Flow")
    if fcf is None:
        if ocf is None or capex is None:
            raise ValueError(f"Could not derive free cash flow for '{ticker}'.")
        fcf = (ocf + capex).dropna()  # capex is reported as a negative number

    idx = fcf.index
    revenue = _row(inc, "Total Revenue", "Operating Revenue")
    dividends = _row(cf, "Cash Dividends Paid", "Common Stock Dividend Paid")
    buybacks = _row(cf, "Repurchase Of Capital Stock", "Common Stock Payments")

    def align(s: Optional[pd.Series], default: float = float("nan")) -> List[float]:
        if s is None:
            return [default] * len(idx)
        return [float(v) for v in s.reindex(idx).values]

    # Effective tax rate, clamped to something sane.
    pretax = _latest(inc, "Pretax Income")
    tax = _latest(inc, "Tax Provision")
    tax_rate = tax / pretax if pretax > 0 else 0.21
    tax_rate = min(max(tax_rate, 0.0), 0.40)

    price = float(info.get("currentPrice") or info.get("regularMarketPrice") or 0.0)
    if not price:
        hist = t.history(period="5d")
        price = float(hist["Close"].iloc[-1]) if not hist.empty else 0.0

    shares = float(
        info.get("sharesOutstanding")
        or _latest(bs, "Ordinary Shares Number", "Share Issued")
        or 0.0
    )
    if shares <= 0:
        raise ValueError(f"Shares outstanding unavailable for '{ticker}'.")

    total_debt = float(info.get("totalDebt") or _latest(bs, "Total Debt"))
    cash = float(
        info.get("totalCash")
        or _latest(bs, "Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents")
    )

    return CompanyData(
        ticker=ticker,
        name=info.get("longName") or info.get("shortName") or ticker,
        currency=info.get("financialCurrency") or info.get("currency") or "USD",
        price=price,
        shares_outstanding=shares,
        market_cap=float(info.get("marketCap") or price * shares),
        beta=float(info.get("beta") or 1.0),
        total_debt=total_debt,
        cash=cash,
        tax_rate=tax_rate,
        interest_expense=abs(_latest(inc, "Interest Expense", "Interest Expense Non Operating")),
        years=[str(d.year) if hasattr(d, "year") else str(d) for d in idx],
        revenue=align(revenue),
        operating_cash_flow=align(ocf),
        capex=align(capex),
        free_cash_flow=[float(v) for v in fcf.values],
        # Yahoo reports cash paid out as negative numbers; store them as positive amounts.
        dividends_paid=[abs(v) for v in align(dividends, 0.0)],
        buybacks=[abs(v) for v in align(buybacks, 0.0)],
        sector=info.get("sector") or "",
        industry=info.get("industry") or "",
        analyst_growth=_analyst_growth(t),
        pe=_num(info.get("trailingPE")),
    )
