# LLM-Comando — Alpha Improvement Plan

**Date:** 2026-07-21 (rev: operator north star + event-driven + data sources)  
**Status:** Direction locked; implement when you say go  
**Depends on:** 4-sleeve cutover can share a weekend; don’t mix mass liquidations with huge prompt rewrites

---

## 0. Operator north star (Curtis — authoritative)

> Comando must **figure out how to win**. Each market session is different.  
> **Yesterday’s failure may win today.**  
> Rule-based books may be limited by Python rules; Comando must **not** become a second rule bot.  
> **Method:** study a stock → **Bull** → **Bear** → decide from **today’s market narrative and conditions**.  
> **Style:** day-trader speed, **investor sense** (real thesis, not noise).  
> **Exit:** sell when the **buy thesis starts to break** — not because a clock or checklist says so.

| Principle | Design implication |
|-----------|-------------------|
| Session-local win | No permanent “never chips / only PT-raises / always bank overnight.” Today’s tape decides. |
| Yesterday ≠ law | Journal = **analogies to weigh**, not forbidden/allowed lists. |
| Study → dialectic → decide | Per-name depth; Bull/Bear/Judge stay core. |
| Narrative of the day | Stock thesis must fit (or consciously fade) **this** session’s story. |
| Day trader + investor sense | Fast OK; every buy needs thesis + falsifiers. |
| Thesis-break exits | Primary sell = thesis weakened/broken/spent. Stops = safety rails only. |
| Python stays thin | Cash, long-only, no ETFs (identity), hours, fills, freeze. No strategy veto pile-on. |

**Fights this today (prompt debt):** LESSONS-as-ban, template worship, overnight defaults, refusal scorecard shaming misses, session-only full dialectic.

**When we implement:** prune strategy-as-rules; keep dialectic + thesis re-verify; event-driven re-study; journal as evidence not commandments.

### Buy / hold / sell contract

- **Buy:** thesis + why it fits **today’s narrative** + falsifiers.  
- **Hold:** re-classify STRENGTHENED / INTACT / WEAKENED / SPENT every look.  
- **Sell:** thesis_wrong / thesis_changed / thesis_played_out — thesis break first.

### Engineering problem statement

1. Late entries + thin real recursion.  
2. Event-driven GO (not only 9 / 11:30 / 14:30).  
3. Doctrine bloat so it can **figure out how to win** each day.

---

## 1. Diagnosis (why notes failed)

| Factor | Effect |
|--------|--------|
| **Discovery = post-print news** | First sighting is often *after* the move. Doctrine cannot create earlier information. |
| **Session-bound dialectic** | Full Bull→Bear→Judge only at 3 fixed crons; watcher is secondary and mostly **pre-armed triggers**, not “new thesis anytime.” |
| **News poll is batch** | `discover_news_makers(..., hours_back=24)` at cycle start — up to hours late vs the print. |
| **Conflicting objectives** | “Deploy cash / beat SPY” vs “don’t chase” → late mediocre trades or cash drag. |
| **Soft memory only** | Journal + LESSONS + scorecards as **prose** — no policy update. |
| **Refusal scorecard bias** | Punishes skipping moonshots → lower bar → more chases. |

**Implication:** Fix **(a)** earlier/faster data, **(b)** event-driven GO path, **(c)** measurable recursion — not more anti-chase essays.

---

## 2. Goals and non-goals

### Goals
1. **Adaptive winner:** each session re-derives what works from **today’s narrative**, not a frozen playbook of bans.  
2. **Study quality:** Bull/Bear on real candidates under current conditions; investor-grade thesis.  
3. **Thesis-break sells** as primary exit discipline.  
4. **Event-driven execution:** GO mid-session without waiting for the clock.  
5. Measure entry quality (chase features) as **feedback**, not as permanent vetoes.  
6. Recursive learning as **short distilled evidence**, not growing commandment lists.  
7. Python thin; Judge free inside rails.

