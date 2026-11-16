"""Point-in-time company financials from SEC EDGAR, for backtesting.

SEC's "company facts" service has every number companies have reported in
their filings since about 2009, each tagged with the date it was *filed*.
That lets a backtest ask "what did investors know on 1 April 2015?" and use
only reports filed before then, which avoids look-ahead bias.

Companies label the same item differently (and change labels over the years),
so each item is looked up through a list of fallback tags.

Downloads are cached on disk for 30 days. No personal details are sent: the
User-Agent is a generic description of this tool.
"""

from __future__ import annotations

import time
from datetime import date
from typing import Dict, Iterable, List, Optional, Tuple

import requests

from . import cache

USER_AGENT = "dcf-tool educational backtest"
SEC_CACHE_HOURS = 24 * 30
_last_call = [0.0]

# Fallback tags, in priority order, for each item we need.
TAGS = {
    "ocf": ["NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
              "PaymentsForCapitalImprovements", "PaymentsToAcquireOtherPropertyPlantAndEquipment"],
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueGoodsNet"],
    "dividends": ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"],
    "buybacks": ["PaymentsForRepurchaseOfCommonStock"],
    "interest": ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt"],
    "tax": ["IncomeTaxExpenseBenefit"],
    "pretax": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
               "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue",
             "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "debt_total": ["LongTermDebt", "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
                   "DebtLongtermAndShorttermCombinedAmount"],
    "debt_noncurrent": ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations"],
    "debt_current": ["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"],
    "short_borrowings": ["ShortTermBorrowings", "CommercialPaper"],
    "diluted_shares": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
    "basic_shares": ["WeightedAverageNumberOfSharesOutstandingBasic"],
    # Depreciation: a rough measure of the spending needed just to maintain the business.
    "depreciation": ["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet",
                     "DepreciationAndAmortization", "Depreciation"],
}
DURATION_ITEMS = {"ocf", "capex", "revenue", "dividends", "buybacks", "interest", "tax", "pretax",
                  "diluted_shares", "basic_shares", "depreciation"}
MIN_PLAUSIBLE_SHARES = 1_000_000   # every company in the backtest has far more; smaller values are mis-scaled
ANNUAL_FORMS = ("10-K", "10-K/A", "10-KT", "20-F", "40-F")


# --------------------------------------------------------------------------- #
# Downloading
# --------------------------------------------------------------------------- #

REQUEST_TIMEOUT = 60   # seconds; the live app lowers this so a slow SEC can't stall a page


def _get_json(url: str) -> dict:
    wait = 0.12 - (time.time() - _last_call[0])  # SEC asks for no more than 10 requests a second
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.time()
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.json()


def lookup_cik(ticker: str) -> int:
    """SEC company ID for a ticker, via EDGAR's company search."""
    ticker = ticker.upper().replace(".", "-")

    def fetch() -> int:
        data = _get_json(f"https://efts.sec.gov/LATEST/search-index?keysTyped={ticker}")
        for hit in data.get("hits", {}).get("hits", []):
            tickers = (hit.get("_source", {}).get("tickers") or "").upper().replace(".", "-")
            if ticker in [t.strip() for t in tickers.split(",")]:
                return int(hit["_id"])
        raise ValueError(f"SEC has no company with ticker {ticker}")

    return cache.cached(f"sec_cik_{ticker}", fetch, max_age_hours=SEC_CACHE_HOURS * 12)


# Companies whose filing history is split across SEC IDs after a restructuring (old ID first).
# EDGAR's ticker search returns only the newest ID, which has little history.
CIK_OVERRIDES = {
    "XOM": [34088, 2115436],     # Exxon Mobil Corp -> ExxonMobil Holdings Corporation
    "DIS": [1001039, 1744489],   # TWDC Enterprises (old Disney) -> Walt Disney Co after the 2019 Fox deal
}


def merge_facts(parts: List[dict]) -> dict:
    """Combine company-facts documents from several SEC IDs into one."""
    merged: dict = {"facts": {}}
    for part in parts:
        for taxonomy, tags in part.get("facts", {}).items():
            for tag, body in tags.items():
                dest = merged["facts"].setdefault(taxonomy, {}).setdefault(tag, {"units": {}})
                for unit, entries in body.get("units", {}).items():
                    dest["units"].setdefault(unit, []).extend(entries)
    return merged


