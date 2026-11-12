"""Command-line valuation for stocks and index funds.

Usage:
    python main.py AZO
    python main.py AAPL --growth 0.08 --wacc 0.09 --terminal 0.025 --years 10
    python main.py AAPL --base latest --growth-source history
    python main.py JPM                       # banks are valued from dividends + buybacks
    python main.py VOO                       # index funds are detected automatically
    python main.py QQQ --growth 0.08 --return 0.09 --payout 0.8
    python main.py AZO --export azo.xlsx     # save the full report as a spreadsheet
    python main.py AZO --refresh             # ignore saved data and download again
"""

from __future__ import annotations

import argparse
import sys
import textwrap

import pandas as pd

from dcf import (
    FundData,
    check_company,
    company_scenarios,
    company_tables,
    default_assumptions,
    default_growth,
    default_index_assumptions,
    fund_scenarios,
    fund_tables,
    implied_growth,
    implied_index_growth,
    index_sensitivity,
    load,
    run_dcf,
    run_index_valuation,
    sensitivity_table,
    to_xlsx,
)

LINE = "=" * 60
DISCLAIMER = "\nNot investment advice. Inputs come from Yahoo Finance and may be incomplete."


def money(x: float) -> str:
    sign = "-" if x < 0 else ""
    x = abs(x)
    for unit, div in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if x >= div:
            return f"{sign}${x / div:,.2f}{unit}"
    return f"{sign}${x:,.2f}"


def pct(x) -> str:
    return "n/a" if x is None or pd.isna(x) else f"{x:.2%}"


def fmt_grid(df: pd.DataFrame, f) -> pd.DataFrame:
    return df.apply(lambda s: s.map(lambda v: f(v) if pd.notna(v) else "-"))


def wrap(text: str, prefix: str = " ") -> str:
    return textwrap.fill(text, width=78, initial_indent=prefix, subsequent_indent=prefix + "  ")


def print_scenarios(table: pd.DataFrame, rate_label: str) -> None:
    t = pd.DataFrame(
        {
            "Growth": table["Growth next year"].map("{:.1%}".format),
            "Long-term": table["Long-term growth"].map("{:.1%}".format),
            rate_label: table["Required return"].map("{:.1%}".format),
            "Value/share": table["Value / share"].map("{:,.2f}".format),
            "Gap": table["Gap vs. price"].map("{:+.1%}".format),
        },
        index=table.index,
    )
    print(f"\nScenarios\n{t.to_string()}")


def export(tables, path: str) -> None:
    with open(path, "wb") as fh:
        fh.write(to_xlsx(tables))
    print(f"\nSaved the full report to {path}")


# --------------------------------------------------------------------------- #
# Stocks
# --------------------------------------------------------------------------- #

