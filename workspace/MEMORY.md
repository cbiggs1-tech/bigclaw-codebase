# MEMORY.md - Long-Term Memory

## Identity
- BigClaw 🦀 — Curtis's investment research agent on Raspberry Pi via OpenClaw
- Website: bigclaw.grandpapa.net (GitHub Pages + Cloudflare Access)

## Curtis Biggs
- Alvarado, Texas (CST) | Retired nuclear engineer (43 yrs Comanche Peak)
- Wife Lynda (50 yrs), 3 daughters, 10 grandchildren
- GitHub: cbiggs1-tech/bigclaw-ai | Slack DM: D0ADHLUJ400
- Values: honest analysis, humble recs, predictive forecasting, no people-pleasing
- Admires @FarzadClaw's human-like writing style

## Infrastructure
- API keys: ~/.env_secrets (chmod 600, sourced from .bashrc)
- Portfolio DB: ~/bigclaw-ai/src/portfolios.db (SQLite)
- Website export: ~/bigclaw-ai/src/export_dashboard.py → docs/data/ → git push
- Alpaca: paper trading, $100k starting capital

## Portfolios (started Feb 3, 2026)
1. **Value Picks** — JNJ, BAC, PG, BRK-B, KO, AAPL, JPM, V, WFC
2. **Innovation Fund** — NVDA, TSLA, PLTR, CRSP, ARKK, RBLX, QBTS (Cathie Wood style)
3. **Growth Value** — MSFT, AAPL, JPM, UNH, NVDA, TSLA
4. **Income Dividends** — Dividend Growth
5. **Momentum Growth** — Aggressive Momentum
- Trailing stops: Value/Income 8%, Defense 10%, Momentum 10%, GARP/Nuclear 12%, AI Defense 15%, Innovation 20%

## Curtis's TSLA Position
- SOLD 750 shares at ~$398 (Feb 23) — ~$298,500 cash
- Target: rebuy 1,000 shares at ≤$298.50 | Sweet spot: $260-$299
- Thesis: Musk is a "master pumper" — FSD/Optimus hype inflates multiple but earnings won't reflect for years. Multiple compression = buy opportunities. 5-year, 5X return scenario.
- Musk left DOGE May 2025. Consumer boycott lingers. Tesla lost #1 EV crown Jan 2026.

## Trading Rules
- ALL purchases must pass through decision engine (score >= +1)
- Bond score ≤-2 overrides marginal buy signals
- No market orders before 10:00 AM ET; limit orders only for buys
- Execution window: 10:00-10:30 AM ET

## Cron Jobs
- Morning Analysis: 9 AM ET Mon-Fri | Afternoon Report: 4:30 PM ET Mon-Fri
- Price Refresh: every 2hr 9-4 PM ET Mon-Fri | Email Check: 8am CST daily
- Good Morning: 6 AM CST daily | Security Audit: 6 AM CST daily
- ARK ITK: 5 PM ET Fridays | Network Scan: 7 AM CST Sundays
- Weekly Research: 8 AM CST Saturdays | Version Check: 9 AM CST Sundays

## Cloudflare Setup
- grandpapa.net DNS on Cloudflare (free plan), NameCheap is registrar
- bigclaw.grandpapa.net CNAME → cbiggs1-tech.github.io (proxied)
- Zero Trust: BigClaw app, email OTP for cbiggs1@gmail.com, 24hr session

## Key Lessons
- **Elon Musk rule:** ALWAYS verify current Musk status with live search before stating any fact. Got caught twice stating outdated DOGE involvement.
- **Accuracy > speed** when real money is involved.
- BRK-B fails on Alpaca — use yfinance fallback.
- Paper account = $100K shared pool but 7 portfolios = $700K virtual in DB.

## Architecture
- Hub-and-spoke: BigClaw primary + future MiniClaws (InvestorClaw, ScheduleClaw, etc.)
- Curtis wants BigClaw to be much more than just finance
