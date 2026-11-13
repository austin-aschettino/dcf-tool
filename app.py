"""Beginner-friendly valuation dashboard for stocks and index funds.

Run with:  streamlit run app.py
"""

from __future__ import annotations

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
)

st.set_page_config(page_title="Stock & Fund Valuation", page_icon="📈", layout="wide")

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

BLUE = "#2563eb"
GREY = "#94a3b8"
AMBER = "#f59e0b"
TEAL = "#0f766e"
RED = "#dc2626"
GREEN_BG = "background-color: rgba(22,163,74,0.28)"
RED_BG = "background-color: rgba(220,38,38,0.22)"
CURRENT_CELL = "font-weight: 800; outline: 3px solid #2563eb; outline-offset: -3px"
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
    sign = "-" if x < 0 else ""
    x = abs(x)
    for unit, div in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if x >= div:
            return f"{sign}${x / div:,.2f}{unit}"
    return f"{sign}${x:,.2f}"


def pct(x, digits: int = 1) -> str:
    return "n/a" if x is None or pd.isna(x) else f"{x:.{digits}%}"


def esc(s: str) -> str:
    """Escape $ so Streamlit doesn't read $...$ as a math formula."""
    return s.replace("$", r"\$")


def scale_for(values) -> tuple:
    """Pick billions or millions for chart axes so labels read '$2.0B', not '$2.0G'."""
    biggest = max((abs(v) for v in values if pd.notna(v)), default=0)
    return (1e9, "B") if biggest >= 1e9 else (1e6, "M")


def explain(text: str) -> None:
    """A beginner explanation box, shown only while 'Show explanations' is on."""
    if st.session_state.get("explain", True):
        st.info(esc(text), icon="💡")


def chart_layout(fig: go.Figure, height: int = 380, **kw) -> go.Figure:
    layout = dict(
        height=height,
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", y=-0.18, x=0),
        hovermode="x unified",
    )
    layout.update(kw)  # callers can override any default
    fig.update_layout(**layout)
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

def verdict_box(name: str, value: float, price: float, upside: float, noun: str, extra: str = "") -> None:
    if upside > 0.15:
        tone, color = "looks **undervalued**", "green"
    elif upside < -0.15:
        tone, color = "looks **overvalued**", "red"
    else:
        tone, color = "looks **roughly fairly priced**", "orange"
    # Phrase it the same way as the "Gap vs. price" metric (value / price - 1) so the numbers match.
    if abs(upside) < 0.005:
        where = "almost exactly the same as"
    else:
        where = f"{abs(upside):.0%} {'above' if upside > 0 else 'below'}"
    with st.container(border=True):
        st.markdown(
            esc(
                f"#### :{color}[{name} {tone}]\n"
                f"Based on your assumptions, the model estimates it's worth **${value:,.2f}** per {noun}, "
                f"{where} today's price of **${price:,.2f}**.\n\n{extra}"
            )
        )
        st.caption(
            "This is what the math says *given the assumptions in the sidebar*, not a prediction of where the "
            "price will go. Change the assumptions and the answer changes."
        )


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


def download_button(tables, ticker: str) -> None:
    try:
        data = to_xlsx(tables)
    except Exception as e:  # never break the page over an export problem
        st.caption(f"Report download unavailable: {e}")
        return
    st.download_button(
        "⬇️ Download full report (Excel)",
        data=data,
        file_name=f"{ticker}-valuation-{date.today().isoformat()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        help="A spreadsheet with the summary, assumptions, forecast, scenarios, what-if grid and past data.",
    )


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
    for col, (name, row) in zip(cols, table.iterrows()):
        with col, st.container(border=True):
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
                  fillcolor="rgba(37,99,235,0.10)", line_width=0, layer="below")
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
    with st.container(border=True):
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
                        fillcolor="rgba(37,99,235,0.10)", name="Wide range (19 in 20)", hoverinfo="skip")
        fig.add_scatter(x=path.index, y=path["likely_high"], mode="lines", line=dict(width=0),
                        showlegend=False, hoverinfo="skip")
        fig.add_scatter(x=path.index, y=path["likely_low"], mode="lines", line=dict(width=0), fill="tonexty",
                        fillcolor="rgba(37,99,235,0.25)", name="Likely range (2 in 3)", hoverinfo="skip")
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
            return "color: #15803d" if v >= 0 else "color: #dc2626"

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
    s1, s2, s3 = st.columns(3)
    s1.metric("Market value (market cap)", money(c.market_cap),
              help="Share price × number of shares: what the stock market says the whole company is worth.")
    s2.metric("Debt minus cash", money(c.net_debt),
              help="What the company owes, minus the cash it holds. Subtracted from the business value "
                   "(except for banks, where it's part of normal business).")
    s3.metric("Shares", f"{c.shares_outstanding / 1e6:,.1f}M", help="How many pieces the company is divided into.")
    s4, s5, s6 = st.columns(3)
    s4.metric("Beta", f"{c.beta:.2f}",
              help="How much the stock swings compared with the overall market. 1.0 = same as the market; "
                   "higher = bumpier, which raises the required return.")
    s5.metric("P/E ratio", f"{c.pe:.1f}" if c.pe else "n/a",
              help="Share price ÷ yearly profit per share: how many dollars you pay for $1 of profit.")
    s6.metric("Analysts' growth forecast", pct(c.analyst_growth),
              help="Analysts' consensus estimate of next year's earnings growth, from Yahoo Finance.")

    st.markdown("#### Past financials")
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


