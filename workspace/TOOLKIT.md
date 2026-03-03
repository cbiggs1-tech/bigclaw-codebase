# 🦀 BigClaw Toolkit — Quick Reference
*Your tools and how to use them. Ask BigClaw to run any of these anytime.*

---

## 🗣️ How to Use These Tools

**You don't need to remember commands.** Just tell me what you want in plain English:

| You say... | I run... |
|-----------|----------|
| "How's TSLA looking?" | Stock Breakdown |
| "What's TSLA worth?" | Valuation Model |
| "How'd NVDA earnings go?" | Earnings Analyzer |
| "Is KO a good dividend stock?" | Dividend Analyzer |
| "How are my portfolios doing?" | Portfolio Report + Analyzer |
| "What should I buy or sell?" | Decision Engine |
| "What's the market doing?" | Macro Scanner |
| "Any upcoming earnings?" | Economic Calendar |
| "What's the sentiment on TSLA?" | Sentiment Scanner |
| "What's Cathie Wood saying?" | ARK ITK Tracker |
| "What's ARK buying/selling?" | ARK Trades Monitor |
| "What's the weather?" | Weather |
| "Check my email" | Email Check (fixit@ or Gmail) |
| "What's on my calendar?" | Google Calendar |

---

## 📊 The Research Desk (10 Tools)

### 1. Stock Breakdown 🔍
**What:** Full analysis of any stock — financials, performance, analysts, technicals, news
**When to use:** "I'm curious about a stock" or "Give me the rundown on XYZ"
**Depth levels:**
- **Basic** — 6-section overview (fast, ~30 sec)
- **Deep** — adds forensic financials, red/green flags, peer comparison (slower, ~2 min)
- **Risk** — adds risk scanner with composite rating
- **Compare** — sector comparison with rankings

### 2. Valuation Model 💰
**What:** Is this stock cheap or expensive? DCF model, comparable companies, bull/base/bear scenarios
**When to use:** "What's a fair price for TSLA?" or "Is NVDA overvalued?"
**Gives you:** Target price with probability-weighted scenarios, sensitivity table

### 3. Earnings Analyzer 📈
**What:** Post-earnings breakdown — did they beat? What's the guidance? How did the stock react?
**When to use:** After a company reports earnings
**Gives you:** EPS beat/miss, margins, guidance, analyst reaction, verdict

### 4. Dividend Analyzer 💵
**What:** Is this a good income stock? Yield, growth history, sustainability, DRIP projections
**When to use:** Evaluating dividend stocks, especially for the Income portfolio
**Gives you:** Yield analysis, payout safety, peer comparison, 10-year DRIP projection

### 5. Portfolio Analyzer 📋
**What:** Risk analysis of our model portfolios — correlations, stress tests, optimization suggestions
**When to use:** "Are my portfolios too risky?" or "What should I rebalance?"
**Gives you:** Beta, Sharpe ratio, drawdown analysis, COVID/2022 stress test, optimization suggestions

### 6. Macro Scanner 🌍
**What:** Big-picture market view — rates, sectors, sentiment, risk-on/off verdict
**When to use:** "What's the market environment?" or before making any trades
**Gives you:** Treasury yields, sector rotation, VIX, consumer sentiment (Michigan + Fear & Greed), S&P/Gold ratio, risk verdict
**New (Feb 16):** Consumer sentiment section with contrarian buy/sell signals

### 7. Decision Engine 🎯
**What:** Scores every holding across 6 dimensions → buy/sell/hold signals
**When to use:** Daily before market open, or "What should I trade?"
**Gives you:** Color-coded signals (🟢 Buy / 🟡 Watch / 🔴 Sell), concentration alerts, earnings calendar, overlap warnings
**This is the tool that drives our trading decisions.**

### 8. Trade Executor ⚡
**What:** Places paper trades on Alpaca based on decision engine signals
**When to use:** After reviewing signals — "Execute the trades"
**Rules:** No orders before 10 AM ET, limit orders only for buys, $25K max per trade
**Safety:** Paper account only. Real money requires your explicit approval.

