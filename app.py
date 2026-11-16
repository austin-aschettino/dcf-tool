"""Beginner-friendly valuation dashboard for stocks and index funds.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import html
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dcf import (
    DCFAssumptions,
    FundData,
    IndexAssumptions,
    check_company,
    company_scenarios,
    company_tables,
    data_age_hours,
    default_assumptions,
    default_growth,
    default_base,
    model_caveats,
    default_index_assumptions,
    fund_scenarios,
    fund_tables,
    implied_growth,
    implied_index_growth,
    index_scenarios,
    index_sensitivity,
    load,
    PriceOutlook,
    company_outlook,
    cone_path,
    fund_outlook,
    make_scenarios,
    price_history,
    run_dcf,
    run_index_valuation,
    sensitivity_table,
    to_xlsx,
    LONG_RUN_EARNINGS_GROWTH,
    demand_level,
    fund_implied_growth_grid,
    fund_needed_path,
    growth_benchmarks,
    implied_discount_rate,
    implied_growth_grid,
    needed_path,
    reference_growth,
    base_cash,
)
from dcf.montecarlo import UNCERTAINTY, simulate_company, simulate_fund
from dcf.portfolio import (EXAMPLE as EXAMPLE_PORTFOLIO, format_holdings, holding_row, parse_holdings,
                           portfolio_volatility, project_value, sector_mix, weighted)
from dcf.quality import implied_prices, multiples, overall, peer_medians, peer_tickers, scorecard
from dcf.fairvalue import fair_value_band, fair_value_methods, price_position

st.set_page_config(page_title="Stock & Fund Valuation", page_icon="📈", layout="wide")

# --------------------------------------------------------------------------- #
# Shareable links: the page address carries the ticker and slider settings
# --------------------------------------------------------------------------- #

MODES = {"home": "Home", "single": "One stock or fund", "compare": "Compare several",
         "portfolio": "My portfolio", "backtest": "Backtest results"}
SHARE: dict = {}   # filled in as the page is drawn, then written to the address bar at the end
# URL parameter -> widget key (for the current ticker T) and type
STOCK_PARAMS = {"src": ("src", str), "base": ("base", str), "tg": ("tg", float), "w": ("w", float),
                "y": ("y", int), "f": ("f", bool)}
FUND_PARAMS = {"fg": ("fg", float), "ftg": ("ftg", float), "fr": ("fr", float), "fp": ("fp", float),
               "fy": ("fy", int), "ff": ("ff", bool)}


def seed_from_url() -> None:
    """On a visitor's first page load, copy settings from the link into the widgets."""
    if st.session_state.get("_seeded"):
        return
    st.session_state["_seeded"] = True
    q = st.query_params
    try:
        mode = MODES.get(q.get("m") or ("single" if q.get("t") else "home"))
        if mode:
            st.session_state["mode"] = mode
        if q.get("dark") == "1":
            st.session_state["dark"] = True
        if q.get("c"):
            picks = [t.strip().upper() for t in q["c"].split(",") if t.strip()][:6]
            st.session_state["compare_list"] = [t for t in picks if t in TICKERS]
            st.session_state["compare_extra"] = ", ".join(t for t in picks if t not in TICKERS)
        if q.get("p"):
            st.session_state["portfolio"] = q["p"]
        t = (q.get("t") or "").strip().upper()
        if not t:
            return
        if t in TICKERS:
            st.session_state["list_ticker"] = t
        else:
            st.session_state["custom_ticker"] = t
        for name, (key, kind) in {**STOCK_PARAMS, **FUND_PARAMS}.items():
            if name in q:
                st.session_state[f"{key}__{t}"] = (q[name] == "1") if kind is bool else kind(q[name])
        if "g" in q:
            src, base = q.get("src", "analyst"), q.get("base", "avg3")
            st.session_state[f"g_{src}_{base}__{t}"] = float(q["g"])
    except (ValueError, TypeError):
        pass   # a mangled link just opens the default view


def share_url() -> str:
    base = (st.context.url or "").split("?")[0] or "http://localhost:8501/"
    return base + ("?" + urlencode(SHARE) if SHARE else "")


def share_button() -> None:
    with st.popover("🔗 Share", help="Get a link that opens this exact view."):
        st.markdown("**Link to this exact view**")
        st.code(share_url(), language=None, wrap_lines=True)
        st.caption("Anyone who opens it sees the same stock or fund and the same slider settings. "
                   "The address bar always holds the latest link too.")


def sync_url() -> None:
    params = {k: str(v) for k, v in SHARE.items()}
    if st.query_params.to_dict() != params:
        st.query_params.from_dict(params)


def is_dark() -> bool:
    return bool(st.session_state.get("dark"))

# --------------------------------------------------------------------------- #
# Styling (colours and fonts live in .streamlit/config.toml; this adds cards and the header)
# --------------------------------------------------------------------------- #

CSS = """
<style>
/* Fonts: Inter when it has loaded, the system's sans-serif font until then (never a serif fallback) */
.stApp, .stApp button, .stApp input, .stApp textarea, .stApp [data-baseweb],
.stApp :is(p, li, span, label, div, td, th, a, strong, em, small, code):not([data-testid="stIconMaterial"]):not([class*="material"]) {
    font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .page-head h2, .home-card h4 {
    font-family: "Plus Jakarta Sans", "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }

/* Page width and spacing */
[data-testid="stMainBlockContainer"] { padding-top: 2.2rem; max-width: 1320px; }

/* Hero banner */
.hero { background: linear-gradient(120deg, #4338ca 0%, #6d28d9 48%, #0891b2 100%); border-radius: 20px;
        padding: 26px 30px; color: #fff; margin-bottom: 8px; position: relative; overflow: hidden;
        box-shadow: 0 10px 30px rgba(67,56,202,.25); }
.hero::after { content: ""; position: absolute; right: -60px; top: -80px; width: 260px; height: 260px;
               border-radius: 50%; background: rgba(255,255,255,.10); }
.hero h1 { color: #fff !important; font-size: 2.1rem; margin: 0 0 4px 0; padding: 0; line-height: 1.15; }
.hero p { color: rgba(255,255,255,.88); margin: 0; font-size: 1.02rem; }
.hero .pills { margin-top: 14px; display: flex; gap: 8px; flex-wrap: wrap; }
.hero .pill { background: rgba(255,255,255,.16); border: 1px solid rgba(255,255,255,.25); border-radius: 999px;
              padding: 3px 12px; font-size: .82rem; font-weight: 600; }

/* Page title for a stock/fund/page with coloured chips */
.page-head { margin: 4px 0 0 0; }
.page-head h2 { margin: 0 0 6px 0; padding: 0; font-size: 2rem; line-height: 1.2; }
.chip { display: inline-block; border-radius: 999px; padding: 2px 10px; margin: 0 6px 6px 0;
        font-size: .875rem; font-weight: 600; border: 1px solid transparent; }
.chip.indigo { background: #eef2ff; color: #4338ca; border-color: #e0e7ff; }
.chip.teal   { background: #f0fdfa; color: #0f766e; border-color: #ccfbf1; }
.chip.amber  { background: #fffbeb; color: #b45309; border-color: #fef3c7; }
.chip.violet { background: #f5f3ff; color: #6d28d9; border-color: #ede9fe; }
.chip.slate  { background: #f1f5f9; color: #334155; border-color: #e2e8f0; }

/* Numbers: each row of figures shares one box, with thin dividers between the figures (#12) */
[data-testid="stMetric"] { background: transparent; border: none; padding: 2px 4px; }
[class*="st-key-kpis_"] { background: #fff; }
[class*="st-key-kpis_"] [data-testid="stColumn"] + [data-testid="stColumn"] { border-left: 1px solid #e3e8f2; padding-left: 16px; }
[data-testid="stMetricLabel"] p { color: #64748b; font-weight: 600; font-size: .875rem; }
[data-testid="stMetricValue"] { font-weight: 700; color: #0f172a; font-size: 1.75rem; }

/* Cards: white panels on the light-grey page */
.st-key-card, [class*="st-key-card_"], [class*="st-key-verdict_"], [class*="st-key-scen_"] { background: #fff; }

/* Verdict cards tinted by the result */
[class*="st-key-verdict_green"]  { background: linear-gradient(135deg, #ecfdf5 0%, #ffffff 60%); border-left: 6px solid #059669 !important; }
[class*="st-key-verdict_red"]    { background: linear-gradient(135deg, #fff1f2 0%, #ffffff 60%); border-left: 6px solid #e11d48 !important; }
[class*="st-key-verdict_orange"] { background: linear-gradient(135deg, #fffbeb 0%, #ffffff 60%); border-left: 6px solid #f59e0b !important; }

/* Scenario cards: red / indigo / teal top edge */
.st-key-scen_0 { border-top: 4px solid #e11d48 !important; }
.st-key-scen_1 { border-top: 4px solid #4f46e5 !important; }
.st-key-scen_2 { border-top: 4px solid #0d9488 !important; }
[class*="st-key-scen_"] [data-testid="stMetric"] { box-shadow: none; border: none; padding: 4px 0; background: transparent; }

/* Tabs as pills */
[data-baseweb="tab-list"] { gap: 2px; background: #fff; padding: 5px; border-radius: 12px; border: 1px solid #e3e8f2;
    flex-wrap: wrap; }
[data-baseweb="tab"] { border-radius: 8px !important; padding: 8px 11px !important; height: auto !important;
    transition: none !important; }   /* no fade: the label never shows white-on-white mid-switch (#5) */
[data-baseweb="tab"] p { font-weight: 600; color: #475569; font-size: .875rem; }
/* Keyboard focus, which the custom tab look had removed (#3) */
[data-baseweb="tab"]:focus-visible { outline: 2px solid #4f46e5; outline-offset: 2px; }
[data-baseweb="tab"][aria-selected="true"]:focus-visible { outline: none; box-shadow: 0 0 0 2px #fff, 0 0 0 4px #4f46e5; }
[data-baseweb="tab"][aria-selected="true"] { background: #4f46e5; }
[data-baseweb="tab"][aria-selected="true"] p { color: #fff !important; }
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"] { display: none; }

/* Section headings: 20px with a small solid marker; verdict headlines sit one step above (#7, #13) */
[data-testid="stMain"] [data-testid="stMarkdownContainer"] h4:not([class*="verdict"]) { font-weight: 700; }
[data-testid="stMain"] [data-testid="stHeadingWithActionElements"] h4 { font-size: 1.25rem; padding: 6px 0 10px 0; }
[class*="st-key-verdict_"] [data-testid="stHeadingWithActionElements"] h4 { font-size: 1.375rem; padding-top: 2px; }
[data-testid="stMain"] [data-testid="stHeadingWithActionElements"] h4::before {
    content: ""; display: inline-block; width: 4px; height: 1em; margin-right: 10px; vertical-align: -2px;
    border-radius: 2px; background: #4f46e5; }
[class*="st-key-verdict_"] [data-testid="stHeadingWithActionElements"] h4::before { display: none; }

/* Charts and tables sit on white cards */
[data-testid="stPlotlyChart"], [data-testid="stTable"] { background: #fff; border-radius: 12px; }

/* Buttons */
[data-testid="stMain"] .stButton button, [data-testid="stDownloadButton"] button { font-weight: 600; }


/* Sidebar brand block */
.side-brand { display: flex; align-items: center; gap: 10px; padding: 4px 0 14px 0; margin-bottom: 6px;
              border-bottom: 1px solid #2b3560; }
.side-brand .logo { width: 38px; height: 38px; border-radius: 11px; display: grid; place-items: center; font-size: 20px;
                    background: linear-gradient(135deg, #6366f1, #06b6d4); }
.side-brand b { color: #fff; font-size: 1.02rem; display: block; line-height: 1.2; }
.side-brand span { color: #9aa6c9; font-size: .75rem; }
[data-testid="stSidebar"] h3 { color: #c7d2fe !important; font-size: .8rem !important; text-transform: uppercase;
                               letter-spacing: .06em; margin-top: .4rem; }
.side-label { color: #8b97bf; font-size: .75rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
              margin: 2px 0 4px 4px; }

/* Sidebar menu: full-width rows, the current page highlighted */
[data-testid="stSidebar"] [class*="st-key-nav_"] button { justify-content: flex-start; border: none !important;
    background: transparent; padding: 7px 12px; min-height: 0; border-radius: 8px; }
[data-testid="stSidebar"] [class*="st-key-nav_"] button p { color: #cbd5e1; font-weight: 500; font-size: .95rem; }
[data-testid="stSidebar"] [class*="st-key-nav_"] button:hover { background: rgba(255,255,255,.07); }
[data-testid="stSidebar"] [class*="st-key-nav_"] [data-testid="stBaseButton-primary"] {
    background: rgba(129,140,248,.22) !important; box-shadow: inset 3px 0 0 #a5b4fc; }
[data-testid="stSidebar"] [class*="st-key-nav_"] [data-testid="stBaseButton-primary"] p { color: #ffffff; font-weight: 700; }
[data-testid="stSidebar"] [class*="st-key-nav_"] button:focus-visible { box-shadow: inset 3px 0 0 #a5b4fc, 0 0 0 2px #a5b4fc !important; }
[data-testid="stSidebar"] [class*="st-key-nav_"] { margin-bottom: -10px; }

/* "Home ›" link above page titles */
.st-key-crumb button { min-height: 0; height: 24px; padding: 0 2px; }
.st-key-crumb button p { color: #4f46e5; font-weight: 600; font-size: .875rem; }
.st-key-crumb [data-testid="stMarkdownContainer"] p { margin: 0; }
.crumb-sep { color: #94a3b8; } .crumb-here { color: #64748b; font-size: .875rem; }
.st-key-page_actions { padding-bottom: 6px; }

/* Home page */
.st-key-card_search { background: #fff; border-color: #c7d2fe !important; }
.st-key-card_search h4 { margin-top: 0; }
.pop-label { color: #64748b; font-size: .75rem; font-weight: 600; margin: 6px 0 2px 0; }
.step { display: flex; gap: 12px; align-items: flex-start; }
.step .num { flex: 0 0 30px; height: 30px; border-radius: 50%; background: #eef2ff; color: #4338ca; font-weight: 800;
             display: grid; place-items: center; }
.step b { display: block; color: #0f172a; margin-bottom: 2px; } .step span { color: #64748b; font-size: .875rem; }

/* Quality scorecard cards */
.qgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 12px; margin: 6px 0 4px 0; }
.qcard { background: #fff; border: 1px solid #e3e8f2; border-radius: 12px; padding: 14px 16px; }
.qtop { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.qname { font-weight: 600; color: #475569; font-size: .875rem; }
.qval { font-weight: 700; font-size: 1.25rem; color: #0f172a; margin: 4px 0 6px 0; }
.qmean { color: #475569; font-size: .875rem; line-height: 1.4; }
.qrule { color: #64748b; font-size: .75rem; margin-top: 6px; }   /* 4.8:1 contrast on white (#16) */
.badge { border-radius: 999px; padding: 2px 10px; font-size: .75rem; font-weight: 700; white-space: nowrap; }
.badge.Strong { background: #d1fae5; color: #047857; } .badge.OK { background: #fef3c7; color: #b45309; }
.badge.Weak { background: #ffe4e6; color: #be123c; } .badge.na { background: #f1f5f9; color: #64748b; }

/* Rows of metrics that hold ranges use slightly smaller numbers so they fit */
[class*="st-key-kpis_compact"] [data-testid="stMetricValue"] { font-size: 1.4rem; }

/* Explanation boxes: quiet one-line headings */
[data-testid="stMain"] [data-testid="stExpander"] details { border: none; background: transparent; }
[data-testid="stMain"] [data-testid="stExpander"] summary { padding: 2px 0; min-height: 0; }
[data-testid="stMain"] [data-testid="stExpander"] summary p { color: #4f46e5; font-weight: 600; font-size: .875rem; }

/* Home page cards */
.home-card h4 { margin: 0 0 4px 0; padding: 0; }
.home-card p { color: #64748b; margin: 0; font-size: .875rem; }

/* Phones: a more compact header */
@media (max-width: 640px) {
    .hero { padding: 18px 18px; border-radius: 16px; }
    .hero h1 { font-size: 1.45rem; }
    .hero p { font-size: .9rem; }
    .hero .pill { font-size: .74rem; padding: 2px 9px; }
    .page-head h2 { font-size: 1.5rem; }
}

/* Footer */
.footer { text-align: center; color: #64748b; font-size: .75rem; padding: 10px 0 4px 0; }

/* Shown only on phones, where the assumptions sit behind the collapsed sidebar (#11) */
.mobile-only { display: none; color: #4f46e5; font-weight: 600; font-size: .875rem; margin: 0; }
@media (max-width: 640px) { .mobile-only { display: block; } }
</style>
"""
DARK_CSS = """
<style>
.stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"], [data-testid="stBottomBlockContainer"] { background: #0b1020 !important; }
[data-testid="stMain"] { color: #e2e8f0; }
[data-testid="stMain"] [data-testid="stMarkdownContainer"] p, [data-testid="stMain"] [data-testid="stMarkdownContainer"] li,
[data-testid="stMain"] [data-testid="stMarkdownContainer"] td, [data-testid="stMain"] [data-testid="stMarkdownContainer"] th,
[data-testid="stMain"] label, [data-testid="stMain"] [data-testid="stWidgetLabel"] p { color: #e2e8f0; }
[data-testid="stMain"] h1, [data-testid="stMain"] h2, [data-testid="stMain"] h3, [data-testid="stMain"] h4, .page-head h2 { color: #f8fafc !important; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p, .footer { color: #94a3b8 !important; }
[data-testid="stMetric"], .st-key-card, [class*="st-key-card_"], [class*="st-key-verdict_"], [class*="st-key-scen_"],
[class*="st-key-kpis_"],
[data-baseweb="tab-list"], [data-testid="stPlotlyChart"], [data-testid="stTable"], [data-testid="stExpander"] details,
.qcard { background: #141b34 !important; border-color: #263056 !important; box-shadow: none !important; }
[data-testid="stMetricValue"], [data-testid="stMetricValue"] div { color: #f8fafc !important; }
[data-testid="stMetricLabel"] p { color: #94a3b8 !important; }
[data-testid="stMetricDelta"] { filter: brightness(1.6) saturate(1.2); }
[class*="st-key-verdict_green"]  { background: linear-gradient(135deg, rgba(5,150,105,.22) 0%, #141b34 65%) !important; }
[class*="st-key-verdict_red"]    { background: linear-gradient(135deg, rgba(225,29,72,.20) 0%, #141b34 65%) !important; }
[class*="st-key-verdict_orange"] { background: linear-gradient(135deg, rgba(245,158,11,.20) 0%, #141b34 65%) !important; }
[data-baseweb="tab"] p { color: #cbd5e1; }
[class*="st-key-verdict_green"] .stMarkdownColoredText { color: #34d399 !important; }
[class*="st-key-verdict_red"] .stMarkdownColoredText { color: #fb7185 !important; }
[class*="st-key-verdict_orange"] .stMarkdownColoredText { color: #fbbf24 !important; }
[data-testid="stTable"] table, [data-testid="stTable"] th, [data-testid="stTable"] td { color: #e2e8f0 !important; border-color: #263056 !important; background-color: transparent; }
/* Data grids are drawn on a canvas, so they're darkened with a colour inversion that keeps red and green. */
[data-testid="stDataFrame"], [data-testid="stDataEditor"] { filter: invert(0.9) hue-rotate(180deg); background: #ffffff !important; }
[data-testid="stAlert"] [data-testid="stMarkdownContainer"] p, [data-testid="stAlert"] [data-testid="stMarkdownContainer"] li { color: #dbe2ff !important; }
[data-testid="stMain"] .stButton button, [data-testid="stPopover"] button, [data-testid="stButtonGroup"] button,
[data-testid="stDownloadButton"] button {
    background: #141b34; color: #e2e8f0; border-color: #2f3a66; }
[data-testid="stPopoverBody"] { background: #141b34 !important; color: #e2e8f0; }
[data-testid="stMain"] hr { border-color: #263056; }
.chip.indigo { background: rgba(99,102,241,.18); color: #c7d2fe; border-color: rgba(99,102,241,.35); }
.chip.teal   { background: rgba(20,184,166,.15); color: #99f6e4; border-color: rgba(20,184,166,.3); }
.chip.amber  { background: rgba(245,158,11,.15); color: #fde68a; border-color: rgba(245,158,11,.3); }
.chip.violet { background: rgba(139,92,246,.18); color: #ddd6fe; border-color: rgba(139,92,246,.35); }
.chip.slate  { background: rgba(148,163,184,.15); color: #e2e8f0; border-color: rgba(148,163,184,.3); }
[data-testid="stMain"] [data-testid="stExpander"] summary p { color: #a5b4fc !important; }
.home-card p { color: #94a3b8 !important; }
.st-key-card_search { background: #141b34 !important; border-color: #2f3a66 !important; }
.step b { color: #f8fafc !important; } .step span, .pop-label, .crumb-here { color: #94a3b8 !important; }
.step .num { background: rgba(99,102,241,.25) !important; color: #c7d2fe !important; }
.st-key-crumb button p { color: #a5b4fc !important; }
.qcard .qmean { color: #cbd5e1 !important; }
[class*="st-key-kpis_"] [data-testid="stColumn"] + [data-testid="stColumn"] { border-left-color: #263056 !important; }
[data-testid="stMetric"] { background: transparent !important; }
.mobile-only { color: #a5b4fc !important; } .qcard .qrule { color: #94a3b8 !important; } .qcard .qname, .qcard .qval { color: #f8fafc !important; }
</style>
"""



