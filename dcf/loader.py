"""One entry point for downloading a ticker, with disk caching."""

from __future__ import annotations

from typing import Union

import pandas as pd
import yfinance as yf

from . import cache
from .data import CompanyData, fetch_company
from .fund import FundData, fetch_fund, is_fund


def _download(ticker: str) -> Union[CompanyData, FundData]:
    t = yf.Ticker(ticker)
    try:
        info = t.info or {}
    except Exception:
        info = {}
    if is_fund(info):
        return fetch_fund(ticker, t=t, info=info)
    return fetch_company(ticker, t=t, info=info)


def load(ticker: str, refresh: bool = False,
         max_age_hours: float = cache.DEFAULT_MAX_AGE_HOURS) -> Union[CompanyData, FundData]:
    """Fetch a ticker, returning FundData for ETFs/mutual funds and CompanyData otherwise.

    Results are cached on disk for `max_age_hours`; refresh=True forces a new download.
    """
    ticker = ticker.strip().upper()
    return cache.cached(ticker, lambda: _download(ticker), max_age_hours=max_age_hours, refresh=refresh)


def data_age_hours(ticker: str):
    return cache.age_hours(ticker.strip().upper())


def price_history(ticker: str, period: str = "5y", refresh: bool = False) -> pd.Series:
    """Daily closing prices (cached like the financial data)."""
    ticker = ticker.strip().upper()

    def download() -> pd.Series:
        h = yf.Ticker(ticker).history(period=period, auto_adjust=False)
        if h is None or h.empty:
            return pd.Series(dtype=float)
        s = h["Close"].copy()
        idx = pd.to_datetime(s.index)
        s.index = idx.tz_localize(None) if idx.tz is not None else idx
        return s

    return cache.cached(f"{ticker}_history_{period}", download, refresh=refresh)
