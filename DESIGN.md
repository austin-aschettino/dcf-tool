---
name: Stock & Fund Valuation
description: What a share is worth, worked out in plain English on an accountant's green analysis pad.
colors:
  ledger-green: "#1e4636"
  ledger-green-raised: "#2c5c48"
  ledger-cloth-deep: "#173a2c"
  cloth-rule: "#3a6b56"
  cloth-ink: "#e3ede6"
  cloth-caption: "#d3e3d9"
  you-blue: "#2747b8"
  you-blue-on-cloth: "#b8c6ff"
  you-blue-deep: "#14256b"
  red-ink: "#b4261d"
  cheap-green: "#1f6b43"
  amber-ink: "#8a5a00"
  analyst-amber: "#a8761b"
  peer-green: "#3f6b57"
  market-grey: "#8a978f"
  pad-ground: "#eef3ec"
  pad-sheet: "#fbfdfa"
  pad-tint: "#e2ebe3"
  rule: "#c9d8cd"
  hairline: "#dbe6dd"
  chart-grid: "#e3ebe5"
  ink: "#16201b"
  ink-soft: "#2b3a32"
  muted-ink: "#4f6057"
  night-ground: "#0e1814"
  night-sheet: "#15231d"
  night-rule: "#2b4136"
  night-hairline: "#22362c"
  night-ink: "#e6eee8"
  night-muted: "#9fb2a6"
  night-ledger: "#8fd1ad"
  night-cloth: "#15362a"
  night-you-blue: "#9db0ff"
  night-red-ink: "#ff9a8f"
  night-cheap-green: "#7fd6a2"
  night-amber: "#f0c36b"
  night-peer-green: "#6fb08f"
  night-analyst-amber: "#d6a24a"
  night-market-grey: "#7d8f85"
typography:
  display:
    fontFamily: "Pad Figures, Public Sans, -apple-system, Segoe UI, sans-serif"
    fontSize: "2.5rem"
    fontWeight: 700
    lineHeight: 1.12
    letterSpacing: "-0.01em"
  headline:
    fontFamily: "Pad Figures, Public Sans, -apple-system, Segoe UI, sans-serif"
    fontSize: "2.1rem"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "-0.01em"
  title-verdict:
    fontFamily: "Pad Figures, Public Sans, -apple-system, Segoe UI, sans-serif"
    fontSize: "1.45rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Pad Figures, Public Sans, -apple-system, Segoe UI, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 700
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Pad Figures, Public Sans, -apple-system, Segoe UI, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    fontFeature: "tnum, lnum"
  body-small:
    fontFamily: "Pad Figures, Public Sans, -apple-system, Segoe UI, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 600
  label:
    fontFamily: "Public Sans, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 700
    letterSpacing: "0.07em"
  figure-total:
    fontFamily: "Source Serif 4, Georgia, Times New Roman, serif"
    fontSize: "2.1rem"
    fontWeight: 700
    lineHeight: 1.1
    fontFeature: "tnum, lnum"
  figure-metric:
    fontFamily: "Source Serif 4, Georgia, Times New Roman, serif"
    fontSize: "1.85rem"
    fontWeight: 600
    lineHeight: 1.2
    fontFeature: "tnum, lnum"
  figure-line:
    fontFamily: "Source Serif 4, Georgia, Times New Roman, serif"
    fontSize: "1.0625rem"
    fontWeight: 400
    fontFeature: "tnum, lnum"
rounded:
  tag: "4px"
  control: "6px"
  sheet: "8px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