def render_company(c, ticker: str) -> None:
    k = lambda name: f"{name}__{ticker}"  # widget keys, per ticker so defaults reset on change
    payout = c.is_financial
    cash_name = "cash returned to shareholders" if payout else "free cash flow"
    rate_name = "Cost of equity" if payout else "Required return (discount rate)"

    st.markdown(f"## {c.name} ({c.ticker})")
    method = ("valued from cash returned to shareholders (a method suited to banks and insurers)" if payout
              else "valued with a discounted cash flow (DCF) model")
    st.caption(f"Stock · {method} · price in {c.currency}")

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
        base = st.radio(
            "Start cash flow from",
            ["avg3", "latest"],
            format_func=lambda b: "3-year average" if b == "avg3" else "Latest year",
            key=k("base"), horizontal=True,
            help="The average smooths out one unusually good or bad year; the latest year reflects the "
                 "company's most recent performance.",
        )

    d = default_assumptions(c, growth_source=src, base=base)
    _, growth_label = default_growth(c, src)
    blocking, warnings = check_company(c, base)

    if blocking:
        with st.container(border=True):
            st.markdown("#### :orange[No valuation for this company]")
            st.write(blocking)
        warnings_box(warnings)
        t_outlook, t_data, t_how = st.tabs(['🎯 Price outlook', '🏢 Company data', '📖 How it works'])
        with t_outlook:
            outlook_tab(c, d, ticker, "share")
        with t_data:
            company_data_tab(c)
        with t_how:
            how_it_works_stock()
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

    a = DCFAssumptions(growth_rate=growth, terminal_growth=terminal, wacc=wacc, years=years, fade=fade, base=base)
    r = run_dcf(c, a)
    g_implied = implied_growth(c, a)
    scen = company_scenarios(c, a)

    warnings_box(warnings)
    tail = priced_in_sentence(g_implied, growth, years, terminal, cash_name)
    if r.terminal_share > 0.75:
        tail += (f"\n\n📌 {r.terminal_share:.0%} of this estimate comes from years after the forecast, "
                 "so it's very sensitive to the long-term assumptions.")
    verdict_box(c.name, r.value_per_share, c.price, r.upside, "share", tail)
    download_button(company_tables(c, a, r, fetch_history(ticker)), ticker)

    t_overview, t_outlook, t_forecast, t_scen, t_data, t_how = st.tabs(['📊 Overview', '🎯 Price outlook', '🔮 Forecast', '🎛️ Scenarios & what-if', '🏢 Company data', '📖 How it works'])

    # ---- Overview ----------------------------------------------------------
    with t_overview:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Estimated value / share", f"${r.value_per_share:,.2f}",
                  help="What the model thinks one share is worth, based on the cash the company should produce.")
        m2.metric("Current price", f"${c.price:,.2f}", help="What one share costs on the stock market right now.")
        m3.metric("Gap vs. price", f"{r.upside:+.1%}", delta=f"{r.upside:+.1%}",
                  help="How far the price would have to move to match the estimate. Negative = the price is above the estimate.")
        m4.metric("Growth priced in", pct(g_implied),
                  delta=(f"{g_implied - growth:+.1%} vs. your setting" if pd.notna(g_implied) else None),
                  delta_color="inverse",
                  help=f"The steady yearly growth in {cash_name} over the next {years} years that would make the "
                       "estimate equal today's price. Higher than your setting = the market expects more than you do.")

        st.markdown("#### Where the value comes from")
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
        chart_layout(fig, yaxis=dict(ticksuffix=unit, tickprefix="$", title=f"$ {'billions' if unit == 'B' else 'millions'}"))
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
        st.markdown("#### Three scenarios")
        scenario_cards(
            scen, c.price, rate_name.split(" (")[0],
            lambda row: {
                g_key: slider_value(row["Growth next year"], -10.0, 30.0, 0.5),
                tg_key: slider_value(row["Long-term growth"], 0.0, 5.0, 0.25),
                w_key: slider_value(row["Required return"], 4.0, 16.0, 0.25),
            },
        )
        st.markdown("#### What if the assumptions are different?")
        st.caption("Estimated value per share for a range of required returns (rows) and long-term growth rates (columns).")
        sensitivity_view(sensitivity_table(c, a), c.price, "Return", rate_name.lower())

    with t_data:
        company_data_tab(c)

    with t_how:
        how_it_works_stock()