def report_company(c, args) -> int:
    a = default_assumptions(c, growth_source=args.growth_source, base=args.base)
    _, growth_label = default_growth(c, args.growth_source)
    if args.growth is not None:
        a.growth_rate, growth_label = args.growth, "your --growth setting"
    if args.terminal is not None:
        a.terminal_growth = args.terminal
    if args.wacc is not None:
        a.wacc = args.wacc
    if args.years is not None:
        a.years = args.years
    if args.no_fade:
        a.fade = False

    payout = c.is_financial
    cash_label = "Cash returned" if payout else "FCF"
    rate_label = "Cost of equity" if payout else "WACC"

    print(f"\n{LINE}\n {c.name} ({c.ticker})\n{LINE}")
    print(f" Price            {c.price:>12,.2f} {c.currency}")
    print(f" Sector           {c.sector} / {c.industry}")
    print(f" Shares out       {c.shares_outstanding / 1e6:>12,.1f} M")
    print(f" Market cap       {money(c.market_cap):>12}")
    print(f" Net debt         {money(c.net_debt):>12}")
    print(f" Beta             {c.beta:>12.2f}")
    print(f" Tax rate         {c.tax_rate:>12.1%}")

    hist = fmt_grid(c.history(), money)
    print(f"\nHistorical cash flows\n{hist.to_string()}")

    blocking, warnings = check_company(c, a.base)
    for w in warnings:
        print("\n" + wrap("NOTE: " + w))
    if blocking:
        print(f"\n{LINE}")
        print(wrap("No valuation: " + blocking))
        print(LINE)
        print(DISCLAIMER)
        return 0

    try:
        r = run_dcf(c, a)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    method = ("cash returned to shareholders (dividends + buybacks)" if payout
              else "free cash flow")
    print(f"\nAssumptions  (valued from {method})")
    print(f" Year-1 growth    {a.growth_rate:>12.1%}{'  (fading to terminal)' if a.fade else ''}")
    print(f"   from           {growth_label}")
    print(f" Terminal growth  {a.terminal_growth:>12.1%}")
    print(f" {rate_label:<17}{a.wacc:>12.1%}")
    base_label = "latest year" if a.base == "latest" else "3-year average"
    print(f" Starting point   {money(r.base_fcf):>12}   ({cash_label.lower() if payout else 'free cash flow'}, {base_label})")

    proj = r.projection_table()
    proj_fmt = pd.DataFrame(
        {
            "Growth": proj["Growth"].map("{:.1%}".format),
            cash_label: proj["FCF"].map(money),
            "Discount": proj["Discount factor"].map("{:.3f}".format),
            "Present value": proj["PV of FCF"].map(money),
        },
        index=proj.index,
    )
    print(f"\nProjection\n{proj_fmt.to_string()}")

    print("\nValuation")
    print(f" Sum of PV        {money(sum(r.pv_fcf)):>12}")
    print(f" PV terminal value{money(r.pv_terminal_value):>12}  ({r.terminal_share:.0%} of value)")
    if payout:
        print(f" Equity value     {money(r.equity_value):>12}  (no debt subtracted: this cash already goes to owners)")
    else:
        print(f" Enterprise value {money(r.enterprise_value):>12}")
        print(f" - Net debt       {money(r.net_debt):>12}")
        print(f" Equity value     {money(r.equity_value):>12}")
    print(LINE)
    print(f" Intrinsic value / share  {r.value_per_share:>10,.2f}")
    print(f" Current price            {r.price:>10,.2f}")
    verdict = "UNDERVALUED" if r.upside > 0 else "OVERVALUED"
    print(f" Upside / downside        {r.upside:>+10.1%}  -> {verdict}")
    g = implied_growth(c, a)
    if pd.notna(g):
        print(f" Growth priced in         {g:>10.1%}  (steady yearly growth for the forecast years that would justify the price)")
    else:
        print(f" Growth priced in         {'n/a':>10}  (no growth rate between -50% and +100% matches the price)")
    print(LINE)

    print_scenarios(company_scenarios(c, a), rate_label)
    print(f"\nSensitivity: value/share  (rows = {rate_label}, columns = terminal growth)")
    print(fmt_grid(sensitivity_table(c, a), lambda v: f"{v:,.0f}").to_string())
    if args.export:
        export(company_tables(c, a, r), args.export)
    print(DISCLAIMER)
    return 0


# --------------------------------------------------------------------------- #
# Index funds
# --------------------------------------------------------------------------- #