def ticker_facts(ticker: str) -> Tuple[dict, int]:
    """(company facts, SIC industry code) for a ticker, joining histories split across SEC IDs."""
    t = ticker.upper()
    ciks = CIK_OVERRIDES.get(t) or [lookup_cik(t)]
    facts = merge_facts([company_facts(c) for c in ciks]) if len(ciks) > 1 else company_facts(ciks[0])
    return facts, company_sic(ciks[-1])


def company_facts(cik: int) -> dict:
    return cache.cached(f"sec_facts_{cik}",
                        lambda: _get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"),
                        max_age_hours=SEC_CACHE_HOURS)


def company_sic(cik: int) -> int:
    def fetch() -> int:
        sic = _get_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json").get("sic")
        return int(sic) if sic else 0
    return cache.cached(f"sec_sic_{cik}", fetch, max_age_hours=SEC_CACHE_HOURS * 12)


def sic_to_sector(sic: int) -> Tuple[str, str]:
    """Map an SEC industry code to the sector/industry names the valuation model understands."""
    if 6020 <= sic <= 6099 or 6710 <= sic <= 6712:
        return "Financial Services", "Banks"
    if 6300 <= sic <= 6411:
        return "Financial Services", "Insurance"
    if 6200 <= sic <= 6299:
        return "Financial Services", "Capital Markets"
    return "", ""


# --------------------------------------------------------------------------- #
# Point-in-time extraction
# --------------------------------------------------------------------------- #

def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def _entries(facts: dict, tag: str, taxonomy: str = "us-gaap") -> List[dict]:
    units = facts.get("facts", {}).get(taxonomy, {}).get(tag, {}).get("units", {})
    for unit in ("USD", "shares"):
        if unit in units:
            return units[unit]
    return []


def annual_values(facts: dict, tags: Iterable[str], asof: str, duration: bool = True) -> Dict[str, float]:
    """{fiscal period end: value} using only annual-report facts filed on or before `asof`.

    For each period the latest filing wins (so restatements known by `asof` are used),
    and tags earlier in `tags` take priority over later ones.
    """
    out: Dict[str, float] = {}
    for tag in tags:
        best: Dict[str, Tuple[str, float]] = {}
        for e in _entries(facts, tag):
            if not str(e.get("form", "")).startswith(ANNUAL_FORMS) or e.get("filed", "9999") > asof:
                continue
            end = e.get("end")
            if not end or e.get("val") is None:
                continue
            if duration:
                start = e.get("start")
                if not start or not 330 <= _days(start, end) <= 400:
                    continue  # skip quarters and odd-length periods
            elif e.get("start"):
                continue
            if end not in best or e["filed"] > best[end][0]:
                best[end] = (e["filed"], float(e["val"]))
        for end, (_, val) in best.items():
            out.setdefault(end, val)
    return out


def shares_outstanding(facts: dict, asof: str) -> Optional[float]:
    """Shares outstanding from the most recent cover page filed on or before `asof`.

    Companies with several share classes report one figure per class in the same
    filing, so figures from the same filing are added together.
    """
    by_filing: Dict[Tuple[str, str], float] = {}
    for e in _entries(facts, "EntityCommonStockSharesOutstanding", "dei"):
        if e.get("filed", "9999") <= asof and e.get("val"):
            key = (e["filed"], e.get("accn", ""))
            by_filing[key] = by_filing.get(key, 0.0) + float(e["val"])
    if not by_filing:
        return None
    return by_filing[max(by_filing)]


def debt_at(facts: dict, asof: str) -> Dict[str, float]:
    """{balance-sheet date: total debt} known by `asof`."""
    total = annual_values(facts, TAGS["debt_total"], asof, duration=False)
    noncur = annual_values(facts, TAGS["debt_noncurrent"], asof, duration=False)
    cur = annual_values(facts, TAGS["debt_current"], asof, duration=False)
    short = annual_values(facts, TAGS["short_borrowings"], asof, duration=False)
    out: Dict[str, float] = {}
    for end in set(total) | set(noncur):
        base = total[end] if end in total else noncur[end] + cur.get(end, 0.0)
        out[end] = base + short.get(end, 0.0)
    return out


