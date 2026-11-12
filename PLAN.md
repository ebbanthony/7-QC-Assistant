# Stock Valuation Dashboard — Automation Plan

Replaces the manual loop of *prompt generator → Claude chat → copy/paste into Excel*
with a local web dashboard that refreshes itself.

## Decisions (from Q&A)

| Topic | Decision |
|---|---|
| Front end | Local web dashboard (Streamlit), runs on Windows |
| Valuation research | Python script → Claude API with web search, structured JSON output |
| Market data | Yahoo Finance (`yfinance`); if it fails for a ticker, Claude finds the quote from another reliable source, and the row is flagged as using a fallback |
| Overwrite policy | Auto-overwrite, every prior value appended to a history table |
| Columns owned by automation | Price, Change %, P/E, Intrinsic Low/Mid/High, Buy Cycle, Sell Cycle, Updated |
| Tickers | Add / edit / remove directly in the dashboard |
| ETFs | Valued by look-through (forward P/E vs. history, weighted view of top holdings) |
| Signal colours | Driven by Mid vs Price (5 bands below) |
| Methodology | Designed fresh (below); no analyst price targets |

## Signal bands (editable in Settings)

`Mid vs Price = (Mid − Price) / Price`

| Band | Range | Meaning | Colour |
|---|---|---|---|
| Strong Buy | ≥ +30% | Obvious buy / add | dark green |
| Add | +10% to +30% | Accumulate | light green |
| Hold | −10% to +10% | Fairly valued | neutral |
| Trim | −25% to −10% | Trim / take some profit | light red |
| Sell | ≤ −25% | Sell / take profit | dark red |

## Architecture

```
app.py                 Streamlit dashboard (table, filters, edit tickers, Refresh, Settings, History)
refresh.py             CLI: `python refresh.py [--all | --tickers NVDA,MSFT | --prices-only | --scheduled]`
valuation/
  market.py            yfinance quotes → Claude fallback
  research.py          Claude API + web search → validated JSON per ticker
  prompts.py           Stock and ETF research prompts
  bands.py             Mid-vs-Price → band/colour
db.py                  SQLite: tickers, valuations (current), history, settings, run_log
data/valuations.db     Local data (git-ignored)
scripts/
  launch_dashboard.bat Double-click to open the app
  install_schedule.ps1 Registers a daily Windows Task Scheduler job
.env                   ANTHROPIC_API_KEY (git-ignored)
```

### Refresh flow
1. Load the active tickers from SQLite.
2. **Prices** (fast, cheap): yfinance batch quote → price, change %, trailing/forward P/E.
   For a missing ticker, ask Claude (web search) for the quote, and store the source and the `fallback` flag.
3. **Valuations** (slow, paid): one Claude API call per ticker using the web-search tool,
   forced to a JSON schema:
   `{low, mid, high, currency, method_notes, sources:[{name,url,value,date}], buy_cycle, sell_cycle, confidence}`.
4. Validate: low ≤ mid ≤ high, all values positive, at least 3 independent sources, and Mid within a sanity range of price
   (otherwise mark the row `needs_review` and keep the old values).
5. Copy the old row to `history`, overwrite `valuations`, and stamp `updated_at`.
6. Write a `run_log` entry (tickers ok / failed, token cost).

### Manual vs. scheduled
- **Manual:** "Refresh all", "Refresh selected rows", and "Prices only" buttons in the dashboard.
  A newly added ticker gets researched automatically.
- **Scheduled:** Windows Task Scheduler runs `refresh.py --scheduled` daily at a fixed time.
  The script checks the cadence set in Settings (Off / Monthly / Quarterly, plus the day of the month)
  and the last full run, and only does the full research when it's due. On other days it refreshes prices only.
  You switch cadence in the dashboard without touching Task Scheduler.
  The task is set to "run as soon as possible after a missed start", so a PC that was asleep catches up.

## Research methodology (prompt design)

**Stocks.** Gather **independent intrinsic / fair-value estimates**, *excluding sell-side analyst price targets
and consensus targets*. Candidate sources: Morningstar fair value, GuruFocus GF Value / DCF,
Alpha Spread, Simply Wall St DCF, Finbox, ValueInvesting.io, and reputable published DCFs.
Then:
- Normalise to the listing currency (e.g. CSU in CAD).
- Drop outliers (more than 2× away from the median).
- **Low** = the lowest kept estimate (or the 25th percentile), **Mid** = the median, **High** = the highest (or the 75th percentile).
- Cite every source with its value and date. Reject estimates older than about 12 months.
- **Buy/Sell Cycle**: classify which phase of the economic cycle favours buying and selling this name
  (Early / Mid / Late / Recession, with the same vocabulary as the current sheet), with a one-line rationale.

**ETFs (look-through).** Two methods, averaged:
1. Fund forward P/E vs. its 5–10-year average P/E → implied fair price.
2. Weighted fair-value gap of the top ~10 holdings (reusing stock valuations already in the DB where they exist).
   Report Low/Mid/High as the range across the two methods. Confidence is marked lower.

**Model / cost.** Default to Claude Sonnet 5.5 for research, with Opus available as a setting.
Rough budget: about $0.10–0.50 per ticker per full refresh, depending on searches, so about $5–20 for ~45 tickers.
A monthly cadence costs a few dollars to low tens per month. The run log shows the actual cost.

## Dashboard features
- A main table that mirrors the Excel layout: Company, Ticker, Price, Change %, P/E, Mid vs Price (bar),
  Low / Mid / High, Updated, Buy Cycle, Sell Cycle, coloured by band.
- Filters by band, group/tag, and stale (> N days); sorting on any column.
- An editable ticker list (add, rename, change exchange suffix such as `CSU.TO`, set ETF flag, tags, remove/archive).
- Manual overrides: pin your own Low/Mid/High or cycle for a row, so automation leaves it alone.
- A row drill-down with sources, method notes, confidence, and a history chart of Mid vs Price over time.
- Export to Excel (.xlsx) with the same formatting.
- A one-time import of your current Excel sheet to seed the tickers and existing valuations.

## Build milestones
1. Data layer + Excel import + dashboard displaying your current numbers with band colours.
2. yfinance price refresh + Claude fallback + "Prices only" button.
3. Claude research (stocks) + validation + history + "Refresh" buttons.
4. ETF look-through method.
5. Settings (bands, cadence, model) + Task Scheduler installer + launcher .bat.
6. Excel export, overrides, history charts.

## What I need from you
- An **Anthropic API key** (console.anthropic.com), saved in `.env` on your PC. Never paste it into chat.
- Your **current workbook (.xlsx)**, or a CSV export, to seed the tickers and the existing valuations.
- **Python 3.11+** on Windows (I'll provide `setup.bat` that creates a venv and installs dependencies).
