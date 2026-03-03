# TOOLS.md - Local Notes

## Brokerage
- **Alpaca** — paper trading account, $100k starting capital
- Keys in ~/.env_secrets (ALPACA_API_KEY, ALPACA_SECRET_KEY)
- BRK-B ticker format fails on Alpaca — use yfinance fallback
- Python: `from alpaca.trading.client import TradingClient`

## Slack
- Curtis DM channel: **D0ADHLUJ400**
- Bot name: BigClaw Agent
- Icon: golden crab logo (set Feb 12, 2026)

## Social/Sentiment APIs
- **X/Twitter** — Bearer token in ~/.env_secrets (X_BEARER_TOKEN), API v2 recent search
- **Apify** — token in ~/.env_secrets, used for Stocktwits scraping fallback
- **Stocktwits** — direct API (no auth) + Apify fallback
- **Reddit/WSB** — public JSON API, User-Agent: BigClawBot/1.0
- **Polymarket** — Gamma API, no auth needed

## News Sources
- **Motley Fool** — RSS feeds (main, investing, retirement, personal_finance) via feedparser
- **Yahoo Finance** — yfinance library per-ticker news
- **Brave Search** — API key in OpenClaw config (env.BRAVE_API_KEY)

## Portfolio Database
- SQLite at ~/bigclaw-ai/src/portfolios.db
- Tables: portfolios, holdings, transactions, daily_snapshots, pending_orders
- Python modules at ~/bigclaw-ai/src/ (portfolio.py, alpaca_data.py, export_dashboard.py)

## Website
- GitHub Pages: bigclaw.grandpapa.net
- Repo: github.com/cbiggs1-tech/bigclaw-ai (branch: main)
- Dashboard files: ~/bigclaw-ai/docs/
- Data JSONs: ~/bigclaw-ai/docs/data/ (portfolios, market, sentiment, news, analysis, portfolio_analysis, metadata)
- Export script: ~/bigclaw-ai/src/export_dashboard.py
- Performance chart: ~/bigclaw-ai/src/generate_chart.py → docs/data/performance_chart.png

## Cron Schedules (Eastern Time)
- Morning Analysis: 9:00 AM ET Mon-Fri
- Afternoon Report: 4:30 PM ET Mon-Fri
- Both deliver to Slack DM D0ADHLUJ400

## Pi Hardware (A/V)
- **Camera:** Huawei/Ruision UVC Camera (USB, /dev/video0) — video + built-in mic
- **Microphone:** Built into camera (ALSA card 3 "Camera", device 0)
- **Speaker:** 3.5mm analog jack (ALSA card 0 "Headphones", PCM volume 100%)
- Capture: `ffmpeg -f v4l2 -i /dev/video0 -frames:v 1 -update 1 -y /tmp/snap.jpg`
- Playback: `aplay -D hw:0,0 file.wav` or `ffmpeg ... | aplay`
- Record audio: `arecord -D hw:3,0 -f S16_LE -r 16000 -c 1 -d 5 /tmp/recording.wav`

## Printers (CUPS)
- **Brother MFC-J6935DW** — networked, queue name `Brother_MFC_J6935DW`
- Also available: Canon MX920 series (`Canon_MX920_series`)
- Print command: `lp -d Brother_MFC_J6935DW /path/to/file.pdf`
- Lynda's iMac shares same Brother printer (separate queues)

## CLI Tools
- jq: JSON processing
- sqlite3: Direct DB queries (`sqlite3 ~/bigclaw-ai/src/portfolios.db`)
- imagemagick (convert): Image manipulation
- sox: Audio processing
- ffmpeg: Video/audio processing

## Coding Tools
- Claude Code CLI: v2.1.39 at ~/.npm-global/bin/claude
- Python 3.13, Node v22.22, Git
- Key Python packages: alpaca-py, yfinance, matplotlib, feedparser, pytz, pandas, numpy, beautifulsoup4, pillow, flask