def chips_html(chips) -> str:
    """[(text, colour)] -> coloured pill labels."""
    return "".join(f'<span class="chip {c}">{html.escape(t)}</span>' for t, c in chips if t)


NAV = [  # (mode code, menu label)
    ("home", "🏠  Home"),
    ("single", "🔎  Value a stock or fund"),
    ("compare", "⚖️  Compare"),
    ("portfolio", "🧺  My portfolio"),
    ("backtest", "🧪  Does the model work?"),
]


def page_head(title: str, chips=()):
    """Page title with a 'Home ›' link above it, so getting back is one click from anywhere."""
    code = {v: k for k, v in MODES.items()}.get(st.session_state.get("mode"), "home")
    section = dict(NAV).get(code, "").split("  ", 1)[-1]
    crumb = st.container(horizontal=True, gap="small", vertical_alignment="center", key="crumb")
    crumb.button("🏠 Home", key="crumb_home", type="tertiary", on_click=open_mode, args=("home",),
                 help="Back to the start page")
    crumb.markdown(f'<span class="crumb-sep">›</span> <span class="crumb-here">{html.escape(section)}</span>',
                   unsafe_allow_html=True)
    left, right = st.columns([3, 1.4], vertical_alignment="bottom")
    left.markdown(f'<div class="page-head"><h2>{html.escape(title)}</h2>{chips_html(chips)}</div>',
                  unsafe_allow_html=True)
    # Download / Share sit on the title row instead of a row of their own; callers fill this slot.
    return right.container(horizontal=True, horizontal_alignment="right", gap="small", key="page_actions")

# --------------------------------------------------------------------------- #
# Ticker list
# --------------------------------------------------------------------------- #

# Tickers offered in the sidebar dropdown. Any other ticker can still be typed in.
TICKERS = {
    # Stocks
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "NVDA": "NVIDIA",
    "GOOGL": "Alphabet (Google)",
    "AMZN": "Amazon",
    "META": "Meta Platforms",
    "TSLA": "Tesla",
    "AZO": "AutoZone",
    "JPM": "JPMorgan Chase (bank)",
    "V": "Visa",
    "KO": "Coca-Cola",
    "COST": "Costco",
    "WMT": "Walmart",
    "JNJ": "Johnson & Johnson",
    "NKE": "Nike",
    # Index funds
    "VOO": "Vanguard S&P 500 ETF",
    "SPY": "SPDR S&P 500 ETF",
    "VTI": "Vanguard Total Stock Market ETF",
    "QQQ": "Invesco QQQ (Nasdaq-100)",
    "VFIAX": "Vanguard 500 Index (mutual fund)",
    "SCHD": "Schwab U.S. Dividend Equity ETF",
    "VXUS": "Vanguard Total International Stock ETF",
    "BND": "Vanguard Total Bond Market ETF",
}
FUND_TICKERS = {"VOO", "SPY", "VTI", "QQQ", "VFIAX", "SCHD", "VXUS", "BND"}

seed_from_url()
st.markdown(CSS, unsafe_allow_html=True)
if is_dark():
    st.markdown(DARK_CSS, unsafe_allow_html=True)

BLUE = "#4f46e5"      # indigo: the app's main colour
GREY = "#94a3b8"
AMBER = "#f59e0b"
TEAL = "#0d9488"
RED = "#e11d48"
BLUE_FILL = "rgba(79,70,229,{a})"
GREEN_BG = "background-color: rgba(5,150,105,0.20)"
RED_BG = "background-color: rgba(225,29,72,0.16)"
CURRENT_CELL = "font-weight: 800; outline: 3px solid #4f46e5; outline-offset: -3px"
NO_TOOLBAR = {"displayModeBar": False}
SCENARIO_ICONS = {"Pessimistic": "🌧️", "Middle (your settings)": "⛅", "Optimistic": "☀️"}
TRADING_DAYS_1Y = 252


def ticker_label(t: str) -> str:
    t = (t or "").upper()
    if t not in TICKERS:
        return t
    kind = "Fund" if t in FUND_TICKERS else "Stock"
    return f"{t} · {TICKERS[t]} ({kind})"


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #

def money(x: float) -> str:
    """$1.85B / $15,400 / $85.20: cents only on amounts under $1,000."""
    sign = "-" if x < 0 else ""
    x = abs(x)
    for unit, div in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if x >= div:
            return f"{sign}${x / div:,.2f}{unit}"
    return f"{sign}${x:,.0f}" if x >= 1000 else f"{sign}${x:,.2f}"


def pct(x, digits: int = 1) -> str:
    return "n/a" if x is None or pd.isna(x) else f"{x:.{digits}%}"


def esc(s: str) -> str:
    """Escape $ so Streamlit doesn't read $...$ as a math formula."""
    return s.replace("$", r"\$")


def scale_for(values) -> tuple:
    """Pick billions or millions for chart axes so labels read '$2.0B', not '$2.0G'."""
    biggest = max((abs(v) for v in values if pd.notna(v)), default=0)
    if biggest >= 1e12:
        return 1e12, "T"
    return (1e9, "B") if biggest >= 1e9 else (1e6, "M")


def explain(text: str, label: str = "What does this mean?") -> None:
    """A beginner explanation, folded away under a one-line heading until clicked."""
    with st.expander(f"💡 {label}"):
        st.markdown(esc(text))


def chart_layout(fig: go.Figure, height: int = 380, **kw) -> go.Figure:
    layout = dict(
        height=height,
        font=dict(family="Inter, sans-serif", color="#cbd5e1" if is_dark() else "#334155"),
        paper_bgcolor="#141b34" if is_dark() else "#ffffff", plot_bgcolor="#141b34" if is_dark() else "#ffffff",
        xaxis=dict(gridcolor="#263056" if is_dark() else "#eef1f6"), yaxis=dict(gridcolor="#263056" if is_dark() else "#eef1f6"),
        hoverlabel=dict(font=dict(family="Inter, sans-serif")),
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", y=-0.18, x=0),
        hovermode="x unified",
    )
    text = "#cbd5e1" if is_dark() else "#334155"
    layout["legend"]["font"] = dict(color=text)
    for axis in ("xaxis", "yaxis"):
        layout[axis].update(tickfont=dict(color=text), title=dict(font=dict(color=text)))
    for part in ("xaxis", "yaxis", "legend"):  # merge so callers keep the colours above
        if part in kw:
            extra = dict(kw[part])
            if isinstance(extra.get("title"), str):
                extra["title"] = dict(text=extra["title"], font=dict(color=text))
            kw[part] = {**layout[part], **extra}
    layout.update(kw)  # callers can override any default
    fig.update_layout(**layout)
    zero = "#33406e" if is_dark() else "#e3e8f2"
    fig.update_xaxes(zerolinecolor=zero)
    fig.update_yaxes(zerolinecolor=zero)
    return fig


def show(fig: go.Figure) -> None:
    st.plotly_chart(fig, config=NO_TOOLBAR)


# --------------------------------------------------------------------------- #
# Data access (disk-cached in dcf.loader; memory-cached here for speed)
# --------------------------------------------------------------------------- #

@st.cache_data(ttl=3600, show_spinner=False)
def fetch(ticker: str):
    return load(ticker)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_history(ticker: str) -> pd.Series:
    try:
        return price_history(ticker)
    except Exception:
        return pd.Series(dtype=float)


def refresh_data(ticker: str) -> None:
    load(ticker, refresh=True)
    price_history(ticker, refresh=True)
    fetch.clear()
    fetch_history.clear()


def reset_assumptions(ticker: str) -> None:
    for k in [k for k in st.session_state if k.endswith(f"__{ticker}")]:
        del st.session_state[k]


def apply_values(values: dict) -> None:
    """Button callback: put scenario values into the sidebar sliders."""
    for key, v in values.items():
        st.session_state[key] = v


def pct_slider(label: str, lo: float, hi: float, default: float, step: float, key: str, help: str) -> float:
    """A slider shown in percent (e.g. 5.0%) that returns a fraction (0.05)."""
    # The value lives only in session state (seeded with the default the first time). Never passing `value=`
    # keeps the slider's identity stable across reruns and lets scenario buttons set it without warnings.
    if key not in st.session_state:
        st.session_state[key] = float(round(min(max(default * 100, lo), hi), 2))
    elif not lo <= st.session_state[key] <= hi:
        st.session_state[key] = float(min(max(st.session_state[key], lo), hi))
    return st.slider(label, lo, hi, step=step, format="%.1f%%", key=key, help=help) / 100


def slider_value(frac: float, lo: float, hi: float, step: float) -> float:
    """Convert a fraction to a slider value in percent, rounded to the slider's step."""
    v = round(frac * 100 / step) * step
    return float(min(max(v, lo), hi))


# --------------------------------------------------------------------------- #
# Shared page pieces
# --------------------------------------------------------------------------- #

def verdict_box(name: str, value: float, price: float, upside: float, noun: str, extra: str = "",
                caveats=()) -> None:
    if upside > 0.15:
        tone, color = "looks **undervalued**", "green"
    elif upside < -0.15:
        # With a known blind spot the honest claim is about the model, not the stock.
        tone, color = ("is priced **well above** this model's estimate" if caveats else "looks **overvalued**"), "red"
    else:
        tone, color = "looks **roughly fairly priced**", "orange"
    # Phrase it the same way as the "Gap vs. price" metric (value / price - 1) so the numbers match.
    if abs(upside) < 0.005:
        where = "almost exactly the same as"
    else:
        where = f"{abs(upside):.0%} {'above' if upside > 0 else 'below'}"
    with st.container(border=True, key=f"verdict_{color}"):
        st.markdown(
            esc(
                f"#### :{color}[{name} {tone}]\n"
                f"Based on your assumptions, the model estimates it's worth **${value:,.2f}** per {noun}, "
                f"{where} today's price of **${price:,.2f}**.\n\n{extra}"
            ),
            help="This is what the math says given the assumptions in the sidebar, not a prediction of where the "
                 "price will go. Change the assumptions and the answer changes.",
        )
        if caveats:
            # Known blind spots of a simple cash-flow model: say so instead of letting a low number speak alone.
            labels = " · ".join(label for label, _ in caveats)
            with st.expander(f"⚠️ This estimate is probably too low here ({labels}). Why?"):
                st.markdown(esc("\n\n".join(f"**{label.capitalize()}.** {text}" for label, text in caveats)))
        st.markdown('<p class="mobile-only">Tap » at the top left to change the assumptions.</p>',
                    unsafe_allow_html=True)


def priced_in_sentence(g: float, mine: float, years: int, terminal: float, what: str) -> str:
    if pd.isna(g):
        return (f"🔎 **What's priced in:** no growth rate between −50% and +100% a year would justify today's price "
                "with these settings.")
    compare = "faster than" if g > mine + 0.005 else ("slower than" if g < mine - 0.005 else "about the same as")
    return (
        f"🔎 **What's priced in:** to justify today's price, {what} would need to grow about **{g:.1%} a year** "
        f"for the next {years} years (then {terminal:.1%} after). That's {compare} the {mine:.1%} you're assuming."
    )


def warnings_box(warnings) -> None:
    for w in warnings:
        st.warning(esc(w), icon="⚠️")


def download_button(tables, ticker: str, row=None) -> None:
    """The Excel download and the share link, side by side (in the title row when given)."""
    row = row if row is not None else st.container(horizontal=True, gap="small")
    try:
        data = to_xlsx(tables)
    except Exception as e:  # never break the page over an export problem
        with row:
            share_button()
        st.caption(f"Report download unavailable: {e}")
        return
    row.download_button(
        "⬇️ Excel report",
        data=data,
        file_name=f"{ticker}-valuation-{date.today().isoformat()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        help="A spreadsheet with the summary, assumptions, forecast, scenarios, what-if grid and past data.",
    )
    with row:
        share_button()


