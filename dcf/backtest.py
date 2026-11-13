"""Backtest: did stocks the model called cheap go on to beat the ones it called expensive?

Every year on the rebalance date (1 April by default, after most annual reports
are filed) each stock in the universe is valued *as of that day*:

* financials: only annual reports already filed with the SEC (point in time)
* price: the actual share price that day (undoing later stock splits)
* risk-free rate: the 10-year Treasury yield that day
* beta: measured from the two years of weekly returns before that day
* growth: past sales growth (analyst forecasts from back then aren't available)

Stocks are then split into equal-sized groups by the model's gap vs. price
(cheapest third, middle third, most expensive third) and each group's average
total return (price change plus dividends) over the next 12 months is measured.

Known limitation: the universe is today's list of large companies, so it leaves
out companies that shrank or disappeared (survivorship bias). Results are
therefore a fair comparison *between* groups but flatter all of them.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

import pandas as pd
import yfinance as yf

from . import cache, sec
from .data import CompanyData
from .model import DCFAssumptions, check_company, compute_wacc, cost_of_equity, historical_growth, run_dcf

# Large US companies with filings back to at least ~2012, across sectors.
UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "ADBE", "CRM", "ORCL", "IBM", "INTC", "CSCO",
    "QCOM", "TXN", "NFLX", "AZO", "ORLY", "HD", "LOW", "TGT", "WMT", "COST", "TJX", "ROST", "NKE", "SBUX",
    "MCD", "BKNG", "DIS", "CMCSA", "T", "VZ", "KO", "PEP", "PG", "CL", "KMB", "MO", "PM", "MDLZ", "GIS",
    "JNJ", "PFE", "MRK", "ABT", "ABBV", "LLY", "AMGN", "GILD", "BMY", "UNH", "XOM", "CVX", "COP", "CAT",
    "DE", "HON", "MMM", "GE", "BA", "LMT", "GD", "RTX", "UPS", "FDX", "UNP", "V", "MA", "JPM", "BAC", "WFC",
]
BENCHMARK = "SPY"
RATE_TICKER = "^TNX"
PRICE_CACHE_HOURS = 24 * 7
GROUP_NAMES = {3: ["Cheapest third", "Middle third", "Most expensive third"]}
MAX_PLAUSIBLE_UPSIDE = 5.0   # estimate more than 6x the price (+500%) is treated as a data error


# --------------------------------------------------------------------------- #
# Prices
# --------------------------------------------------------------------------- #

def load_prices(ticker: str, start: str = "2009-01-01") -> pd.DataFrame:
    """Daily prices with: close (as traded that day), adj (total-return index incl. dividends)."""

    def download() -> pd.DataFrame:
        h = yf.Ticker(ticker).history(start=start, auto_adjust=False, actions=True)
        if h is None or h.empty:
            return pd.DataFrame(columns=["close", "adj"])
        idx = pd.to_datetime(h.index)
        h.index = idx.tz_localize(None) if idx.tz is not None else idx
        # yfinance's Close is adjusted for later splits; multiply by the splits that happened afterwards
        # to recover the price that actually traded on each day.
        splits = h.get("Stock Splits", pd.Series(0.0, index=h.index)).replace(0, 1.0).fillna(1.0)
        after = splits[::-1].cumprod()[::-1].shift(-1).fillna(1.0)
        out = pd.DataFrame({"close": h["Close"] * after, "adj": h["Adj Close"]})
        return out.dropna()

    return cache.cached(f"bt_px_{ticker}_{start}", download, max_age_hours=PRICE_CACHE_HOURS)


def value_on(series: pd.Series, when: pd.Timestamp) -> Optional[float]:
    """Last value on or before `when` (within 10 days), else None."""
    s = series.loc[:when]
    if s.empty or (when - s.index[-1]).days > 10:
        return None
    return float(s.iloc[-1])


def forward_return(adj: pd.Series, when: pd.Timestamp, years: float = 1.0) -> Optional[float]:
    """Total return (incl. dividends) from `when` to `years` later; None if that's in the future."""
    later = when + pd.DateOffset(days=int(round(365.25 * years)))
    if adj.empty or later > adj.index[-1]:
        return None
    a, b = value_on(adj, when), value_on(adj, later)
    if not a or not b:
        return None
    return b / a - 1


def estimate_beta(adj: pd.Series, market: pd.Series, when: pd.Timestamp, weeks: int = 104) -> Optional[float]:
    """Beta from weekly returns over the `weeks` before `when`."""
    start = when - pd.DateOffset(weeks=weeks)
    s = adj.loc[start:when].resample("W-FRI").last().pct_change()
    m = market.loc[start:when].resample("W-FRI").last().pct_change()
    df = pd.concat([s, m], axis=1, keys=["s", "m"]).dropna()
    if len(df) < 52 or df["m"].var() == 0:
        return None
    b = df["s"].cov(df["m"]) / df["m"].var()
    return float(min(max(b, 0.3), 2.5))


# --------------------------------------------------------------------------- #
# Valuing one stock on one date
# --------------------------------------------------------------------------- #

