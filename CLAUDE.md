# BigClaw AI — Project Context for Claude Code

Autonomous paper trading system running on a Raspberry Pi, managing 7 thematic
portfolios + Treasury Reserve through the Alpaca paper account. Decision engine
scores stocks with style-specific weights; a best-in-class optimizer holds the
top 10 by score at all times. Website at bigclaw.grandpapa.net served from `docs/`.

## Architecture

| Component | Location | Purpose |
|---|---|---|
| Pi (host `bigclaw`, user `cbiggs90`) | `~/.openclaw/workspace/scripts/` | Live trading scripts |
| Pi (same host) | `~/bigclaw-ai/` | Git repo clone — website source + `scripts/` mirror |
| GitHub repo | `cbiggs1-tech/bigclaw-codebase` | Source of truth for code, not data |
| SQLite DB | Pi `~/bigclaw-ai/src/portfolios.db` | Portfolio state. WAL mode, 30s timeout |
| Alpaca | paper account | Execution layer — treated as source of truth for positions |

**Rule of thumb:** Pi is truth for live state. Repo is truth for code. Alpaca is truth for positions.

## Portfolio Structure

7 active portfolios + 1 reserve, each allocated capital tracked independently in the DB:

1. **Value Picks** ($100K) — Buffett/Graham quality value
2. **Innovation Fund** ($100K) — Cathie Wood disruptive innovation
3. **Growth Value** ($100K) — Peter Lynch GARP
4. **Income Dividends** ($100K) — dividend growth + safety
5. **Momentum Growth** ($100K) — CANSLIM momentum
6. **Nuclear Renaissance** ($100K) — domain-expertise nuclear/energy
7. **AI Defense & Autonomous** ($100K) — Pentagon thematic
8. **Treasury Reserve** ($300K) — parked capital (not actively traded)

Each portfolio is a walled garden. **No borrowing between portfolios. No overdraft.**

## Cash Wall Defense Stack (CRITICAL)

Every buy order passes through 7 layers. If you modify any buy/sell path, all 7 must still be active.

1. **WAL checkpoint** in `get_verified_cash()` — forces reads to see latest commits
2. **Atomic cash cap** in `_execute_buy_order()` — `actual_alloc = min(alloc, available)` **before** calculating shares
3. **Global buying-power guard** in `_execute_buy_order()` — checks Alpaca account can cover the order
4. **Robust partial-fill polling** via `_wait_for_fill()` shared helper — 3s + 10×2s retries, waits for `filled_qty >= ordered` or `status == FILLED`. Used by both buy AND sell paths.
5. **Inter-buy delay** (2 seconds) in optimization loop — ensures WAL visibility between sequential buys
6. **Lock file** in `main()` — prevents double execution. 30-min stale-lock auto-recovery
7. **Post-trade reconciliation** (`reconcile_with_alpaca`) — minor mismatches (<=2 shares, <=5%) logged as warnings; critical mismatches halt trading via `ALPACA_MISMATCH.flag`

## Decision Engine (pristine invariants)

- `_as_float()` helper in `decision_engine.py` — coerces any yfinance field to float or None. Apply to EVERY numeric comparison pulled from yfinance/finviz. Never do `info.get("X") > 0` directly — yfinance occasionally returns strings, NaN, Inf.
- **Per-ticker try/except** in `run_analysis` — a single bad ticker cannot kill the run. Skipped tickers are marked `scoring_error: True` with score 0 and flagged in `results`.
- **Style weight key names** must match emitted signal category names exactly: `RSI`, `MACD`, `SMA50`, `SMA200`, `Cross`, `RelStrength`, `EarningsGrowth`, `RevenueGrowth`, `PE`, `DebtEquity`, `ShortInterest`, `Insider`, `BondMkt`, `ValueOverride`, `DividendYield`, `PEG`, `ROE`, `FCF`, `GrossMargin`, `PayoutSafety`, `EarningsProximity`. Mismatch = silent fallback to weight 1.0.
- **BOND_WEIGHTS keys** must match portfolio names exactly: `Value Picks`, `Innovation Fund`, `Growth Value`, `Income Dividends`, `Momentum Growth`, `Nuclear Renaissance`, `AI Defense & Autonomous`.

## Best-in-Class Strategy

Each portfolio holds the top `MAX_HOLDINGS` (10) stocks by score at all times. NOT buy-and-hold.

Per session:
1. Score ALL candidates (held + universe). Rank by score.
2. Target = top 10. Anything held but not in top 10 gets sold.
3. Anything in top 10 not held gets bought (cash permitting, score >= SCORE_BUY_MINIMUM).
4. If at max count and a better candidate arrives, sell weakest held to fund it.
5. `MAX_POSITION_PCT` (20%) only enforced at monthly rebalance — let winners run.
6. SGOV exempt from all counts/checks (legacy — sweep removed, but holdings exist from before).