def sensitivity_view(sens: pd.DataFrame, price: float, rows_label: str, rows_explain: str) -> None:
    n_rows, n_cols = sens.shape
    mid_r, mid_c = n_rows // 2, n_cols // 2

    def styles(df: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame("", index=df.index, columns=df.columns)
        for i in range(n_rows):
            for j in range(n_cols):
                v = df.iat[i, j]
                css = "" if pd.isna(v) or not price else (GREEN_BG if v >= price else RED_BG)
                if i == mid_r and j == mid_c:
                    css += "; " + CURRENT_CELL
                out.iat[i, j] = css
        return out

    shown = sens.copy()
    shown.index = [f"{rows_label} {r}" for r in shown.index]
    shown.columns = [f"Growth {c}" for c in shown.columns]
    style = shown.style.format(lambda v: "—" if pd.isna(v) else f"${v:,.0f}").apply(styles, axis=None)
    st.table(style)
    st.caption(
        esc(f"🟩 green = worth more than today's price (${price:,.2f})  ·  🟥 red = worth less  ·  "
            "outlined cell = your current assumptions")
    )
    explain(
        "**What this shows:** the same valuation repeated with different assumptions, so you can see how much "
        f"the answer depends on them. Each row uses a different {rows_explain}; each column uses a different "
        "long-term growth rate (how fast it grows after the forecast period, forever).\n\n"
        "**How to read it:** start at the outlined cell (your current settings). Moving **down** a row "
        "(a higher required return) makes the value **fall**; moving **right** (faster long-term growth) makes it "
        "**rise**. If most of the grid is green, it looks cheap under most reasonable assumptions; if most "
        "is red, it looks expensive. A mixed grid means the verdict depends heavily on what you assume."
    )


def scenario_cards(table: pd.DataFrame, price: float, rate_label: str, apply_keys) -> None:
    """Three cards (pessimistic / middle / optimistic), each with a button that loads it into the sliders.

    apply_keys(row) returns {session_state_key: slider_value} for that scenario.
    """
    cols = st.columns(3)
    for i, (col, (name, row)) in enumerate(zip(cols, table.iterrows())):
        with col, st.container(border=True, key=f"scen_{i}"):
            st.markdown(f"**{SCENARIO_ICONS.get(name, '')} {name}**")
            st.metric("Value / share", f"${row['Value / share']:,.2f}", delta=f"{row['Gap vs. price']:+.1%} vs. price")
            lines = (f"Growth next year **{row['Growth next year']:.1%}**  \n"
                     f"Long-term growth **{row['Long-term growth']:.1%}**  \n"
                     f"{rate_label} **{row['Required return']:.1%}**")
            if "Expected yearly return" in row:
                lines += f"  \nExpected return **{pct(row['Expected yearly return'])}**"
            st.markdown(lines)
            if not name.startswith("Middle"):
                st.button(f"Use {name.lower()} settings", key=f"use_{name}", on_click=apply_values,
                          args=(apply_keys(row),), width="stretch")
    explain(
        "**What this shows:** instead of one precise-looking number, three versions of the estimate.\n\n"
        "- **Pessimistic:** slower growth and a higher required return, as if things go worse than expected.\n"
        "- **Middle:** your current sidebar settings.\n"
        "- **Optimistic:** faster growth and a lower required return.\n\n"
        "If today's price sits between the pessimistic and optimistic values, the market is pricing in an outcome "
        "within a reasonable range. Press **Use … settings** to load a scenario into the sliders. Scenarios are "
        "always built around your *current* settings, so after loading one the other two shift around it; "
        "press **↺ Reset to defaults** in the sidebar to start over."
    )


def price_chart(ticker: str, price: float, scen: pd.DataFrame, noun: str) -> None:
    hist = fetch_history(ticker)
    st.markdown("#### Price over the last 5 years vs. the estimate")
    if hist is None or hist.empty:
        st.caption("Price history isn't available for this ticker.")
        return
    lo = float(scen["Value / share"].iloc[0])
    mid = float(scen["Value / share"].iloc[1])
    hi = float(scen["Value / share"].iloc[2])
    fig = go.Figure()
    x0, x1 = hist.index.min(), hist.index.max()
    fig.add_shape(type="rect", x0=x0, x1=x1, y0=min(lo, hi), y1=max(lo, hi),
                  fillcolor=BLUE_FILL.format(a=0.10), line_width=0, layer="below")
    fig.add_scatter(x=hist.index, y=hist.values, name="Share price", mode="lines", line=dict(color=GREY, width=2))
    fig.add_scatter(x=[x0, x1], y=[mid, mid], name="Estimated value (your settings)", mode="lines",
                    line=dict(color=BLUE, width=3, dash="dash"))
    fig.add_scatter(x=[x0, x1], y=[lo, lo], name="Pessimistic", mode="lines",
                    line=dict(color=RED, width=1, dash="dot"))
    fig.add_scatter(x=[x0, x1], y=[hi, hi], name="Optimistic", mode="lines",
                    line=dict(color=TEAL, width=1, dash="dot"))
    top = max(float(hist.max()), hi, mid) * 1.08
    chart_layout(fig, height=380, yaxis=dict(tickprefix="$", tickformat=",.0f", range=[0, top]))
    show(fig)
    first = float(hist.iloc[0])
    change = price / first - 1 if first else float("nan")
    explain(
        f"**What this shows:** the {noun} price over the last 5 years (grey line) compared with today's estimate "
        "(blue dashed line). The shaded band runs from the pessimistic to the optimistic scenario.\n\n"
        f"**How to read it:** over this period the price changed by **{pct(change, 0)}**. When the grey line is above "
        "the band, the market was paying more than even the optimistic scenario suggests; below it, less than "
        "the pessimistic one. The estimate is a single line because it uses today's data; it doesn't show what "
        "the model would have said in past years."
    )


def data_freshness(ticker: str) -> None:
    age = data_age_hours(ticker)
    with st.sidebar:
        if age is not None:
            when = "less than an hour ago" if age < 1 else f"{age:.0f} hours ago"
            st.caption(f"Data downloaded {when}. Saved data is reused for up to 12 hours.")
        st.button("🔄 Download fresh data", on_click=refresh_data, args=(ticker,), width="stretch",
                  help="Ignore the saved copy and download the latest numbers from Yahoo Finance.")


# --------------------------------------------------------------------------- #
# Stocks
# --------------------------------------------------------------------------- #

SCENARIO_COLORS = {"Pessimistic": RED, "Middle (your settings)": BLUE, "Optimistic": TEAL}


def _chg(o: PriceOutlook, p: float) -> str:
    c = o.change(p)
    return "n/a" if pd.isna(c) else f"{c:+.0%}"


def outlook_tab(data, a, ticker: str, noun: str) -> None:
    """The 🎯 Price outlook tab: typical swings, model fair value and analyst targets at a chosen horizon."""
    is_fund = isinstance(data, FundData)
    st.markdown("#### Where could the price be?")
    years = st.radio("Look ahead", [1, 3, 5], format_func=lambda y: f"{y} year{'s' if y > 1 else ''}",
                     horizontal=True, key=f"horizon__{ticker}")
    prices = fetch_history(ticker)
    o = fund_outlook(data, a, prices, years) if is_fund else company_outlook(data, a, prices, years)
    when = "in 1 year" if years == 1 else f"in {years} years"
    m = "Middle (your settings)"

    # ---- Plain-English summary ---------------------------------------------
    parts = []
    if o.has_volatility:
        div_note = f", minus its {o.dividend_yield:.1%} dividend" if o.dividend_yield >= 0.001 else ""
        parts.append(
            f"📊 **Typical swings.** Over the last year, {data.ticker} moved about **±{o.volatility:.0%} a year**. "
            f"If it earns a normal return ({o.expected_return:.1%} a year{div_note}), the middle of the range {when} is "
            f"**${o.center:,.2f}** ({_chg(o, o.center)}). In about **2 out of 3** outcomes the price would land between "
            f"**${o.likely[0]:,.2f}** and **${o.likely[1]:,.2f}** ({_chg(o, o.likely[0])} to {_chg(o, o.likely[1])}); "
            f"in about **19 out of 20**, between **${o.wide[0]:,.2f}** and **${o.wide[1]:,.2f}**."
        )
    else:
        parts.append("📊 **Typical swings:** not enough price history to measure how much this one usually moves.")
    if m in o.fair_future:
        lo, hi = o.fair_future.get("Pessimistic"), o.fair_future.get("Optimistic")
        rng = f", with a range of **${lo:,.2f}** (pessimistic) to **${hi:,.2f}** (optimistic)" if lo and hi else ""
        parts.append(
            f"🧮 **Model fair value.** If the price moved to the model's estimate, it would be about "
            f"**${o.fair_future[m]:,.2f}** {when} ({_chg(o, o.fair_future[m])}){rng}."
        )
    else:
        parts.append("🧮 **Model fair value:** not available, because the model can't value this one "
                     "(see the note at the top of the page).")
    if o.analysts:
        an = o.analysts
        who = f"{an['count']} analysts'" if an.get("count") else "Analysts'"
        rating = f" Their overall rating: **{an['recommendation']}**." if an.get("recommendation") else ""
        parts.append(
            f"🏦 **Analysts.** {who} average 12-month target is **${an['mean']:,.2f}** ({_chg(o, an['mean'])}), "
            f"ranging from **${an['low']:,.2f}** to **${an['high']:,.2f}**.{rating}"
        )
    elif not is_fund:
        parts.append("🏦 **Analysts:** Yahoo Finance has no analyst price targets for this stock.")
    with st.container(border=True, key="card_outlook"):
        st.markdown(esc(f"Today's price: **${o.price:,.2f}** per {noun}.\n\n" + "\n\n".join(parts)))

    # ---- Fan chart -----------------------------------------------------------
    hist = prices.iloc[-TRADING_DAYS_1Y:] if prices is not None and not prices.empty else pd.Series(dtype=float)
    start = hist.index[-1] if not hist.empty else pd.Timestamp.today().normalize()
    end = start + pd.DateOffset(years=years)
    fig = go.Figure()
    if o.has_volatility:
        path = cone_path(o.price, o.expected_return, o.dividend_yield, o.volatility, years, start=start)
        fig.add_scatter(x=path.index, y=path["wide_high"], mode="lines", line=dict(width=0),
                        showlegend=False, hoverinfo="skip")
        fig.add_scatter(x=path.index, y=path["wide_low"], mode="lines", line=dict(width=0), fill="tonexty",
                        fillcolor=BLUE_FILL.format(a=0.10), name="Wide range (19 in 20)", hoverinfo="skip")
        fig.add_scatter(x=path.index, y=path["likely_high"], mode="lines", line=dict(width=0),
                        showlegend=False, hoverinfo="skip")
        fig.add_scatter(x=path.index, y=path["likely_low"], mode="lines", line=dict(width=0), fill="tonexty",
                        fillcolor=BLUE_FILL.format(a=0.25), name="Likely range (2 in 3)", hoverinfo="skip")
        fig.add_scatter(x=path.index, y=path["center"], mode="lines", name="Middle (normal return)",
                        line=dict(color=BLUE, dash="dash", width=2))
    if not hist.empty:
        fig.add_scatter(x=hist.index, y=hist.values, mode="lines", name="Price (last 12 months)",
                        line=dict(color=GREY, width=2))
    for name, v in o.fair_future.items():
        fig.add_scatter(x=[end], y=[v], mode="markers+text", name=f"Model: {name.split(' (')[0].lower()}",
                        marker=dict(color=SCENARIO_COLORS.get(name, BLUE), size=12, symbol="circle"),
                        text=[f"${v:,.0f}"], textposition="middle right", cliponaxis=False)
    if o.analysts:
        an = o.analysts
        # Targets are for 12 months. On the 1-year view, nudge the diamond left so it doesn't hide the model's dots.
        x_an = start + pd.DateOffset(years=1) - (pd.DateOffset(days=25) if years == 1 else pd.DateOffset(days=0))
        fig.add_scatter(
            x=[x_an], y=[an["mean"]], mode="markers", name="Analysts' targets (low–high)",
            marker=dict(color=AMBER, size=13, symbol="diamond"),
            error_y=dict(type="data", array=[an["high"] - an["mean"]], arrayminus=[an["mean"] - an["low"]],
                         color=AMBER, thickness=2, width=10),
        )
    chart_layout(fig, height=440, hovermode="closest",
                 yaxis=dict(tickprefix="$", tickformat=",.0f", rangemode="tozero"),
                 xaxis=dict(range=[hist.index[0] if not hist.empty else start, end + pd.DateOffset(months=3)]),
                 legend=dict(orientation="h", y=-0.15, x=0))
    show(fig)
    explain(
        "**How to read this chart:**\n"
        "- The **grey line** is the actual price over the last 12 months.\n"
        "- The **blue fan** shows how far the price could typically wander from here, based on how much it has "
        "moved in the past year. The darker band holds about 2 out of 3 outcomes, the lighter band about 19 out "
        "of 20. It widens over time because uncertainty builds up, and it's lopsided (more room up than down) "
        "because prices can rise without limit but can't fall below zero.\n"
        "- The **dots** on the right are the model's fair value at the end of the period (red pessimistic, "
        "blue middle, green optimistic): where the price would be if the market agreed with the model.\n"
        "- The **amber diamond** is the analysts' average 12-month target, with a line from the lowest to the "
        "highest target."
    )

    # ---- Upside / downside table ---------------------------------------------
    st.markdown(f"#### Upside and downside {when}")
    t = o.table().reset_index()
    if not t.empty:
        t["Change vs. today"] = t["Change vs. today"] * 100
        t["Yearly return incl. dividends"] = t["Yearly return incl. dividends"] * 100

        def tint(v):
            if pd.isna(v):
                return ""
            return "color: #059669; font-weight: 600" if v >= 0 else "color: #e11d48; font-weight: 600"

        style = t.style.format({
            "Price": "${:,.2f}", "Change vs. today": "{:+.1f}%", "Yearly return incl. dividends": "{:+.1f}%",
        }, na_rep="n/a")
        style = style.map(tint, subset=["Change vs. today", "Yearly return incl. dividends"]) if hasattr(style, "map") \
            else style.applymap(tint, subset=["Change vs. today", "Yearly return incl. dividends"])
        st.dataframe(style, hide_index=True, width="stretch", height=36 * (len(t) + 1) + 4)  # show every row
    explain(
        "**What the columns mean:**\n"
        f"- **Price:** where the price would be {when} in that outcome.\n"
        "- **Change vs. today:** the upside (green) or downside (red) from today's price.\n"
        "- **Yearly return incl. dividends:** the same change spread over the period as an average yearly return, "
        "plus any dividends you'd collect along the way (analyst targets always cover 12 months).\n\n"
        "**How the three lenses fit together:** *typical swings* show the realistic range of outcomes for a stock "
        "that behaves like it has recently; *model fair value* shows where the price would be if the market came "
        "round to the model's view; *analysts* show what Wall Street expects. When they point in different "
        "directions, as they often do, that's a sign of genuine uncertainty, not a mistake."
    )
    st.caption(
        "These are ranges and reference points, not predictions. Prices can move outside even the wide range, "
        "especially around big news, earnings surprises or market crashes. Not investment advice."
    )


HISTORY_NAMES = {
    "Revenue": "Sales (revenue)",
    "Operating cash flow": "Cash from operations",
    "Capex": "Spent on equipment (capex)",
    "Free cash flow": "Free cash flow",
    "Dividends": "Dividends paid",
    "Buybacks": "Shares bought back",
    "Cash returned to shareholders": "Cash returned to shareholders",
}


def company_data_tab(c, base_amount=None) -> None:
    st.markdown("#### Company snapshot")
    st.caption(f"{c.sector} · {c.industry}" if c.sector else "")
    s1, s2, s3 = kpi_row(3, "snap1")
    s1.metric("Market value (market cap)", money(c.market_cap),
              help="Share price × number of shares: what the stock market says the whole company is worth.")
    s2.metric("Debt minus cash", money(c.net_debt),
              help="What the company owes, minus the cash it holds. Subtracted from the business value "
                   "(except for banks, where it's part of normal business).")
    s3.metric("Shares", f"{c.shares_outstanding / 1e6:,.1f}M", help="How many pieces the company is divided into.")
    s4, s5, s6 = kpi_row(3, "snap2")
    s4.metric("Beta", f"{c.beta:.2f}",
              help="How much the stock swings compared with the overall market. 1.0 = same as the market; "
                   "higher = bumpier, which raises the required return.")
    s5.metric("P/E ratio", f"{c.pe:.1f}" if c.pe else "n/a",
              help="Share price ÷ yearly profit per share: how many dollars you pay for $1 of profit.")
    s6.metric("Analysts' growth forecast", pct(c.analyst_growth),
              help="Analysts' consensus estimate of next year's earnings growth, from Yahoo Finance.")

    st.markdown("#### Past financials")
    src = getattr(c, "statements_source", "Yahoo Finance")
    st.caption(f"Yearly figures from {src}" + (" (the company's own filings with the SEC)" if src == "SEC EDGAR" else "")
               + ". Share price, debt and cash from Yahoo Finance.")
    h = c.history().rename(columns=HISTORY_NAMES)
    st.dataframe(h.style.format(lambda v: "n/a" if pd.isna(v) else money(v)), width="stretch")
    text = (
        "**What these mean:**\n"
        "- **Sales (revenue):** everything customers paid the company that year.\n"
        "- **Cash from operations:** cash that came in from running the business, after paying staff, suppliers, "
        "rent and so on.\n"
        "- **Spent on equipment (capex):** money spent on stores, factories, computers and other long-lasting "
        "things. It's shown as negative because it's money going out.\n"
        "- **Free cash flow:** cash from operations minus capex, i.e. what's left over for owners."
    )
    if c.is_financial:
        text += (
            "\n- **Dividends paid / shares bought back:** cash handed to shareholders directly, or by buying back "
            "shares (which gives each remaining share a bigger slice of the company).\n"
            "- **Cash returned to shareholders:** the two added together. For a bank this is the number the "
            "valuation uses, because its free cash flow swings with deposits and loans."
        )
    explain(text)


# --------------------------------------------------------------------------- #
# Reverse DCF
# --------------------------------------------------------------------------- #

def _rates_around(rate: float, floor: float) -> list:
    """Required returns 2 points either side of the user's, kept above long-term growth."""
    return [round(rate + d, 4) for d in (-0.02, -0.01, 0.0, 0.01, 0.02) if rate + d > floor + 0.005]


def reverse_verdict(g: float, ref: float, what: str, caption: str) -> None:
    head, color, text = demand_level(g, ref, what)
    with st.container(border=True, key=f"verdict_{color}_reverse"):
        st.markdown(esc(f"#### :{color}[{head}]\n{text}"))
        st.caption(esc(caption))


def growth_bars(rows: list, title: str) -> None:
    """Horizontal bars: [(label, value, colour)], to set the growth priced in against reality checks."""
    rows = [r for r in rows if r[1] is not None and pd.notna(r[1])]
    if not rows:
        return
    st.markdown(f"#### {title}")
    labels = [r[0] for r in rows][::-1]
    values = [r[1] * 100 for r in rows][::-1]
    colors = [r[2] for r in rows][::-1]
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h", marker_color=colors,
        text=[f"{v:+.1f}%" for v in values], textposition="outside", cliponaxis=False,
        hovertemplate="%{y}: %{x:.1f}% a year<extra></extra>",
    ))
    lo, hi = min(values + [0]), max(values + [0])
    pad = max(hi - lo, 5) * 0.18
    chart_layout(fig, height=70 + 52 * len(rows), showlegend=False, hovermode="closest",
                 xaxis=dict(ticksuffix="%", range=[lo - (pad if lo < 0 else 0), hi + pad], zeroline=True),
                 # Size the label margin from the text: Plotly measures labels before the web font loads.
                 yaxis=dict(automargin=False, ticksuffix="  "),
                 margin=dict(l=int(7.2 * max(len(t) for t in labels)) + 24, r=30, t=10, b=10))
    show(fig)


