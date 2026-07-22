# Commando GO alpha test — after Friday close

**When:** After market close Friday 2026-07-25 (ET)  
**Goal:** See whether event-driven RADAR GO fires produce measurable edge vs standing down / SPY.

## Scope
Do **not** change live trading rules Friday afternoon.  
**Read-only analysis** + optional scorecard wiring for next week.

## Data sources
- \data/llm_comando_event_fires.json\ — fire log
- \data/llm_comando_journal.jsonl\ — type=radar entries + decisions/trades
- \data/llm_comando_outcomes.jsonl\ — closed trades (if any GO buys closed)
- \logs/llm_comando_radar.log\ — GO narrative lines
- Alpaca / yfinance for forward returns on tickers that were bought or stood-down

## Metrics to compute
1. Count: GO fires, stand_down vs buy vs sell decisions
2. Cost: sum of fire costs for the week
3. For each **buy** from radar: entry features + forward 1d / 5d return vs SPY
4. For **stand_down** on gap-downs (e.g. MCB-style): did avoiding hurt or help? (forward path of skipped names)
5. Holdings thesis-break sells: outcome vs if held
6. Compare week: Commando total return vs SPY (same window)

## Deliverable
- Short report: \data/comando_go_alpha_YYYY-MM-DD.md\
- Optional next step: auto-append GO outcomes to entry_features / weekly scorecard (only if first report is useful)

## Caps (already live)
- Event fires: **100/day** (Sonnet mini-sessions ~\.02–0.03 each)

## Related
- Radar: \scripts/llm_comando_radar.py\
- News utils: \scripts/llm_comando_news.py\
- Ops note: \data/COMANDO_RADAR.md\