# --------------------------------------------------------------------------- #
# Index funds
# --------------------------------------------------------------------------- #

def fund_facts(f: FundData) -> None:
    k1, k2, k3, k4 = st.columns(4)
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
    st.markdown(f"## {f.name} ({f.ticker})")
    st.caption(" · ".join(x for x in ["Index fund", kind, f.family, f.category] if x))

    if not f.can_value:
        with st.container(border=True):
            st.markdown("#### No valuation for this fund")
            st.write(
                "This fund has no P/E ratio, which usually means it holds bonds rather than stocks. The valuation "
                "model works by valuing the earnings of the companies a fund owns, so it only applies to stock funds."
            )
        fund_facts(f)
        fund_holdings(f)
        st.divider()
        outlook_tab(f, default_index_assumptions(f), ticker, "fund share")
        return

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
    download_button(fund_tables(f, a, r, fetch_history(ticker)), ticker)

    t_overview, t_outlook, t_forecast, t_scen, t_inside, t_how = st.tabs(['📊 Overview', '🎯 Price outlook', '🔮 Forecast', '🎛️ Scenarios & what-if', "🧺 What's inside", '📖 How it works'])

    with t_overview:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Estimated value / share", f"${r.value_per_share:,.2f}",
                  help="What the model thinks one share of the fund is worth.")
        m2.metric("Current price", f"${f.price:,.2f}")
        m3.metric("Gap vs. price", f"{r.upside:+.1%}", delta=f"{r.upside:+.1%}",
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
        st.markdown("#### Three scenarios")
        scenario_cards(
            scen, f.price, "Required return",
            lambda row: {
                g_key: slider_value(row["Growth next year"], -5.0, 15.0, 0.25),
                tg_key: slider_value(row["Long-term growth"], 0.0, 6.0, 0.25),
                r_key: slider_value(row["Required return"], 4.0, 16.0, 0.25),
            },
        )
        st.markdown("#### What if the assumptions are different?")
        st.caption("Estimated value per fund share for a range of required returns (rows) and long-term growth rates (columns).")
        sensitivity_view(index_sensitivity(f, a), f.price, "Return", "required return")

    with t_inside:
        fund_holdings(f)

    with t_how:
        how_it_works_fund()


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
    row = {"Ticker": t, "Name": data.name, "Type": "Bank/insurer" if data.is_financial else "Stock",
           "Price": data.price, "P/E": data.pe}
    a = default_assumptions(data)
    blocking, warnings = check_company(data, a.base)
    if blocking:
        return {**row, "Notes": "Can't value: negative cash flow"}
    r = run_dcf(data, a)
    notes = []
    if data.is_financial:
        notes.append("valued from dividends + buybacks")
    if any("negative" in w or "swung" in w for w in warnings):
        notes.append("uneven cash flow")
    return {**row, "Estimated value": r.value_per_share, "Gap vs. price": r.upside * 100,
            "Growth assumed": a.growth_rate * 100, "Growth priced in": implied_growth(data, a) * 100,
            "Notes": ", ".join(notes)}


def render_compare() -> None:
    with st.sidebar:
        st.markdown("### 1. Choose up to 6 to compare")
        picks = st.multiselect(
            "From the list", options=list(TICKERS), default=["VOO", "QQQ", "AAPL", "JPM"],
            format_func=ticker_label, max_selections=6, key="compare_list",
        )
        extra = st.text_input("Add other tickers", placeholder="e.g. HD, DIS (comma-separated)", key="compare_extra")
    tickers = list(dict.fromkeys(picks + [x.strip().upper() for x in extra.split(",") if x.strip()]))[:6]

    st.markdown("## Compare stocks and funds")
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
    st.dataframe(
        df, width="stretch",
        column_config={
            "Price": st.column_config.NumberColumn(format="$%.2f"),
            "Estimated value": st.column_config.NumberColumn(format="$%.2f", help="Value per share with default assumptions."),
            "Gap vs. price": st.column_config.NumberColumn(format="%+.1f%%", help="Positive = estimate above the price."),
            "Growth assumed": st.column_config.NumberColumn(format="%.1f%%", help="The default growth rate used."),
            "Growth priced in": st.column_config.NumberColumn(
                format="%.1f%%", help="Steady yearly growth over the forecast that would justify today's price."),
            "Expected return": st.column_config.NumberColumn(format="%.1f%%", help="Funds only: yearly return at today's price."),
            "P/E": st.column_config.NumberColumn(format="%.1f"),
            "Yearly fee": st.column_config.NumberColumn(format="%.2f%%", help="Funds only: expense ratio."),
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
        chart_layout(fig, height=120 + 50 * len(v), showlegend=False, hovermode="closest",
                     xaxis=dict(tickformat="+.0%", title="Estimated value vs. today's price"))
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

    st.markdown("## Backtest: did the model's calls work?")
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
    with st.container(border=True):
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

    m1, m2, m3, m4 = st.columns(4)
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
- **Same model as the app:** a 5-year DCF with growth fading to 2.5%, discounted at the WACC (banks: dividends + buybacks at the cost of equity). Growth comes from past sales growth, because analysts' forecasts from back then aren't freely available.
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


def how_it_works_stock() -> None:
    st.markdown("#### How the estimate is made")
    st.markdown(
        """
The idea behind it: **a company is worth the cash it will produce in the future, converted into today's money.**

1. **Start with recent cash.** Take the company's free cash flow: the 3-year average, or the latest year if you choose.
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
- **It's only as good as the assumptions.** Small changes to the required return or long-term growth can move the answer a lot; the *Scenarios & what-if* tab shows how much.
- **"Overvalued" doesn't mean the price will fall.** It means the market expects more growth, or accepts a lower return, than you've assumed. The *growth priced in* figure tells you how much more.
- **It's simplified.** Professional models forecast sales, costs and investment line by line.
- Data comes from Yahoo Finance and may be incomplete. This is an educational tool, not investment advice.
"""
    )
    st.markdown("#### Glossary")
    st.markdown(GLOSSARY)


def how_it_works_fund() -> None:
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
    st.markdown("#### Glossary")
    st.markdown(GLOSSARY)


# --------------------------------------------------------------------------- #
# Page
# --------------------------------------------------------------------------- #

def _picked_from_list():
    st.session_state["custom_ticker"] = ""  # a list choice replaces any typed ticker


if "explain" not in st.session_state:
    st.session_state["explain"] = True

with st.sidebar:
    mode = st.radio("What do you want to do?", ["One stock or fund", "Compare several", "Backtest results"],
                    key="mode", help="Backtest results: how the model's past calls actually turned out.")

st.title("📈 Stock & Fund Valuation")
st.markdown("Estimate what a stock or index fund is worth, based on the cash it's expected to produce.")

if mode == "Compare several":
    render_compare()
elif mode == "Backtest results":
    render_backtest()
else:
    with st.sidebar:
        st.markdown("### 1. Choose a stock or fund")
        choice = st.selectbox(
            "From the list",
            options=list(TICKERS),
            index=list(TICKERS).index("AZO"),
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

    if not ticker:
        st.info("Pick a stock or fund in the sidebar to begin.")
        st.stop()

    try:
        with st.spinner(f"Downloading {ticker}'s financial data from Yahoo Finance… (about 20 seconds the first time)"):
            data = fetch(ticker)
    except Exception as e:
        st.error(f"Couldn't load **{ticker}**: {e}\n\nCheck the ticker is spelled correctly (for example AAPL for Apple).")
        st.stop()

    if isinstance(data, FundData):
        render_fund(data, ticker)
    else:
        render_company(data, ticker)
    data_freshness(ticker)

with st.sidebar:
    st.divider()
    st.toggle("Show beginner explanations", key="explain",
              help="Shows a 💡 box under each chart and table explaining what it means.")

st.divider()
st.caption("Data from Yahoo Finance via yfinance. For learning purposes only, not investment advice.")