def implied_grid_view(grid: pd.DataFrame, ref: float, cur_rate: float, cur_years: int, rate_word: str) -> None:
    """Table of growth priced in, coloured by how it compares with the realistic yardstick."""
    def cell_style(v: float) -> str:
        if pd.isna(v):
            return ""
        if v > ref + 0.02:
            return RED_BG
        if v < ref - 0.02:
            return GREEN_BG
        return "background-color: rgba(245,158,11,0.22)"

    def styles(df: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame("", index=df.index, columns=df.columns)
        for i, rate in enumerate(grid.index):
            for j, yrs in enumerate(grid.columns):
                css = cell_style(df.iat[i, j])
                if abs(rate - cur_rate) < 1e-6 and yrs == cur_years:
                    css += "; " + CURRENT_CELL
                out.iat[i, j] = css
        return out

    shown = grid.copy()
    shown.index = [f"{rate_word} {r:.1%}" for r in grid.index]
    shown.columns = [f"Over {n} years" for n in grid.columns]
    st.table(shown.style.format(lambda v: "—" if pd.isna(v) else f"{v:.1%}").apply(styles, axis=None))
    ref_txt = "n/a" if pd.isna(ref) else f"{ref:.1%}"
    st.caption(f"🟩 below the yardstick ({ref_txt})  ·  🟧 close to it  ·  🟥 above it  ·  outlined cell = your settings")


def reverse_tab_stock(c, a, g_implied: float, cash_name: str, rate_name: str) -> None:
    rate_short = rate_name.split(" (")[0].lower()
    st.markdown("#### Working backwards from today's price")
    explain(
        "**What a reverse DCF is:** the rest of the app goes *assumptions → value*: you choose growth and a required "
        "return, and it works out what the stock is worth. A reverse DCF flips that around: it starts from **today's "
        "price** and asks *what would you have to believe for that price to be fair?*\n\n"
        "That's often more useful, because nobody knows the right growth rate, but you can judge whether the "
        "growth the market is betting on looks realistic compared with what the company has actually done."
    )
    r_implied = implied_discount_rate(c, a)
    ref = reference_growth(c)
    bench = growth_benchmarks(c)
    reverse_verdict(
        g_implied, ref, "the company",
        f"Yardstick = average of past sales growth and analysts' forecast. Uses your {rate_short} of {a.wacc:.1%}, "
        f"{a.years} forecast years and {a.terminal_growth:.1%} long-term growth; change them in the sidebar.",
    )

    m1, m2, m3, m4 = kpi_row(4, "row1")
    m1.metric("Growth priced in", pct(g_implied),
              help=f"The steady yearly growth in {cash_name} for the next {a.years} years that makes the estimate "
                   "equal today's price.")
    m2.metric("Your growth assumption", pct(a.growth_rate),
              delta=(f"{a.growth_rate - g_implied:+.1%} vs. priced in" if pd.notna(g_implied) else None),
              help="Your 'Growth next year' slider. Positive = you expect more than the price needs.")
    m3.metric("Return priced in", pct(r_implied),
              delta=(f"{r_implied - a.wacc:+.1%} vs. your {rate_short.split()[0]}" if pd.notna(r_implied) else None),
              help="The yearly return you'd earn buying at today's price if your growth assumptions come true. "
                   f"Higher than your {rate_short} = the stock looks cheap on your assumptions.")
    m4.metric("Realistic yardstick", pct(ref),
              help="Average of the company's past sales growth and analysts' forecast for next year.")

    rows = [("Priced in by today's price", g_implied, BLUE), ("Your assumption", a.growth_rate, "#7c3aed")]
    rows += [(k, v, TEAL if k.startswith("Analysts") else GREY) for k, v in bench.items()]
    growth_bars(rows, "Growth priced in vs. reality checks")
    explain(
        "**How to read it:** the **indigo bar** is the growth the market is betting on. The other bars are reality "
        "checks: what you assume, how fast sales and cash flow actually grew over the past few years, and what "
        "analysts expect next year. If the indigo bar is much longer than all of them, the price needs the company "
        "to beat its own record. If it's shorter, the price asks for less than the company has been delivering."
    )

    path = needed_path(c, a, g_implied)
    if path:
        start = base_cash(c, a.base)
        hist_years = c.years
        proj_years = ([str(int(hist_years[-1]) + i) for i in range(1, a.years + 1)]
                      if hist_years else [f"Year {i}" for i in range(1, a.years + 1)])
        mine = run_dcf(c, a).projected_fcf
        div, unit = scale_for(list(c.valuation_cash_flow) + path + mine)
        st.markdown(f"#### The {cash_name} today's price is counting on")
        fig = go.Figure()
        fig.add_bar(x=hist_years, y=[v / div for v in c.valuation_cash_flow], name="Actual (past)", marker_color=GREY)
        fig.add_bar(x=proj_years, y=[v / div for v in path], name="Needed to justify the price", marker_color=BLUE)
        fig.add_scatter(x=proj_years, y=[v / div for v in mine], name="Your forecast", mode="lines+markers",
                        line=dict(color=TEAL, width=3))
        chart_layout(fig, yaxis=dict(ticksuffix=unit, tickprefix="$"))
        show(fig)
        st.markdown(esc(
            f"To justify **${c.price:,.2f}** a share, {cash_name} would need to reach **{money(path[-1])}** by "
            f"{proj_years[-1]}: **{path[-1] / start:.1f}×** the starting point of {money(start)}, and then keep "
            f"growing {a.terminal_growth:.1%} a year after that."
        ))
        explain(
            "**What this shows:** grey bars are what the company actually produced. **Indigo bars** are what it "
            "would need to produce, growing at the rate priced in, for today's price to be fair. The **teal line** "
            "is your own forecast from the sidebar. Where the teal line is above the indigo bars, you expect more "
            "than the price needs; below them, less."
        )

    st.markdown("#### Growth priced in for other required returns and time frames")
    years_list = sorted({5, 10, 15, a.years})
    grid = implied_growth_grid(c, a, _rates_around(a.wacc, a.terminal_growth), years_list)
    implied_grid_view(grid, ref, a.wacc, a.years, "Return")
    explain(
        "**How to read the table:** each cell is the steady yearly growth the price needs, for a different "
        f"{rate_short} (rows) and forecast length (columns).\n\n"
        "- Moving **down** (a higher required return) makes the price harder to justify, so the growth needed rises.\n"
        "- Moving **right** (more years of growth before slowing down) spreads the effort out, so the yearly growth "
        "needed falls.\n\n"
        "If most cells are red, the price looks demanding whatever reasonable return you pick; if most are green, "
        "it asks for less than the company's record."
    )


def reverse_tab_fund(f, a, r, g_implied: float) -> None:
    st.markdown("#### Working backwards from today's price")
    explain(
        "**What a reverse valuation is:** instead of choosing assumptions and working out what the fund is worth, "
        "it starts from **today's price** and asks *what would the fund's companies have to achieve for that price "
        "to be fair?* For a broad index fund, the key question is how fast the combined profits of all its "
        "companies must grow."
    )
    ref = LONG_RUN_EARNINGS_GROWTH
    reverse_verdict(
        g_implied, ref, "the fund",
        f"Yardstick = roughly {ref:.0%} a year, the long-run earnings growth of large US companies (including "
        f"inflation). Uses your required return of {a.required_return:.1%} and {a.years} forecast years.",
    )
    m1, m2, m3, m4 = kpi_row(4, "row2")
    m1.metric("Earnings growth priced in", pct(g_implied),
              help=f"The steady yearly profit growth for the next {a.years} years that makes the estimate equal today's price.")
    m2.metric("Your growth assumption", pct(a.growth_rate),
              delta=(f"{a.growth_rate - g_implied:+.1%} vs. priced in" if pd.notna(g_implied) else None))
    m3.metric("Return priced in", pct(r.implied_return),
              delta=(f"{r.implied_return - a.required_return:+.1%} vs. your target" if pd.notna(r.implied_return) else None),
              help="The yearly return you'd earn buying at today's price if your growth assumptions come true, after fees.")
    m4.metric("Long-run yardstick", pct(ref), help="Rough long-run yearly earnings growth of large US companies.")

    growth_bars([("Priced in by today's price", g_implied, BLUE), ("Your assumption", a.growth_rate, "#7c3aed"),
                 ("Long-run average (large US companies)", ref, GREY)],
                "Growth priced in vs. reality checks")

    path = fund_needed_path(f, a, g_implied)
    if path:
        years = [f"Year {i}" for i in range(1, a.years + 1)]
        st.markdown("#### Profit per fund share that today's price is counting on")
        fig = go.Figure()
        fig.add_bar(x=["Today"], y=[f.earnings_per_share], name="Today", marker_color=GREY)
        fig.add_bar(x=years, y=path, name="Needed to justify the price", marker_color=BLUE)
        fig.add_scatter(x=years, y=r.earnings, name="Your forecast", mode="lines+markers", line=dict(color=TEAL, width=3))
        chart_layout(fig, yaxis=dict(tickprefix="$", title="$ per fund share"))
        show(fig)
        st.markdown(esc(
            f"To justify **${f.price:,.2f}**, the profit behind each fund share would need to grow from "
            f"**${f.earnings_per_share:,.2f}** today to **${path[-1]:,.2f}** in {a.years} years "
            f"(**{path[-1] / f.earnings_per_share:.1f}×**)."
        ))

    st.markdown("#### Growth priced in for other required returns and time frames")
    grid = fund_implied_growth_grid(f, a, _rates_around(a.required_return, a.terminal_growth),
                                    sorted({5, 10, 15, 20, a.years}))
    implied_grid_view(grid, ref, a.required_return, a.years, "Return")
    explain(
        "**How to read the table:** each cell is the steady yearly profit growth the price needs, for a different "
        "required return (rows) and forecast length (columns). Higher required returns need more growth; longer "
        "time frames need less growth per year."
    )


# --------------------------------------------------------------------------- #
# Probability view
# --------------------------------------------------------------------------- #

SCEN_VIEWS = ["Three scenarios", "Probability view", "What-if grid"]


def kpi_row(n: int, key: str):
    """n columns of figures inside one bordered box, separated by thin dividers (instead of n boxes)."""
    return st.container(border=True, key=f"kpis_{key}").columns(n)


def view_switch(options: list, key: str) -> str:
    """A compact row of buttons to switch between parts of a tab (keeps tabs from getting long)."""
    choice = st.segmented_control("Choose what to see", options, default=options[0], key=key)
    return choice or options[0]


def short_money(x: float) -> str:
    """Compact dollars for tight spaces: $85, $1.2k, $34k, $1.5M."""
    if abs(x) >= 1_000_000:
        return f"${x / 1e6:,.1f}M"
    if abs(x) >= 10_000:
        return f"${x / 1000:,.0f}k"
    if abs(x) >= 1_000:
        return f"${x / 1000:.1f}k"
    return f"${x:,.0f}"


def probability_view(simulate, price: float, central: float, noun: str, key: str) -> None:
    st.markdown("#### How likely is today's price to be justified?")
    level = st.segmented_control(
        "How unsure are you about the assumptions?", list(UNCERTAINTY), default="Medium", key=f"mc_level__{key}",
        help="How far growth, long-term growth and the required return are allowed to wander from your settings. "
             "Medium: growth ±3 points, required return ±1 point (about 2 in 3 draws stay within that).",
    ) or "Medium"
    sim = simulate(level)
    q = sim.summary()
    m1, m2, m3, m4 = kpi_row(4, "compact_mc")
    m1.metric("Chance it's justified", f"{sim.prob_above_price:.0%}",
              help=f"Share of the 5,000 simulated outcomes where the value is at least today's price (${price:,.2f}).")
    m2.metric("Middle outcome", f"${q['p50']:,.2f}", help="Half of the outcomes are above this, half below.")
    m3.metric("Likely range", f"{short_money(q['p25'])} – {short_money(q['p75'])}",
              help=f"The middle half of outcomes: ${q['p25']:,.2f} to ${q['p75']:,.2f}.")
    m4.metric("Wide range (9 in 10)", f"{short_money(q['p5'])} – {short_money(q['p95'])}",
              help=f"9 in 10 outcomes: ${q['p5']:,.2f} to ${q['p95']:,.2f}.")

    lo, hi = sim.percentile(1), sim.percentile(99)
    vals = sim.values[(sim.values >= lo) & (sim.values <= hi)]
    size = (hi - lo) / 60 if hi > lo else 1
    bins = dict(start=lo, end=hi, size=size)
    fig = go.Figure()
    fig.add_histogram(x=vals[vals < price], xbins=bins, name="Below today's price", marker_color=RED, opacity=0.75)
    fig.add_histogram(x=vals[vals >= price], xbins=bins, name="Above today's price", marker_color=TEAL, opacity=0.75)
    fig.add_vline(x=price, line_dash="dash", line_color=AMBER, line_width=2,
                  annotation_text=f"Today ${price:,.0f}", annotation_position="top")
    fig.add_vline(x=central, line_color=BLUE, line_width=2,
                  annotation_text=f"Your estimate ${central:,.0f}", annotation_position="bottom right")
    chart_layout(fig, height=360, barmode="overlay", hovermode="closest",
                 xaxis=dict(tickprefix="$", tickformat=",.0f", title=f"Estimated value per {noun}"),
                 yaxis=dict(title="Number of outcomes"))
    show(fig)
    explain(
        "**What this shows:** the valuation run 5,000 times, each time with slightly different growth, long-term "
        "growth and required return drawn around your settings. Each bar counts how many outcomes landed at that "
        "value: **teal** ones are above today's price (the price is justified), **red** ones below.\n\n"
        "**How to read it:** the *chance the price is justified* is the share of teal. Around 50% means the price "
        "matches your assumptions; much lower means the price needs things to go better than you expect. The "
        "range is lopsided to the right because small changes in growth or the required return can make the "
        "value much larger, but it can't fall below zero as easily. The middle 98% of outcomes are drawn."
    )


# --------------------------------------------------------------------------- #
# Company: snapshot, quality, similar companies
# --------------------------------------------------------------------------- #

COMPANY_VIEWS = ["Snapshot", "Quality check", "Similar companies"]


def quality_view(c) -> None:
    checks = scorecard(c)
    label, color, _ = overall(checks)
    counts = {g: sum(ch.grade == g for ch in checks) for g in ("Strong", "OK", "Weak")}
    with st.container(border=True, key=f"verdict_{color}_quality"):
        st.markdown(f"#### :{color}[{label}]")
        st.markdown(f"**{counts['Strong']} strong**, **{counts['OK']} OK** and **{counts['Weak']} weak** "
                    f"out of {len(checks)} checks.")
        st.caption("Quality is about the business, not the share price: a great company can still be too expensive, "
                   "and a weaker one can be a bargain.")
    cards = []
    for ch in checks:
        badge = "na" if ch.grade == "n/a" else ch.grade
        cards.append(
            f'<div class="qcard"><div class="qtop"><span class="qname">{html.escape(ch.name)}</span>'
            f'<span class="badge {badge}">{html.escape(ch.grade)}</span></div>'
            f'<div class="qval">{html.escape(ch.value)}</div>'
            f'<div class="qmean">{html.escape(ch.meaning)}</div>'
            f'<div class="qrule">{html.escape(ch.rule)}</div></div>'
        )
    st.html('<div class="qgrid">' + "".join(cards) + "</div>")
    st.caption("Margins, returns and EBITDA from Yahoo Finance; sales and cash flow from the yearly figures in the snapshot.")


def _load_many(tickers: list) -> dict:
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {t: pool.submit(load, t) for t in tickers}
    out = {}
    for t, fut in futures.items():
        try:
            data = fut.result()
        except Exception:
            continue
        if not isinstance(data, FundData):
            out[t] = data
    return out


def peers_view(c, dcf_value) -> None:
    tickers = peer_tickers(c)
    st.markdown("#### How the price compares with similar companies")
    if not tickers:
        st.info("There's no list of similar companies for this industry yet.")
        return
    with st.spinner("Loading similar companies… (a few seconds the first time)"):
        peers = _load_many(tickers)
    if not peers:
        st.warning("Couldn't load the similar companies right now.")
        return
    med = peer_medians(list(peers.values()))
    rows = [{"Company": f"▶ {c.name} ({c.ticker})", **multiples(c)}]
    rows += [{"Company": f"{p.name} ({t})", **multiples(p)} for t, p in peers.items()]
    rows.append({"Company": "Median of similar companies", **med})
    table = pd.DataFrame(rows).set_index("Company")
    pct_cols = ["Cash flow yield", "Operating margin", "Sales growth"]
    st.dataframe(
        table, width="stretch",
        column_config={
            "P/E": st.column_config.NumberColumn(format="%.1f", help="Price ÷ last year's profit per share."),
            "Forward P/E": st.column_config.NumberColumn(format="%.1f", help="Price ÷ next year's expected profit per share."),
            "EV/EBITDA": st.column_config.NumberColumn(format="%.1f", help="Whole-business value (incl. debt) ÷ earnings before interest, tax and depreciation."),
            **{col: st.column_config.NumberColumn(format="percent") for col in pct_cols},
        },
    )
    implied = implied_prices(c, med)
    if implied:
        st.markdown("#### What the share would be worth if priced like its peers")
        labels = list(implied) + (["Your DCF estimate"] if dcf_value else [])
        values = list(implied.values()) + ([dcf_value] if dcf_value else [])
        colors = [TEAL if v >= c.price else RED for v in implied.values()] + ([BLUE] if dcf_value else [])
        fig = go.Figure(go.Bar(x=values, y=labels, orientation="h", marker_color=colors,
                               text=[f"${v:,.0f}" for v in values], textposition="outside", cliponaxis=False,
                               hovertemplate="%{y}: $%{x:,.2f}<extra></extra>"))
        fig.add_vline(x=c.price, line_dash="dash", line_color=AMBER, line_width=2,
                      annotation_text=f"Today ${c.price:,.0f}", annotation_position="top")
        chart_layout(fig, height=80 + 50 * len(labels), showlegend=False, hovermode="closest",
                     xaxis=dict(tickprefix="$", tickformat=",.0f", range=[0, max(values + [c.price]) * 1.2]),
                     yaxis=dict(automargin=False, ticksuffix="  "),
                     margin=dict(l=int(7.2 * max(len(x) for x in labels)) + 24, r=30, t=30, b=10))
        show(fig)
        lo, hi = min(implied.values()), max(implied.values())
        st.markdown(esc(f"Priced like its peers, {c.ticker} would trade between **${lo:,.0f}** and **${hi:,.0f}** "
                        f"a share, depending on the measure (today: **${c.price:,.2f}**)."))
    explain(
        "**What this shows:** a second way to value a company, used by most professionals alongside a DCF: "
        "compare its price with similar businesses.\n\n"
        "- **P/E:** dollars paid for each $1 of yearly profit. **Forward P/E** uses next year's expected profit.\n"
        "- **EV/EBITDA:** the value of the whole business (including debt) compared with its earnings before "
        "interest, tax and depreciation. Useful when companies have different amounts of debt.\n"
        "- **Cash flow yield:** yearly free cash flow as a share of the company's market value. Higher = cheaper.\n\n"
        "**The bars** ask: *if this company were priced like the typical similar company, what would one share "
        "cost?* Green bars are above today's price, red below. Peers can be expensive or cheap together, and "
        "faster-growing or more profitable companies usually deserve higher multiples, so this is a sanity check, "
        "not a verdict."
    )


def company_tab(c, ticker: str, dcf_value=None) -> None:
    view = view_switch(COMPANY_VIEWS, f"co_view__{ticker}")
    if view == COMPANY_VIEWS[1]:
        quality_view(c)
    elif view == COMPANY_VIEWS[2]:
        peers_view(c, dcf_value)
    else:
        company_data_tab(c)


# --------------------------------------------------------------------------- #
# Portfolio
# --------------------------------------------------------------------------- #

COLOUR_HEX = {"green": TEAL, "orange": AMBER, "red": RED, "grey": GREY}



MARKET_AVERAGE = 0.10   # long-run average yearly return of US stocks, dividends included (roughly, since 1926)
DEFAULT_VOLATILITY = 0.15


RETURN_CHOICES = {   # key: (label, caption)
    "model": ("The model's estimate", "Based on today's prices of your holdings"),
    "market": (f"Stock market average ({MARKET_AVERAGE:.0%})", "US stocks' long-run average, dividends included"),
    "cautious": ("Cautious (5%)", "In case returns disappoint"),
    "own": ("Choose my own", "Set any rate with the slider below"),
}
INFLATION = 0.025


def future_value_view(rows: list, total: float, model_return) -> None:
    st.markdown("#### What could your portfolio be worth?")
    st.markdown(f"Starting from what your holdings are worth today, **${total:,.0f}**. Answer three questions:")
    has_model = model_return is not None and pd.notna(model_return)
    keys = [k for k in RETURN_CHOICES if has_model or k != "model"]

    def label(k: str) -> str:
        name = RETURN_CHOICES[k][0]
        return f"{name} ({model_return:.1%})" if k == "model" else name

    with st.container(border=True, key="card_fv_inputs"):
        c1, c2, c3 = st.columns([1, 1, 1.3], gap="large")
        with c1:
            years = st.slider("① How many years will you invest?", 1, 40, 10, key="fv_years", format="%d years")
        with c2:
            monthly = st.number_input("② How much will you add each month? ($)", min_value=0, max_value=1_000_000,
                                      value=0, step=50, key="fv_monthly")
            st.caption("Enter 0 if you won't add any money.")
        with c3:
            pick = st.radio("③ What yearly return should we assume?", keys, format_func=label, key="fv_choice",
                            captions=[RETURN_CHOICES[k][1] for k in keys])
        rate = {"model": model_return, "market": MARKET_AVERAGE, "cautious": 0.05}.get(pick)
        if rate is None:
            rate = st.slider("My yearly return", 0.0, 15.0, 7.0, 0.5, format="%.1f%%", key="fv_custom") / 100
    real = st.toggle(f"Show in today's dollars (takes out {INFLATION:.1%} yearly inflation)", key="fv_real",
                     help="Future dollars buy less than today's. Turn this on to see what the amounts would buy now.")

    prices = {r["Ticker"]: fetch_history(r["Ticker"]) for r in rows}
    vol = portfolio_volatility(prices, {r["Ticker"]: r["Amount"] for r in rows})
    vol_note = "based on how your holdings moved over the last 3 years"
    if vol is None or not 0.03 <= vol <= 0.8:
        vol, vol_note = DEFAULT_VOLATILITY, "a typical figure for a stock portfolio (not enough price history)"

    proj = project_value(total, monthly, years, rate, vol)
    if real:
        proj = proj.div((1 + INFLATION) ** proj.index.to_series(), axis=0)
    end = proj.loc[years]
    dollars = " in today's dollars" if real else ""
    with st.container(border=True, key="verdict_green_fv"):
        st.markdown(esc(
            f"#### :green[Most likely around ${end['p50']:,.0f}{dollars}]\n"
            f"If you start with **${total:,.0f}**"
            + (f", add **${monthly:,.0f} a month**" if monthly else "")
            + f" and earn about **{rate:.1%} a year**, after **{years} years** you'd most likely have around "
            f"**${end['p50']:,.0f}**. In 8 out of 10 cases it would be between **${end['p10']:,.0f}** and "
            f"**${end['p90']:,.0f}**. You'd have put in **${end['put_in']:,.0f}** yourself"
            + (", in today's dollars" if real else "") + "."
        ))
    m1, m2, m3, m4 = kpi_row(4, "compact_fv")
    m1.metric(f"Most likely in {years} yr", short_money(end["p50"]),
              help=f"Half of the simulated outcomes end above this, half below. Exactly: ${end['p50']:,.0f}.")
    m2.metric("Likely range (8 in 10)", f"{short_money(end['p10'])} – {short_money(end['p90'])}",
              help=f"8 in 10 outcomes land between ${end['p10']:,.0f} and ${end['p90']:,.0f}.")
    m3.metric("You'd put in", short_money(end["put_in"]),
              help="Today's value plus all the monthly additions.")
    m4.metric("Growth from investing", short_money(end["p50"] - end["put_in"]),
              help="Middle outcome minus the money you put in.")

    x = list(proj.index)
    fig = go.Figure()
    fig.add_scatter(x=x, y=proj["p90"], mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip")
    fig.add_scatter(x=x, y=proj["p10"], mode="lines", line=dict(width=0), fill="tonexty",
                    fillcolor=BLUE_FILL.format(a=0.12), name="8 in 10 outcomes", hoverinfo="skip")
    fig.add_scatter(x=x, y=proj["p75"], mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip")
    fig.add_scatter(x=x, y=proj["p25"], mode="lines", line=dict(width=0), fill="tonexty",
                    fillcolor=BLUE_FILL.format(a=0.25), name="Middle half", hoverinfo="skip")
    fig.add_scatter(x=x, y=proj["p50"], mode="lines", name="Middle outcome", line=dict(color=BLUE, width=3),
                    hovertemplate="Year %{x}: $%{y:,.0f}<extra></extra>")
    fig.add_scatter(x=x, y=proj["put_in"], mode="lines", name="Money put in", line=dict(color=GREY, dash="dash"),
                    hovertemplate="Year %{x}: $%{y:,.0f} put in<extra></extra>")
    chart_layout(fig, height=380, hovermode="x unified",
                 xaxis=dict(title="Years from now", dtick=max(1, years // 10)),
                 yaxis=dict(tickprefix="$", tickformat=",.0f", rangemode="tozero"))
    show(fig)
    explain(
        f"**How this works:** your portfolio (${total:,.0f} today) is simulated 4,000 times, month by month. Each "
        f"month it earns a random return that averages **{rate:.1%} a year** and swings about **±{vol:.0%} a year** "
        f"({vol_note}), then your monthly addition is added.\n\n"
        "**How to read it:** the dark band holds the middle half of outcomes, the light band 8 in 10. The blue "
        "line is the middle outcome; the grey dashed line is just the money you put in, so the gap between them "
        "is what investing added. The range widens over time because good and bad years compound.\n\n"
        "**Keep in mind:** amounts are in future dollars, not adjusted for inflation (at about 2.5% a year, "
        f"$1 in {years} years buys what about ${1 / 1.025 ** years:.2f} buys today). Taxes and fees aren't "
        "included, and real markets can do worse than even the low end. Not investment advice.",
        "How this works and what it leaves out",
    )

def render_portfolio() -> None:
    actions = page_head("My portfolio")
    with actions:
        share_button()
    st.caption("Enter what you own and what each holding is worth today. Each one is valued with its default "
               "assumptions. Nothing you type is saved anywhere except the page link.")
    if "portfolio" not in st.session_state:
        st.session_state["portfolio"] = EXAMPLE_PORTFOLIO
    if "pf_table" not in st.session_state:   # the editor's starting table must stay the same between reruns
        st.session_state["pf_table"] = pd.DataFrame(
            parse_holdings(st.session_state["portfolio"]) or [("VOO", 1000.0)], columns=["Ticker", "Value today ($)"])

    left, right = st.columns([1, 2], gap="large")
    with left:
        st.markdown("#### Your holdings")
        edited = st.data_editor(
            st.session_state["pf_table"], num_rows="dynamic", hide_index=True, key="pf_holdings", width="stretch",
            column_config={
                "Ticker": st.column_config.TextColumn(help="The stock or fund's ticker, e.g. VOO or AAPL.",
                                                      required=True),
                "Value today ($)": st.column_config.NumberColumn(
                    help="What this holding is worth now (its market value in your brokerage app), "
                         "not what you paid for it.",
                    min_value=0.0, step=100.0, format="dollar", required=True),
            },
        )
        st.caption("Use each holding's **value today** (shares × today's price), not what you paid. "
                   + ("This is an example: click a cell to change it, or the + row to add one."
                      if st.session_state["portfolio"] == EXAMPLE_PORTFOLIO else ""))
    holdings = [(str(t).strip().upper(), float(a)) for t, a in zip(edited["Ticker"], edited["Value today ($)"])
                if isinstance(t, str) and t.strip() and pd.notna(a) and a > 0]
    merged: dict = {}
    for t, a in holdings:
        merged[t] = merged.get(t, 0.0) + a
    holdings = list(merged.items())[:15]
    st.session_state["portfolio"] = format_holdings(holdings)
    SHARE["p"] = st.session_state["portfolio"]
    if not holdings:
        with right:
            st.info("Add at least one holding on the left.")
        return

    with st.spinner("Valuing your holdings… (a few seconds for any not loaded recently)"):
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {t: pool.submit(load, t) for t, _ in holdings}
        rows, failed = [], []
        for t, amount in holdings:
            try:
                rows.append(holding_row(t, amount, futures[t].result()))
            except Exception:
                failed.append(t)
    if failed:
        st.warning(f"Couldn't load: {', '.join(failed)}. Check the spelling.", icon="⚠️")
    if not rows:
        return

    total = sum(r["Amount"] for r in rows)
    exp = weighted(rows, "Expected return")
    gap = weighted(rows, "Gap vs. price")
    stretched = [r for r in rows if r["Colour"] == "red"]
    stretched_share = sum(r["Amount"] for r in stretched) / total if total else 0
    with right:
        st.markdown("#### At a glance")
        glance = st.container(border=True, key="kpis_glance")
        a1, a2 = glance.columns(2)
        a1.metric("Total value", money(total))
        a2.metric("Expected return a year", pct(exp),
                  help="Value-weighted average of each holding's return priced in: what you'd earn a year buying "
                       "at today's prices if the default assumptions come true.")
        b1, b2 = glance.columns(2)
        b1.metric("Average gap vs. model value", f"{gap:+.1%}" if gap is not None else "n/a",
                  help="Value-weighted gap between each holding's model value and its price. Negative = priced "
                       "above the model's estimates.")
        b2.metric("Money in demanding prices", f"{stretched_share:.0%}",
                  help="Share of your money in holdings whose price assumes more growth than their track record "
                       "(red in the table below).")

    t_break, t_future = st.tabs(["📊 Breakdown", "🔮 Future value"])
    with t_future:
        future_value_view(rows, total, exp)
    with t_break:
        c1, c2 = st.columns(2, gap="large")
        with c1:
            st.markdown("#### Where your money is")
            mix = sector_mix(rows).rename(index={"Communication services": "Communication",
                                                  "Financial services": "Financials"})
            mix = mix.groupby(level=0).sum().sort_values(ascending=False)
            top = mix.head(7)
            if len(mix) > 7:
                top["Other"] = mix.iloc[7:].sum()
            fig = go.Figure(go.Pie(labels=list(top.index), values=list(top.values), hole=0.55, sort=False,
                                   marker=dict(colors=["#4f46e5", "#0d9488", "#f59e0b", "#e11d48", "#7c3aed",
                                                       "#0ea5e9", "#64748b", "#94a3b8"]),
                                   textinfo="percent", hovertemplate="%{label}: $%{value:,.0f}<extra></extra>"))
            chart_layout(fig, height=340, hovermode="closest", legend=dict(orientation="v", x=1.02, y=0.5))
            show(fig)
        with c2:
            st.markdown("#### Expected return by holding")
            ok = [r for r in rows if pd.notna(r["Expected return"])]
            fig = go.Figure(go.Bar(
                x=[r["Expected return"] * 100 for r in ok], y=[r["Ticker"] for r in ok], orientation="h",
                marker_color=[COLOUR_HEX.get(r["Colour"], GREY) for r in ok],
                text=[f"{r['Expected return']:.1%}" for r in ok], textposition="outside", cliponaxis=False,
                hovertemplate="%{y}: %{x:.1f}% a year<extra></extra>"))
            if exp is not None:
                fig.add_vline(x=exp * 100, line_dash="dash", line_color=BLUE,
                              annotation_text=f"Portfolio {exp:.1%}", annotation_position="top")
            top = max([r["Expected return"] * 100 for r in ok] + [exp * 100 if exp else 0, 1])
            chart_layout(fig, height=340, showlegend=False, hovermode="closest",
                         xaxis=dict(ticksuffix="%", range=[0, top * 1.2]), yaxis=dict(autorange="reversed"))
            show(fig)

        table = pd.DataFrame([{k: r[k] for k in ("Ticker", "Name", "Type", "Amount", "Price", "Value / share",
                                                   "Gap vs. price", "Expected return", "Growth priced in",
                                                   "Expectations")} for r in rows])
        table["Weight"] = table["Amount"] / total
        for col in ("Weight", "Gap vs. price", "Expected return", "Growth priced in"):
            table[col] = table[col] * 100   # shown with one decimal like the rest of the app
        table = table[["Ticker", "Name", "Amount", "Weight", "Gap vs. price", "Expected return", "Growth priced in",
                       "Expectations"]]
        tone = {r["Ticker"]: r["Colour"] for r in rows}

        def tint(row):
            bg = {"green": GREEN_BG, "red": RED_BG, "orange": "background-color: rgba(245,158,11,0.22)"}.get(tone[row["Ticker"]], "")
            return ["" if col != "Expectations" else bg for col in row.index]

        st.markdown("#### Holdings")
        st.dataframe(
            table.style.apply(tint, axis=1), hide_index=True, width="stretch",
            column_config={
                "Name": st.column_config.TextColumn(width=270),
                "Amount": st.column_config.NumberColumn(format="dollar"),
                "Weight": st.column_config.NumberColumn(format="%.1f%%"),
                "Gap vs. price": st.column_config.NumberColumn(
                    "Gap vs. model", format="%+.1f%%", help="Model value ÷ price − 1. Negative = priced above the model."),
                "Expected return": st.column_config.NumberColumn(format="%.1f%%"),
                "Growth priced in": st.column_config.NumberColumn(format="%.1f%%"),
            },
        )
        explain(
            "**How to read this page:**\n"
            "- **Where your money is** adds up your holdings by sector, *looking inside funds*: $1,000 in an S&P 500 "
            "fund counts as about $300 in technology, $130 in financials and so on. It shows whether you're more "
            "concentrated than you think.\n"
            "- **Expected return** is each holding's *return priced in*: the yearly return you'd earn buying at "
            "today's price if the default growth assumptions come true. Colours show how demanding the price is "
            "(green modest, amber in line with the record, red demanding).\n"
            "- These use default assumptions and simple models, so treat them as a starting point for questions, "
            "not as forecasts. Not investment advice."
        )


# --------------------------------------------------------------------------- #
# Fair value by method ("football field")
# --------------------------------------------------------------------------- #

KIND_COLOURS = {"model": BLUE, "peers": TEAL, "analysts": AMBER, "market": GREY}


@st.cache_data(ttl=3600, show_spinner=False)
def peer_prices_for(ticker: str) -> dict:
    """Share prices implied by similar companies' valuation multiples (empty if none can be loaded)."""
    c = fetch(ticker)
    peers = _load_many(peer_tickers(c))
    return implied_prices(c, peer_medians(list(peers.values()))) if peers else {}


def fair_value_verdict(name: str, price: float, band, tail: str, caveats) -> None:
    """The headline: where today's price sits among the valuation methods, plus what it assumes."""
    lo, mid, hi = band
    pos = price_position(price, band)
    color = {"below": "green", "within": "orange", "above": "red"}[pos]
    head = {"below": f"{name} looks **cheap** on most measures",
            "within": f"{name} is priced **within** its fair-value range",
            "above": f"{name} looks **expensive** on most measures"}[pos]
    with st.container(border=True, key=f"verdict_{color}"):
        st.markdown(
            esc(f"#### :{color}[{head}]\n"
                f"Most valuation methods put it between **${lo:,.2f}** and **${hi:,.2f}** a share (middle "
                f"**${mid:,.2f}**); today's price is **${price:,.2f}**. The chart below shows each method.\n\n{tail}"),
            help="The range is where the valuation methods' central estimates fall. With four or more methods, "
                 "the single highest and lowest are left out so one unusual result can't stretch it. "
                 "Not a prediction of where the price will go.",
        )
        if caveats:
            labels = " · ".join(label for label, _ in caveats)
            with st.expander(f"⚠️ The cash-flow model is probably too low here ({labels}). Why?"):
                st.markdown(esc("\n\n".join(f"**{label.capitalize()}.** {text}" for label, text in caveats)))
        st.markdown('<p class="mobile-only">Tap » at the top left to change the assumptions.</p>',
                    unsafe_allow_html=True)


def football_field(methods, price: float, band, distorted: bool) -> None:
    """Each method's range as a bar, the agreed range shaded, and today's price as a line."""
    shown = [m for m in methods if m.high > 0]
    if not shown:
        return
    labels = [("⚠️ " if distorted and m.name.startswith("Cash-flow model (free") else "") + m.name for m in shown]
    labels, shown = labels[::-1], shown[::-1]           # first method at the top
    fig = go.Figure()
    if band:
        fig.add_vrect(x0=band[0], x1=band[2], fillcolor="rgba(5,150,105,0.10)", line_width=0, layer="below",
                      annotation_text="Most methods", annotation_position="top left",
                      annotation_font=dict(color="#059669", size=12))
    fig.add_bar(
        x=[m.high - m.low for m in shown], base=[m.low for m in shown], y=labels, orientation="h",
        marker=dict(color=[KIND_COLOURS[m.kind] for m in shown],
                    opacity=[0.4 if (distorted and m.name.startswith("Cash-flow model (free")) or not m.counts
                             else 0.9 for m in shown]),
        text=[f"${m.low:,.0f} – ${m.high:,.0f}" for m in shown], textposition="outside", cliponaxis=False,
        customdata=[[m.mid, m.note] for m in shown],
        hovertemplate="%{y}<br>$%{base:,.0f} to $%{x:,.0f} wide<br>middle $%{customdata[0]:,.2f}<br>%{customdata[1]}<extra></extra>",
        showlegend=False,
    )
    fig.add_scatter(x=[m.mid for m in shown], y=labels, mode="markers", name="Middle estimate",
                    marker=dict(symbol="line-ns", size=22, line=dict(width=3, color="#0f172a")),
                    hovertemplate="Middle: $%{x:,.2f}<extra></extra>")
    fig.add_vline(x=price, line_dash="dash", line_color=RED, line_width=2,
                  annotation_text=f"Today ${price:,.0f}", annotation_position="top")
    top = max([m.high for m in shown] + [price]) * 1.18
    chart_layout(fig, height=110 + 56 * len(shown), hovermode="closest", showlegend=False,
                 xaxis=dict(tickprefix="$", tickformat=",.0f", range=[0, top]),
                 yaxis=dict(automargin=False, ticksuffix="  "),
                 margin=dict(l=int(7.0 * max(len(x) for x in labels)) + 24, r=40, t=30, b=10))
    show(fig)
    explain(
        "**What this shows:** several different ways of answering *what is one share worth?*, side by side. "
        "Each bar runs from that method's low to high estimate; the black tick is its middle. The **red dashed "
        "line** is today's price and the **green band** is where most methods agree.\n\n"
        "- **Cash-flow model (free cash flow):** this app's main model, using your sidebar settings. The bar runs "
        "from the pessimistic to the optimistic scenario.\n"
        "- **Cash-flow model (underlying cash flow):** the same model, but counting only the spending needed to "
        "*maintain* the business (estimated from depreciation), not spending on growth. For companies investing "
        "heavily, like Amazon or Microsoft, this is usually the fairer version.\n"
        "- **Priced like similar companies:** what the share would cost at the P/E, EV/EBITDA and cash-flow "
        "yield of similar large companies.\n"
        "- **Analysts' 12-month targets:** Wall Street's lowest, average and highest price targets.\n"
        "- **Traded over the last 12 months** (grey): where the price has actually been. Context, not a fair value.\n\n"
        "**How to read it:** when the bars overlap around the price, the price looks reasonable. When the red line "
        "sits to the right of most bars, the price is betting on more than these methods assume; to the left, "
        "less. Methods disagreeing a lot is itself useful: it means the value is genuinely uncertain."
    )


def render_company(c, ticker: str) -> None:
    k = lambda name: f"{name}__{ticker}"  # widget keys, per ticker so defaults reset on change
    payout = c.is_financial
    cash_name = "cash returned to shareholders" if payout else "free cash flow"
    rate_name = "Cost of equity" if payout else "Required return (discount rate)"

    method = ("Valued from cash returned to shareholders (bank method)" if payout
              else "Discounted cash flow (DCF) model")
    actions = page_head(f"{c.name} ({c.ticker})", [("Stock", "indigo"), (c.industry or c.sector, "slate"),
                                                   ("Bank method" if payout else "", "violet")])

    # ---- Sidebar ------------------------------------------------------------
    with st.sidebar:
        st.markdown("### 2. Adjust the assumptions")
        has_analyst = c.analyst_growth is not None
        src = st.radio(
            "Start growth from",
            ["analyst", "history"] if has_analyst else ["history"],
            format_func=lambda s: "Analysts' forecast" if s == "analyst" else "Past sales growth",
            key=k("src"), horizontal=True,
            help="Analysts' forecast = Wall Street's consensus for next year's earnings growth. "
                 "Past sales growth = how fast revenue grew over the last few years.",
        )
        st.session_state.setdefault(k("base"), default_base(c))   # latest year if cash flow has been growing
        base = st.radio(
            "Start cash flow from",
            ["avg3", "latest"],
            format_func=lambda b: "3-year average" if b == "avg3" else "Latest year",
            key=k("base"), horizontal=True,
            help="The average smooths out one unusually good or bad year; the latest year reflects the "
                 "company's most recent performance. The default is the latest year when cash flow has been "
                 "growing (the average would lag behind), and the average otherwise.",
        )

    SHARE.update(t=ticker, src=src, base=base)
    d = default_assumptions(c, growth_source=src, base=base)
    _, growth_label = default_growth(c, src)
    blocking, warnings = check_company(c, base)

    if blocking:
        with actions:
            share_button()
        with st.container(border=True, key="verdict_orange"):
            st.markdown("#### :orange[No valuation for this company]")
            st.write(blocking)
        warnings_box(warnings)
        with st.spinner("Comparing with similar companies… (a few seconds the first time)"):
            other = fair_value_methods(c, d, peer_prices_for(ticker), fetch_history(ticker))
        if any(m.counts for m in other):
            st.markdown("#### Other ways to value it")
            football_field(other, c.price, fair_value_band(other), distorted=False)
        t_outlook, t_data = st.tabs(["Price outlook", "Company"])
        with t_outlook:
            outlook_tab(c, d, ticker, "share")
        with t_data:
            company_tab(c, ticker)
        return

    g_key, tg_key, w_key = k(f"g_{src}_{base}"), k("tg"), k("w")
    with st.sidebar:
        st.caption(f"Starting values come from {growth_label}. Drag a slider to try a different scenario.")
        growth = pct_slider(
            "Growth next year", -10.0, 30.0, d.growth_rate, 0.5, g_key,
            f"How fast you expect the company's {cash_name} to grow next year.",
        )
        fade = st.checkbox(
            "Slow growth down over time", value=True, key=k("f"),
            help="Gradually lowers growth each year until it reaches the long-term rate, since no company grows fast forever.",
        )
        terminal = pct_slider(
            "Long-term growth (forever)", 0.0, 5.0, d.terminal_growth, 0.25, tg_key,
            "Growth assumed for every year after the forecast. Usually 2–3%, roughly inflation plus a little.",
        )
        wacc = pct_slider(
            rate_name, 4.0, 16.0, d.wacc, 0.25, w_key,
            "The yearly return investors want for owning this stock. Higher = future cash is worth less today = "
            "lower value." + (" For banks this is the cost of equity: the return shareholders demand." if payout
                              else " Technically called WACC."),
        )
        years = st.slider(
            "Years to forecast", 3, 15, d.years, key=k("y"),
            help="How many years are forecast one by one before switching to the long-term growth rate.",
        )
        st.button("↺ Reset to defaults", on_click=reset_assumptions, args=(ticker,), width="stretch")
        st.caption(f"Model's suggested {rate_name.split(' (')[0].lower()}: {d.wacc:.1%} (based on beta {c.beta:.2f}).")

    if wacc <= terminal:
        st.error("The required return must be higher than long-term growth, otherwise the value would be infinite. "
                 "Lower long-term growth or raise the required return.")
        st.stop()

    SHARE.update(g=st.session_state[g_key], tg=st.session_state[tg_key], w=st.session_state[w_key], y=years,
                 f=int(fade))
    a = DCFAssumptions(growth_rate=growth, terminal_growth=terminal, wacc=wacc, years=years, fade=fade, base=base)
    r = run_dcf(c, a)
    g_implied = implied_growth(c, a)
    scen = company_scenarios(c, a)

    warnings_box(warnings)
    tail = priced_in_sentence(g_implied, growth, years, terminal, cash_name)
    caveats = model_caveats(c, a)
    with st.spinner("Comparing with similar companies… (a few seconds the first time)"):
        peer_prices = peer_prices_for(ticker)
    methods = fair_value_methods(c, a, peer_prices, fetch_history(ticker), distorted=bool(caveats))
    band = fair_value_band(methods)
    if band:
        fair_value_verdict(c.name, c.price, band, tail, caveats)
    else:
        verdict_box(c.name, r.value_per_share, c.price, r.upside, "share", tail, caveats=caveats)
    download_button(company_tables(c, a, r, fetch_history(ticker)), ticker, actions)

    t_overview, t_reverse, t_outlook, t_forecast, t_scen, t_data = st.tabs(
        ["Overview", "Reverse DCF", "Price outlook", "Forecast", "Scenarios", "Company"])

    # ---- Overview ----------------------------------------------------------
    with t_overview:
        m1, m2, m3, m4 = kpi_row(4, "compact_fair")
        m1.metric("Current price", f"${c.price:,.2f}", help="What one share costs on the stock market right now.")
        if band:
            m2.metric("Fair-value range", f"{short_money(band[0])} – {short_money(band[2])}",
                      help=f"Where most valuation methods put one share: ${band[0]:,.2f} to ${band[2]:,.2f}. "
                           "See the chart below.")
            gap_m = band[1] / c.price - 1
            m3.metric("Middle of the methods", f"${band[1]:,.2f}", delta=f"{gap_m:+.1%} vs. price",
                      help="The middle of the valuation methods' central estimates.")
        else:
            m2.metric("Cash-flow model", f"${r.value_per_share:,.2f}",
                      help="What the cash-flow model thinks one share is worth with your sidebar settings.")
            gap_d = r.value_per_share - c.price
            m3.metric("Gap vs. price", f"{r.upside:+.1%}", delta=f"{'-' if gap_d < 0 else '+'}${abs(gap_d):,.2f} vs. price")
        m4.metric("Growth priced in", pct(g_implied),
                  delta=(f"{g_implied - growth:+.1%} vs. your setting" if pd.notna(g_implied) else None),
                  delta_color="inverse",
                  help=f"The steady yearly growth in {cash_name} over the next {years} years that would make the "
                       "estimate equal today's price. Higher than your setting = the market expects more than you do.")

        st.markdown("#### Fair value by method")
        football_field(methods, c.price, band, distorted=bool(caveats))

        st.markdown(f"#### How the cash-flow model gets to ${r.value_per_share:,.2f}")
        div, unit = scale_for([r.enterprise_value, r.equity_value])
        if payout:
            measure = ["relative", "relative", "total"]
            labels = [f"Cash returned over<br>the next {years} years", "Cash returned in<br>all years after",
                      "Value for<br>shareholders"]
            ys = [sum(r.pv_fcf) / div, r.pv_terminal_value / div, 0]
            texts = [money(sum(r.pv_fcf)), money(r.pv_terminal_value), money(r.equity_value)]
        else:
            measure = ["relative", "relative", "total", "relative", "total"]
            labels = [f"Cash from the<br>next {years} years", "Cash from all<br>years after",
                      "Value of the<br>whole business", "Minus debt<br>(net of cash)", "Value for<br>shareholders"]
            ys = [sum(r.pv_fcf) / div, r.pv_terminal_value / div, 0, -r.net_debt / div, 0]
            texts = [money(sum(r.pv_fcf)), money(r.pv_terminal_value), money(r.enterprise_value),
                     money(-r.net_debt), money(r.equity_value)]
        fig = go.Figure(go.Waterfall(
            orientation="v", measure=measure, x=labels, y=ys, text=texts,
            textposition="outside", cliponaxis=False,
            connector=dict(line=dict(color=GREY, dash="dot")),
            increasing=dict(marker=dict(color=BLUE)),
            decreasing=dict(marker=dict(color=RED)),
            totals=dict(marker=dict(color=TEAL)),
        ))
        chart_layout(fig, height=420, yaxis=dict(ticksuffix=unit, tickprefix="$"), showlegend=False)
        show(fig)
        st.markdown(esc(
            f"Value for shareholders **{money(r.equity_value)}** ÷ **{c.shares_outstanding / 1e6:,.1f} million** shares "
            f"= **${r.value_per_share:,.2f} per share**."
        ))
        if r.terminal_share > 0.75:
            st.markdown(esc(f"📌 **{r.terminal_share:.0%}** of this estimate comes from the years after the forecast "
                            "(the second bar), so it's very sensitive to the long-term growth and required return."))
        if payout:
            explain(
                "**What this shows:** how the estimate is built, in today's money. The **blue bars** add up the cash "
                f"the company is expected to hand to shareholders (dividends + buybacks): first the next {years} years, "
                "then everything after. For a bank, that total *is* the value for shareholders: debt isn't "
                "subtracted, because borrowing and lending is the bank's normal business and the cash returned is "
                "what's left after it."
            )
        else:
            explain(
                "**What this shows:** how the estimate is built, step by step, all in today's money.\n\n"
                f"1. **Blue bars** add up the cash the company is expected to produce: first the next {years} years one "
                "by one, then everything after that (the \"terminal value\").\n"
                "2. Together they give the **value of the whole business**.\n"
                "3. **Debt is subtracted** (minus any cash the company holds), because lenders get paid before owners.\n"
                "4. What's left is the **value for shareholders**, divided by the number of shares to get the "
                "value of one share.\n\n"
                "If the second blue bar is much taller than the first, most of the value depends on the distant future."
            )
        price_chart(ticker, c.price, scen, "share")

    with t_reverse:
        reverse_tab_stock(c, a, g_implied, cash_name, rate_name)

    with t_outlook:
        outlook_tab(c, a, ticker, "share")

    # ---- Forecast ----------------------------------------------------------
    with t_forecast:
        hist_years = c.years
        proj_years = ([str(int(hist_years[-1]) + i) for i in range(1, years + 1)]
                      if hist_years else [f"Year {i}" for i in range(1, years + 1)])
        past = c.valuation_cash_flow
        div, unit = scale_for(list(past) + r.projected_fcf)

        st.markdown(f"#### {cash_name.capitalize()}: past and forecast")
        fig = go.Figure()
        fig.add_bar(x=hist_years, y=[v / div for v in past], name="Actual (past)", marker_color=GREY)
        fig.add_bar(x=proj_years, y=[v / div for v in r.projected_fcf], name="Forecast", marker_color=BLUE)
        fig.add_scatter(x=proj_years, y=[v / div for v in r.pv_fcf], name="Forecast, in today's money",
                        mode="lines+markers", line=dict(color=AMBER, width=3))
        chart_layout(fig, yaxis=dict(ticksuffix=unit, tickprefix="$", title=f"$ {dict(T='trillions', B='billions').get(unit, 'millions')}"))
        show(fig)
        what = ("*cash returned to shareholders*: the dividends a company pays plus the shares it buys back. "
                "For banks it's a steadier and more meaningful measure than free cash flow."
                if payout else
                "*free cash flow*, the cash a company has left after paying its bills and investing in its business. "
                "It's the money that could go to owners, and it's what this whole valuation is based on.")
        explain(
            f"**What this shows:** {what}\n\n"
            "**How to read it:**\n"
            "- **Grey bars** are what the company actually produced in past years.\n"
            "- **Blue bars** are the forecast, growing at the rates you set in the sidebar.\n"
            "- The **orange line** is each forecast year converted into *today's money*. It sits below the blue bars "
            "because money received in the future is worth less than money today (you could invest today's money and "
            "earn a return in the meantime). The further away the year, the bigger the gap."
        )

        st.markdown("#### Year-by-year forecast")
        proj = r.projection_table()
        proj.index = proj_years
        proj.columns = ["Growth that year", cash_name.capitalize(), "Worth today per $1", "Value in today's money"]
        st.dataframe(
            proj.style.format({
                "Growth that year": "{:.1%}", cash_name.capitalize(): money,
                "Worth today per $1": "${:.2f}", "Value in today's money": money,
            }),
            width="stretch",
        )
        explain(
            "**How to read the table:** each row is one future year. *Worth today per $1* is the discount: e.g. "
            "$0.91 means $1 received that year is worth about 91 cents today at your required return. Multiply the "
            "cash by it to get the *value in today's money*."
        )

    # ---- Scenarios & what-if ----------------------------------------------
    with t_scen:
        view = view_switch(SCEN_VIEWS, k("scen_view"))
        if view == SCEN_VIEWS[0]:
            st.markdown("#### Three scenarios")
            scenario_cards(
                scen, c.price, rate_name.split(" (")[0],
                lambda row: {
                    g_key: slider_value(row["Growth next year"], -10.0, 30.0, 0.5),
                    tg_key: slider_value(row["Long-term growth"], 0.0, 5.0, 0.25),
                    w_key: slider_value(row["Required return"], 4.0, 16.0, 0.25),
                },
            )
        elif view == SCEN_VIEWS[1]:
            probability_view(lambda lvl: simulate_company(c, a, level=lvl), c.price, r.value_per_share, "share", ticker)
        else:
            st.markdown("#### What if the assumptions are different?")
            st.caption("Estimated value per share for a range of required returns (rows) and long-term growth rates (columns).")
            sensitivity_view(sensitivity_table(c, a), c.price, "Return", rate_name.lower())

    with t_data:
        company_tab(c, ticker, r.value_per_share)



# --------------------------------------------------------------------------- #
# Index funds
# --------------------------------------------------------------------------- #

def fund_facts(f: FundData) -> None:
    k1, k2, k3, k4 = kpi_row(4, "fundfacts")
    k1.metric("Yearly fee (expense ratio)", f"{f.expense_ratio:.2%}",
              help="What the fund charges each year, taken out of your returns. Index funds are usually under 0.2%.")
    k2.metric("Dividend yield", f"{f.dividend_yield:.2%}",
              help="Cash paid out to investors each year as a share of the price.")
    k3.metric("P/E ratio", f"{f.pe:.1f}" if f.can_value else "n/a",
              help="Price ÷ yearly earnings of the companies the fund owns. Higher = you pay more for each $1 of profit. "
                   "The S&P 500's long-run average is about 16.")
    k4.metric("Fund size", money(f.total_assets), help="Total money invested in the fund.")
    st.caption(
        f"Past performance (average per year): last 3 years **{pct(f.return_3y)}** · last 5 years **{pct(f.return_5y)}** · "
        f"beta **{f.beta:.2f}**. Past returns don't predict future ones."
    )


def fund_holdings(f: FundData) -> None:
    left, right = st.columns(2)
    with left:
        st.markdown("#### Biggest holdings")
        if f.holdings:
            h = f.holdings_table()
            h["Weight"] = h["Weight"] * 100
            st.dataframe(
                h, hide_index=True, width="stretch",
                column_config={
                    "Weight": st.column_config.ProgressColumn(
                        "Share of fund", format="%.1f%%", min_value=0.0, max_value=float(h["Weight"].max())
                    )
                },
            )
            st.caption(f"These {len(f.holdings)} companies make up {f.top_holdings_weight:.0%} of the fund. "
                       "Yahoo Finance only lists the top 10.")
        else:
            st.write("Yahoo Finance has no holdings data for this fund.")
    with right:
        st.markdown("#### Industries (sectors)")
        if f.sectors:
            s = f.sectors_table().sort_values("Weight")
            fig = go.Figure(go.Bar(
                x=s["Weight"], y=s["Sector"], orientation="h", marker_color=BLUE,
                text=[f"{w:.0%}" for w in s["Weight"]], textposition="outside",
            ))
            chart_layout(fig, height=380, showlegend=False, hovermode="closest",
                         xaxis=dict(tickformat=".0%", range=[0, float(s["Weight"].max()) * 1.18]))
            show(fig)
        else:
            st.write("No sector breakdown available for this fund.")
    explain(
        "**What this shows:** what you actually own when you buy one share of the fund. An index fund is a basket "
        "of many companies; buying it gives you a small slice of all of them.\n\n"
        "- **Biggest holdings:** the companies the fund has the most money in. If a few names make up a large share, "
        "the fund's results depend heavily on them.\n"
        "- **Industries:** how the money is spread across parts of the economy. A fund that's heavy in one sector "
        "(for example technology) is more exposed to that sector's ups and downs."
    )


def render_fund(f: FundData, ticker: str) -> None:
    kind = "Mutual fund" if f.fund_type == "MUTUALFUND" else "ETF"
    actions = page_head(f"{f.name} ({f.ticker})", [("Index fund", "indigo"),
                                                   (f"Fee {f.expense_ratio:.2%} a year", "slate")])

    if not f.can_value:
        with st.container(border=True, key="verdict_orange"):
            st.markdown("#### :orange[No valuation for this fund]")
            st.write(
                "This fund has no P/E ratio, which usually means it holds bonds rather than stocks. The valuation "
                "model works by valuing the earnings of the companies a fund owns, so it only applies to stock funds."
            )
        fund_facts(f)
        fund_holdings(f)
        st.divider()
        outlook_tab(f, default_index_assumptions(f), ticker, "fund share")
        return

    SHARE["t"] = ticker
    d = default_index_assumptions(f)
    k = lambda name: f"{name}__{ticker}"
    g_key, tg_key, r_key = k("fg"), k("ftg"), k("fr")

    with st.sidebar:
        st.markdown("### 2. Adjust the assumptions")
        st.caption("The fund is valued as if all its companies were one big business.")
        growth = pct_slider(
            "Earnings growth next year", -5.0, 15.0, d.growth_rate, 0.25, g_key,
            "How fast you expect the combined profits of the fund's companies to grow next year.",
        )
        fade = st.checkbox("Slow growth down over time", value=True, key=k("ff"),
                           help="Gradually moves growth toward the long-term rate.")
        terminal = pct_slider(
            "Long-term growth (forever)", 0.0, 6.0, d.terminal_growth, 0.25, tg_key,
            "Growth assumed for every year after the forecast. For a broad index, roughly the economy's growth plus inflation (3–5%).",
        )
        req = pct_slider(
            "Required return", 4.0, 16.0, d.required_return, 0.25, r_key,
            "The yearly return you want from owning stocks. Higher = future profits are worth less today = lower value.",
        )
        payout = pct_slider(
            "Share of profit paid to owners", 30.0, 100.0, d.payout, 5.0, k("fp"),
            "How much of their profit companies hand back through dividends and share buybacks, instead of reinvesting.",
        )
        years = st.slider("Years to forecast", 5, 20, d.years, key=k("fy"),
                          help="How many years are forecast one by one before switching to long-term growth.")
        st.button("↺ Reset to defaults", on_click=reset_assumptions, args=(ticker,), width="stretch")
        st.caption(f"Model's suggested required return: {d.required_return:.1%} (based on beta {f.beta:.2f}).")

    if req + f.expense_ratio <= terminal:
        st.error("The required return must be higher than long-term growth, otherwise the value would be infinite.")
        st.stop()

    SHARE.update(fg=st.session_state[g_key], ftg=st.session_state[tg_key], fr=st.session_state[r_key],
                 fp=st.session_state[k("fp")], fy=years, ff=int(fade))
    a = IndexAssumptions(growth_rate=growth, terminal_growth=terminal, required_return=req, payout=payout, years=years, fade=fade)
    r = run_index_valuation(f, a)
    g_implied = implied_index_growth(f, a)
    scen = fund_scenarios(f, a)

    extra = ""
    if pd.notna(r.implied_return):
        extra = (f"📈 **Expected return:** buying at today's price, the model expects about **{pct(r.implied_return)} a year** "
                 f"(after fees), compared with the **{req:.1%}** you asked for.\n\n")
    extra += priced_in_sentence(g_implied, growth, years, terminal, "the companies' combined earnings")
    verdict_box(f.name, r.value_per_share, f.price, r.upside, "fund share", extra)
    download_button(fund_tables(f, a, r, fetch_history(ticker)), ticker, actions)

    t_overview, t_reverse, t_outlook, t_forecast, t_scen, t_inside = st.tabs(
        ["Overview", "Reverse valuation", "Price outlook", "Forecast", "Scenarios", "What's inside"])

    with t_overview:
        m1, m2, m3, m4 = kpi_row(4, "row4")
        m1.metric("Estimated value / share", f"${r.value_per_share:,.2f}",
                  help="What the model thinks one share of the fund is worth.")
        m2.metric("Current price", f"${f.price:,.2f}")
        gap_d = r.value_per_share - f.price
        m3.metric("Gap vs. price", f"{r.upside:+.1%}", delta=f"{'-' if gap_d < 0 else '+'}${abs(gap_d):,.2f} vs. price",
                  help="Negative = the price is above the estimate.")
        gap = r.implied_return - req
        m4.metric("Expected yearly return", pct(r.implied_return),
                  delta=f"{gap:+.1%} vs. your target" if pd.notna(gap) else None,
                  help="The yearly return you'd earn buying at today's price if the growth assumptions come true, after fees.")
        explain(
            "**The most useful number here is the expected yearly return.** Rather than asking \"is the fund cheap?\", "
            "it asks \"if I buy today, what return should I expect?\" If it's below your target (the required return "
            "slider), the model says the fund is priced higher than your assumptions justify, but you'd still expect "
            "a positive return, just a smaller one."
        )
        fund_facts(f)

        st.markdown("#### Where the value comes from")
        fig = go.Figure(go.Waterfall(
            measure=["relative", "relative", "total"],
            x=[f"Cash from the<br>next {years} years", "Cash from all<br>years after", "Estimated value<br>per share"],
            y=[sum(r.pv_cash), r.pv_terminal_value, 0],
            text=[f"${sum(r.pv_cash):,.0f}", f"${r.pv_terminal_value:,.0f}", f"${r.value_per_share:,.0f}"],
            textposition="outside", cliponaxis=False,
            connector=dict(line=dict(color=GREY, dash="dot")),
            increasing=dict(marker=dict(color=BLUE)),
            totals=dict(marker=dict(color=TEAL)),
        ))
        fig.add_hline(y=f.price, line_dash="dash", line_color=AMBER,
                      annotation_text=f"Current price ${f.price:,.0f}", annotation_position="top left")
        chart_layout(fig, height=420, yaxis=dict(tickprefix="$"), showlegend=False)
        show(fig)
        explain(
            "**What this shows:** the estimated value of one fund share, split into the cash expected over the "
            f"next {years} years and the cash from every year after that, both in today's money. The **dashed orange "
            "line** is the current price: if the green bar is shorter, the model values the fund below its price."
        )
        price_chart(ticker, f.price, scen, "fund")

    with t_reverse:
        reverse_tab_fund(f, a, r, g_implied)

    with t_outlook:
        outlook_tab(f, a, ticker, "fund share")

    with t_forecast:
        st.markdown("#### Cash paid to owners per fund share: forecast")
        proj_years = [f"Year {i}" for i in range(1, years + 1)]
        fig = go.Figure()
        fig.add_bar(x=proj_years, y=r.earnings, name="Profit per fund share", marker_color=GREY)
        fig.add_bar(x=proj_years, y=r.cash, name="Paid to owners", marker_color=BLUE)
        fig.add_scatter(x=proj_years, y=r.pv_cash, name="Paid to owners, in today's money",
                        mode="lines+markers", line=dict(color=AMBER, width=3))
        chart_layout(fig, yaxis=dict(tickprefix="$", title="$ per fund share"))
        show(fig)
        explain(
            "**What this shows:** each fund share represents a small slice of the profits of every company in the fund.\n\n"
            f"- **Grey bars:** that slice of profit each year. It starts at **${f.earnings_per_share:,.2f}** "
            f"(price ${f.price:,.2f} ÷ P/E {f.pe:.1f}) and grows at your growth rate.\n"
            f"- **Blue bars:** the part ({payout:.0%}) that companies hand back to owners as dividends and buybacks.\n"
            "- **Orange line:** that cash converted into today's money. It shrinks over time because money further in "
            f"the future is worth less today. The fund's {f.expense_ratio:.2%} yearly fee is included here."
        )
        st.markdown("#### Year-by-year forecast")
        proj = r.projection_table()
        proj.index = proj_years
        proj.columns = ["Growth that year", "Profit per share", "Paid to owners", "Worth today per $1", "Value in today's money"]
        st.dataframe(
            proj.style.format({
                "Growth that year": "{:.1%}", "Profit per share": "${:,.2f}", "Paid to owners": "${:,.2f}",
                "Worth today per $1": "${:.2f}", "Value in today's money": "${:,.2f}",
            }),
            width="stretch",
        )

    with t_scen:
        view = view_switch(SCEN_VIEWS, k("scen_view"))
        if view == SCEN_VIEWS[0]:
            st.markdown("#### Three scenarios")
            scenario_cards(
                scen, f.price, "Required return",
                lambda row: {
                    g_key: slider_value(row["Growth next year"], -5.0, 15.0, 0.25),
                    tg_key: slider_value(row["Long-term growth"], 0.0, 6.0, 0.25),
                    r_key: slider_value(row["Required return"], 4.0, 16.0, 0.25),
                },
            )
        elif view == SCEN_VIEWS[1]:
            probability_view(lambda lvl: simulate_fund(f, a, level=lvl), f.price, r.value_per_share, "fund share", ticker)
        else:
            st.markdown("#### What if the assumptions are different?")
            st.caption("Estimated value per fund share for a range of required returns (rows) and long-term growth rates (columns).")
            sensitivity_view(index_sensitivity(f, a), f.price, "Return", "required return")

    with t_inside:
        fund_holdings(f)



# --------------------------------------------------------------------------- #
# Compare mode
# --------------------------------------------------------------------------- #

def compare_row(t: str, data) -> dict:
    """One row of the comparison table, using each ticker's default assumptions."""
    if isinstance(data, FundData):
        row = {"Ticker": t, "Name": data.name, "Type": "Fund", "Price": data.price, "P/E": data.pe,
               "Yearly fee": data.expense_ratio * 100}
        if not data.can_value:
            return {**row, "Notes": "Bond fund: no valuation"}
        a = default_index_assumptions(data)
        r = run_index_valuation(data, a)
        return {**row, "Estimated value": r.value_per_share, "Gap vs. price": r.upside * 100,
                "Growth assumed": a.growth_rate * 100, "Growth priced in": implied_index_growth(data, a) * 100,
                "Expected return": r.implied_return * 100, "Notes": ""}
    row = {"Ticker": t, "Name": data.name, "Type": "Bank" if data.is_financial else "Stock",
           "Price": data.price, "P/E": data.pe}
    a = default_assumptions(data)
    blocking, warnings = check_company(data, a.base)
    if blocking:
        return {**row, "Notes": "Can't value: negative cash flow"}
    r = run_dcf(data, a)
    notes = []
    if data.is_financial:
        notes.append("bank method")
    if any("negative" in w or "swung" in w for w in warnings):
        notes.append("uneven cash flow")
    if model_caveats(data, a):
        notes.append("likely too low")
    return {**row, "Estimated value": r.value_per_share, "Gap vs. price": r.upside * 100,
            "Growth assumed": a.growth_rate * 100, "Growth priced in": implied_growth(data, a) * 100,
            "Notes": ", ".join(notes)}


def render_compare() -> None:
    st.session_state.setdefault("compare_list", ["VOO", "QQQ", "AAPL", "JPM"])
    with st.sidebar:
        st.markdown("### 1. Choose up to 6 to compare")
        picks = st.multiselect(
            "From the list", options=list(TICKERS),
            format_func=ticker_label, max_selections=6, key="compare_list",
        )
        extra = st.text_input("Add other tickers", placeholder="e.g. HD, DIS (comma-separated)", key="compare_extra")
    tickers = list(dict.fromkeys(picks + [x.strip().upper() for x in extra.split(",") if x.strip()]))[:6]
    SHARE["c"] = ",".join(tickers)

    with page_head("Compare stocks and funds"):
        share_button()
    st.caption("Each one uses its own default assumptions. Open it in single view to adjust them.")
    if not tickers:
        st.info("Pick at least one stock or fund in the sidebar.")
        return

    # Download in parallel; the disk cache makes repeat visits instant.
    with st.spinner(f"Loading {len(tickers)} tickers… (about 20 seconds for any not downloaded recently)"):
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {t: pool.submit(load, t) for t in tickers}
        rows, failed = [], []
        for t, fut in futures.items():
            try:
                rows.append(compare_row(t, fut.result()))
            except Exception:
                failed.append(t)
    if failed:
        st.warning(f"Couldn't load: {', '.join(failed)}. Check the spelling.", icon="⚠️")
    if not rows:
        return

    df = pd.DataFrame(rows).set_index("Ticker")
    for col in ["Estimated value", "Gap vs. price", "Growth assumed", "Growth priced in", "Expected return", "Yearly fee", "Notes"]:
        if col not in df.columns:
            df[col] = None
    df = df[["Name", "Type", "Price", "Estimated value", "Gap vs. price", "Growth assumed", "Growth priced in",
             "Expected return", "P/E", "Yearly fee", "Notes"]]
    num_cols = ["Price", "Estimated value", "Gap vs. price", "Growth assumed", "Growth priced in",
                "Expected return", "P/E", "Yearly fee"]
    df[num_cols] = df[num_cols].apply(pd.to_numeric, errors="coerce")
    shown = df.copy()
    # Fund-only columns are written as text so stocks show "—" instead of Streamlit's "None".
    shown["Expected return"] = df["Expected return"].map(lambda v: "—" if pd.isna(v) else f"{v:.1f}%")
    shown["Yearly fee"] = df["Yearly fee"].map(lambda v: "—" if pd.isna(v) else f"{v:.2f}%")
    st.dataframe(
        shown, width="stretch", height=35 * (len(df) + 1) + 3,             # every row visible, no inner scroll
        column_config={
            "Name": st.column_config.TextColumn(width=170),
            "Type": st.column_config.TextColumn(width=72),
            "Price": st.column_config.NumberColumn(format="$%.2f", width=72),
            "Estimated value": st.column_config.NumberColumn(
                "Est. value", format="$%.2f", width=72, help="Value per share with default assumptions."),
            "Gap vs. price": st.column_config.NumberColumn(
                "Gap", format="%+.1f%%", width=72, help="Estimated value vs. price. Positive = estimate above the price."),
            "Growth assumed": st.column_config.NumberColumn(
                "Growth", format="%.1f%%", width=72, help="The default growth rate used for the estimate."),
            "Growth priced in": st.column_config.NumberColumn(
                "Priced in", format="%.1f%%", width=72,
                help="Steady yearly growth over the forecast that would justify today's price."),
            "Expected return": st.column_config.TextColumn(
                "Return", width=72, help="Funds only: expected yearly return at today's price, after fees."),
            "P/E": st.column_config.NumberColumn(format="%.1f", width=72),
            "Yearly fee": st.column_config.TextColumn("Fee", width=72, help="Funds only: yearly expense ratio."),
            "Notes": st.column_config.TextColumn(
                width=110, help="'likely too low': heavy investment, a recent dip in cash flow or a very volatile "
                                "stock, which this simple model tends to undervalue. Open it in single view for details."),
        },
    )

    valued = df.dropna(subset=["Gap vs. price"])
    if not valued.empty:
        st.markdown("#### Estimate vs. price")
        v = valued.sort_values("Gap vs. price")
        fig = go.Figure(go.Bar(
            x=v["Gap vs. price"] / 100, y=v.index, orientation="h",
            marker_color=[TEAL if g >= 0 else RED for g in v["Gap vs. price"]],
            text=[f"{g:+.0f}%" for g in v["Gap vs. price"]], textposition="outside", cliponaxis=False,
        ))
        fig.add_vline(x=0, line_color=GREY)
        xs = list(v["Gap vs. price"] / 100)
        chart_layout(fig, height=120 + 50 * len(v), showlegend=False, hovermode="closest",
                     xaxis=dict(tickformat="+.0%", title="Estimated value vs. today's price",
                                range=[min(min(xs), 0) * 1.15 - 0.05, max(max(xs), 0) * 1.15 + 0.05]))
        show(fig)

        st.markdown("#### Growth priced in vs. growth assumed")
        g = valued.dropna(subset=["Growth priced in"])
        fig = go.Figure()
        fig.add_bar(y=g.index, x=g["Growth assumed"] / 100, name="Growth assumed (default)", orientation="h",
                    marker_color=GREY)
        fig.add_bar(y=g.index, x=g["Growth priced in"] / 100, name="Growth priced in by the market", orientation="h",
                    marker_color=BLUE)
        chart_layout(fig, height=140 + 60 * len(g), barmode="group", hovermode="closest",
                     xaxis=dict(tickformat=".0%"))
        show(fig)

    explain(
        "**How to read this:**\n"
        "- **Gap vs. price:** green bars point right when the estimate is *above* today's price (looks cheap), red "
        "bars point left when it's *below* (looks expensive).\n"
        "- **Growth priced in vs. assumed:** the blue bar is how fast each one would need to grow for today's price "
        "to make sense; the grey bar is the model's default guess. When blue is much longer than grey, the market "
        "is far more optimistic than the default assumptions.\n"
        "- **Expected return** (funds) is the yearly return you'd earn buying today if the assumptions hold.\n\n"
        "Stocks and funds use different models, and every number here uses default assumptions, so treat this as "
        "a starting point for comparison, not a ranking of what to buy."
    )


# --------------------------------------------------------------------------- #
# Backtest results
# --------------------------------------------------------------------------- #

GROUP_COLORS = {"Cheapest third": TEAL, "Middle third": GREY, "Most expensive third": RED,
                "All stocks (equal weight)": "#64748b", "S&P 500 (SPY)": AMBER}


def correlation_words(rho: float) -> str:
    if pd.isna(rho):
        return "unknown"
    size = abs(rho)
    strength = ("essentially no" if size < 0.03 else "a very weak" if size < 0.07
                else "a weak" if size < 0.15 else "a moderate")
    direction = "" if size < 0.03 else (" positive" if rho > 0 else " negative")
    return f"{strength}{direction}"


def render_backtest() -> None:
    from dcf.backtest import load_results  # imported here so the page loads even if results are missing

    with page_head("Backtest: did the model's calls work?"):
        share_button()
    st.caption("Every year, the model valued about 70 large US companies using only information available at the "
               "time, then we checked what their share prices actually did over the next 12 months.")
    signals, summary = load_results()
    if summary is None or signals is None or not summary.get("yearly"):
        st.info("No backtest results yet. Run `python run_backtest.py` in the project folder, then reload this page.")
        return

    names = summary["group_names"]
    cheap, dear = names[0], names[-1]
    avg = summary["avg_return"]
    n, beat = summary["n_years"], summary["cheap_beat_expensive"]
    diff = avg[cheap] - avg[dear]
    rho = summary["avg_rank_correlation"]
    period = f"{summary['first_year']}–{summary['last_year'] + 1}"

    if diff > 0.02 and beat > n / 2:
        verdict, color = "The model's \"cheap\" stocks did better, on average", "green"
    elif diff < -0.02 and beat < n / 2:
        verdict, color = "The model's \"cheap\" stocks did worse, on average", "red"
    else:
        verdict, color = "No clear difference between \"cheap\" and \"expensive\" stocks", "orange"
    with st.container(border=True, key=f"verdict_{color}"):
        st.markdown(esc(
            f"#### :{color}[{verdict}]\n"
            f"Over {n} years ({period}), the third of stocks the model rated **cheapest** returned **{avg[cheap]:.1%} a "
            f"year** on average, versus **{avg[dear]:.1%}** for the **most expensive** third: a gap of "
            f"**{diff:+.1%} a year**. The cheapest third came out ahead in **{beat} of {n} years**. Across all stocks, "
            f"the model's gap vs. price had {correlation_words(rho)} relationship with the next year's return "
            f"(rank correlation {rho:+.2f}, where 0 means none and 1 means perfect)."
        ))
        st.caption("Past results don't guarantee future ones, and this test has important limits; see the bottom of "
                   "the page before drawing conclusions.")

    m1, m2, m3, m4 = kpi_row(4, "row5")
    m1.metric("Cheapest third", pct(avg[cheap]), help="Average yearly return, including dividends.")
    m2.metric("Most expensive third", pct(avg[dear]))
    m3.metric("Difference", f"{diff:+.1%}", delta=f"{diff:+.1%} a year")
    m4.metric("Years cheap won", f"{beat} of {n}")

    yearly = pd.DataFrame(summary["yearly"]).set_index("year")
    series = names + ["All stocks (equal weight)", "S&P 500 (SPY)"]

    # ---- Growth of $1 ---------------------------------------------------------
    st.markdown("#### What $1 would have grown to")
    years = list(yearly.index)
    x = [years[0]] + [y + 1 for y in years]
    fig = go.Figure()
    for s in series:
        values = [1.0] + list((1 + yearly[s].fillna(0)).cumprod())
        fig.add_scatter(x=x, y=values, name=s, mode="lines+markers",
                        line=dict(color=GROUP_COLORS.get(s, BLUE), width=3 if s in (cheap, dear) else 2,
                                  dash="dot" if s.startswith("S&P") else "dash" if s.startswith("All") else None))
    chart_layout(fig, height=400, yaxis=dict(tickprefix="$", tickformat=",.2f", title="Value of $1"),
                 xaxis=dict(dtick=1))
    show(fig)
    g1 = summary["growth_of_1"]
    explain(
        "**What this shows:** imagine putting $1 into each group every April and re-picking the stocks each year. "
        f"By {summary['last_year'] + 1}, $1 in the cheapest third grew to **${g1[cheap]:.2f}**, in the most expensive "
        f"third to **${g1[dear]:.2f}**, and in the S&P 500 to **${g1['S&P 500 (SPY)']:.2f}** (all including dividends, "
        "before trading costs and taxes).\n\n"
        "**How to read it:** if the green line (cheap) ends well above the red line (expensive), the model's "
        "valuations helped pick better stocks over this period. The grey line is all ~70 stocks equally weighted, "
        "which shows how much of any outperformance just comes from this group of companies."
    )

    # ---- Year by year -----------------------------------------------------------
    st.markdown("#### Year by year: cheapest third minus most expensive third")
    gap = (yearly[cheap] - yearly[dear]).dropna()
    fig = go.Figure(go.Bar(
        x=[f"{y}–{str(y + 1)[2:]}" for y in gap.index], y=gap.values,
        marker_color=[TEAL if v >= 0 else RED for v in gap.values],
        text=[f"{v:+.0%}" for v in gap.values], textposition="outside", cliponaxis=False,
    ))
    chart_layout(fig, height=340, showlegend=False, hovermode="closest", yaxis=dict(tickformat="+.0%"))
    show(fig)
    explain(
        "**What this shows:** for each 12-month period (April to April), how much better (green, above zero) or "
        "worse (red, below zero) the cheapest third did than the most expensive third.\n\n"
        "**How to read it:** a model with a real, reliable edge would show mostly green bars. Long runs of one "
        "colour usually reflect market fashions; for example, years when fast-growing tech companies (which a DCF "
        "often calls expensive) led the market show up as red."
    )

    # ---- Three-year view ------------------------------------------------------------
    three = summary.get("three_year") or {}
    if three:
        n3, beat3 = summary.get("three_year_n", 0), summary.get("three_year_beat", 0)
        st.markdown("#### Does it work better over 3 years?")
        c1, c2, c3 = st.columns(3)
        c1.metric("Cheapest third, 3 years", f"{three[cheap]:.1%} a year")
        c2.metric("Most expensive third, 3 years", f"{three[dear]:.1%} a year")
        c3.metric("Periods cheap won", f"{beat3} of {n3}")
        gap3 = three[cheap] - three[dear]
        explain(
            "**Why check this:** valuation is often said to matter more over several years than over one, because "
            "prices take time to move towards what a business is worth.\n\n"
            f"**What happened here:** holding each group for 3 years instead of 1, the cheapest third returned "
            f"**{three[cheap]:.1%} a year** and the most expensive third **{three[dear]:.1%}** (a gap of "
            f"**{gap3:+.1%} a year**), with the cheapest third ahead in **{beat3} of {n3}** starting years. "
            + ("So the longer horizon didn't help in this period. That's consistent with 2012–2025 being an era when "
               "fast-growing companies, which cash-flow models tend to rate as expensive, kept winning."
               if gap3 <= 0.005 else
               "So the model's view lined up better with results over the longer horizon.")
        )

    # ---- Scatter -------------------------------------------------------------------
    used = signals[signals["group"].notna()].copy()
    if not used.empty:
        st.markdown("#### Every stock, every year")
        clip = used.assign(upside_c=used["upside"].clip(-1, 2), fwd_c=used["fwd_1y"].clip(-0.8, 1.5))
        fig = go.Figure(go.Scatter(
            x=clip["upside_c"], y=clip["fwd_c"], mode="markers",
            marker=dict(size=7, color=clip["year"], colorscale="Blues", showscale=True,
                        colorbar=dict(title="Year"), line=dict(width=0.5, color="white")),
            text=[f"{t} {y}" for t, y in zip(used["ticker"], used["year"])],
            hovertemplate="%{text}<br>Model gap vs. price: %{x:+.0%}<br>Next-year return: %{y:+.0%}<extra></extra>",
        ))
        fig.add_hline(y=0, line_color=GREY)
        fig.add_vline(x=0, line_color=GREY)
        chart_layout(fig, height=420, hovermode="closest", showlegend=False,
                     xaxis=dict(tickformat="+.0%", title="Model's estimate vs. price (right = looked cheap)"),
                     yaxis=dict(tickformat="+.0%", title="Return over the next 12 months"))
        show(fig)
        explain(
            "**What this shows:** each dot is one stock in one year. Further **right** = the model said it was "
            "cheaper; further **up** = it did better over the next year. Extreme values are pinned to the edges so "
            "the chart stays readable.\n\n"
            "**How to read it:** if the model worked well, dots would drift from bottom-left to top-right. A shapeless "
            "cloud means the valuation alone told you little about the next year. That's common: over one year, share "
            "prices are driven mostly by news, earnings surprises and sentiment."
        )

    # ---- Tables ----------------------------------------------------------------------
    st.markdown("#### Results by year")
    shown = yearly[["stocks"] + series + ["rank_correlation"]].copy()
    shown.index = [f"Apr {y} → Apr {y + 1}" for y in shown.index]
    fmt = {s: "{:+.1%}" for s in series}
    fmt["rank_correlation"] = "{:+.2f}"
    st.dataframe(shown.rename(columns={"stocks": "Stocks valued", "rank_correlation": "Rank correlation"})
                 .style.format({("Rank correlation" if k == "rank_correlation" else k): v for k, v in fmt.items()},
                               na_rep="n/a"),
                 width="stretch")

    st.markdown("#### Look inside a year")
    year = st.selectbox("Year", sorted(signals["year"].unique(), reverse=True),
                        format_func=lambda y: f"April {y} → April {y + 1}", key="bt_year")
    sub = signals[signals["year"] == year].copy()
    sub["Group"] = sub["group"].map(lambda g: names[int(g)] if pd.notna(g) else "")
    sub["Note"] = sub["excluded"].replace({"": ""})
    sub = sub.sort_values("upside", ascending=False)
    st.dataframe(
        sub[["ticker", "price", "value", "upside", "Group", "fwd_1y", "growth", "discount_rate", "Note"]],
        hide_index=True, width="stretch",
        column_config={
            "ticker": "Ticker",
            "price": st.column_config.NumberColumn("Price then", format="$%.2f"),
            "value": st.column_config.NumberColumn("Model value", format="$%.2f"),
            "upside": st.column_config.NumberColumn("Gap vs. price", format="percent"),
            "fwd_1y": st.column_config.NumberColumn("Next 12 months", format="percent"),
            "growth": st.column_config.NumberColumn("Growth used", format="percent"),
            "discount_rate": st.column_config.NumberColumn("Discount rate", format="percent"),
        },
    )
    explain("Sorted from what the model thought was cheapest to most expensive. Compare the *Gap vs. price* column "
            "with *Next 12 months* to see where it was right and wrong. Stocks with a note were skipped that year, "
            "usually because they had negative cash flow or not enough filings yet.")

    # ---- Method and limitations ---------------------------------------------------------
    with st.expander("How this test was done, and its limits", expanded=False):
        st.markdown(
            """
**Method**
- **Dates:** every 1 April from the first year shown, after most companies have filed their annual reports.
- **No peeking:** each valuation uses only annual reports already filed with the SEC by that date, the actual share price that day, the 10-year Treasury yield that day, and beta from the previous two years.
- **Same model as the app:** a 10-year DCF with growth fading to 2.5%, starting from the latest year's cash flow when it had been growing (otherwise the 3-year average), discounted at the WACC with a 4.5% market risk premium (banks: dividends + buybacks at the cost of equity). Growth comes from past sales growth, because analysts' forecasts from back then aren't freely available.
- **Groups:** stocks are ranked by the model's gap vs. price and split into equal thirds. Each group's result is the simple average return (price change plus dividends) over the following 12 months.

**Limits to keep in mind**
- **Survivorship bias:** the list is today's big companies. Firms that shrank, were bought or went bust over the period aren't included, which flatters all groups.
- **Small sample:** about 70 stocks and a dozen or so years. A few big winners (or losers) can swing the results.
- **Short horizons:** results are measured over 1 year (and 3 years in the section above). Valuation signals are often studied over 5–10 years, which this data is too short to test well.
- **One era:** 2012–2025 was dominated by fast-growing technology companies. A model that favours steady cash generators may do differently in other periods.
- **Simplified model and data:** financial items are read automatically from SEC filings using standard labels, and some companies' figures may be missed or misread. Safeguards cross-check share counts and skip estimates above 6× the price as likely data errors; skipped cases are labelled in *Look inside a year*.
- **Mergers and spin-offs:** right after a big deal the latest annual report can describe a different company (e.g. Abbott in April 2013 still included AbbVie, spun off that January), which can mislead the model for a year.
- **No costs:** trading costs and taxes are ignored.
- **The past isn't the future:** even a real historical edge can disappear.
"""
        )
    st.caption("Run `python run_backtest.py` to refresh these results. Not investment advice.")


# --------------------------------------------------------------------------- #
# "How it works" tabs
# --------------------------------------------------------------------------- #

GLOSSARY = """
| Term | In plain English |
|---|---|
| **Free cash flow** | Cash a company has left after paying its bills and investing in itself. The money that could go to owners. |
| **Cash returned to shareholders** | Dividends plus share buybacks: what a company actually hands to its owners. Used for banks. |
| **Discounting** | Converting future money into today's money. \\$100 next year is worth less than \\$100 now, because today's money could be invested in the meantime. |
| **Required return / discount rate** | The yearly return investors want for taking on the risk. The higher it is, the less future cash is worth today. |
| **WACC** | "Weighted average cost of capital": the required return for a company, mixing what shareholders and lenders expect. |
| **Cost of equity** | The return shareholders alone demand. Used instead of WACC for banks. |
| **Terminal value** | The value of every year after the forecast, calculated in one step by assuming steady growth forever. |
| **Growth priced in** | The steady growth rate that would make the estimate equal today's price: what the market seems to expect. |
| **Beta** | How much a stock moves compared with the whole market. 1.0 = moves with the market; 1.5 = about 50% bigger swings. |
| **Market cap** | Share price × number of shares: what the market says the whole company is worth. |
| **Net debt** | Debt minus cash. What would be left owing if the company used its cash to pay down debt. |
| **P/E ratio** | Price ÷ earnings. How many dollars you pay for each \\$1 of yearly profit. |
| **Expense ratio** | A fund's yearly fee, as a percentage of what you've invested. |
| **Index fund** | A fund that buys every company in a market index (like the S&P 500), so you own a slice of all of them. |
"""


def how_it_works_stock(glossary: bool = True) -> None:
    st.markdown("#### How the estimate is made")
    st.markdown(
        """
The idea behind it: **a company is worth the cash it will produce in the future, converted into today's money.**

1. **Start with recent cash.** Take the company's free cash flow: the latest year if it has been growing, otherwise the 3-year average (you can switch).
2. **Forecast it.** Grow it each year at the *growth next year* rate (by default, analysts' forecast), slowing down toward the *long-term growth* rate.
3. **Add the far future.** After the forecast years, assume steady long-term growth forever, and value all of it in one step (the "terminal value").
4. **Convert to today's money.** Shrink every future amount using the *required return*. Money further away shrinks more.
5. **Subtract debt.** Lenders get paid first, so take away debt (minus cash) to get the value for shareholders.
6. **Per share.** Divide by the number of shares and compare with the market price.
7. **Work backwards.** The tool also finds the growth rate that would make the estimate equal today's price: what's *priced in*.

**Banks and insurers** are different: their cash flow swings with deposits, loans and premiums, so the tool values the cash they return to shareholders (dividends + buybacks) at the *cost of equity*, and doesn't subtract debt.

**Companies that burn cash** (negative free cash flow) can't be valued this way, and the tool says so instead of showing a misleading number.
"""
    )
    st.markdown("#### Things to keep in mind")
    st.markdown(
        """
- **It's only as good as the assumptions.** Small changes to the required return or long-term growth can move the answer a lot; the *Scenarios* tab shows how much.
- **"Overvalued" doesn't mean the price will fall.** It means the market expects more growth, or accepts a lower return, than you've assumed. The *growth priced in* figure tells you how much more.
- **It's simplified.** Professional models forecast sales, costs and investment line by line.
- Figures come from company filings (SEC EDGAR) and Yahoo Finance and may be incomplete. This is an educational tool, not investment advice.
"""
    )
    if glossary:
        st.markdown("#### Glossary")
        st.markdown(GLOSSARY)


def how_it_works_fund(glossary: bool = True) -> None:
    st.markdown("#### How the estimate is made")
    st.markdown(
        """
An index fund has no business of its own, so the model treats **all the companies in it as one big company**:

1. **Profit per fund share.** Price ÷ P/E ratio = the slice of yearly profit each fund share represents.
2. **Forecast it.** Grow that profit at the *earnings growth* rate, slowing toward *long-term growth*.
3. **Cash to owners.** Only part of the profit is handed back (dividends and buybacks), so multiply by the *share of profit paid to owners*.
4. **Convert to today's money** using the *required return* plus the fund's yearly fee, and add the far-future terminal value.
5. **Compare with the price.** The tool also works backwards to find the **expected yearly return** at today's price, and the **growth priced in**.
"""
    )
    st.markdown("#### Things to keep in mind")
    st.markdown(
        """
- **High prices usually mean lower future returns, not necessarily a crash.** Valuation says little about the next year or two, but more about the next ten.
- The default growth (6%) and payout (85%) are general starting points, not figures from each fund's own history.
- Bond funds can't be valued this way, because they hold loans rather than companies with profits.
- This is an educational tool, not investment advice.
"""
    )
    if glossary:
        st.markdown("#### Glossary")
        st.markdown(GLOSSARY)


# --------------------------------------------------------------------------- #
# Page
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# Home
# --------------------------------------------------------------------------- #

POPULAR_STOCKS = [("AAPL", "Apple"), ("MSFT", "Microsoft"), ("NVDA", "NVIDIA"), ("AMZN", "Amazon"),
                  ("KO", "Coca-Cola"), ("COST", "Costco"), ("JPM", "JPMorgan")]
POPULAR_FUNDS = [("VOO", "S&P 500"), ("QQQ", "Nasdaq-100"), ("VTI", "Total US market"), ("SCHD", "Dividend stocks")]


def open_ticker(t: str) -> None:
    """Button callback: show one stock or fund."""
    t = (t or "").strip().upper()
    if not t:
        return
    st.session_state["mode"] = MODES["single"]
    if t in TICKERS:
        st.session_state["list_ticker"] = t
        st.session_state["custom_ticker"] = ""
    else:
        st.session_state["list_ticker"] = None
        st.session_state["custom_ticker"] = t


def _picked_from_list() -> None:
    st.session_state["custom_ticker"] = ""   # a list choice replaces any typed ticker


def open_mode(code: str) -> None:
    st.session_state["mode"] = MODES[code]


def _search_submitted() -> None:
    open_ticker(st.session_state.get("home_search", ""))
    st.session_state["home_search"] = ""


def popular_row(key: str) -> None:
    """Popular stocks and funds as one-click buttons, labelled with their names."""
    for label, items in (("Popular stocks", POPULAR_STOCKS), ("Popular index funds", POPULAR_FUNDS)):
        st.markdown(f'<div class="pop-label">{label}</div>', unsafe_allow_html=True)
        row = st.container(horizontal=True, gap="small")
        for t, name in items:
            row.button(f"{name} · {t}", key=f"{key}_{t}", on_click=open_ticker, args=(t,))


def render_home() -> None:
    st.markdown(
        '<div class="hero"><h1>📈 Stock &amp; Fund Valuation</h1>'
        "<p>Find out what a stock or index fund is worth, what its price is betting on, and how your own "
        "portfolio could grow. Made for beginners: every chart explains itself.</p></div>",
        unsafe_allow_html=True,
    )

    with st.container(border=True, key="card_search"):
        st.markdown("#### 🔎 Look up a stock or fund")
        row = st.container(horizontal=True, gap="small", vertical_alignment="bottom")
        row.text_input("Ticker", key="home_search", placeholder="Type a ticker, e.g. AAPL, HD or VOO, and press Enter",
                       on_change=_search_submitted, label_visibility="collapsed", width="stretch")
        row.button("Go", key="home_go", type="primary", on_click=_search_submitted)
        popular_row("home_pop")

    st.markdown("#### What would you like to do?")
    cards = [
        ("single", "🔎 Value a stock or fund", "See what it's worth, what the price assumes and how it could move.",
         "Value a stock"),
        ("compare", "⚖️ Compare", "Put up to six stocks and funds side by side with the same yardstick.",
         "Compare"),
        ("portfolio", "🧺 My portfolio", "Enter what you own: see your mix, expected return and future value.",
         "Open my portfolio"),
        ("backtest", "🧪 Does the model work?", "How the model's calls on ~70 companies turned out since 2012.",
         "See the results"),
    ]
    cols = st.columns(4)
    for col, (code, title, text, cta) in zip(cols, cards):
        with col, st.container(border=True, key=f"card_home_{code}", height="stretch",
                               vertical_alignment="distribute"):
            st.html(f'<div class="home-card"><h4>{html.escape(title)}</h4><p>{html.escape(text)}</p></div>')
            st.button(f"{cta} →", key=f"home_open_{code}", on_click=open_mode, args=(code,), width="stretch")

    st.markdown("#### New here? Three steps")
    steps = [
        ("Pick a stock or fund", "Search above, or click one of the popular names."),
        ("Read the verdict", "A coloured box says whether it looks cheap, fair or expensive, and why."),
        ("Try your own view", "Move the sliders in the sidebar. The whole page updates as you go."),
    ]
    for col, (i, (head, text)) in zip(st.columns(3), enumerate(steps, 1)):
        col.html(f'<div class="step"><div class="num">{i}</div><div><b>{html.escape(head)}</b>'
                 f'<span>{html.escape(text)}</span></div></div>')

    st.markdown("#### Learn the basics")
    with st.expander("How a stock is valued (DCF)"):
        how_it_works_stock(glossary=False)
    with st.expander("How an index fund is valued"):
        how_it_works_fund(glossary=False)
    with st.expander("Glossary of terms"):
        st.markdown(GLOSSARY)


st.session_state.setdefault("mode", MODES["home"])
mode_code = {v: k for k, v in MODES.items()}.get(st.session_state["mode"], "home")
with st.sidebar:
    st.markdown('<div class="side-brand"><div class="logo">📈</div><div><b>Valuation Lab</b>'
                '<span>Stocks &amp; index funds, explained</span></div></div>', unsafe_allow_html=True)
    st.markdown('<div class="side-label">Menu</div>', unsafe_allow_html=True)
    for code, label in NAV:
        st.button(label, key=f"nav_{code}", on_click=open_mode, args=(code,), width="stretch",
                  type="primary" if code == mode_code else "secondary")
    st.divider()
if mode_code not in ("home", "single"):
    SHARE["m"] = mode_code
if is_dark():
    SHARE["dark"] = 1

if mode_code == "home":
    render_home()
elif mode_code == "compare":
    render_compare()
elif mode_code == "backtest":
    render_backtest()
elif mode_code == "portfolio":
    render_portfolio()
else:
    with st.sidebar:
        st.markdown("### 1. Choose a stock or fund")
        # Two fields on purpose: one box that accepts both would match a typed "HD" to SCHD on Enter.
        choice = st.selectbox(
            "From the list",
            options=list(TICKERS),
            index=None,
            placeholder="Search by name or ticker…",
            format_func=ticker_label,
            key="list_ticker",
            on_change=_picked_from_list,
            help="Common stocks and index funds. Click and type to search the list.",
        )
        custom = st.text_input(
            "Or type any other ticker",
            key="custom_ticker",
            placeholder="e.g. HD, DIS, VIG",
            help="A ticker is the short code a stock trades under (Home Depot = HD). Overrides the list while filled in.",
        )
    ticker = (custom or choice or "").strip().upper()

    data = None
    if not ticker:
        SHARE["m"] = "single"
        page_head("Choose a stock or fund")
        st.markdown("Search the list in the sidebar, type any ticker there, or start with a popular one:")
        popular_row("single_pop")
    else:
        try:
            with st.spinner(f"Downloading {ticker}'s data from SEC filings and Yahoo Finance… "
                            "(about 20 seconds the first time)"):
                data = fetch(ticker)
        except Exception as e:
            st.error(f"Couldn't load **{ticker}**: {e}\n\nCheck the ticker is spelled correctly "
                     "(for example AAPL for Apple).")
    if data is not None:
        if isinstance(data, FundData):
            render_fund(data, ticker)
        else:
            render_company(data, ticker)
        data_freshness(ticker)

with st.sidebar:
    if mode_code in ("single", "compare"):   # these pages add their own controls above
        st.divider()
    st.toggle("🌙 Dark mode", key="dark", help="Switch the page to dark colours.")

st.divider()
st.markdown('<div class="footer">Company filings from SEC EDGAR · prices and fund data from Yahoo Finance · '
            "For learning purposes only, not investment advice.</div>", unsafe_allow_html=True)
sync_url()