components:
  chip:
    backgroundColor: "{colors.pad-sheet}"
    textColor: "#2e4a3d"
    typography: "{typography.body-small}"
    rounded: "{rounded.tag}"
    padding: "1px 8px"
  chip-ledger:
    backgroundColor: "{colors.pad-sheet}"
    textColor: "{colors.ledger-green}"
    rounded: "{rounded.tag}"
    padding: "1px 8px"
  chip-you:
    backgroundColor: "{colors.pad-sheet}"
    textColor: "{colors.you-blue}"
    rounded: "{rounded.tag}"
    padding: "1px 8px"
  sidebar-tag:
    backgroundColor: "{colors.you-blue-on-cloth}"
    textColor: "{colors.you-blue-deep}"
    rounded: "{rounded.tag}"
  button:
    backgroundColor: "{colors.pad-sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
  nav-item:
    backgroundColor: "{colors.ledger-green}"
    textColor: "#d5e4da"
    rounded: "{rounded.control}"
    padding: "7px 12px"
  nav-item-active:
    backgroundColor: "{colors.ledger-green-raised}"
    textColor: "#ffffff"
    rounded: "{rounded.control}"
    padding: "7px 12px"
  tab:
    textColor: "{colors.muted-ink}"
    padding: "10px 14px"
  tab-active:
    textColor: "{colors.ledger-green}"
    padding: "10px 14px"
  sheet:
    backgroundColor: "{colors.pad-sheet}"
    rounded: "{rounded.sheet}"
  quality-card:
    backgroundColor: "{colors.pad-sheet}"
    rounded: "{rounded.sheet}"
    padding: "14px 16px"
  footing-total:
    textColor: "{colors.ink}"
    typography: "{typography.figure-total}"
  badge-strong:
    backgroundColor: "#e2f0e6"
    textColor: "{colors.cheap-green}"
    rounded: "{rounded.tag}"
    padding: "1px 8px"
  badge-ok:
    backgroundColor: "#f6edd9"
    textColor: "#7a4f00"
    rounded: "{rounded.tag}"
    padding: "1px 8px"
  badge-weak:
    backgroundColor: "#f8e3e1"
    textColor: "#a2231a"
    rounded: "{rounded.tag}"
    padding: "1px 8px"
---

# Design System: Stock & Fund Valuation

## Overview

**Creative North Star: "The Columnar Pad"**

The app is an accountant's green analysis pad. A valuation is arithmetic that foots, so every page shows its working down to a double-ruled answer: lines of figures right-aligned to one shared column, an operator in the margin, a subtotal in heavier ink, and a total underlined twice with today's price written beneath it. The pad is bound in ledger-green bookcloth (the sidebar), its pages are pale green stock, and the ink is near-black, with red ink for negatives and one blue ink set aside for the visitor's own assumptions.

Density is a working sheet's, not a brochure's: flat sheets with hairline rules, no shadows, no tinted gradient cards, no star scores, no brand-indigo everywhere. Words are set in Public Sans; every numeral, at every size and inside running sentences, is set in Source Serif 4 with tabular lining figures, so a number always looks like a number and columns never shift when a slider moves. The verdict is written in plain words first and coloured only in its headline ink; the arithmetic sits beside it as a footing, on the stock page and the fund page alike; the methods chart follows.

Dark mode is the same pad at night: a deep green-black ground, the same hairlines lifted, the inks brightened to hold contrast. Nothing changes structurally between themes.

**Key Characteristics:**
- Ledger-green bookcloth sidebar on a pale green pad ground.
- One serif figure face (Source Serif 4, tabular lining) for every number, layered in front of Public Sans.
- Blue ink reserved for the visitor's own assumptions and what is computed from them; what the market prices in is written in ledger green.
- Red ink and accounting parentheses for negatives.
- Flat sheets, 1px hairline rules, 4/6/8px corners, no shadows.
- The footing (a column of figures ending on a double-ruled total) as the signature for computed answers.

## Colors

A green-on-green paper palette of inks, where every hue beyond the greens means something specific.

### Primary
- **Ledger Bookcloth Green** (ledger-green): the sidebar cloth, Streamlit's primary colour, the active tab underline and label, the "Home" crumb, expander headings, step numerals on Home. Structure and navigation, never a judgement.
- **Raised Cloth** (ledger-green-raised): the selected sidebar menu item, and the primary button fill in dark mode.
- **Deep Cloth** (ledger-cloth-deep) and **Cloth Rule** (cloth-rule): the sidebar's secondary surfaces and the hairline under the brand.
- **Cloth Ink** (cloth-ink) and **Cloth Caption** (cloth-caption): text on the sidebar; captions are set to about 7:1 on the cloth rather than faded.

### Secondary
- **The Visitor's Blue Ink** (you-blue): the visitor's own numbers wherever they are quoted in text (the `.you` style, bold), the cash-flow model's bar on the fair-value chart (the model runs on the visitor's settings), the "Middle (your settings)" scenario, "Your assumption" and "Your forecast" bars and lines beside the market's priced-in growth, the forecast bars of cash-flow and fund charts, the outline of the current cell in what-if grids, links, the text-selection tint and keyboard focus rings. **Blue on the Cloth** (you-blue-on-cloth) is the same ink lifted for the sidebar: slider thumb values, the sidebar's primary colour, and the fill of the tickers the visitor has picked, which are written in **Deep Blue** (you-blue-deep) on it (about 8:1). Deep Blue is also the optimistic end of the scenario hue.

