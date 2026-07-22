# BigClaw AI — Project Context for Grok 4.5

**Primary coding agent:** Grok 4.5 (this session / VS Code Grok Build)  
**Operator:** Curtis Biggs  
**Last handoff refresh:** 2026-07-21  

This file is the operating manual for coding work on BigClaw. Prefer **live Pi state + this file + `DESIGN_BASIS.md`** over chat memory or local Windows copies.

---

## 1. What BigClaw Is

Autonomous **paper-trading** investment research system on a Raspberry Pi.

- **Never real money.** Connecting to a live brokerage is a full redesign, not a config flip.
- **9 active portfolios** (~$100K each, paper):
  1. Value Picks (Buffett/Graham)
  2. Innovation Fund (Cathie Wood)
  3. Growth Value (Lynch GARP)
  4. Income Dividends
  5. Momentum Growth (CANSLIM)
  6. Nuclear Renaissance (domain expertise)
  7. AI Defense & Autonomous
  8. **LLM-ETF Focus** (dialectic; ETF-tilted control)
  9. **LLM-Commando** (dialectic; single-stock only)
- **Treasury Reserve retired** (May 2026, `is_active=0`). Idle cash stays cash — **no SGOV sweep**.
- Dashboard: https://bigclaw.grandpapa.net  
- Code review remote: https://github.com/cbiggs1-tech/bigclaw-codebase  

### Dual decision architecture (load-bearing)

| Layer | Portfolios | Who decides | Python role |
|-------|------------|-------------|-------------|
| **Rule-based** | 1–7 | Deterministic: style gates + 20-dim scores + best-in-class top-10 + trailing stops + **entry gate** | Full strategy |
| **LLM dialectic** | 8–9 | Bull → Bear → **Judge** (Commando Judge = Opus 4.8) | Info + safety rails only; **no Python sell strategy** |

Do **not** blend these. Hard IPS gates on the 7; principles/lenses for the Judge on the 2.

---

## 2. Sources of Truth (in order)

1. **Pi live runtime** — `ssh bigclaw` → `~/bigclaw-ai/`  
   - Scripts: `~/bigclaw-ai/scripts/`  
   - **Symlink:** `~/.openclaw/workspace/scripts` → `~/bigclaw-ai/scripts` (edit repo = edit live)  
   - DB: `~/bigclaw-ai/src/portfolios.db` (WAL, 30s busy timeout)  