### Non-goals
- Turning Comando into IPS/style-gate clone of the 7.  
- Pure price-momentum discovery with no thesis.  
- UW / options flow.  
- Weekly doctrine rewrites that re-cage the Judge.  
- Force full investment every day.  
- Rule `decision_engine.py` scores for Comando buys.

### Success metrics

| Metric | Target (4–6 weeks) |
|--------|---------------------|
| Median day-of move / extension at entry | Down vs C0 baseline |
| **% of buys from event-driven path** (not scheduled session) | Rising; target **≥50%** of entries |
| Median **minutes from headline/event → fill** | Down |
| Win rate chase vs non-chase | Document; kill bad templates |
| vs SPY + cash% | Scoreboard always |
| Cost / empty cycles | No blow-up (budget caps on event fires) |

---

## 3. Architecture after plan (event-driven)

```
  ┌──────────────────────────────────────────────────────────┐
  │  CONTINUOUS RADAR (market hours, e.g. every 1–2 min)      │
  │  - News delta since last poll (Alpaca/Benzinga feed)      │
  │  - Event calendar (earnings/FDA/econ) due soon            │
  │  - Price triggers armed by last GO / session              │
  │  Filter → "actionable?" (new ticker+headline, not noise)  │
  └────────────────────────┬─────────────────────────────────┘
                           │ GO candidate
                           ▼
  ┌──────────────────────────────────────────────────────────┐
  │  DECISION PATH (does NOT wait for 9/11:30/14:30)           │
  │  Fast path: focused Judge (or full dialectic if budget)   │
  │  Inputs: playbook, chase features, holdings, this event   │
  │  Output: buy/sell/stand_down + new triggers               │
  │  Shared lock with cycle/watcher/reconciler + cash clamp   │
  └────────────────────────┬─────────────────────────────────┘
                           │ GO
                           ▼
                    Alpaca market order → record_trade
                           │
                    entry_features + outcomes → monthly playbook

  Scheduled 9 / 11:30 / 14:30 become BACKUP full rebalancing
  sessions (book review, cash, overnight doctrine) — not the
  only time a buy is allowed.
```

**Naming:** Comando’s “decision engine” = dialectic + rails + event router.  
It does **not** call the 7-book `decision_engine.py`.

---

## 4. Phased work

### Phase C0 — Baseline (1 session, read-only + small logging if needed)

**Do first; no strategy change.**

| Task | Detail |
|------|--------|
| C0.1 | Script: from journal + fills, compute last 30–60 days: extension at entry, day-return at entry, hours-since-news if available, realized outcome when known. |
| C0.2 | Publish baseline table to Slack or `data/comando_baseline.md`. |
| C0.3 | Freeze Comando **prompt/doctrine edits** for the duration of C1–C3 (bugfixes only). |

**Exit:** You see how often entries were already extended / day-spiked.

---

### Phase C1 — Make chase measurable (core recursion input)

**Code, low risk, no change to what Judge is allowed to buy yet.**

| Task | Detail |
|------|--------|
| C1.1 | On every **buy** (cycle + watcher), Python records `entry_features.jsonl` (or extend outcomes/journal): ticker, ts, fill price, pct_from_prior_close, pct_5d, pct_above_200ma, rsi14, news_mention_count_24h, first_seen_ts if known, cycle name. |
| C1.2 | On every **close**, join features → outcomes; set `entry_chase_score` (simple rubric, e.g. points for day-move &gt; 3%, &gt;15% above 200d, RSI&gt;75). |
| C1.3 | **CHASE SCORECARD** block each cycle: last N buys — median day-move, median extension, win rate chase vs non-chase. Numbers only + one line implication. |
| C1.4 | **Fix refusal scorecard:** split passes into (a) extended/runners you correctly skipped vs (b) non-extended fresh catalysts that then worked. Only (b) counts as “bar too high.” |

**Exit:** Every cycle the Judge sees quantitative “you have been chasing / not” instead of only prose.

**Files (likely):** `llm_comando.py`, `llm_comando_watcher.py`, `llm_comando_reconciler.py`, maybe small `comando_features.py`.