### 9. Economic Calendar 📅
**What:** Upcoming earnings, FOMC meetings, CPI/jobs releases, SEC filings
**When to use:** "What's coming up this week?" or "When does NVDA report?"
**Gives you:** Dates, countdowns, and context for each event

### 10. Sentiment Scanner 🐦
**What:** What are people saying about a stock? X/Twitter + Reddit/WSB sentiment
**When to use:** "What's the buzz on TSLA?" or "Is Reddit bullish on PLTR?"
**Gives you:** Sentiment scores, trending topics, volume of mentions

---

## 🔭 Market Intelligence

### ARK ITK Tracker 🏹
**What:** Auto-summarizes Cathie Wood's weekly "In The Know" YouTube presentation
**When:** Runs automatically every Friday at 5 PM ET, posts to Slack
**Why it matters:** Our Innovation Fund follows her thesis. Keeps us aligned.

### ARK Trades Monitor 🏹
**What:** Shows what ARK is buying/selling each day
**When to use:** "What's ARK buying?" or check after market close
**Why it matters:** If Cathie's trimming a name we hold, we should know

### Polymarket 🎰
**What:** Prediction market odds on major events
**When to use:** "What are the odds of X?" or for market-relevant predictions
**Gives you:** Current prices (= probability %), volume, trending markets

---

## 📬 Communication & Scheduling

### Email (fixit@grandpapa.net) ✉️
- Checked automatically 3x/day (8am, 12pm, 5pm CST)
- I draft replies but don't send without your OK
- Purpose: grandpapa.net game support

### Gmail (cbiggs1@gmail.com) 📧
- Connected via OAuth
- Can read, search, archive emails
- Standing approval for spam unsubscribes
- ⚠️ Token may expire (test app, 7-day refresh)

### Google Calendar 📆
- Shows upcoming events
- Included in morning reports

### Weather 🌤️
- Alvarado, TX forecast
- Included in morning reports

---

## 🤖 Automated Reports (Cron Jobs)

| When | What | Where |
|------|------|-------|
| **9:00 AM ET Mon-Fri** | Morning briefing: weather, calendar, email, portfolios, macro, sentiment | Slack DM |
| **4:30 PM ET Mon-Fri** | Afternoon report: portfolio P&L, trade summary, market wrap | Slack DM |
| **8am/12pm/5pm CST daily** | Email check (fixit@) | Slack DM if anything |
| **6:00 AM CST daily** | Security audit (Pi health) | Slack DM if issues |
| **5:00 PM ET Fridays** | ARK ITK weekly summary | Slack DM |

---

## 🏦 Our Portfolios (5 total)

| # | Name | Style | Started |
|---|------|-------|---------|
| 1 | **Value Picks** | Deep Value | Feb 3, 2026 |
| 2 | **Innovation Fund** | Disruptive Innovation (Cathie Wood style) | Feb 3, 2026 |
| 3 | **Growth Value** | GARP (Growth at Reasonable Price) | Feb 3, 2026 |
| 4 | **Income Dividends** | Dividend Growth | Launching Tue Feb 18 |
| 5 | **Momentum Growth** | Aggressive Momentum | Launching Tue Feb 18 |

All paper trading ($100K each) via Alpaca. I can trade autonomously on these. Real money = your call.

---

## 🌐 Website
**bigclaw.grandpapa.net** — auto-updated by morning/afternoon reports
- Dashboard with portfolio summaries
- Signals page (building now)
- Market data, sentiment, news

---

## 💡 Pro Tips

1. **Just ask naturally** — you don't need to remember tool names
2. **"Deep dive on X"** = I'll run multiple tools and give you the full picture
3. **"Quick take on X"** = just the headlines, no deep analysis
4. **"Compare X vs Y"** = side-by-side comparison
5. **"What would Cathie think?"** = I'll frame it through ARK's thesis
6. **"Update the website"** = I'll regenerate data and push to GitHub

---

*This file lives at `~/.openclaw/workspace/TOOLKIT.md` — I'll keep it updated as we add new tools.*
