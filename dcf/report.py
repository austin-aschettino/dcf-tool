"""Tables summarising a valuation, plus an Excel export of them.

The same tables feed the dashboard's download button and `main.py --export`.
"""

from __future__ import annotations

import io
import math
from datetime import date
from typing import Dict

import pandas as pd

from .data import CompanyData
from .fund import (
    FundData,
    IndexAssumptions,
    IndexResult,
    implied_index_growth,
    index_scenarios,
    index_sensitivity,
    run_index_valuation,
)
from .model import DCFAssumptions, DCFResult, implied_growth, make_scenarios, run_dcf, sensitivity_table


def _pct(x) -> str:
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.2%}"


# --------------------------------------------------------------------------- #
# Scenario tables
# --------------------------------------------------------------------------- #

def company_scenarios(c: CompanyData, a: DCFAssumptions) -> pd.DataFrame:
    rows = []
    for name, s in make_scenarios(a).items():
        r = run_dcf(c, s)
        rows.append({
            "Scenario": name,
            "Growth next year": s.growth_rate,
            "Long-term growth": s.terminal_growth,
            "Required return": s.wacc,
            "Value / share": r.value_per_share,
            "Gap vs. price": r.upside,
        })
    return pd.DataFrame(rows).set_index("Scenario")


def fund_scenarios(f: FundData, a: IndexAssumptions) -> pd.DataFrame:
    rows = []
    for name, s in index_scenarios(a).items():
        r = run_index_valuation(f, s)
        rows.append({
            "Scenario": name,
            "Growth next year": s.growth_rate,
            "Long-term growth": s.terminal_growth,
            "Required return": s.required_return,
            "Value / share": r.value_per_share,
            "Gap vs. price": r.upside,
            "Expected yearly return": r.implied_return,
        })
    return pd.DataFrame(rows).set_index("Scenario")


# --------------------------------------------------------------------------- #
# Report tables
# --------------------------------------------------------------------------- #

def company_tables(c: CompanyData, a: DCFAssumptions, r: DCFResult) -> Dict[str, pd.DataFrame]:
    g_implied = implied_growth(c, a)
    method = ("Cash returned to shareholders (dividends + buybacks), discounted at the cost of equity"
              if r.method == "payout" else "Free cash flow, discounted at the WACC")
    summary = pd.DataFrame(
        [
            ("Company", f"{c.name} ({c.ticker})"),
            ("Report date", date.today().isoformat()),
            ("Method", method),
            ("Current price", c.price),
            ("Estimated value / share", r.value_per_share),
            ("Gap vs. price", _pct(r.upside)),
            ("Growth priced in (per year, forecast period)", _pct(g_implied)),
            ("Share of value after the forecast", _pct(r.terminal_share)),
            ("Business value", r.enterprise_value),
            ("Net debt subtracted", r.net_debt),
            ("Value for shareholders", r.equity_value),
            ("Shares outstanding", c.shares_outstanding),
        ],
        columns=["Item", "Value"],
    ).set_index("Item")
    assumptions = pd.DataFrame(
        [
            ("Growth next year", _pct(a.growth_rate)),
            ("Slow growth toward long-term rate", "Yes" if a.fade else "No"),
            ("Long-term growth", _pct(a.terminal_growth)),
            ("Required return (discount rate)", _pct(a.wacc)),
            ("Years forecast", a.years),
            ("Starting cash flow", "Latest year" if a.base == "latest" else "3-year average"),
            ("Starting cash flow amount", r.base_fcf),
            ("Beta", c.beta),
        ],
        columns=["Assumption", "Value"],
    ).set_index("Assumption")
    projection = r.projection_table()
    projection.columns = ["Growth", "Cash flow", "Worth today per $1", "Value in today's money"]
    return {
        "Summary": summary,
        "Assumptions": assumptions,
        "Projection": projection,
        "Scenarios": company_scenarios(c, a),
        "What-if (value per share)": sensitivity_table(c, a),
        "Past financials": c.history(),
    }


def fund_tables(f: FundData, a: IndexAssumptions, r: IndexResult) -> Dict[str, pd.DataFrame]:
    summary = pd.DataFrame(
        [
            ("Fund", f"{f.name} ({f.ticker})"),
            ("Report date", date.today().isoformat()),
            ("Method", "Whole index valued as one company: earnings x payout, discounted at the required return plus fees"),
            ("Current price", f.price),
            ("Estimated value / share", r.value_per_share),
            ("Gap vs. price", _pct(r.upside)),
            ("Expected yearly return at today's price", _pct(r.implied_return)),
            ("Growth priced in (per year, forecast period)", _pct(implied_index_growth(f, a))),
            ("P/E ratio", f.pe),
            ("Expense ratio", _pct(f.expense_ratio)),
            ("Dividend yield", _pct(f.dividend_yield)),
        ],
        columns=["Item", "Value"],
    ).set_index("Item")
    assumptions = pd.DataFrame(
        [
            ("Earnings growth next year", _pct(a.growth_rate)),
            ("Slow growth toward long-term rate", "Yes" if a.fade else "No"),
            ("Long-term growth", _pct(a.terminal_growth)),
            ("Required return", _pct(a.required_return)),
            ("Share of profit paid to owners", _pct(a.payout)),
            ("Years forecast", a.years),
        ],
        columns=["Assumption", "Value"],
    ).set_index("Assumption")
    projection = r.projection_table()
    tables = {
        "Summary": summary,
        "Assumptions": assumptions,
        "Projection": projection,
        "Scenarios": fund_scenarios(f, a),
        "What-if (value per share)": index_sensitivity(f, a),
    }
    if f.holdings:
        tables["Top holdings"] = f.holdings_table().set_index("Symbol")
    if f.sectors:
        tables["Sectors"] = f.sectors_table().set_index("Sector")
    return tables


def to_xlsx(tables: Dict[str, pd.DataFrame]) -> bytes:
    """Write each table to its own sheet and return the workbook as bytes."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        for name, df in tables.items():
            sheet = name[:31]  # Excel's sheet-name limit
            df.to_excel(xl, sheet_name=sheet)
            ws = xl.sheets[sheet]
            for col in ws.columns:
                width = max(len(str(cell.value)) if cell.value is not None else 0 for cell in col)
                ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 10), 70)
    return buf.getvalue()