### Tertiary
- **Red Ink** (red-ink): negatives (in parentheses) and "worth less than the price" verdicts.
- **Cheap Green** (cheap-green): "worth more than the price" verdicts and Strong badges.
- **Amber Ink** (amber-ink): cautionary verdict headlines; **Analyst Amber** (analyst-amber) marks analysts' targets on charts and nothing else.
- **Peer Green** (peer-green), the chart's ledger green: what the market's price implies (growth "priced in", cash "needed to justify the price", Compare's priced-in bars), peers' implied prices, estimates above today's price, and the backtest's cheapest third.
- **Market Grey** (market-grey): past actuals, the middle third, and the market's own traded range (drawn outlined only, as context).
- **Demand levels** (how demanding a holding's price is, on the portfolio page) reuse the verdict inks: cheap-green, amber-ink and red-ink, never the chart source colours.
- **Portfolio mix:** the sector pie uses a ledger palette in fixed order: #1e4636, #4f8a6c, #a8761b, #5b4a8a, #2f7f8f, #8a978f, #c9b27a, #b9c9bf.

### Neutral
- **Pad Ground** (pad-ground): the page. **Pad Sheet** (pad-sheet): every panel, chart and table sheet, and the Plotly paper colour. **Pad Tint** (pad-tint): Streamlit's secondary background (inputs, segmented controls).
- **Rule** (rule): panel edges, the tab baseline, zero lines. **Hairline** (hairline): footing row rules and dividers between figures in a row. **Chart Grid** (chart-grid): Plotly gridlines.
- **Ink** (ink): headings, figures, today's-price line. **Soft Ink** (ink-soft): body copy and chart text. **Muted Ink** (muted-ink): labels, captions (main column), inactive tabs, footing operators and the footer.
- **Reference lines** are ink: today's price on the fair-value chart, "today's money" forecast lines, and the S&P 500 benchmark (dotted). "All stocks" is muted ink (dashed).
- Night counterparts: night-ground, night-sheet, night-rule, night-hairline, night-ink, night-muted, night-ledger, night-cloth (the sidebar at night, set in the dark stylesheet), the lifted inks night-you-blue, night-red-ink, night-cheap-green, night-amber, and the chart inks night-peer-green, night-analyst-amber, night-market-grey. Headings at night use #f4f8f5.

### Named Rules
**The Blue Ink Rule.** Blue means "yours". It marks only the visitor's assumptions, choices and figures computed from them; what the market's price implies is ledger green, analysts are amber, and market data, peers and the verdict never use blue. Nothing decorative is blue.

**The Red Ink Rule.** Negatives are written in red ink inside accounting parentheses, with the closing bracket hanging outside the figure column so digits stay aligned. Red and green are kept for value against price and never used for categories.

**The Bookcloth Rule.** Ledger green binds and navigates (sidebar, active tab, crumbs, expander headings). It does not carry a verdict; verdicts, and the demand levels that echo them, use cheap-green, red-ink and amber-ink.

**The Source Ink Rule.** On a chart, a colour names whose number it is: blue for the visitor, ledger green for the market's price, amber for analysts, grey for the past and for context, ink for reference lines. Amber never marks today's price.

## Typography

**Display Font:** Public Sans (with -apple-system, Segoe UI, sans-serif)
**Body Font:** Public Sans
**Figure Font:** Source Serif 4 (with Georgia, Times New Roman, serif), tabular lining numerals

**Character:** A plain, public-service grotesque for the words and an old-style-born serif for the numbers, so a reader can tell at a glance which marks are arithmetic. Headings are 700 with a slight negative track (-0.01em).

Figures reach every surface two ways: a `--figures` stack applied directly to metric values, footing values, quality-card values and table cells; and a numerals-only web face, **Pad Figures**, cut from Source Serif 4 with a unicode-range of digits, `$ % ( ) + .` and the true minus, placed before Public Sans in every text stack (including Plotly's font family). Commas and hyphens are left out of the range so words keep Public Sans punctuation. Tables are set in that same stack (words sans, digits serif) and scroll sideways inside their sheet when wide. The whole app sets `font-variant-numeric: tabular-nums lining-nums`.

### Hierarchy
- **Display** (700, 2.5rem, 1.12; 1.8rem on phones): the Home statement only.
- **Headline** (700, 2.1rem, 1.15; 1.55rem on phones): the company or page title.
- **Verdict title** (700, 1.45rem, 1.25, balanced wrap): the plain-words verdict heading.
- **Title** (700, 1.25rem, 18px above / 8px below): section headings in the main column.
- **Body** (400, 1rem, Streamlit default leading): explanations, kept to 64ch inside the verdict and wrapped with `text-wrap: pretty`.
- **Small** (600, 0.8125–0.9rem): chips, metric labels, tab labels, crumbs, expander headings.
- **Label** (700, 0.75rem, 0.07–0.08em, uppercase): the footing caption and the sidebar's section labels only.
- **Figure total** (Source Serif 4 700, 2.1rem, 1.1; 1.75rem on phones): the footed answer.
- **Figure metric** (Source Serif 4 600, 1.85rem; 1.5rem in compact rows; 1.35rem under 440px): figure rows.
- **Figure line** (Source Serif 4 400, 1.0625rem; today's price 1.25rem): footing lines.

### Named Rules
**The One Figure Face Rule.** Every numeral, from the largest total to a digit inside a sentence or a chart tick, is Source Serif 4 with tabular lining figures. Never let a number fall back to the sans.

**The Still Column Rule.** Figures are right-aligned to a shared column and tabular, so moving a slider changes digits, never positions.

## Layout

The main column is capped at 1280px with 2.2rem above it; the sidebar is the bookcloth, compact enough that the first assumption slider shows on a laptop screen. The stock and fund pages open with the crumb, the title row (title and chips left, Excel and Share actions right in a 2.4 : 1.6 split), then two columns: the verdict sheet and the footing sheet (on the fund page, "How the model gets there": two cash lines footing to the value per fund share). Tabs follow on one ruled line (scrolling sideways on phones), then figure rows and charts.

A row of figures is one bordered sheet split by hairline dividers rather than several boxes; it becomes a 2 × 2 grid when its container is under 820px. The quality scorecard is an auto-fill grid of 250px-minimum cards with a 12px gap. Spacing runs on 4 / 8 / 12 / 16px steps. Below 640px everything stacks to one column (verdict, footing, figures 2 × 2, chart), type steps down as listed above, and a phone-only line points to the sidebar toggle. Charts keep every method at full size on phones.

## Elevation & Depth

The system is flat. Depth comes from a lighter sheet (pad-sheet) laid on the ground (pad-ground) and a 1px rule at its edge; nothing casts a shadow, in either theme (dark mode explicitly strips Streamlit's shadows). Emphasis is carried by ink weight and rules, never by lift.

### Named Rules
**The Hairline Rule.** Separation is a 1px rule or hairline, never a shadow, a gradient or a tinted card.

## Shapes

Three corners only: 4px for tags (chips, badges, metric deltas), 6px for controls (buttons, sidebar menu items), 8px for sheets (panels, charts, tables, quality cards). Tabs are square and marked by a 3px underline sitting on the 1px tab baseline. The one ornamental line in the system is the 4px double rule under a footed total.

## Components

### Buttons
- **Shape:** gently rounded controls (6px).
- **Default:** Streamlit's bordered button on the pad, label 600 weight; in dark mode filled with night-sheet and bordered with night-rule. Primary buttons at night fill with raised cloth (#2c5c48) and white text.
- **Disabled:** 55% opacity, default cursor.
- **Crumb:** a tertiary "Home" button in ledger green (600, 0.875rem) followed by a muted "›" and the current section.

### Chips
- **Style:** 4px tags on the sheet colour with a rule border, 0.8125rem 600, text #2e4a3d (soft ink at night). The ledger variant (stock or fund type) writes in ledger green with a #9fbcac border; the "you" variant writes in the visitor's blue with a #b9c4ea border.
- **Picked tickers (sidebar):** multiselect tags filled with blue on the cloth and written in deep blue, text and remove icon alike.

### Cards / Containers
- **Corner Style:** 8px.
- **Background:** pad-sheet on pad-ground (night-sheet at night).
- **Shadow Strategy:** none (see Elevation & Depth).
- **Border:** 1px rule.
- **Internal Padding:** Streamlit's bordered-container default; quality cards 14px 16px.

### Inputs / Fields
- **Style:** Streamlit widgets with borders shown, 8px base radius, filled with pad-tint; on the sidebar, the cloth's deep green with light placeholder text (#b9d0c2).
- **Sliders:** assumption values above the thumb are written in blue on the cloth (#b8c6ff), Source Serif 4 700, tabular.

### Navigation
- **Sidebar menu:** full-width text buttons on the cloth, left-aligned, 0.95rem 500 in #d5e4da; hover adds a 7% white wash; the current page fills with raised cloth and turns white 700. Focus is a 2px #9db0ff ring.
- **Tabs:** one ruled line; labels 600 0.9rem in muted ink, ink on hover; the selected tab gets a 3px ledger-green underline and ledger-green label. No transition. Focus is a 2px blue outline offset 2px.
- **Expanders:** quiet one-line headings in ledger green (600, 0.875rem) with a book icon, underlined on hover; no box.

### Figure Row
One bordered sheet of metrics separated by hairline dividers. Labels in muted ink (600, 0.8125rem), values in the figure face (600, 1.85rem). Deltas are 4px tags; the one neutral delta ("vs. your setting") sits in soft ink on a pale tint.

### Verdict Sheet
A plain sheet whose headline alone carries the result: cheap-green when the price sits well below the range, red-ink well above, amber-ink as caution, and plain ink when the price is inside the range or within 10% of its edge. The body states the range, where today's price sits, how many methods agree, and the "not a prediction" caption.

### The Footing (signature)
The computation added up as a column: an uppercase muted caption, then rows of label and right-aligned figure separated by hairlines, with the operator (+, −, =, ÷) in a fixed 1.1em muted margin. Subtotals are 600 in ink; negatives are red ink in parentheses with a hanging bracket; the total is 2.1rem 700 underlined with a 4px double rule; today's price follows at 1.25rem with no rule.

### Fair Value by Method Chart
Horizontal range bars per method (34% row height), coloured by source: visitor's blue for the model, ledger green for peers, analyst amber for analysts, the market's range outlined only in muted ink. An ink tick marks each middle estimate, a dashed 2px ink line marks today's price, and a ledger-green wash (8% light, 14% dark) shades where most methods agree. Method names sit above each bar with their range on the right, on sheet-coloured backgrounds so the price line passes behind them. Hover notes are wrapped at 30 characters so the label fits a phone-width card. Clicking a bar focuses that method and dims the others to 22%; double-click restores them. No mode bar.

### Charts (general)
Plotly on the sheet colour, chart-grid gridlines, rule-coloured zero lines, soft-ink text, Pad Figures first in the font stack, a horizontal legend below the plot, x-unified hover, no toolbar. Scenarios share one blue hue that deepens from pessimistic (#8193d6) through yours (#2747b8) to optimistic (#14256b). Growth bars set "Priced in by today's price" (ledger green) against "Your assumption" (blue) and grey reality checks. The backtest scatter shades by year on a ledger-green sequential scale (#dbe6dd to #1e4636; #22362c to #8fd1ad at night).

### Quality Badges
4px tags, 0.75rem 700: Strong in cheap green on a pale green tint, OK in deep amber on a pale amber tint, Weak in red on a pale red tint, each with a matching hairline border; not-applicable in muted ink.

## Do's and Don'ts

### Do:
- **Do** set every numeral in Source Serif 4 with tabular lining figures, through Pad Figures in front of Public Sans.
- **Do** end every computed answer on a footing: right-aligned figures, operators in the margin, a 4px double-ruled total, today's price beneath.
- **Do** write the visitor's own assumptions, and what is computed from them, in the reserved blue ink (#2747b8 on the pad, #b8c6ff on the cloth, #9db0ff at night), and what the market prices in in ledger green.
- **Do** write negatives in red ink inside parentheses with the closing bracket hanging outside the column.
- **Do** separate with 1px rules and hairlines on flat sheets with 4 / 6 / 8px corners.
- **Do** colour only the verdict's headline ink, and leave it plain ink when the price is inside the range or within 10% of an edge.

### Don't:
- **Don't** use shadows, gradient cards, tinted panel backgrounds or star scores.
- **Don't** use blue for anything that is not the visitor's own layer: not brand accents, not market data, not decoration.
- **Don't** use ledger green to signal a judgement; it is the binding, not a verdict.
- **Don't** set a number in the sans, or in proportional figures.
- **Don't** fade captions with opacity (Streamlit's 60% caption fade is overridden to full opacity); give them a colour that passes contrast on its own ground.
- **Don't** use amber for anything but analysts, or chart source colours for demand levels.