2. **Alpaca paper** — positions / fills execution truth  
3. **GitHub `main`** — code history / review snapshot (not deploy tooling)  
4. **Docs:** `DESIGN_BASIS.md` (engineering), `PORTFOLIO_STYLES.md` (IPS), this `GROK.md`  
5. **Claude memory (legacy):** `C:\Users\cbigg\.claude\projects\C--Users-cbigg\memory\` — useful history; **verify before acting**  
6. **Windows OneDrive `bigclaw-ai`** — **stale**. Do not deploy from it.

**Rule of thumb:** Pi = live state. Repo = code. Alpaca = positions. Memory files can lag.

### Access

```bash
ssh bigclaw
# Host: BigClaw · user: cbiggs90 · LAN ~192.168.1.171 (alias bigclaw)
# Secrets: source ~/.env_secrets
```

OpenClaw gateway: `systemctl --user status openclaw-gateway.service`  
Logs: `~/bigclaw-ai/logs/bigclaw.log`  
Mismatch halt flag: grep codebase for `ALPACA_MISMATCH` — **do not guess path**.

### Windows checkout gotcha

GitHub tree includes `docs/data/charts/CON.json`. **`CON` is a reserved Windows device name** — normal `git clone` checkout fails on Windows. Prefer SSH to Pi, or sparse-checkout excluding that path. Do not invent renames without Curtis approval (dashboard data).

---

## 3. Working Style (Curtis)

- Results over process theater. Short answers unless asked for depth.
- Decisive when given clear options.
- Protect what works; no drive-by refactors.
- After behavior changes: update **DESIGN_BASIS.md** + **docs/sources.html** when schedules, feeds, rules, or infra change.
- Prefer **1–2 weeks stable run** after a batch of fixes before layering more (`feedback_validate_before_layering`).
- Financial-grade quality: one wrong number destroys trust. Prefer **halt** over trade on bad data.

---

## 4. Absolute Safety Rules

### Never without explicit per-instance permission
- Wipe / reset / drop / truncate `portfolios.db`
- `bigclaw_full_reset.py`, `full_reset_monday.py`, mass liquidations
- Force-push to `main`, destructive git history rewrite on Pi
- Anything that spends **real** money or touches live brokerage credentials

### Always
- Re-read **fresh holdings** at LLM sell execution; clamp sells to held shares (June 15 short incident).
- Keep **cash wall** stack intact on every buy path (see §6).
- **Verify paths by grepping live code** for flag/lock/state constants (May SHOP / wrong `ALPACA_MISMATCH` path).
- **STOP-at-first-error is banned.** Trace callers, parallel paths, partial fills, edge cases; fix the *class* of bug.
- Dual interpreters:
  - LLM scripts → `venv/bin/python` (slack_sdk, anthropic, numpy; **no `ta`**)
  - Rule engine → system `python3` (`ta`; **no slack_sdk**)
- Atomic writes for shared JSON (e.g. `signals.json`: temp + `os.replace`).
- Pre-trade **mass-desync / unexpected short** guards stay on.

---

## 5. Rule-Based Portfolios (1–7) — Doctrine

### Best-in-class (not buy-and-hold)
- Each book: top **10** by score every session. Hard cap **70** holdings across the 7.
- Rank held + candidates together; sell weakest to fund better. No loyalty.
- `MAX_POSITION_PCT` 20% enforced at **monthly** rebalance — let winners run intramonth.
- **No SWAP_GAP inertia** that blocks a clearly better name.

### IPS gates are authoritative
- Style gate fail = fail. **No AI override layer** (`gate_reasoning.py` retired → `scripts/attic/`).
- Dynamics = scoring + rotation, not case-by-case LLM exceptions.
- Universe / whitelist changes = IPS discussion, not silent bypass.

### Entry gate (July 17 2026) — candidates only
- Anti-extension / overbought: `autonomous_trader.passes_entry_gate`
- Never force-sells holdings; LLM books never hit `plan_portfolio`
- Style-aware: value/income tight (12–15% / RSI 70–72); momentum/theme looser (25% / RSI 80)
- Emits via `decision_engine` fields `rsi14`, `pct_above_200ma`
- Trailing **stops kept** (audit: stopped names continued down ~4.65%)

### Decision engine invariants
- `_as_float()` on every yfinance/finviz numeric comparison
- Per-ticker try/except — one bad ticker cannot kill the run
- **Style weight keys must match emitted categories exactly**  
  `RSI`, `MACD`, `SMA50`, `SMA200`, `Cross`, `RelStrength`, `EarningsGrowth`, `RevenueGrowth`, `PE`, `DebtEquity`, `ShortInterest`, `Insider`, `BondMkt`, `ValueOverride`, `DividendYield`, `PEG`, `ROE`, `FCF`, `GrossMargin`, `PayoutSafety`, `EarningsProximity`  
  Mismatch → silent weight `1.0` (historical P0 bug class)
- **BOND_WEIGHTS keys** = exact portfolio names
- Alpaca bars tz-aware vs yfinance naive: normalize **before** `concat` (`alpaca_data.get_daily_bars`, fix 2026-07-21)

### Cash wall (7 layers — do not remove)
1. WAL checkpoint in `get_verified_cash()`
2. Atomic cash cap before share calc in `_execute_buy_order()`
3. Global buying-power guard vs Alpaca
4. Robust partial-fill polling `_wait_for_fill()`
5. Inter-buy delay (~2s) for WAL visibility
6. Lock file in `main()` (stale-lock recovery)
7. Post-trade reconcile; critical mismatch → `ALPACA_MISMATCH` halt

### Other rule-based rails
- Sell before buy  
- Market hours only (roughly 10:00–16:00 ET for autonomous path)  
- Trailing stops only ratchet up  
- Planned actions dashboard **must** call `plan_portfolio()` — never reimplement trader logic  

---

## 6. LLM Portfolios (8–9) — Doctrine

### Python's job
- Information at the right time: news, prices, macro regime, journal, lessons, peer scoreboard  
- Execute cleanly: Alpaca + `record_trade`  
- Safety rails only: cash isolation, market hours, ticker validation, ETF blacklist (Commando), schema validation, catastrophic freeze at ~50% drawdown, mismatch/short guards  

### Python's job is NOT
- Strategy sells, hold timers, profit targets, or thesis vetoes as hard code  
- Discovering candidates by **price momentum alone** (reverted June 25 — news/catalyst only)

### Judge principles (not rules)
- Judge = decision-maker / gap-finder, not checklist executor  
- Lenses: alpha (risk-adjusted), already-priced-in, room-to-run, conviction exit, overnight/wartime banking  
- **Only mechanical safety is hard**; judgment stays free inside rails  
- Keep worldview coherent — prune conflicting “just one more rule” creep  

### Alpha objective
- Target: high reward / low–med risk  
- Money-market / cash = zero-alpha baseline (paper cash earns 0; real-world inflation context used in prompts)  
- Grade process at decision time, not by lucky P&L  
- Exit by **would-I-buy-now / opportunity cost**, not a clock  
- Commando overnight: burden of proof on **holding** green into the close in risk-off / war tape; bank + re-enter next day is not churn  

### Soft vs hard experiment (July 17)
- Same extension finding: **hard veto** on 7, **LESSONS info** on 2 via `llm_lessons.py`  
- Do not “fix” the experiment by bolting hard extension gates onto Commando without explicit direction  

### Known pending (as of 2026-07-21 worklog)
- ETF Focus evidence-dialectic mirror (sell classification + Bull/Bear analogs)  
- Feed this-session mechanical exits into Judge context (stop-loss reconciliation lens)  
- Insider-buying UW backtest refinement (`~/uw_experiments/`)  
- Strategic pivot interest: collaborative analyst product (`analyst_in_a_box.py`) — understanding over pure short-term timing  

---

## 7. Cost & Ops Philosophy

- Steady-state ops **cheap** → headroom for R&D  
- Default **deterministic** over “AI second opinion on every X”  
- Surveillance + Slack alert > complex auto-fix  
- Before new LLM consumers: estimate $/day; justify if not trivial  
- Briefings already migrated off broken OpenClaw exec-approval crons where needed — prefer **native system crontab** for shell reliability  

### Model notes (runtime vs coding)
- Live bot: Sonnet/OpenRouter/Gemini for cost; Commando **Judge = Opus 4.8** (Fable failed reliability)  
- Coding agent is now **Grok 4.5** — apply full rigor on live money path; do not cargo-cult Claude `/model opus` commands  
- Prefer dry-run + compile + targeted tests before deploy on trading path  

---

## 8. Anti-Hallucination Pipeline

1. Python gathers → flat file with `=== SECTION ===` markers  
2. LLM reads file only; numbers must appear verbatim; else “data unavailable”  
3. Price Oracle + Output Guardrail for outbound prices  

Reports should include **Data Health** (stale JSON, failed sources, cron errors).

---

## 9. Deploy Discipline

```bash
# On Pi, from repo
cd ~/bigclaw-ai
# edit scripts/ (symlink serves OpenClaw)
source ~/.env_secrets
# dry-run / unit checks under the CORRECT interpreter
# git commit + push origin main when appropriate
```

- `scripts/` and OpenClaw workspace are the **same files** via symlink  
- Website data push via `scripts/push_docs.sh` (flock-serialized)  
- Attribute commits honestly (e.g. Grok 4.5 / human) — drop Claude co-author trailers  
- After deploy: watch next cron cycle, logs, Slack; confirm no halt flags  

### Common manual commands

```bash
ssh bigclaw
source ~/.env_secrets
cd ~/bigclaw-ai