No loyalty to existing positions. "If a stock doesn't perform, it becomes someone else's stock."

## Schedules

### System crontab (`crontab -e` on Pi) — reliable, always runs

- `50 6 * * *` morning_briefing_gather.py
- `55 7 * * 1-5` morning_data_gather.py
- `25 15 * * 1-5` afternoon_data_gather.py
- `30 7 * * 1-5` daily_export.sh
- `0 9,10,12,14 * * 1-5` refresh_all.sh
- `30 16 * * 1-5` refresh_all.sh
- `0 10 * * 1-5` autonomous_trader.py (**only one trader trigger — OpenClaw duplicate is disabled**)
- `*/15 9-15 * * 1-5` stop_check.py
- `0 9 * * 6` candidate_screener.py (Saturday)
- `30 10,11,12,13,14,15 * * 1-5` sentiment.py
- **`SHELL=/bin/bash` required at top** (cron default `dash` doesn't support `source`)

### OpenClaw crons (`~/.openclaw/cron/jobs.json`) — LLM-powered

- Good Morning + Security Check (07:00 CT, Gemini Flash Lite)
- Morning Data Gather (07:55 CT, Gemini) — reads file, no LLM analysis
- Morning Market Analysis (08:00 CT, Sonnet 4.6) — formats + posts to Slack
- Afternoon Summary (15:30 CT, Sonnet 4.6)
- Weekly Research Session (Sat 08:00, Sonnet)
- Weekly Style Compliance Audit (Sat 09:00, Gemini)
- Others: Options Intelligence, Price Refresh, ARK ITK, Network Scan, Version Check

**OpenClaw runs via systemd user service** — `openclaw-gateway.service`. If crons stop firing, check:
```bash
systemctl --user status openclaw-gateway.service
# If stuck auto-restarting:
systemctl --user reset-failed openclaw-gateway.service
systemctl --user restart openclaw-gateway.service
```

## Known pitfalls

- **OpenClaw exec permissions:** Only Gemini-via-OpenRouter auto-allows `exec` tool. Grok (direct or via OpenRouter), Haiku, and direct Anthropic Sonnet all require manual approval → cron dies with "approval required". Do NOT swap models on exec-using crons without finding OpenClaw's permission layer first.
- **Slack message parameter:** Use `target=D0ADHLUJ400, channel=slack`. Old `channel=D0ADHLUJ400` syntax fails.
- **DAY orders after market close:** Market orders submitted after 4 PM ET expire without filling. Reset scripts should check market hours.
- **SGOV sweep is REMOVED** — every DB write failure we've seen came from SGOV. Idle cash stays as cash. If you see `MONEY_MARKET_TICKER` code, it's legacy SGOV exemption guards, not active sweep.
- **OpenRouter credit exhaustion** has historically silenced all LLM crons for days. Check `~/.openclaw/cron/runs/*.jsonl` when crons go quiet.
- **yfinance returns strings/None/NaN randomly.** ANY new numeric comparison against yfinance fields must wrap with `_as_float()`.

## Common commands

```bash
# SSH to the Pi
ssh cbiggs90@bigclaw

# Check DB vs Alpaca sync (should always be zero mismatches)
ssh cbiggs90@bigclaw 'source ~/.env_secrets && python3 -c "..."'

# Manual trader run (emergency / test)
ssh cbiggs90@bigclaw "cd ~/.openclaw/workspace/scripts && source ~/.env_secrets && python3 autonomous_trader.py"

# Full reset (last resort — liquidates all positions, wipes DB)
ssh cbiggs90@bigclaw "cd ~/.openclaw/workspace/scripts && python3 bigclaw_full_reset.py --execute"

# Check OpenClaw cron schedule and status
ssh cbiggs90@bigclaw "python3 /tmp/check_openclaw_jobs.py"
```

## Working principles

- **STOP at first error is banned.** Before deploying any fix, trace every downstream caller, every parallel code path, every edge case. Fix the class of bug, not the instance.
- **Financial-grade quality.** One wrong number destroys trust. If unsure, halt trading (circuit breaker) rather than proceed on bad data.
- **Pi is truth.** Always read live state from the Pi before acting. Auto-memory can be stale.
- **Terse responses.** Curtis wants results, not explanations of process. Summarize in 1-3 sentences unless deeper analysis is explicitly requested.
- **External review.** Grok (via chat) reviews major code changes independently. Push to GitHub before asking for review.

## Style guide for edits

- No emojis in code comments or logs unless already present in the file.
- Descriptive log lines over silent operations: `log_trade()` for trade actions, `logger.info/warning/error` for diagnostics.
- Commits attribute with `Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>`.
- Changes to `scripts/` also get copied to Pi at `~/.openclaw/workspace/scripts/`. Keep both in sync.

## When in doubt

Read MEMORY.md via the auto-memory system for this user — it indexes previous sessions and decisions.
