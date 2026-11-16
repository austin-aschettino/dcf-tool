---
version: 1
slug: "app-py"
primary_target: "app.py"
related_targets: []
---

# Surface brief: the whole app (app.py)

Scope: every page of the Streamlit app (Home, Value a stock or fund, Compare, My portfolio, Does the model work?). Visitor mode: Operate.

Audience and job: beginner investors, finance students and portfolio reviewers who want to know what a stock or fund is worth, what the price assumes and how sure anyone can be. Constraints: stays on Streamlit; nothing structural is off-limits; must not look like a template or feel playful; plain English, honesty about limits and dark mode are kept.

Memorable moment: the footing, where the value is added up as a column and lands on a double-ruled per-share figure next to today's price.

## Direction contract

THESIS: A valuation is arithmetic that foots, so every page shows its working down to a double-ruled answer. It refuses the fintech-dashboard default of tinted gradient cards, star scores and a brand-indigo everything.

OWN-WORLD: The accountant's green analysis pad. Ledger-green bookcloth sidebar (#1e4636 family), pale green pad stock as the ground (#eef3ec family), near-black ink, red ink for negatives in accounting parentheses, and one reserved blue ink used only for the visitor's own assumptions. Hairline green-grey rules instead of shadows; flat panels, 6–8px radius. Public Sans for words, Source Serif 4 with tabular lining figures for every number, at every size.

STORY: The visitor reads the verdict in plain words, sees the arithmetic foot to the per-share value, compares it with today's price, then explores methods and assumptions knowing which figures are theirs (blue) and which are the market's or the model's.

FIRST VIEWPORT: Green sidebar: brand, page menu, ticker field, assumption sliders in blue ink. Main: crumb, company title with chips; then two columns: the verdict panel (headline, range sentence, what's priced in, "not a prediction") and the footing panel (lines adding to a double-ruled per-share value, today's price beneath). Tabs, then the fair-value-by-method chart. Phones: one column, verdict, footing, figures 2×2, chart.

FORM: Columnar Pad, 4th of 7 on the ordered grounded list (corporate finance textbook, central-bank fan-chart reports, 10-K statements, columnar pad, financial newspaper market pages, Swiss information design, banknote engraving). seed:85550437a306a698. Raises: reserved blue ink for the user's own layer; figures right-aligned to a shared column and totals that foot; columns never move when a slider changes; one figure face at every size; focused method dims the others; phone charts keep each method full size. Signature move: the footing (the double-ruled total), used for every computed answer.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