---

### Phase C2 — Recursive playbook (real learning loop)

| Task | Detail |
|------|--------|
| C2.1 | Weekly or monthly job `comando_distill.py` (can start **manual** monthly): read outcomes + entry features + sell classifications → write **`data/comando_playbook.md`** (max ~20 lines). **Replace** file; do not append forever. |
| C2.2 | Inject playbook into context **instead of** long raw journal tail (keep last 3–5 cycles only for continuity). |
| C2.3 | Templates with explicit hit rates, e.g. “fresh multi-bank PT + day flat” vs “same-day rumor spike” — kill or demote negative templates in the distill, not in live prompt edits. |
| C2.4 | Require Judge JSON field `entry_quality_self_check`: {day_move_known, extended_flag, why_not_chase} — schema validated; empty → reject trade (syntax rail, not strategy). |

**Exit:** Learning is a **short, replaced playbook** grounded in labeled results, not a growing essay pile.

---

### Phase C3 — Event-driven GO + earlier information clock

**Highest leverage. Includes: don’t wait for scheduled sessions.**

#### C3-A — Buy when GO fires (not on the clock)

| Task | Detail |
|------|--------|
| C3.A1 | **News radar process** (`llm_comando_radar.py` or extend watcher): every **1–2 min** during RTH, poll news **since last cursor** (not 24h dump). Dedupe by (ticker, headline hash). |
| C3.A2 | **Actionability filter (Python, cheap):** new liquid single-stock; not ETF; optional min relevance; drop pure noise; attach **chase features snapshot** (day-move, extension) before any LLM call. |
| C3.A3 | **Event-driven decision:** on pass, acquire **shared Comando lock**; run **fast decision path** immediately:  
  - **Default:** focused single-call Judge (like today’s trigger fire) with Bull/Bear skipped for speed, **or**  
  - **High-stakes / size &gt; N%:** mini dialectic (Bear mandatory priced-in + Judge)  
  Explicit: **no wait** for next 9 / 11:30 / 14:30 cron. |
| C3.A4 | If Judge says buy → **execute immediately** (same fill/clamp/stop-init path as cycle). If stand_down → log to passed + reason. |
| C3.A5 | **Budget caps:** max event-driven LLM fires/day (e.g. 8–12) + max $ cost; queue or drop lower-priority events. Prevents token spiral. |
| C3.A6 | **Scheduled sessions demoted:** morning/midday/afternoon = full book review, overnight doctrine, peer scoreboard, **re-arm** watches — not the sole entry gate. Metric: `% entries from radar/watcher vs scheduled`. |
| C3.A7 | Unify watcher + radar under one lock and one “fire” ledger so cycle/radar/watcher never double-buy. |

#### C3-B — Earlier *content* (pre-move), not just faster late news

| Task | Detail |
|------|--------|
| C3.B1 | **Event calendar** in radar + sessions: earnings, major econ, known binary dates (free first). |
| C3.B2 | Judge may emit **`watchlist_theses[]`** (pre-GO): thesis, invalidation, trigger — armed for radar/watcher. |
| C3.B3 | Pre-event: allow small **probe** or wait-for-trigger; full size on confirm. |
| C3.B4 | Optional T+1 full-size for pure same-day news with huge day-move (policy). |

**Exit criteria:**  
- A headline can produce a fill **minutes later**, not at the next clock slot.  
- Some entries come from **pre-armed watches / calendar**, not only post-spike news.

**Risks:** cost, double-fire, late news still late — mitigate with caps, lock, chase features in the GO path.

---

### Phase C3-S — Information sources (sooner / better)

See **§8 Data sources** for full ranking. Implementation order:

