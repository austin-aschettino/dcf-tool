# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Delegated: stays on Streamlit (Python), deployed on Streamlit Cloud. The valuation engine, data loaders, caching and every page are Python, so the design is expressed through `.streamlit/config.toml`, the injected CSS in `app.py`, Plotly chart styling and Streamlit's own components rather than a separate front end.

## Users

Three audiences, all with the same core job: understand what a stock or index fund is worth and why, without already knowing valuation.

- **Beginner investors**: members of the public looking at a stock before buying it.
- **Finance students**: people learning DCF, multiples and reverse DCF who want to see the mechanics move.
- **The author's portfolio audience**: employers and peers looking at the project as evidence of finance and engineering skill.

## Product Purpose

Estimates what a stock or index fund is worth from the cash it is expected to produce, then explains every step in plain English. Success is a visitor who leaves knowing what the price assumes, how wide the honest range of values is, and which assumptions move the answer.

## Positioning

A valuation tool that teaches while it values and refuses false precision: several methods side by side instead of one model number, the growth the price is betting on stated as one sentence, and open admissions when the simple model is probably wrong for a company.

## Operating Context

- Entry is a ticker: picked from a list of common stocks and funds, or typed.
- Pages: Home, Value a stock or fund (stocks, banks and index funds each handled differently), Compare (up to 6), My portfolio, Does the model work? (backtest since 2012).
- Assumptions are changed with sliders; scenarios can be loaded into them.
- Used on desktop and on phones.
- Data comes from SEC EDGAR filings and Yahoo Finance; first load of a ticker takes about 20 seconds, then it is cached for 12 hours.
- A command-line report (`main.py`) and a backtest script exist alongside the dashboard.

## Capabilities and Constraints

- Stocks valued with a DCF; banks and insurers from cash returned to shareholders; index funds as one combined business with an expected yearly return; cash-burning companies get an explanation instead of a number.
- Fair value by method (football field), what's priced in (reverse DCF), scenarios, a 5,000-run probability view, what-if grid, price outlook, quality scorecard, peer comparison.
- Shareable links (the URL holds ticker and slider settings) and an Excel export.
- Dark mode is a supported theme.
- Educational only: never investment advice, never a prediction.

## Brand Commitments

- Name: "Stock & Fund Valuation".
- Voice: plain English for a non-expert; jargon only when named and explained.
- Honesty is binding: show ranges, say when methods disagree, flag known blind spots, and label anything that is not a prediction.
- The footer's "For learning purposes only, not investment advice" stays.

## Evidence on Hand

- Real backtest results in `results/` and the README (cheapest third vs most expensive third, 2012 onwards). The edge is small and the README says so; never present it as stronger.
- No testimonials, users, press or logos exist. Do not invent any.

## Product Principles

1. Explain before impressing: every number earns a sentence a beginner can follow.
2. Ranges over points: show the spread and the disagreement, not one confident figure.
3. Say what the price assumes, not just what the model says.
4. Admit the model's limits where they apply, in the place they apply.
5. The answer first, the mechanics one step away.