def company_asof(ticker: str, facts: dict, sic: int, when: pd.Timestamp, prices: pd.DataFrame,
                 market: pd.Series, rf: float) -> Optional[CompanyData]:
    sector, industry = sec.sic_to_sector(sic)
    s = sec.snapshot(facts, when.strftime("%Y-%m-%d"), financial=bool(sector))
    if s is None:
        return None
    price = value_on(prices["close"], when)
    beta = estimate_beta(prices["adj"], market, when)
    if not price or beta is None:
        return None
    tax_rate = s["tax"] / s["pretax"] if s["pretax"] and s["pretax"] > 0 else 0.21
    return CompanyData(
        ticker=ticker, name=ticker, currency="USD", price=price, shares_outstanding=s["shares"],
        market_cap=price * s["shares"], beta=beta, total_debt=s["total_debt"], cash=s["cash"],
        tax_rate=min(max(tax_rate, 0.0), 0.40), interest_expense=s["interest_expense"], years=s["years"],
        revenue=s["revenue"], operating_cash_flow=s["operating_cash_flow"], capex=s["capex"],
        free_cash_flow=s["free_cash_flow"], dividends_paid=s["dividends_paid"], buybacks=s["buybacks"],
        sector=sector, industry=industry,
    )


def point_in_time_assumptions(c: CompanyData, rf: float) -> DCFAssumptions:
    """The app's default assumptions, using only information available at the time."""
    g = min(max(historical_growth(c), -0.05), 0.20)
    rate = cost_of_equity(c, rf=rf) if c.is_financial else compute_wacc(c, rf=rf)
    return DCFAssumptions(growth_rate=g, terminal_growth=0.025, wacc=min(max(rate, 0.06), 0.15), years=5, base="avg3")


def value_stock(ticker: str, facts: dict, sic: int, when: pd.Timestamp, prices: pd.DataFrame,
                market: pd.Series, rf: float) -> dict:
    row = {"date": when.strftime("%Y-%m-%d"), "year": when.year, "ticker": ticker}
    c = company_asof(ticker, facts, sic, when, prices, market, rf)
    if c is None:
        return {**row, "excluded": "not enough data"}
    a = point_in_time_assumptions(c, rf)
    blocking, _ = check_company(c, a.base)
    row.update(price=c.price, beta=c.beta, rf=rf, growth=a.growth_rate, discount_rate=a.wacc,
               method="payout" if c.is_financial else "fcf")
    if blocking:
        return {**row, "excluded": "negative cash flow"}
    r = run_dcf(c, a)
    if r.value_per_share <= 0:
        # Debt bigger than the whole business value: the model can't say anything useful, so don't rank it.
        return {**row, "value": r.value_per_share, "excluded": "debt exceeds value"}
    if r.upside > MAX_PLAUSIBLE_UPSIDE:
        # A large, established company worth over 6x its price almost always means a misread filing.
        return {**row, "value": r.value_per_share, "upside": r.upside, "excluded": "implausible (likely data error)"}
    r3 = forward_return(prices["adj"], when, 3.0)
    return {**row, "value": r.value_per_share, "upside": r.upside, "excluded": "",
            "fwd_1y": forward_return(prices["adj"], when, 1.0),
            "fwd_3y": (1 + r3) ** (1 / 3) - 1 if r3 is not None and r3 > -1 else None}


# --------------------------------------------------------------------------- #
# Running and summarising
# --------------------------------------------------------------------------- #

def rebalance_dates(first_year: int, last_year: int, month_day: str = "04-01") -> List[pd.Timestamp]:
    return [pd.Timestamp(f"{y}-{month_day}") for y in range(first_year, last_year + 1)]


def run_backtest(tickers: Iterable[str] = UNIVERSE, first_year: int = 2012, last_year: Optional[int] = None,
                 month_day: str = "04-01", progress: Callable[[str], None] = print) -> pd.DataFrame:
    """Value every ticker on every rebalance date. Returns one row per (date, ticker)."""
    if last_year is None:
        # The latest rebalance date whose following 12 months have fully happened.
        cutoff = pd.Timestamp(date.today()) - pd.DateOffset(years=1)
        last_year = cutoff.year if cutoff >= pd.Timestamp(f"{cutoff.year}-{month_day}") else cutoff.year - 1
    dates = rebalance_dates(first_year, last_year, month_day)

    market = load_prices(BENCHMARK)["adj"]
    rates = load_prices(RATE_TICKER)["close"]
    rows: List[dict] = []
    tickers = list(tickers)
    for i, t in enumerate(tickers, 1):
        try:
            facts, sic = sec.ticker_facts(t)
            prices = load_prices(t)
        except Exception as e:  # network trouble or an unknown ticker: skip it, keep going
            progress(f"[{i}/{len(tickers)}] {t}: skipped ({e})")
            continue
        for d in dates:
            rf = (value_on(rates, d) or 4.0) / 100
            rows.append(value_stock(t, facts, sic, d, prices, market, rf))
        progress(f"[{i}/{len(tickers)}] {t}: done")

    signals = pd.DataFrame(rows)
    bench = {d.year: forward_return(market, d, 1.0) for d in dates}
    signals["benchmark_fwd_1y"] = signals["year"].map(bench)
    return signals


