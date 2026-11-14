"""Fetch the financial inputs a DCF needs.

Financial statements (revenue, cash flow, capital spending, dividends, buybacks) come from the
SEC's EDGAR database when the company files there, with Yahoo Finance as the fallback. The share
price, debt and cash, analyst estimates and ratios come from Yahoo Finance (via yfinance).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date
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
    dividend_rate: Optional[float] = None    # dollars per share per year
    target_low: Optional[float] = None       # analysts' 12-month price targets
    target_mean: Optional[float] = None
    target_high: Optional[float] = None
    analyst_count: Optional[int] = None
    recommendation: str = ""                 # e.g. "buy", "hold", "strong_buy"
    statements_source: str = "Yahoo Finance"  # where the yearly figures came from
    # Ratios from Yahoo, for the quality scorecard and the comparison with similar companies.
    forward_pe: Optional[float] = None
    ev_to_ebitda: Optional[float] = None
    ebitda: Optional[float] = None
    operating_margin: Optional[float] = None  # fractions, e.g. 0.21 = 21%
    profit_margin: Optional[float] = None
    return_on_assets: Optional[float] = None
    return_on_equity: Optional[float] = None

    @property
    def dividend_yield(self) -> float:
        """Yearly dividend as a fraction of the price (0.003 = 0.3%)."""
        return (self.dividend_rate or 0.0) / self.price if self.price else 0.0

    @property
    def has_analyst_targets(self) -> bool:
        return bool(self.target_mean and self.target_low and self.target_high)

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


def _sec_statements(ticker: str, financial: bool) -> Optional[dict]:
    """The last four annual reports from SEC EDGAR, or None if the SEC has nothing usable."""
    try:
        from . import sec   # imported here so a problem with the SEC module never blocks Yahoo data
        facts, _ = sec.ticker_facts(ticker)
        return sec.snapshot(facts, date.today().isoformat(), max_years=4, financial=financial)
    except Exception as e:   # not an SEC filer (e.g. a foreign company), or EDGAR unreachable
        logging.getLogger(__name__).info("SEC data unavailable for %s: %s", ticker, e)
        return None


def fetch_company(ticker: str, t: Optional[yf.Ticker] = None, info: Optional[dict] = None,
                  use_sec: bool = True) -> CompanyData:
    ticker = ticker.strip().upper()
    t = t or yf.Ticker(ticker)

    if info is None:
        info = {}
        try:
            info = t.info or {}
        except Exception:
            pass

    financial = is_financial_industry(info.get("sector") or "", info.get("industry") or "")
    sec_data = _sec_statements(ticker, financial) if use_sec else None
    if sec_data:
        return _build(ticker, t, info, _from_sec(sec_data))

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

    statements = dict(
        years=[str(d.year) if hasattr(d, "year") else str(d) for d in idx],
        revenue=align(revenue),
        operating_cash_flow=align(ocf),
        capex=align(capex),
        free_cash_flow=[float(v) for v in fcf.values],
        # Yahoo reports cash paid out as negative numbers; store them as positive amounts.
        dividends_paid=[abs(v) for v in align(dividends, 0.0)],
        buybacks=[abs(v) for v in align(buybacks, 0.0)],
        tax_rate=tax_rate,
        interest_expense=abs(_latest(inc, "Interest Expense", "Interest Expense Non Operating")),
        shares=_latest(bs, "Ordinary Shares Number", "Share Issued"),
        total_debt=_latest(bs, "Total Debt"),
        cash=_latest(bs, "Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents"),
        source="Yahoo Finance",
    )
    return _build(ticker, t, info, statements)


def _from_sec(s: dict) -> dict:
    """Turn an SEC snapshot into the same shape as the Yahoo statements."""
    tax_rate = s["tax"] / s["pretax"] if s.get("pretax", 0) > 0 else 0.21
    return dict(
        years=s["years"], revenue=s["revenue"], operating_cash_flow=s["operating_cash_flow"],
        capex=s["capex"], free_cash_flow=s["free_cash_flow"], dividends_paid=s["dividends_paid"],
        buybacks=s["buybacks"], tax_rate=min(max(tax_rate, 0.0), 0.40), interest_expense=s["interest_expense"],
        shares=s["shares"], total_debt=s["total_debt"], cash=s["cash"], source="SEC EDGAR",
    )


def _build(ticker: str, t: yf.Ticker, info: dict, st: dict) -> CompanyData:
    """Combine yearly statements (SEC or Yahoo) with Yahoo's price, balance sheet and ratios."""
    price = float(info.get("currentPrice") or info.get("regularMarketPrice") or 0.0)
    if not price:
        hist = t.history(period="5d")
        price = float(hist["Close"].iloc[-1]) if not hist.empty else 0.0

    shares = float(info.get("sharesOutstanding") or st.get("shares") or 0.0)
    if shares <= 0:
        raise ValueError(f"Shares outstanding unavailable for '{ticker}'.")
    # Yahoo's debt includes leases and its cash includes short-term investments, which is what the
    # valuation needs; the SEC/statement figures are only a fallback when Yahoo has none.
    total_debt = float(info.get("totalDebt") or st.get("total_debt") or 0.0)
    cash = float(info.get("totalCash") or st.get("cash") or 0.0)

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
        tax_rate=st["tax_rate"],
        interest_expense=st["interest_expense"],
        years=st["years"],
        revenue=st["revenue"],
        operating_cash_flow=st["operating_cash_flow"],
        capex=st["capex"],
        free_cash_flow=st["free_cash_flow"],
        dividends_paid=st["dividends_paid"],
        buybacks=st["buybacks"],
        sector=info.get("sector") or "",
        industry=info.get("industry") or "",
        analyst_growth=_analyst_growth(t),
        pe=_num(info.get("trailingPE")),
        # Yahoo's "dividendYield" field is in percent for stocks, so derive the yield from the dollar rate instead.
        dividend_rate=_num(info.get("dividendRate")),
        target_low=_num(info.get("targetLowPrice")),
        target_mean=_num(info.get("targetMeanPrice")),
        target_high=_num(info.get("targetHighPrice")),
        analyst_count=int(info["numberOfAnalystOpinions"]) if _num(info.get("numberOfAnalystOpinions")) else None,
        recommendation=(info.get("recommendationKey") or "").replace("_", " "),
        statements_source=st.get("source", "Yahoo Finance"),
        forward_pe=_num(info.get("forwardPE")),
        ev_to_ebitda=_num(info.get("enterpriseToEbitda")),
        ebitda=_num(info.get("ebitda")),
        operating_margin=_num(info.get("operatingMargins")),
        profit_margin=_num(info.get("profitMargins")),
        return_on_assets=_num(info.get("returnOnAssets")),
        return_on_equity=_num(info.get("returnOnEquity")),
    )
