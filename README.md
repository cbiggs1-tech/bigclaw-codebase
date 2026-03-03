# BigClaw Codebase

BigClaw is an AI-powered investment research agent running on a Raspberry Pi via [OpenClaw](https://openclaw.com). It uses Grok 4 as its primary model with Gemini fallbacks.

## Purpose of This Repo

This is a **read-only snapshot** of the BigClaw configuration and codebase, published for external review and analysis. All API keys and secrets have been redacted.

## Structure

```
openclaw.json          # Main config (model routing, params, channels) - REDACTED
workspace/
  SOUL.md              # Personality, analytical mandates, response style
  MEMORY.md            # Long-term memory and portfolio context
  ANALYSIS.md          # Deep synthesis protocol reference
  AGENTS.md            # Behavioral rules, heartbeat, safety
  IDENTITY.md          # Name, avatar, vibe
  TOOLS.md             # Tool inventory and API notes
  USER.md              # User profile
  HEARTBEAT.md         # Heartbeat config
  scripts/             # Python scripts for analysis, trading, reporting
    portfolio_report.py
    decision_engine.py
    macro_scanner.py
    sentiment.py
    trade_executor.py
    ... and more
skills/                # ClawHub skills (25+ installed)
  self-improve/        # Self-diagnosis and tuning skill
  portfolio-manager/
  stock-evaluator/
  ... and more
cron/
  jobs.json            # Scheduled job configs (morning analysis, price refresh, etc.)
```

## Key Features

- **7 paper trading portfolios** via Alpaca API (Value, Innovation, Growth Value, Income Dividends, Momentum Growth, Nuclear Renaissance, AI Defense)
- **Decision engine** with scoring system for trade signals
- **Automated reports** posted to Slack and pushed to GitHub Pages dashboard
- **Self-improvement skill** for diagnosing and fixing its own response quality
- **Deep synthesis mandate** requiring causal chain analysis, not just data dumps

## Not Included

- API keys / tokens (redacted)
- Google credentials
- Portfolio database (portfolios.db)
- Session state / delivery queue
- Runtime logs
