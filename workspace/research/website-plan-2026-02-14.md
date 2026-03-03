# BigClaw Website — Current State & Upgrade Plan
*bigclaw.grandpapa.net — GitHub Pages at ~/bigclaw-ai/docs/*

---

## 📍 Current Website Structure

### Tech Stack
- **Static site** hosted on GitHub Pages (no backend)
- Single `index.html` + `styles.html` + `chart-detail.html`
- Bloomberg-terminal inspired dark theme (Inter font, dark navy/black)
- TradingView live news widget embedded
- Data loaded from JSON files in `docs/data/`
- Auto-updated by morning/afternoon cron jobs via `export_dashboard.py` → git push

### Current Data Files (`docs/data/`)
| File | Content | Updated By |
|------|---------|------------|
| `portfolios.json` | Portfolio holdings, values, returns | export_dashboard.py |
| `market.json` | Market indices, sector data | export_dashboard.py |
| `sentiment.json` | X/Reddit/Stocktwits sentiment scores | export_dashboard.py |
| `news.json` | Recent financial news headlines | export_dashboard.py |
| `analysis.json` | Market analysis text | export_dashboard.py |
| `portfolio_analysis.json` | Portfolio commentary/analysis | afternoon cron |
| `performance_chart.png` | Portfolio performance chart | generate_chart.py |
| `metadata.json` | Last update timestamp | export_dashboard.py |

### Current Pages/Sections
1. **Dashboard Home** (index.html)
   - Portfolio summary cards (3 portfolios, total value, returns)
   - Market indices ticker (S&P, Nasdaq, Dow)
   - Performance chart (static PNG)
   - TradingView news widget
   - Sentiment scores
   - Market analysis text
   - Last updated timestamp

2. **Chart Detail** (chart-detail.html)
   - Enlarged performance chart view

### Known Issues
- ❌ Mobile rendering problems on iPhone (GitHub Issue #3)
- ❌ Only shows 3 portfolios (needs to handle 5)
- ❌ No interactive tools — just static data display
- ❌ Performance chart is a static PNG, not interactive
- ❌ No per-stock analysis pages
- ❌ Sentiment data can go stale (Stocktwits 403)

---

## 🛠️ Available Tools (not yet on website)

### Research Scripts (`~/.openclaw/workspace/scripts/`)
| Script | Output | Website Potential |
|--------|--------|-------------------|
| `stock_breakdown.py` | Full stock analysis (--deep --risk --compare) | Per-ticker analysis pages |
| `valuation_model.py` | DCF, comps, bull/base/bear scenarios | Valuation section per stock |
| `earnings_analyzer.py` | Post-earnings breakdown | Earnings reaction pages |
| `dividend_analyzer.py` | Yield, DRIP projections, sustainability | Dividend portfolio dashboard |
| `portfolio_analyzer.py` | Risk, correlation, optimization, stress test | Portfolio health dashboard |
| `macro_scanner.py` | Market overview, sector rotation, VIX | Enhanced market overview |
| `decision_engine.py` | Buy/sell/hold signals with scores | **Trading Signals dashboard** |
| `trade_executor.py` | Executes paper trades via Alpaca | Trade log/history page |
| `technical_analysis.py` | RSI, MACD, Bollinger, SMA, signals | Technical charts section |
| `economic_calendar.py` | Earnings dates, FOMC, CPI/jobs | Events calendar page |
| `sentiment.py` | X + Reddit sentiment by ticker | Enhanced sentiment section |
| `polymarket.py` | Prediction market data | Prediction odds section |

### Data Sources Available
- Alpaca (paper trading positions + orders)
- yfinance (prices, financials, fundamentals)
- finvizfinance (screener, analyst ratings, insider trades)
- edgartools (SEC filings, Form 4 insider trades)
- X/Twitter API (sentiment)
- Reddit/WSB (public sentiment)
- Polymarket (prediction markets)
- Open-Meteo (weather)
- Google Calendar + Gmail

---

## 🚀 Proposed Website Upgrade

### New Site Architecture

```
bigclaw.grandpapa.net/
├── index.html          ← Dashboard home (enhanced)
├── portfolios.html     ← All 5 portfolios deep dive
├── signals.html        ← Daily Decision Dashboard (decision_engine output)
├── research/           ← Per-ticker analysis pages
│   ├── TSLA.html
│   ├── NVDA.html
│   └── ...
├── macro.html          ← Market overview (macro_scanner output)
├── calendar.html       ← Earnings & economic calendar
├── trades.html         ← Trade log & history
├── data/               ← JSON data files (auto-updated)
│   ├── portfolios.json
│   ├── signals.json        ← NEW: decision engine output
│   ├── macro.json          ← NEW: macro scanner output
│   ├── research/           ← NEW: per-ticker analysis JSONs
│   │   ├── TSLA.json
│   │   └── ...
│   ├── trades.json         ← NEW: trade history log
│   ├── calendar.json       ← NEW: upcoming events
│   ├── market.json
│   ├── sentiment.json
│   └── metadata.json
└── assets/
    ├── bigclaw-icon.jpg
    └── charts/             ← Generated chart images
```

### Page Designs

#### 1. Dashboard Home (Enhanced)
- **Portfolio summary** — all 5 portfolios with sparkline charts
- **Today's Signals** — top 3 buy/sell signals from decision engine
- **Market Pulse** — S&P, Nasdaq, VIX, 10yr yield, risk-on/off indicator
- **Upcoming Events** — next 7 days earnings, FOMC, etc.
- **Recent Trades** — last 5 executed paper trades with rationale
- **Last updated timestamp**

#### 2. Portfolio Deep Dive (`portfolios.html`)
- Tabs for each of the 5 portfolios
- Per portfolio: holdings table, sector allocation pie chart, P&L
- Correlation heatmap
- Optimization suggestions (from portfolio_analyzer)
- Stress test results (COVID, 2022 bear)
- Performance vs S&P 500

#### 3. Trading Signals (`signals.html`) ⭐ HIGH VALUE
- Full decision engine dashboard
- Color-coded: 🔴 Sell, 🟡 Watch, 🟢 Buy, ⚪ Hold
- Scores with reasoning for each holding
- Earnings calendar countdown
- Concentration and overlap alerts
- Updated daily before market open

#### 4. Research Pages (`research/TICKER.html`)
- Generated from stock_breakdown.py --deep --risk --json
- Sections: Overview, Financials, Performance, Analysts, Technicals, Risk
- Valuation model summary (DCF, comps, bull/base/bear)
- Auto-generated for all portfolio holdings
- On-demand for any ticker via Slack command

#### 5. Market Overview (`macro.html`)
- Generated from macro_scanner.py --json
- Interest rates, yield curve
- Sector rotation heatmap (ETF performance)
- VIX & risk indicators
- Market breadth
- Risk-On / Risk-Off verdict

#### 6. Economic Calendar (`calendar.html`)
- Earnings dates for all holdings
- FOMC meetings
- CPI, jobs, GDP releases
- Sorted by date, countdown timers

#### 7. Trade History (`trades.html`)
- Log of all paper trades executed
- Date, ticker, action, shares, price, rationale, P&L
- Running performance vs buy-and-hold

### Implementation Approach

**Phase 1 — Data Pipeline (build first)**
- Add --json output to all scripts (most already have it)
- Create `export_research.py` master script that:
  - Runs decision_engine.py --json → data/signals.json
  - Runs macro_scanner.py --json → data/macro.json
  - Runs stock_breakdown.py --json for each holding → data/research/TICKER.json
  - Copies trade log → data/trades.json
  - Runs economic_calendar.py --json → data/calendar.json
- Wire into morning/afternoon cron jobs

**Phase 2 — Website Build**
- Build new HTML pages that read from JSON data files
- Use vanilla JS (no framework needed for static site)
- Keep Bloomberg-dark theme
- Mobile-responsive (fix Issue #3)
- Add navigation menu

**Phase 3 — Polish**
- Interactive charts (Chart.js or lightweight library)
- Sector allocation pie charts
- Correlation heatmaps
- Sparkline mini-charts for portfolio cards
- Search bar for any ticker

### Update Flow (automated)
```
Morning (9 AM ET):
  1. Cron runs all analysis scripts
  2. export_research.py generates all JSONs
  3. git push to GitHub Pages
  4. Website auto-updates (no server needed)

After Trades (10:30 AM ET):
  5. Trade executor logs trades
  6. Update trades.json
  7. git push

Afternoon (4:30 PM ET):
  8. Afternoon report updates portfolio data
  9. git push final daily update
```

---

## 📋 Priority Order

1. **Signals page** — highest value, most unique to BigClaw
2. **Enhanced dashboard** — first impression, shows all 5 portfolios
3. **Portfolio deep dive** — where the real analysis lives
4. **Market overview** — macro context
5. **Research pages** — per-ticker deep dives
6. **Trade history** — accountability and performance tracking
7. **Calendar** — nice to have

---

*This plan turns bigclaw.grandpapa.net from a basic dashboard into a full research terminal.*
*All data auto-generated from our existing tools — no manual updates needed.*