| Priority | Source | Role | Cost |
|----------|--------|------|------|
| P0 | **Alpaca news streaming/poll with cursor** (already paid via Alpaca) | Faster same-day headlines; radar backbone | $0 extra |
| P0 | **Earnings / econ calendar** (yfinance calendar, existing `economic_calendar.py`, free APIs) | *Before* the print | Free |
| P1 | **SEC EDGAR Form 8-K / press wire** (edgartools already in stack) | Material events often before retail Twitter | Free |
| P1 | **CNBC/Reuters RSS** (watcher already partial) | Second wire; keep for radar | Free |
| P2 | **Benzinga Pro / News API** (if Alpaca lag is proven in C0) | Lower latency headlines | Paid |
| P2 | **Polygon or similar real-time news** | Low-latency JSON news | Paid |
| Avoid | UW flow, dark pool as entry signal | Already tested weak | — |
| Avoid | Paying for “AI stock picks” feeds | No edge, high noise | — |

**Rule:** Pay only if C0/C1 shows **latency of current news** is a top driver of late fills. Don’t pay for another post-print narrative stream.

---

### Phase C4 — Optional soft rail (only if C1 metrics stay bad)

**Do not implement until 2–3 weeks of C1 data.**

| Option | Rule | When |
|--------|------|------|
| C4a | Soft veto: block buy if `pct_above_200ma` &gt; style threshold **and** day-move &gt; X% unless ticker was on `watchlist_theses` prior session | Chase rate still high |
| C4b | Soft veto: block buy if day-move &gt; Y% from prior close with no pre-watch | Same |
| C4c | Stay soft forever; only playbook | Chase rate already falling |

This mirrors the 7-book entry-gate experiment: **one narrow physics rail**, Judge free inside it.

---

### Phase C5 — Ops / reliability (support alpha)

| Task | Detail |
|------|--------|
| C5.1 | Enforce Judge timeout so retries fit pre-close budget (known hang issue). |
| C5.2 | Shared trade mutex with rule trader (from system reliability plan) when that lands. |
| C5.3 | Stop-exit → Judge context (“this session mechanical exits”) — pending item from worklog. |
| C5.4 | Peer scoreboard already windowed to Comando start — keep; show cash% always. |

---

## 5. Policy choices for you (before C3/C4)

| # | Question | Options |
|---|----------|---------|
| P1 | On a thin board, prefer **cash** or **force one “least bad” trade**? | Recommend: **cash OK** if scorecards show forced trades underperform |
| P2 | **T+1 full size** for pure news names? | Recommend: try as default for news-only; same-day OK only if day-move &lt; threshold *or* pre-watched |
| P3 | Soft rail C4 after evidence? | Recommend: **yes if chase metrics flat after C1–C2** |
| P4 | Probe size for first touch? | e.g. max 5% book until thesis reconfirmed |

---

## 6. What we will stop doing

1. Adding more LESSONS bullets for the same idea.  
2. Editing Bull/Bear/Judge walls of text weekly.  
3. Using refusal scorecard that shames skipping moonshots.  
4. Expecting Opus to overcome same-day public news latency alone.

---

## 7. Suggested sequence (tonight start)

| Order | Phase | When |
|-------|-------|------|
| 1 | **C0** baseline | **Tonight** (read-only / offline scripts OK) |
| 2 | **C1** entry features + chase + refusal fix | **Tonight / weekend** (log even if radar not live) |
| 3 | **C5** shared lock + timeout hygiene | Before or with C3.A (safety for multi-fire) |
| 4 | **C3.A** radar + immediate GO decision | **Weekend / next week open** — main “don’t wait for sessions” deliverable |
| 5 | **C3.B** calendar + watchlist_theses | Same week as C3.A |
| 6 | **C3-S** paid news only if latency proven | After 1–2 weeks metrics |
| 7 | **C2** playbook distill | After ≥1–2 weeks labeled entries |
| 8 | **C4** soft rail | Data-gated |

**Tonight-safe:** C0 + C1 logging (no need for market open).  
**Needs RTH to validate:** C3.A end-to-end GO → fill.

---

## 8. Data sources — what gets Comando *actionable* data *sooner*

### The hard truth
Anything that only reports **“stock moved / headline hit Twitter”** is still **late**.  
**Sooner** means either:
1. **Lower latency** on the same public headline (minutes matter for fills), or  
2. **Earlier class of fact** (scheduled event, filing, pre-registered watch).