# Trader (careful)
venv or system python as appropriate — see dual interpreters
python3 scripts/autonomous_trader.py   # often system python3

# Decision engine
python3 scripts/decision_engine.py --json

# Logs
tail -100 logs/bigclaw.log
ls logs/*_last_error.log
```

---

## 10. Schedules (verify live; docs lag)

System crontab is the reliable backbone. High-level:

- Morning / afternoon data gathers  
- `refresh_all.sh` / price refresh + dashboard  
- **`autonomous_trader.py` ~10:00** (single trader trigger; OpenClaw duplicates disabled)  
- `stop_check.py` every ~15 min  
- LLM cycles + 5-min watchers (Commando) / slower ETF watcher  
- Saturday candidate screener  

`SHELL=/bin/bash` required in crontab (`source` fails under dash).

OpenClaw cron: `~/.openclaw/cron/jobs.json` — **do not put exec-heavy jobs on models that require manual approval**.

---

## 11. Strategic Context (July 2026)

Evidence so far: short-term single-stock edge from free public data is weak; all books lag SPY on honest measurement. System remains valuable as:

1. Education / paper laboratory  
2. Rule-based IPS engine with hard gates + entry gate  
3. LLM dialectic experiment (soft vs hard governance)  
4. Possible **collaborative analyst** product direction (human-in-the-loop Judge, not pure auto-timing)

Do not “optimize” by turning Commando into a second rule bot unless Curtis redirects.

---

## 12. Incident Classes (remember these patterns)

| Incident | Lesson |
|----------|--------|
| Phantom shares / accounting | DB vs Alpaca reconcile; never invent cash |
| June 15 shorts | Fresh holdings + clamp at execute; concurrent watcher/cycle |
| SHOP flag path | Grep real paths; end-to-end verify next consumer |
| Alpaca paper wipe / mass desync | Halt trading; DB preserved research |
| KTOS oversell | Short-position guard + exit cooldown |
| signals.json tear | Atomic writers only |
| tz-aware concat crash | Normalize before merge; log full stderr |
| OpenClaw exec approval | Native cron + allowed models |
| gate_reasoning cost | No AI IPS override |

---

## 13. Claude-Specific Patterns — Adapt or Drop

| Claude pattern | Grok 4.5 action |
|----------------|-----------------|
| `CLAUDE.md` as agent entry | Use **this `GROK.md`**; keep `CLAUDE.md` as legacy reference until retired |
| Auto-memory under `~/.claude/.../memory/` | Read for history; **verify on Pi**; maintain `project_active_worklog.md` or update this file at checkpoints |
| `/model opus` escalation | N/A — one model; **self-escalate care** on live trading path (slower, more verification) |
| `Co-Authored-By: Claude...` commits | Drop; use Grok/human attribution if any |
| “Ultrathink” as a mode word | Keep the **behavior** (full root-cause, no stop-at-first-error) without the brand |
| Claude Code Bash allow-lists / ask-rules | Explicit user confirm for DB wipes, resets, force-push, mass liquidations |
| OpenClaw `SOUL.md` / `AGENTS.md` | Those shape the **Slack bot personality**, not Grok coding sessions — do not overwrite casually |
| External “Grok reviews Claude PR” | Role flip: Grok implements; optional second-pass review still valuable |
| Windows-local edit as deploy | **Never** — always Pi (or verified scp + Pi test) |
| Stale ARCHITECTURE/README (Treasury, 7-only, AI gate) | Prefer **DESIGN_BASIS.md + this file + live code** |

---

## 14. Doc Map

| Doc | Role |
|-----|------|
| `GROK.md` (this file) | Coding agent operating manual |
| `CLAUDE.md` | Legacy Claude Code context (may drift) |
| `DESIGN_BASIS.md` | Authoritative engineering / DBD source |
| `PORTFOLIO_STYLES.md` | IPS philosophies & compliance |
| `ARCHITECTURE.md` | Component map (may lag on portfolio count) |
| `~/.openclaw/workspace/SOUL.md` | Interactive agent identity |
| Claude `memory/*.md` | Session lessons (historical) |
| `docs/sources.html` | Public data-source bibliography |

---

## 15. Readiness Checklist for a Coding Session

1. `ssh bigclaw` works  
2. `git -C ~/bigclaw-ai status -sb` and `git log --oneline -15`  
3. No unexpected `ALPACA_MISMATCH` / drawdown freeze flags (grep real paths)  
4. Skim `logs/bigclaw.log` tail for today’s failures  
5. Confirm interpreter before running a script  
6. For trading-path edits: dry-run, unit/integration smoke, watch next cron  

---

## 16. Current Focus Snapshot (2026-07-21)

- **Fixed:** `decision_engine` crash from tz-aware/tz-naive merge in `get_daily_bars` (commit `4e035a9`). Logging improved to capture real traceback.  
- **Live:** entry gate firing (e.g. Innovation veto ARM extended).  
- **Watch:** 10:00 trader success after fix; entry gate first full live day.  
- **Optional next:** DBD §6.9 note on Alpaca price-fetch resilience; UW insider backtest refinement; ETF evidence-dialectic mirror.  

*When in doubt: read live code on the Pi, then DESIGN_BASIS, then act small and verify end-to-end.*
