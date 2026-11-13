"""Run the historical backtest and save the results for the dashboard.

Usage:
    python run_backtest.py                      # default universe, 2012 to the latest complete year
    python run_backtest.py --first 2015         # start later
    python run_backtest.py --tickers AAPL MSFT KO PEP JNJ PFE

Results are written to results/backtest_signals.csv and results/backtest_summary.json.
The first run downloads about 10 years of filings and prices for each company
(a few minutes); later runs reuse the saved downloads.
"""

from __future__ import annotations

import argparse
import sys

from dcf.backtest import UNIVERSE, run_backtest, save_results, summarize


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Backtest the valuation model against what stock prices did next.")
    p.add_argument("--first", type=int, default=2012, help="First rebalance year (default 2012)")
    p.add_argument("--last", type=int, help="Last rebalance year (default: latest with a full year of results)")
    p.add_argument("--tickers", nargs="+", help="Stocks to include (default: about 70 large US companies)")
    args = p.parse_args(argv)

    signals = run_backtest(args.tickers or UNIVERSE, first_year=args.first, last_year=args.last)
    summary = summarize(signals)
    save_results(signals, summary)

    valued = signals[signals["excluded"] == ""]
    print(f"\nValued {len(valued)} stock-years; excluded {len(signals) - len(valued)} "
          f"({signals['excluded'].value_counts().to_dict()})")
    print(f"\nYears {summary.first_year}-{summary.last_year}, about {summary.avg_stocks_per_year:.0f} stocks a year\n")
    print(f"{'Group':<28}{'Avg yearly return':>18}{'$1 grew to':>12}")
    for name in summary.group_names + ["All stocks (equal weight)", "S&P 500 (SPY)"]:
        print(f"{name:<28}{summary.avg_return[name]:>17.1%}{summary.growth_of_1[name]:>12.2f}")
    print(f"\nCheapest third beat most expensive third in {summary.cheap_beat_expensive} of {summary.n_years} years")
    print(f"Average rank correlation (gap vs. next-year return): {summary.avg_rank_correlation:+.3f}")
    print("\nSaved to results/backtest_signals.csv and results/backtest_summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
