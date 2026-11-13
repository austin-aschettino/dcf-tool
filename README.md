# 📈 Stock & Fund Valuation

A beginner-friendly tool that estimates what a stock or index fund is worth, based on the cash it's expected to produce. It comes as an interactive web dashboard (Streamlit) and a command-line report.

- **Stocks** are valued with a discounted cash flow (DCF) model: forecast the company's free cash flow, convert it to today's money, subtract debt, divide by shares.
- **Banks and insurers** are detected automatically and valued from the cash they return to shareholders (dividends + buybacks), because their free cash flow isn't meaningful.
- **Index funds** (VOO, SPY, QQQ, …) are valued as if all their companies were one big business, with an **expected yearly return** at today's price.
- **Companies that burn cash** get a clear explanation instead of a misleading number.

Everything is explained in plain English inside the app, with a 💡 box under every chart and table.

> Educational tool only, not investment advice. Data comes from Yahoo Finance via [yfinance](https://github.com/ranaroussi/yfinance) and may be incomplete.

## Features

| | |
|---|---|
| **Plain-English verdict** | "AutoZone looks roughly fairly priced: worth about $3,461, 6% above today's price." |
| **What's priced in** | The growth rate the current price implies, e.g. *"Apple would need to grow 34% a year for 5 years."* |
| **Scenarios** | Pessimistic / middle / optimistic estimates, each loadable into the sliders with one click. |
| **What-if grid** | Value across a range of required returns and long-term growth rates, coloured against the price. |
| **Price outlook** | Where the price could be in 1, 3 or 5 years: the typical range from past price swings, the model's fair value, and analysts' 12-month targets, with upside and downside for each. |
| **Price history** | 5 years of prices against the estimate and the scenario range. |
| **Compare mode** | Up to 6 stocks and funds side by side. |
| **Excel export** | Download the full report (summary, assumptions, forecast, scenarios, what-if, past data). |
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
  data.py           downloads company financials from Yahoo Finance
  fund.py           index-fund data and valuation
  model.py          DCF math, bank handling, warnings, reverse DCF, scenarios
  report.py         summary tables and Excel export
  outlook.py        price outlook: typical swings, future fair value, analyst targets
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

## Sharing it online (free)

1. Push this folder to a GitHub repository.
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in with GitHub and choose **Create app**.
3. Pick the repository, branch `main` and file `app.py`, then **Deploy**.

Streamlit Community Cloud installs `requirements.txt` automatically and gives you a public link. On the free plan the app goes to sleep after a few days without visitors and takes a moment to wake up.

## Limitations

- The model is simplified: professional DCFs forecast sales, costs and investment line by line.
- Yahoo Finance only lists a fund's top 10 holdings, and data can be missing or delayed.
- Results depend heavily on the assumptions; use the scenarios and what-if grid to see how much.