def assign_groups(signals: pd.DataFrame, n_groups: int = 3) -> pd.DataFrame:
    """Label each valued stock with its group for that year (0 = cheapest)."""
    out = signals.copy()
    out["group"] = pd.NA
    usable = out["excluded"].eq("") & out["upside"].notna() & out["fwd_1y"].notna()
    for year, idx in out[usable].groupby("year").groups.items():
        sub = out.loc[idx, "upside"]
        if len(sub) < n_groups:
            continue
        # Highest upside (cheapest) -> group 0. Ranking first keeps groups equal-sized even with ties.
        ranks = sub.rank(ascending=False, method="first")
        out.loc[idx, "group"] = pd.qcut(ranks, n_groups, labels=False).astype(int)
    return out


@dataclass
class BacktestSummary:
    first_year: int
    last_year: int
    n_years: int
    avg_stocks_per_year: float
    group_names: List[str]
    avg_return: Dict[str, float]          # average yearly return per group (+ universe, benchmark)
    growth_of_1: Dict[str, float]         # $1 invested at the start, compounded
    cheap_beat_expensive: int             # years the cheapest group beat the most expensive one
    avg_rank_correlation: float           # average Spearman correlation of upside vs next-year return
    yearly: List[dict]                    # one entry per year
    three_year: Dict[str, float] = None   # average yearly return over the following 3 years, per group
    three_year_beat: int = 0              # start years where the cheapest group beat the most expensive over 3 years
    three_year_n: int = 0

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


def summarize(signals: pd.DataFrame, n_groups: int = 3) -> BacktestSummary:
    g = assign_groups(signals, n_groups)
    names = GROUP_NAMES.get(n_groups, [f"Group {i + 1}" for i in range(n_groups)])
    used = g[g["group"].notna()].copy()
    used["group"] = used["group"].astype(int)

    yearly = []
    for year, sub in used.groupby("year"):
        entry = {"year": int(year), "stocks": int(len(sub))}
        for k, name in enumerate(names):
            entry[name] = float(sub.loc[sub["group"] == k, "fwd_1y"].mean())
        entry["All stocks (equal weight)"] = float(sub["fwd_1y"].mean())
        bench = sub["benchmark_fwd_1y"].dropna()
        entry["S&P 500 (SPY)"] = float(bench.iloc[0]) if not bench.empty else float("nan")
        # Spearman rank correlation, computed from ranks so it needs no extra libraries.
        entry["rank_correlation"] = float(sub["upside"].rank().corr(sub["fwd_1y"].rank()))
        yearly.append(entry)

    cols = names + ["All stocks (equal weight)", "S&P 500 (SPY)"]
    table = pd.DataFrame(yearly)
    avg = {c: float(table[c].mean()) for c in cols} if not table.empty else {}
    growth = {c: float((1 + table[c].fillna(0)).prod()) for c in cols} if not table.empty else {}
    beat = int((table[names[0]] > table[names[-1]]).sum()) if not table.empty else 0

    # Same groups, judged over the following 3 years (annualised), where that much time has passed.
    three, beat3, n3 = {}, 0, 0
    if "fwd_3y" in used.columns:
        by = used.dropna(subset=["fwd_3y"]).groupby(["year", "group"])["fwd_3y"].mean().unstack()
        if not by.empty and set(range(n_groups)) <= set(by.columns):
            three = {name: float(by[k].mean()) for k, name in enumerate(names)}
            beat3, n3 = int((by[0] > by[n_groups - 1]).sum()), int(len(by))

    return BacktestSummary(
        first_year=int(table["year"].min()) if not table.empty else 0,
        last_year=int(table["year"].max()) if not table.empty else 0,
        n_years=len(table),
        avg_stocks_per_year=float(table["stocks"].mean()) if not table.empty else 0.0,
        group_names=names,
        avg_return=avg,
        growth_of_1=growth,
        cheap_beat_expensive=beat,
        avg_rank_correlation=float(table["rank_correlation"].mean()) if not table.empty else float("nan"),
        yearly=yearly,
        three_year=three,
        three_year_beat=beat3,
        three_year_n=n3,
    )


RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"


def save_results(signals: pd.DataFrame, summary: BacktestSummary, folder: Path = RESULTS_DIR) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    assign_groups(signals).to_csv(folder / "backtest_signals.csv", index=False)
    (folder / "backtest_summary.json").write_text(summary.to_json())


def load_results(folder: Path = RESULTS_DIR):
    """(signals, summary dict) from the last saved run, or (None, None)."""
    try:
        signals = pd.read_csv(folder / "backtest_signals.csv")
        signals["excluded"] = signals["excluded"].fillna("")
        summary = json.loads((folder / "backtest_summary.json").read_text())
        return signals, summary
    except (OSError, ValueError):
        return None, None