def pick_share_count(cover: Optional[float], diluted: Optional[float], basic: Optional[float],
                     balance_sheet: Optional[float]) -> Optional[float]:
    """Choose a share count from the several figures a company reports, resisting data errors.

    Real examples this guards against: Mastercard's cover page listing only one share class
    (122M instead of ~1.1B), and McDonald's tagging diluted shares in millions (721.9).
    Mis-scaled values are dropped, then the middle of what's left is used, so a single bad
    figure can't win. With only two that disagree by more than 2x, the cover page is the one
    that most often leaves out share classes, so the other figure is preferred.
    """
    candidates = [v for v in (cover, diluted, basic, balance_sheet) if v and v >= MIN_PLAUSIBLE_SHARES]
    if not candidates:
        return None
    if len(candidates) == 2 and cover in candidates:
        other = candidates[1] if candidates[0] == cover else candidates[0]
        if not 0.5 <= cover / other <= 2.0:
            return other
    candidates.sort()
    mid = len(candidates) // 2
    return candidates[mid] if len(candidates) % 2 else (candidates[mid - 1] + candidates[mid]) / 2


def snapshot(facts: dict, asof: str, max_years: int = 4, financial: bool = False) -> Optional[dict]:
    """Everything the valuation needs, as known on `asof`. None if there isn't enough data.

    Banks and insurers don't report capex, and the model values them from dividends +
    buybacks instead, so for them the years are taken from those items.
    """
    series = {k: annual_values(facts, TAGS[k], asof) for k in DURATION_ITEMS}
    ocf, capex = series["ocf"], series["capex"]
    if financial:
        ends = sorted(set(series["dividends"]) | set(series["buybacks"]))[-max_years:]
    else:
        ends = sorted(e for e in ocf if e in capex)[-max_years:]
    if len(ends) < 2:
        return None
    if _days(ends[-1], asof) > 460:   # latest annual report is too old to be current
        return None
    debt = debt_at(facts, asof)
    cash = annual_values(facts, TAGS["cash"], asof, duration=False)
    last = ends[-1]

    def pick(d: Dict[str, float], default: float = 0.0) -> float:
        return d.get(last, default)

    cover = shares_outstanding(facts, asof)
    others = dict(
        diluted=series["diluted_shares"].get(last),
        basic=series["basic_shares"].get(last),
        balance_sheet=annual_values(facts, ["CommonStockSharesOutstanding"], asof, duration=False).get(last),
    )
    # Companies that file a cover-page share count only a handful of times (e.g. Visa: twice ever) report
    # their share classes in a form this data doesn't include, so a lone cover figure can't be trusted.
    sparse_cover = len(_entries(facts, "EntityCommonStockSharesOutstanding", "dei")) < 8
    if sparse_cover and not any(v and v >= MIN_PLAUSIBLE_SHARES for v in others.values()):
        return None
    shares = pick_share_count(cover=cover, **others)
    if not shares:
        return None
    nan = float("nan")
    return {
        "years": [e[:4] for e in ends],
        "period_end": last,
        "revenue": [series["revenue"].get(e, nan) for e in ends],
        "operating_cash_flow": [ocf.get(e, nan) for e in ends],
        "capex": [-abs(capex.get(e, 0.0)) for e in ends],
        "free_cash_flow": [ocf.get(e, nan) - abs(capex.get(e, 0.0)) for e in ends],
        "dividends_paid": [abs(series["dividends"].get(e, 0.0)) for e in ends],
        "buybacks": [abs(series["buybacks"].get(e, 0.0)) for e in ends],
        "depreciation": [series["depreciation"].get(e, nan) for e in ends],
        "shares": float(shares),
        "total_debt": pick(debt),
        "cash": pick(cash),
        "interest_expense": abs(pick(series["interest"])),
        "tax": pick(series["tax"]),
        "pretax": pick(series["pretax"]),
    }