def report_fund(f: FundData, args) -> int:
    kind = "Mutual fund" if f.fund_type == "MUTUALFUND" else "ETF"
    print(f"\n{LINE}\n {f.name} ({f.ticker})  -  {kind}\n{LINE}")
    print(f" Price            {f.price:>12,.2f} {f.currency}")
    if f.family or f.category:
        print(f" Family / type    {(f.family + ' / ' + f.category).strip(' /')}")
    print(f" Total assets     {money(f.total_assets):>12}")
    print(f" Expense ratio    {f.expense_ratio:>12.2%}   (yearly fee)")
    print(f" Dividend yield   {f.dividend_yield:>12.2%}")
    print(f" P/E ratio        {f.pe:>12.1f}" if f.can_value else f" P/E ratio        {'n/a':>12}")
    print(f" Beta (3y)        {f.beta:>12.2f}")
    print(f" Avg return 3y/5y {pct(f.return_3y):>12} / {pct(f.return_5y)}")

    if f.holdings:
        h = f.holdings_table()
        h["Weight"] = h["Weight"].map("{:.2%}".format)
        print(f"\nTop {len(f.holdings)} holdings  ({f.top_holdings_weight:.1%} of the fund)")
        print(h.to_string(index=False))
    if f.sectors:
        s = f.sectors_table()
        s["Weight"] = s["Weight"].map("{:.1%}".format)
        print(f"\nSector weights\n{s.to_string(index=False)}")

    if not f.can_value:
        print(f"\n{LINE}")
        print(" No valuation: this fund has no P/E ratio (for example, a bond fund).")
        print(" The index model values a basket of stocks from its earnings, so it")
        print(" only works for stock funds.")
        print(LINE)
        print(DISCLAIMER)
        return 0

    a = default_index_assumptions(f)
    if args.growth is not None:
        a.growth_rate = args.growth
    if args.terminal is not None:
        a.terminal_growth = args.terminal
    req = args.required_return if args.required_return is not None else args.wacc
    if req is not None:
        a.required_return = req
    if args.payout is not None:
        a.payout = args.payout
    if args.years is not None:
        a.years = args.years
    if args.no_fade:
        a.fade = False

    try:
        r = run_index_valuation(f, a)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print("\nAssumptions  (the index is valued as one big company)")
    print(f" Earnings / share {f.earnings_per_share:>12,.2f}   (price / P/E)")
    print(f" Earnings yield   {f.earnings_yield:>12.2%}   (1 / P/E)")
    print(f" Year-1 growth    {a.growth_rate:>12.1%}{'  (fading to terminal)' if a.fade else ''}")
    print(f" Terminal growth  {a.terminal_growth:>12.1%}")
    print(f" Required return  {a.required_return:>12.1%}   (risk-free + beta x risk premium)")
    print(f" Payout           {a.payout:>12.0%}   (dividends + buybacks, share of earnings)")

    proj = r.projection_table()
    proj_fmt = pd.DataFrame(
        {
            "Growth": proj["Growth"].map("{:.1%}".format),
            "Earnings": proj["Earnings / share"].map("{:,.2f}".format),
            "Cash to owners": proj["Cash to owners"].map("{:,.2f}".format),
            "Discount": proj["Discount factor"].map("{:.3f}".format),
            "PV of cash": proj["PV of cash"].map("{:,.2f}".format),
        },
        index=proj.index,
    )
    print(f"\nProjection (per fund share)\n{proj_fmt.to_string()}")

    print("\nValuation (per fund share)")
    print(f" Sum of PV(cash)  {sum(r.pv_cash):>12,.2f}")
    print(f" PV terminal value{r.pv_terminal_value:>12,.2f}  ({r.terminal_share:.0%} of value)")
    print(LINE)
    print(f" Fair value / share       {r.value_per_share:>10,.2f}")
    print(f" Current price            {r.price:>10,.2f}")
    verdict = "UNDERVALUED" if r.upside > 0 else "OVERVALUED"
    print(f" Upside / downside        {r.upside:>+10.1%}  -> {verdict}")
    print(f" Implied yearly return    {pct(r.implied_return):>10}  (if you buy today, after fees)")
    print(f"   vs. required return    {a.required_return:>10.2%}")
    print(f" Growth priced in         {pct(implied_index_growth(f, a)):>10}  (steady yearly earnings growth for the forecast years that justifies the price)")
    print(LINE)

    print_scenarios(fund_scenarios(f, a), "Required")
    print("\nSensitivity: value/share  (rows = required return, columns = terminal growth)")
    print(fmt_grid(index_sensitivity(f, a), lambda v: f"{v:,.0f}").to_string())
    if args.export:
        export(fund_tables(f, a, r), args.export)
    print(DISCLAIMER)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Valuation for a stock (DCF) or an index fund (whole-index model).")
    p.add_argument("ticker", help="Stock or fund ticker, e.g. AZO or VOO")
    p.add_argument("--growth", type=float, help="Year-1 growth rate (e.g. 0.07)")
    p.add_argument("--terminal", type=float, help="Terminal growth rate (e.g. 0.025)")
    p.add_argument("--wacc", type=float, help="Stocks: discount rate / WACC (e.g. 0.09)")
    p.add_argument("--return", dest="required_return", type=float, help="Funds: required yearly return (e.g. 0.09)")
    p.add_argument("--payout", type=float, help="Funds: share of earnings paid to owners (e.g. 0.85)")
    p.add_argument("--years", type=int, help="Projection years (default 5 for stocks, 10 for funds)")
    p.add_argument("--no-fade", action="store_true", help="Hold growth flat instead of fading to terminal")
    p.add_argument("--base", choices=["avg3", "latest"], default="avg3",
                   help="Stocks: start from the 3-year average cash flow (default) or the latest year")
    p.add_argument("--growth-source", choices=["analyst", "history"], default="analyst",
                   help="Stocks: default growth from analysts' forecast (default) or past sales growth")
    p.add_argument("--export", metavar="FILE.xlsx", help="Save the full report as an Excel spreadsheet")
    p.add_argument("--refresh", action="store_true", help="Ignore saved data and download fresh numbers")
    args = p.parse_args(argv)

    pd.set_option("display.width", 120)
    print(f"Fetching data for {args.ticker.upper()}...")
    try:
        data = load(args.ticker, refresh=args.refresh)
    except Exception as e:  # network errors, bad tickers, etc.
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if isinstance(data, FundData):
        return report_fund(data, args)
    return report_company(data, args)


if __name__ == "__main__":
    sys.exit(main())