## BigClaw Scripts (workspace/scripts/)
- **portfolio_report.py** — Portfolio data from Alpaca + SQLite DB
- **polymarket.py** — Prediction market data (Gamma API, no auth needed)
  - `--market-movers` for finance-relevant markets
  - `--search "query"` for specific topics
  - `--trending` for top volume markets
- **sentiment.py** — Multi-source sentiment (X + Reddit + Stocktwits)
  - `source ~/.env_secrets && python3 sentiment.py TSLA NVDA AAPL`
  - Stocktwits API returns 403 as of Feb 2026 — X and Reddit work fine
- **technical_analysis.py** — RSI, MACD, Bollinger, SMA, support/resistance, signals
  - `python3 technical_analysis.py TSLA NVDA AAPL`
- **economic_calendar.py** — Earnings dates, FOMC schedule, CPI/jobs, SEC filings
  - `python3 economic_calendar.py --all TSLA NVDA --sec`
  - `python3 economic_calendar.py --earnings TSLA` (just earnings)
  - `python3 economic_calendar.py --economic` (just macro events)
- **weather.py** — Open-Meteo forecast for Alvarado, TX (no API key)

## Python Finance Packages
- **edgartools** — SEC EDGAR filings, insider trades, company data (set_identity required)
  - `from edgar import set_identity, Company; set_identity("BigClaw fixit@grandpapa.net")`
  - `Company("TSLA").get_filings(form="10-K")`, `form="4"` for insider trades
- **finvizfinance** — Stock screener, fundamentals, insider trading, analyst ratings
  - `from finvizfinance.quote import finvizfinance` — per-ticker data
  - `from finvizfinance.screener.overview import Overview` — stock screener
- **ffn** — Financial functions library (returns analysis, drawdowns, stats)
- **ta + pandas-ta** — Technical indicators (RSI, MACD, Bollinger, etc.)

## Email
- **Himalaya CLI** — fixit@grandpapa.net (IMAP/SMTP via Namecheap Private Email)
  - Config: ~/.config/himalaya/config.toml
  - `himalaya envelope list` — inbox
  - `himalaya message read <id>` — read message
  - Email check cron: 8am, 12pm, 5pm CST daily

## GitHub CLI
- `gh` authenticated as cbiggs1-tech via GH_TOKEN in ~/.env_secrets
- `gh issue list/create`, `gh pr list`, `gh api` all working

## File Locations
- API secrets: ~/.env_secrets (chmod 600, sourced from .bashrc)
- Old bot code: ~/bigclaw-ai/src/ (tools/, agent.py, bot.py, scheduler.py, etc.)
- OpenClaw workspace: ~/.openclaw/workspace/
- BigClaw icon: ~/bigclaw-ai/docs/bigclaw-icon.jpg

## Discord — BigClaw Server
- Guild ID: 1469020342495215741
- #general channel ID: 1469020343535669343
- unusual_whales_crier bot: active, posts economic news + market updates + trading states + ticker alerts
- Monitored tickers: TSLA, NVDA, SPY, QQQ, PLTR, MSFT, GE, TLT, GLD, VIX
- BigClaw Trading bot ID: 1469045633267793930
- Read messages: `curl -H "Authorization: Bot $DISCORD_TOKEN" "https://discord.com/api/v10/channels/1469020343535669343/messages"`

## Unusual Whales API
- Token: UNUSUAL_WHALES_TOKEN in ~/.env_secrets
- Script: ~/.openclaw/workspace/scripts/unusual_whales.py
- Endpoints confirmed working:
  - `/api/stock/{ticker}/option-contracts` — options flow per ticker
  - `/api/darkpool/{ticker}` — real-time dark pool prints
  - `/api/option-trades/flow-alerts` — market-wide unusual flow alerts
  - `/api/congress/recent-trades` — congressional trading disclosures
- Usage: `source ~/.env_secrets && python3 scripts/unusual_whales.py [--ticker TSLA] [--congress] [--flow-alerts] [--all]`
- Best signal days: Tue-Thu (avoid Monday open and Friday/expiry noise)
