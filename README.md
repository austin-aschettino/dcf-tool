# 📈 Stock & Fund Valuation

[![Tests](https://github.com/austin-aschettino/dcf-tool/actions/workflows/tests.yml/badge.svg)](https://github.com/austin-aschettino/dcf-tool/actions/workflows/tests.yml)

A beginner-friendly tool that estimates what a stock or index fund is worth, based on the cash it's expected to produce. It comes as an interactive web dashboard (Streamlit) and a command-line report.

- **Stocks** are valued with a discounted cash flow (DCF) model: forecast the company's free cash flow, convert it to today's money, subtract debt, divide by shares.
- **Banks and insurers** are detected automatically and valued from the cash they return to shareholders (dividends + buybacks), because their free cash flow isn't meaningful.
- **Index funds** (VOO, SPY, QQQ, …) are valued as if all their companies were one big business, with an **expected yearly return** at today's price.
- **Companies that burn cash** get a clear explanation instead of a misleading number.

Everything is explained in plain English inside the app: every chart and table has a 💡 *What does this mean?* note you can open.

> Educational tool only, not investment advice. Company financial statements come from the SEC's [EDGAR](https://www.sec.gov/edgar) database (the companies' own filings), with Yahoo Finance as a fallback for companies that don't file with the SEC. Share prices, debt and cash, analyst estimates and fund data come from Yahoo Finance via [yfinance](https://github.com/ranaroussi/yfinance) and may be incomplete.

## Features

| | |
|---|---|
| **Plain-English verdict** | "AutoZone looks roughly fairly priced: worth about $3,461, 6% above today's price." |
| **What's priced in** | The growth rate the current price implies, e.g. *"Apple would need to grow 34% a year for 5 years."* |
| **Reverse DCF** | Works backwards from today's price: the growth and return the market is betting on, how demanding that is compared with the company's track record, the cash flow the price needs, and a grid of growth priced in for other required returns and time frames. |
| **Scenarios** | Pessimistic / middle / optimistic estimates, each loadable into the sliders with one click. |
| **Probability view** | Runs the valuation 5,000 times with assumptions drawn around yours, and shows the range of values and the chance today's price is justified. |
| **What-if grid** | Value across a range of required returns and long-term growth rates, coloured against the price. |
| **Price outlook** | Where the price could be in 1, 3 or 5 years: the typical range from past price swings, the model's fair value, and analysts' 12-month targets, with upside and downside for each. |
| **Price history** | 5 years of prices against the estimate and the scenario range. |
| **Quality check** | A plain-English scorecard of the business: margins, cash-flow margin, return on assets, debt load, sales growth and how steady the cash is (banks get bank-specific checks). |
| **Similar companies** | P/E, forward P/E, EV/EBITDA and cash-flow yield next to similar large companies, plus what the share would cost if priced like them. |
| **Home page** | A starting point with ticker search, popular tickers, shortcuts to each part of the app and a short guide to how valuation works. |
| **My portfolio** | Enter what you own (at today's market value): total value, expected return a year, sector mix (looking inside funds), which holdings have demanding prices, and a **future value** calculator with monthly additions and a range of outcomes. |
| **Compare mode** | Up to 6 stocks and funds side by side. |
| **Backtest** | Tests the model on history: every year since 2012, value ~70 large companies using only information available at the time, and check whether the "cheap" ones beat the "expensive" ones over the next 12 months. |
| **Excel export** | Download the full report (summary, assumptions, forecast, scenarios, what-if, past data). |
| **Shareable links** | The page address holds the ticker and slider settings, so a link opens the exact same view. The 🔗 Share button copies it. |
| **Dark mode** | A toggle at the bottom of the sidebar. |
| **Fast reloads** | Downloaded data is saved for 12 hours, so reopening a ticker is instant. |

## Getting started

You need Python 3.9 or newer.

```bash
git clone <your-repo-url> dcf-tool
cd dcf-tool
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### The dashboard

```bash
streamlit run app.py
```

Then open the address it prints (usually http://localhost:8501). Pick a stock or fund in the sidebar, or type any ticker.

### The command-line report

```bash
python main.py AZO                          # a stock
python main.py JPM                          # a bank (valued from dividends + buybacks)
python main.py VOO                          # an index fund
python main.py AAPL --growth 0.08 --wacc 0.09 --terminal 0.025 --years 10
python main.py AAPL --base latest --growth-source history
python main.py QQQ --return 0.09 --payout 0.8
python main.py AZO --export azo.xlsx        # save the report as a spreadsheet
python main.py AZO --refresh                # ignore saved data and download again
python main.py AAPL --horizon 3             # price outlook 3 years ahead (1, 3 or 5)
```

Run `python main.py --help` for every option.

## Backtest

```bash
python run_backtest.py                      # ~70 companies, 2012 to the latest complete year
python run_backtest.py --first 2015 --tickers AAPL MSFT KO PEP JNJ
```

Each year on 1 April, every stock is valued **as of that day**, with no look-ahead:

- **Financials:** only annual reports already filed with the SEC, read from [SEC EDGAR](https://www.sec.gov/edgar)'s free company-facts data (restated figures count only once they're filed).
- **Price:** the price that actually traded that day (later stock splits undone).
- **Risk-free rate:** the 10-year Treasury yield that day. **Beta:** from the previous two years of weekly returns.
- **Growth:** past sales growth (historical analyst forecasts aren't freely available).

Stocks are split into thirds by the model's gap vs. price, and each third's average total return over the next 12 months is compared, along with the S&P 500. Results are saved to `results/` and shown on the dashboard's **Backtest results** page. The first run downloads about 10 years of filings and prices per company (a few minutes); later runs reuse them.

**What it found (April 2012 – April 2026, ~66 stocks a year, 922 valuations):**

| Group (by model's gap vs. price) | Avg return, next 12 months | Avg return a year, next 3 years |
|---|---|---|
| Cheapest third | 16.4% | 13.4% |
| Middle third | 15.2% | 12.2% |
| Most expensive third | 17.5% | 15.3% |
| S&P 500 (SPY) | 15.1% | – |

The model's "cheap" stocks did **not** beat its "expensive" ones: the cheapest third won in 5 of 14 years over 12 months and 0 of 12 periods over 3 years, and the rank correlation between the model's gap and the next year's return was about zero. That's consistent with 2012–2025 being dominated by fast-growing companies that cash-flow models tend to rate as expensive, and a reminder that a valuation estimate is a starting point for judgement, not a trading signal.

**Limits:** the universe is today's large companies (survivorship bias), the sample is small, and a 1-year horizon is short for a valuation signal. See the dashboard page for details.

## How it works

1. **Starting cash flow:** the company's free cash flow (3-year average, or latest year).
2. **Growth:** analysts' forecast of next year's earnings growth by default (or past sales growth), fading to a long-term rate (2.5%).
3. **Terminal value:** every year after the forecast, valued in one step assuming steady growth forever.
4. **Discounting:** future cash is converted to today's money at the required return. That's the WACC for ordinary companies, or the cost of equity for banks, both estimated from the stock's beta.
5. **Per share:** subtract net debt (not for banks), divide by shares, compare with the price.
6. **Reverse DCF:** solve for the steady growth rate that would make the estimate equal today's price.

Index funds use the same idea on the fund's combined earnings (price ÷ P/E), the share paid to owners, and the fund's fee.

## Project layout

```
app.py              Streamlit dashboard
main.py             command-line report
dcf/
  data.py           company financials (SEC EDGAR statements, Yahoo prices and ratios)
  quality.py        business quality scorecard and similar-company comparison
  montecarlo.py     probability view (thousands of valuations with varied assumptions)
  portfolio.py      portfolio valuation and sector mix
  fund.py           index-fund data and valuation
  model.py          DCF math, bank handling, warnings, reverse DCF, scenarios
  reverse.py        reverse DCF: return priced in, growth grids, reality checks
  report.py         summary tables and Excel export
  outlook.py        price outlook: typical swings, future fair value, analyst targets
  sec.py            point-in-time financials from SEC EDGAR (for the backtest)
  backtest.py       historical backtest engine and summary
run_backtest.py     runs the backtest and saves results/
results/            saved backtest results shown on the dashboard
  cache.py          on-disk cache of downloaded data (.cache/)
  loader.py         one load() for stocks and funds, plus price history
tests/              automated tests (pytest)
```

## Running the tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The tests use small made-up companies with answers you can check by hand, for example "$100 a year forever at 10% is worth $1,000", so they run offline in about a second.

They also run automatically on GitHub after every push (see the **Actions** tab); the badge at the top shows whether the latest run passed.

## Sharing it online (free)

1. Push this folder to a GitHub repository.
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in with GitHub and choose **Create app**.
3. Pick the repository, branch `main` and file `app.py`, then **Deploy**.

Streamlit Community Cloud installs `requirements.txt` automatically and gives you a public link. On the free plan the app goes to sleep after a few days without visitors and takes a moment to wake up.

## Limitations

- The model is simplified: professional DCFs forecast sales, costs and investment line by line.
- Yahoo Finance only lists a fund's top 10 holdings, and data can be missing or delayed.
- Results depend heavily on the assumptions; use the scenarios and what-if grid to see how much.