### Already in-house (use harder before paying)

| Source | How Comando uses it today | Gap |
|--------|---------------------------|-----|
| **Alpaca News** (Benzinga-class) | Cycle start, 24h top mentions | Batch; not continuous; hours_back=24 dilutes “just now” |
| **Watcher */5** | Price/news/time triggers **pre-set by Judge** | Cannot invent a new thesis mid-day unless trigger exists |
| **yfinance / calendars** | Partial | Not in continuous radar |
| **SEC / edgartools** | Skills / research, not Comando loop | Underused for 8-K “just filed” |
| **Economic calendar scripts** | Briefings | Not wired to Comando GO |

### Free — worth wiring (priority order)

| Source | Why it’s earlier / better | Action |
|--------|---------------------------|--------|
| **Alpaca news with since-cursor poll (1–2 min)** | Same wire, **much faster path to GO** | C3.A1 — do this first |
| **Earnings dates** (yf calendar / free calendar APIs) | Thesis **before** print | C3.B1 |
| **SEC EDGAR 8-K / Form 4** | Material event / insider often before secondary media loops | Poll recent filings for liquid names + holdings |
| **RSS (Reuters/CNBC/PR Newswire)** | Redundant wire; catch misses | Already partial; fold into radar |
| **FOMC / CPI / jobs calendar** | Regime; avoid opening into binary (you already teach this) | Event radar |
| **Company IR / scheduled events** (harder) | True early | Later; high labor |

### Paid — only if free path still too slow

| Source | What you buy | When to consider |
|--------|--------------|------------------|
| **Benzinga Pro / real-time news API** | Faster, cleaner structured news | If Alpaca news cursor still lags prints by minutes on your fills |
| **Polygon news / Massive-style feeds** | Low-latency JSON news + trades | Same latency proof |
| **Bloomberg/Refinitiv** | Institutional tape | Overkill for paper + cost/labor |
| **Quiver / congressional / alt-data** | Niche | Weak for Comando short-horizon |
| **UW / options flow** | Flow | **No** — tested, cancel plan stands |

### What not to buy
- Another “sentiment AI” layer on the same headlines.  
- Options flow for entry timing.  
- Expensive terminals for a paper commando book.

### Latency test (decide paid vs free)
For 20 sample headlines over a week: timestamp **source first seen** vs **price already moved X%**.  
If Alpaca cursor is within ~1–2 minutes of major wires, **don’t pay**. If systematically 10–30+ minutes late, paid wire may be worth it.

---

## 9. Event-driven GO — behavioral contract

1. **Market open + no HALT flags** → radar may fire.  
2. **New actionable event** → lock → decision path → optional buy **now**.  
3. **Scheduled sessions** still run for full portfolio dialectic, overnight banking doctrine, and re-arming watches.  
4. **GO is not “price up”** — GO is (new citable info **or** armed trigger **or** calendar event) **and** Judge (or fast Judge) approval **and** rails.  
5. **Caps** on fires/day protect cost and overtrading.  
6. **Chase features** always computed before buy so “immediate” ≠ “blind chase.”

---

## 10. Interaction with 4-sleeve cutover

- Comando **stays live**.  
- Same weekend: prefer **C0/C1** + design of radar; run **flatten kills** separately with DB backup.  
- Turn on **C3.A live GO** only when lock + budget + dry-run path verified (Mon open OK).

---

## 11. Approval / tonight checklist

- [x] Direction: event-driven, not session-only  
- [x] Start tonight: **C0 + C1**  
- [ ] **C3.A** radar + immediate GO — approve for weekend build  
- [ ] **C3-S** stay free-first unless latency test fails  
- [ ] Policies P1–P4: use recommendations unless you override  

**Default if you say “start tonight”:** implement C0 + C1 on Pi; scaffold C3.A dry-run flag (`--radar-dry-run`) without live buys until you flip GO live.
