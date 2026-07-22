# Commando event-driven news (shipped 2026-07-21)

## What was built

1. **llm_comando_news.py** — shared helpers
   - Alpaca news with time cursor
   - Recency-weighted ticker ranking (half-life ~4h)
   - Shared daily event-fire budget (default 10/day)
   - Earnings + FOMC calendar block

2. **llm_comando_radar.py** — continuous GO path
   - Cron: every 2 minutes, weekdays 08:00–15:59 CT
   - On NEW single-stock news: focused Sonnet decision (not full Bull/Bear)
   - Holdings prioritized for thesis-break sells
   - Executes immediately when market open (shared lock with cycle)
   - Log: logs/llm_comando_radar.log
   - State: data/llm_comando_radar_state.json

3. **Scheduled cycles (9 / 11:30 / 14:30)**
   - Discovery now recency-weighted (not raw 24h counts)
   - EVENT CALENDAR injected into context

4. **Watcher (every 5 min)**
   - Still runs mechanical exits + armed triggers
   - NEW: holdings with fresh Alpaca headlines get synthetic fires
     (re-verify thesis / sell if breaking) even if Judge set 0 triggers

## Manual test
`ash
source ~/.env_secrets
venv/bin/python scripts/llm_comando_radar.py --dry-run
tail -50 logs/llm_comando_radar.log
`

## Budgets
- Radar+watcher focused LLM: max 100/day (~\ worst-case at \.02-0.03/fire) (data/llm_comando_event_fires.json)
- Watcher still has max_fires 6 in its own state file
