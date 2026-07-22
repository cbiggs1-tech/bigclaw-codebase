#!/usr/bin/env python3
"""LLM-driven discretionary portfolio - 3-Sonnet dialectic decision engine.

Goal: Beat SPY and beat the 7 rule-based BigClaw portfolios on $100K paper.
Method: Three Claude Sonnet 4.6 agents in a dialectic structure:
  1. BULL agent - argues strongest case FOR each candidate trade
  2. BEAR agent - argues strongest case AGAINST (reads bull case + same data)
  3. JUDGE agent - reads data + bull + bear + journal, makes final decisions

The JUDGE produces structured JSON of trades + reasoning + exit_thesis.
Python validates (ticker exists, cash available, drawdown not catastrophic),
executes via Alpaca, records to DB, appends to journal.

No rule-based filters. No top-10 score. No target-price discipline.
Only safety rails: cash wall, ticker validation, catastrophic-drawdown freeze.

Designed to be the 8th portfolio - separate experiment from the rule-based
engine validation window. Goal is to test whether LLM judgment with
self-feedback beats hand-coded rules over time.

Usage:
    llm_portfolio.py                  # production: 3-agent run, execute trades, post Slack
    llm_portfolio.py --dry-run        # full pipeline but no Alpaca submits, no Slack post
    llm_portfolio.py --observe-only   # judge produces strategy doc only, no trades
    llm_portfolio.py --channel CXXX   # override Slack channel
"""
import argparse
import datetime
import json
import os
import re
import sqlite3
import sys
import time
import urllib.parse
from pathlib import Path

import warnings
warnings.filterwarnings("ignore")

import anthropic
import feedparser
import yfinance as yf
from slack_sdk import WebClient

# ---------- constants ----------
PORTFOLIO_NAME = "LLM-ETF Focus"
DEFAULT_CHANNEL = "D0ADHLUJ400"
MODEL_BULL = "claude-sonnet-4-6"
MODEL_BEAR = "claude-sonnet-4-6"
MODEL_JUDGE = "claude-sonnet-4-6"
MAX_TOKENS_DEBATE = 6000     # bull / bear each (longer with new mandates)
MAX_TOKENS_JUDGE = 8000     # was 4000; gap_analysis + cycle-positioning fields overflowed it -> JSON truncation/parse fail (2026-06-17)
LLM_TIMEOUT = 120.0

# Safety rails (Curtis's minimum)
CATASTROPHIC_DRAWDOWN_FLOOR = 50_000.0   # USD - freeze if portfolio drops below

LOCK_FILE = Path("/tmp/llm_portfolio.lock")
FAILURE_FLAG = Path.home() / "bigclaw-ai" / "logs" / "LLM_PORTFOLIO_FAILED.flag"
DRAWDOWN_FLAG = Path.home() / "bigclaw-ai" / "logs" / "LLM_PORTFOLIO_DRAWDOWN_FREEZE.flag"
LLM_LOG = Path.home() / "bigclaw-ai" / "logs" / "llm_calls.jsonl"
JOURNAL = Path.home() / "bigclaw-ai" / "data" / "llm_journal.jsonl"

# Durable, curated lessons from analyzing our own trades (extension risk, opportunity-cost
# exit, etc.) — shared with LLM-Commando. Injected into the data feed as INFORMATION, not
# rules; the Bull/Bear/Judge weigh it and decide. Guarded so a missing module never breaks a cycle.
try:
    from llm_lessons import render_lessons
except Exception:
    def render_lessons():
        return ""
OUTPUT_JSON = Path.home() / "bigclaw-ai" / "docs" / "data" / "llm_portfolio.json"
DECISIONS_DIR = Path.home() / "bigclaw-ai" / "data" / "llm_decisions"
DB_PATH = Path.home() / "bigclaw-ai" / "src" / "portfolios.db"

SECTOR_ETFS = ['XLK', 'XLF', 'XLE', 'XLV', 'XLI', 'XLP', 'XLY', 'XLB', 'XLU', 'XLRE', 'XLC']
FACTOR_ETFS = ['IWM', 'MTUM', 'QUAL', 'USMV', 'IWN']
MACRO_ETFS  = ['SPY', 'TLT', 'UUP', 'GLD', 'USO']
INVERSE_ETFS = ['SH', 'PSQ', 'DOG', 'RWM']  # -1x inverse: S&P / Nasdaq-100 / Dow / Russell 2000 - express a bearish edge as a LONG buy that rises when the market falls
REGIME_TICKERS = ['^VIX', 'HYG', 'LQD', '^TNX', 'IWM']  # vol / HY credit / IG credit / 10y yield / small-cap breadth - macro regime tells

# ---------- utilities ----------
def log(msg, level="INFO"):
    print(f"[{datetime.datetime.now(datetime.timezone.utc).isoformat()}] {level} {msg}")

def write_failure_flag(reason):
    try:
        FAILURE_FLAG.parent.mkdir(parents=True, exist_ok=True)
        FAILURE_FLAG.write_text(json.dumps({
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "reason": reason,
        }, indent=2))
        log(f"Wrote failure flag: {FAILURE_FLAG}", "WARN")
    except Exception as e:
        log(f"Could not write failure flag: {e}", "ERROR")

def acquire_lock():
    if LOCK_FILE.exists():
        try:
            pid = int(LOCK_FILE.read_text().strip())
            try:
                os.kill(pid, 0)
                log(f"Already running as PID {pid} - aborting", "WARN")
                sys.exit(1)
            except ProcessLookupError:
                log(f"Stale lock from PID {pid} - reclaiming", "WARN")
        except (ValueError, OSError):
            pass
    LOCK_FILE.write_text(str(os.getpid()))

def release_lock():
    try: LOCK_FILE.unlink()
    except FileNotFoundError: pass

def load_secrets():
    s = {}
    for line in (Path.home() / ".env_secrets").read_text().splitlines():
        line = line.strip()
        if line.startswith("export "): line = line[7:]
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            s[k.strip()] = v.strip().strip('"').strip("'")
    return s

def log_llm_call(agent, model, in_tok, out_tok, cost, duration):
    try:
        LLM_LOG.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "script": "llm_portfolio.py",
            "agent": agent,
            "model": model, "input_tokens": in_tok, "output_tokens": out_tok,
            "cost_usd": round(cost, 4), "duration_sec": round(duration, 1),
        }
        with LLM_LOG.open("a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception as e:
        log(f"llm_log write failed: {e}", "WARN")


# ---------- state gathering ----------
def get_portfolio_state():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    pf = conn.execute("SELECT id, starting_cash, current_cash FROM portfolios WHERE name=?",
                      (PORTFOLIO_NAME,)).fetchone()
    if pf is None:
        conn.close()
        raise RuntimeError(f"Portfolio {PORTFOLIO_NAME!r} not in DB. Run setup first.")
    holdings = conn.execute(
        "SELECT ticker, shares, avg_cost, first_bought_at FROM holdings "
        "WHERE portfolio_id=? AND shares>0 ORDER BY ticker", (pf['id'],)
    ).fetchall()
    conn.close()
    return {
        "id": pf['id'],
        "starting_cash": pf['starting_cash'],
        "current_cash": pf['current_cash'],
        "holdings": [dict(h) for h in holdings],
    }

def get_peer_returns():
    """Returns dict of {portfolio_name: totalReturn_pct} for all OTHER active portfolios.
       Read from dashboard portfolios.json so we get the same numbers the user sees."""
    try:
        path = Path.home() / "bigclaw-ai" / "docs" / "data" / "portfolios.json"
        d = json.loads(path.read_text())
        return {p['name']: p.get('totalReturn') for p in d.get('portfolios', [])
                if p['name'] != PORTFOLIO_NAME}
    except Exception as e:
        log(f"Could not read peer returns: {e}", "WARN")
        return {}

def get_market_snapshot():
    """Sector ETFs + factor ETFs + macro ETFs - current price + 1d/5d/30d returns."""
    universe = SECTOR_ETFS + FACTOR_ETFS + MACRO_ETFS + INVERSE_ETFS + REGIME_TICKERS
    hist = yf.download(universe, period='1y', progress=False, threads=True)['Close']
    def r(t, n):
        try:
            if len(hist[t]) < n+1: return None
            return float(hist[t].iloc[-1] / hist[t].iloc[-n-1] - 1) * 100
        except Exception: return None
    out = {}
    for t in universe:
        try:
            out[t] = {
                "price": float(hist[t].iloc[-1]),
                "ret_1d": r(t, 1), "ret_5d": r(t, 5), "ret_30d": r(t, 30),
                "ret_63d": r(t, 63), "ret_126d": r(t, 126),
            }
        except Exception:
            pass
    return out

def get_news(tickers, secrets):
    """Pull Alpaca/Benzinga per-ticker (for held + recently-traded) + broad CNBC/Reuters."""
    from alpaca.data.historical.news import NewsClient
    from alpaca.data.requests import NewsRequest
    client = NewsClient(api_key=secrets['ALPACA_API_KEY'],
                        secret_key=secrets['ALPACA_SECRET_KEY'])
    start = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=2)
    per_ticker = {}
    if tickers:
        for i in range(0, len(tickers), 20):
            batch = tickers[i:i+20]
            try:
                r = client.get_news(NewsRequest(symbols=",".join(batch), start=start, limit=50))
                items = []
                if hasattr(r, 'data') and isinstance(r.data, dict):
                    for v in r.data.values():
                        items.extend(v if isinstance(v, list) else [v])
                for item in items:
                    for sym in (getattr(item, 'symbols', None) or []):
                        if sym in batch:
                            per_ticker.setdefault(sym, []).append({
                                'time': item.created_at.isoformat()[:16],
                                'headline': item.headline,
                            })
            except Exception as e:
                log(f"Alpaca batch error: {e}", "WARN")
    for s in per_ticker:
        per_ticker[s] = sorted(per_ticker[s], key=lambda x: x['time'], reverse=True)[:5]

    # CNBC
    cnbc = []
    for name, url in [
        ('Top', 'https://www.cnbc.com/id/100003114/device/rss/rss.html'),
        ('Markets', 'https://www.cnbc.com/id/10000664/device/rss/rss.html'),
        ('Business', 'https://www.cnbc.com/id/10001147/device/rss/rss.html'),
    ]:
        try:
            f = feedparser.parse(url)
            for e in f.entries[:12]:
                cnbc.append({'source': f'CNBC {name}', 'headline': e.get('title', '')})
        except Exception as e:
            log(f"CNBC {name} error: {e}", "WARN")

    # Reuters via Google News
    reuters = []
    for q in ['site:reuters.com markets', 'site:reuters.com business']:
        try:
            url = f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}&hl=en-US&gl=US"
            f = feedparser.parse(url)
            for e in f.entries[:10]:
                reuters.append({'source': e.get('source', {}).get('title', 'Reuters'),
                               'headline': e.get('title', '')})
        except Exception as e:
            log(f"Reuters {q} error: {e}", "WARN")

    return {"per_ticker": per_ticker, "cnbc": cnbc, "reuters": reuters}

def read_journal_tail(n=30):
    if not JOURNAL.exists(): return []
    entries = []
    for line in JOURNAL.read_text().splitlines():
        line = line.strip()
        if not line: continue
        try: entries.append(json.loads(line))
        except Exception: pass
    return entries[-n:]

def compute_portfolio_value(state, market):
    """Cash + sum(shares * current_price)."""
    val = state['current_cash']
    for h in state['holdings']:
        # try to use market snapshot if it has the ticker, else fetch individually
        spot = None
        if h['ticker'] in market:
            spot = market[h['ticker']].get('price')
        if spot is None:
            try:
                spot = float(yf.Ticker(h['ticker']).fast_info['lastPrice'])
            except Exception:
                spot = h['avg_cost']  # fall back
        val += h['shares'] * spot
        h['current_price'] = spot
        h['unrealized_pl'] = (spot - h['avg_cost']) * h['shares']
        h['unrealized_pl_pct'] = (spot / h['avg_cost'] - 1) * 100 if h['avg_cost'] else 0
    return val


# ---------- prompt builders ----------
def build_state_context(state, total_value, market, news, journal, peer_returns, today_iso, cycle_name=None):
    lines = []
    lines.append(f"## TODAY: {today_iso}")
    if cycle_name:
        _cycle_labels = {
            "morning":   "MORNING (09:00 CT) — full run: thesis-check every holding, then deploy cash or consciously hold",
            "midday":    "MIDDAY (11:30 CT) — full run, same rules: thesis-check every holding, then deploy cash or consciously hold",
            "afternoon": "AFTERNOON (14:30 CT) — full run, same rules: thesis-check every holding, then deploy cash or consciously hold",
        }
        lines.append(f"## CYCLE: {_cycle_labels.get(cycle_name, cycle_name)}")
    lines.append(f"## YOUR PORTFOLIO (LLM Discretionary)")
    lines.append(f"  Starting cash: ${state['starting_cash']:,.2f}")
    lines.append(f"  Current cash:  ${state['current_cash']:,.2f}")
    lines.append(f"  Total value:   ${total_value:,.2f}")
    lines.append(f"  Cumulative return: {(total_value / state['starting_cash'] - 1) * 100:+.2f}%")
    if state['holdings']:
        lines.append(f"\n## YOUR CURRENT HOLDINGS ({len(state['holdings'])}):")
        for h in state['holdings']:
            lines.append(f"  {h['ticker']:<6s} {h['shares']:>5.0f} sh @ ${h['avg_cost']:.2f}  "
                        f"current ${h.get('current_price',0):.2f}  "
                        f"unrealized: {h.get('unrealized_pl_pct',0):+.1f}% (${h.get('unrealized_pl',0):+,.0f})  "
                        f"bought {h.get('first_bought_at','?')[:10]}")
    else:
        lines.append("\n## YOUR CURRENT HOLDINGS: none (all cash)")

    spy = market.get('SPY', {})
    lines.append(f"\n## BENCHMARKS")
    lines.append(f"  SPY 1d: {spy.get('ret_1d',0):+.2f}%  5d: {spy.get('ret_5d',0):+.2f}%  30d: {spy.get('ret_30d',0):+.2f}%")
    if peer_returns:
        lines.append(f"\n  Rule-based BigClaw portfolios (totalReturn % since their start):")
        for name, ret in peer_returns.items():
            mark = ""
            if ret is not None:
                mark = "  <-- BEATING you" if ret > (total_value / state['starting_cash'] - 1) * 100 else ""
            lines.append(f"    {name:<25s} {ret:>+6.2f}%{mark}" if ret is not None else f"    {name:<25s}  n/a")

    lines.append("\n" + render_lessons())

    lines.append(f"\n## SECTOR ETF PERFORMANCE (1d / 5d / 30d):")
    for t in SECTOR_ETFS:
        m = market.get(t, {})
        if m:
            lines.append(f"  {t}  1d {m.get('ret_1d',0):+5.2f}%  5d {m.get('ret_5d',0):+5.2f}%  30d {m.get('ret_30d',0):+5.2f}%")

    lines.append(f"\n## FACTOR ETF PERFORMANCE:")
    for t in FACTOR_ETFS:
        m = market.get(t, {})
        if m:
            lines.append(f"  {t}  1d {m.get('ret_1d',0):+5.2f}%  5d {m.get('ret_5d',0):+5.2f}%  30d {m.get('ret_30d',0):+5.2f}%")

    lines.append(f"\n## MACRO ETF PERFORMANCE:")
    for t in MACRO_ETFS:
        m = market.get(t, {})
        if m:
            lines.append(f"  {t}  1d {m.get('ret_1d',0):+5.2f}%  5d {m.get('ret_5d',0):+5.2f}%  30d {m.get('ret_30d',0):+5.2f}%")

    # MACRO REGIME (vol / credit / rates / cycle tells) - forward-looking, not lagging news
    _vix = market.get('^VIX', {}); _hyg = market.get('HYG', {}); _lqd = market.get('LQD', {})
    _tnx = market.get('^TNX', {}); _xly = market.get('XLY', {}); _xlp = market.get('XLP', {})
    _iwm = market.get('IWM', {}); _spy = market.get('SPY', {})
    _reg = []
    if _vix.get('price') is not None:
        _vx = _vix['price']
        _vband = ("CALM" if _vx < 15 else "NORMAL" if _vx < 22 else "ELEVATED"
                  if _vx < 25 else "HIGH" if _vx < 30 else "EXTREME")
        _reg.append(f"  VIX {_vx:.1f} [{_vband}]  (last-yr median ~17, 75th pct ~19; concern threshold 22; 5d {_vix.get('ret_5d') or 0:+.0f}%, 30d {_vix.get('ret_30d') or 0:+.0f}%)")
    if _hyg.get('ret_30d') is not None and _lqd.get('ret_30d') is not None:
        _reg.append(f"  Credit: HY(HYG) 30d {_hyg['ret_30d']:+.2f}% vs IG(LQD) 30d {_lqd['ret_30d']:+.2f}% - HY leading = risk-on credit")
    if _tnx.get('price') is not None:
        _reg.append(f"  10y yield {_tnx['price']:.2f}  (5d {_tnx.get('ret_5d') or 0:+.1f}%, 30d {_tnx.get('ret_30d') or 0:+.1f}%)")
    if _xly.get('ret_63d') is not None and _xlp.get('ret_63d') is not None:
        _reg.append(f"  Offense/Defense: XLY(disc) 3mo {_xly['ret_63d']:+.1f}% vs XLP(staples) 3mo {_xlp['ret_63d']:+.1f}% - disc>staples = expansion")
    if _iwm.get('ret_63d') is not None and _spy.get('ret_63d') is not None:
        _reg.append(f"  Breadth: IWM(small) 3mo {_iwm['ret_63d']:+.1f}% vs SPY 3mo {_spy['ret_63d']:+.1f}% - small-caps leading = risk-on")
    _secs = [(t, market.get(t, {}).get('ret_63d')) for t in SECTOR_ETFS if market.get(t, {}).get('ret_63d') is not None]
    if _secs:
        _secs.sort(key=lambda x: x[1], reverse=True)
        _reg.append('  Sector rotation 3mo - leaders: ' + ', '.join(f'{t} {v:+.0f}%' for t, v in _secs[:3]) + '  |  laggards: ' + ', '.join(f'{t} {v:+.0f}%' for t, v in _secs[-3:]))
    if _reg:
        lines.append('')
        lines.append('## MACRO REGIME (cycle tells):')
        lines.extend(_reg)

    if news.get('per_ticker'):
        lines.append(f"\n## NEWS FOR HELD/RECENT TICKERS (Alpaca/Benzinga, last 2 days):")
        for sym, items in news['per_ticker'].items():
            lines.append(f"  {sym}:")
            for n in items: lines.append(f"    [{n['time']}] {n['headline']}")

    lines.append(f"\n## BROAD MARKET HEADLINES (CNBC):")
    for n in news.get('cnbc', [])[:25]:
        lines.append(f"  [{n['source']}] {n['headline']}")

    lines.append(f"\n## BROAD MARKET HEADLINES (Reuters):")
    for n in news.get('reuters', [])[:20]:
        lines.append(f"  [{n['source']}] {n['headline']}")

    if journal:
        lines.append(f"\n## YOUR JOURNAL (last {len(journal)} cycles - your past decisions and outcomes):")
        for e in journal[-20:]:
            lines.append(f"\n  --- {e.get('date','?')} ---")
            if e.get('trades'):
                for t in e['trades']:
                    lines.append(f"    {t['action'].upper()} {t['shares']} {t['ticker']}  "
                                f"rationale: {t.get('rationale','')[:200]}")
                    if t.get('exit_thesis'):
                        lines.append(f"      exit_thesis: {t['exit_thesis'][:200]}")
            if e.get('patterns_noted'):
                lines.append(f"    patterns_noted: {e['patterns_noted'][:300]}")
            if e.get('outcomes'):
                lines.append(f"    outcomes (filled later by reconciler): {json.dumps(e['outcomes'])[:300]}")
            if e.get('flagged_triggers'):
                lines.append(f"    FLAGGED_TRIGGERS (safety check flagged {len(e['flagged_triggers'])} nonsense level(s) you set):")
                for _dt in e['flagged_triggers'][:5]:
                    lines.append(f"      - {_dt.get('reason','')[:200]}")
    else:
        lines.append("\n## YOUR JOURNAL: empty (this is your first cycle)")

    return "\n".join(lines)


BULL_SYSTEM = """You are the BULL agent in a 3-agent dialectical trading decision system.

Your job: For each candidate trade opportunity in today's data, build the strongest possible
case FOR the trade. Be aggressive. Look for asymmetric upside. Find what other traders might
be missing. Identify catalysts, technical setups, sentiment shifts, sector momentum, or
mean-reversion opportunities.

DEPLOYMENT MANDATE (not optional cheerleading - symmetric to the Bear's reject-test). Cash is NOT a
safe default: in this ~4% inflation environment, with zero interest on idle account cash, sitting in
cash is a guaranteed real loss of ~4%/year. So each cycle you MUST surface the best deployable
sector/factor setup you can find, ranked, with its reward-to-risk - and do NOT pre-reject a leader
just because it already moved (an established uptrend that is not yet extended is buyable; the move
having started is the point, not a disqualifier). Only if no sector or factor offers a positive edge
over a guaranteed real cash loss do you conclude "cash beats everything today," and then name what
would have to change for you to deploy.

ANTI-CHEATING:
- Your training data ends January 2026. Today is provided in the data. Trust ONLY the data feed.
- Every factual claim must be cited from the data feed. Saying "Apple announced X" without it
  appearing in the news feed is hallucination.
- Every thesis must reference specific data: a sector move, a headline, a P&L pattern, a divergence.

OUTPUT: For 2-5 candidate trades (existing positions or new ideas), provide:
- Ticker
- Direction (buy / add / hold-and-watch / trim)
- Strongest bull thesis (3-5 sentences, data-cited)
- Catalyst or trigger (what's driving this?)
- Time horizon (1-day / 3-day / 1-week / longer)
- Conviction (0.0 to 1.0)

Be aggressive but grounded. The BEAR agent will challenge you - if your thesis is weak it
will be torn apart. If you have no high-conviction ideas, say so and recommend cash."""

BEAR_SYSTEM = """You are the BEAR agent in a 3-agent dialectical trading decision system.

Your job has TWO STAGES, in order:

STAGE 1 — FACT VERIFICATION (do this FIRST, before any adversarial reasoning):
For each specific factual claim the BULL made — earnings numbers, analyst ratings,
price levels, dates, quoted headlines, percentages — locate the supporting evidence
in the data feed (the news section, market_snapshot, candidate_snapshot, or
Candidate Strength Ranking). Check three things explicitly:

  (a) Does the cited fact actually exist in the data feed?
  (b) Did the Bull read the direction correctly? (Upgrade vs downgrade, raise vs cut,
      reaffirm vs withdraw, beat vs miss — these get flipped frequently)
  (c) Is the cited number correct? (Price target above or below current price,
      percentage gain or loss, share count, etc.)

If you find a factual error — Bull cited something that isn't in the feed, misread a
direction, or quoted a number that contradicts what the feed actually shows — that is
your STRONGEST possible refutation. State the error explicitly with the actual data
from the feed, and treat the entire downstream thesis as compromised. A wrong fact is
not a debatable interpretation; it is a disqualifying mistake.

STAGE 2 — ADVERSARIAL REASONING (only after Stage 1):
For each surviving (factually accurate) Bull thesis, build the strongest possible
case AGAINST it. Be skeptical. Look for counter-evidence. Find hidden risks. Argue
why each trade is wrong, late, or already priced in. Identify what the bull missed.

ANTI-CHEATING:
- Your training data ends January 2026. Today is provided in the data. Trust ONLY the data feed.
- Every factual claim must be cited from the data feed.
- Don't be contrarian for its own sake - if a bull thesis is genuinely strong and you cannot
  find weakness, say so honestly. The JUDGE needs your real assessment, not theatrical opposition.

For each bull thesis, provide:
- Ticker
- Strongest counter-case (3-5 sentences, data-cited)
- What the bull missed (a specific blindspot)
- Probability the bull thesis is wrong (0.0 to 1.0)
- If the trade should be reversed (sell instead of buy, etc.), say so

Also: if the bull missed an obvious SHORT-side opportunity (sell, trim, avoid), name it.

If the BULL recommended cash and you agree, confirm it. If you see opportunities the
bull missed entirely, name them."""

JUDGE_SYSTEM = """You are the JUDGE agent in a 3-agent dialectical trading decision system.
You are the only agent whose decisions become actual trades.

You have read:
1. Today's full data feed (portfolio, market, news, your journal)
2. The BULL agent's case for trades
3. The BEAR agent's counter-case

YOUR JOB: Make the actual trade decisions. You MUST address the strongest counter-arguments
from the BEAR before committing to any trade. If the BEAR has surfaced a real risk you cannot
rebut, do not take the trade.

YOUR FIRST MOVE IS NOT TO ADJUDICATE - IT IS TO FIND THE GAP. The Bull and Bear are both
advocates; each argues inside the frame it was handed, and a coherent debate can be collectively
blind to the question neither thought to raise. You are the only seat that can see what the debate
structurally cannot, and THAT is where your edge comes from. Before you weigh Bull against Bear,
name what is ABSENT from BOTH cases that would change this decision over the next days-to-week. For
every proposed entry you MUST answer, independently of whether either side raised it:
  - Is there still ROOM TO RUN? A one-day pop may already be spent, but a move having STARTED is
    not the same as priced-in - an established sector trend that is not yet extended usually has
    more to give. "It already moved" alone is never a reason to pass; only an overshot or spent move is.
  - Is the driver a fresh, still-playing-out catalyst, or a stale one the tape has already digested?
  - What has to STAY true over the next few days for this to work, and what specific development
    would break it (that is your exit signal)?
Only after you have named the shared omissions do you rule.

ANTI-CHEATING (these are mechanical, you will be checked):
- Every factual claim cited from the data feed only
- Every ticker must be a real ticker (verified before trade submits)
- Cannot spend more cash than current_cash provided
- No hallucinated news, analysts, or earnings

YOUR FEEDBACK LOOP: Each cycle you read your journal. The exit_thesis field on each past
trade tells you whether your prediction came true. Patterns of wrong predictions should
change your behavior. Don't just keep doing what didn't work.

YOUR GOAL: Beat SPY and beat the 7 rule-based BigClaw portfolios over the next weeks.
OBJECTIVE IS ALPHA - risk-adjusted return on a SHORT-TERM horizon (1-day to 1-week mostly). This is
a fast-turnover trading book, NOT a buy-and-hold thesis fund: quick profits are GOOD and risk-
lowering - every hour held adds exposure to gaps and reversals - and cutting losses fast is correct.
Take the defined gain and redeploy; do not loiter in a position whose catalyst has played out. Risk
here includes time-in-market, not just drawdown depth. Reject the bad quadrant: small upside for
large downside. CASH IS NOT FREE - it is a guaranteed slow loss: in this ~4% inflation environment,
with zero interest on idle account cash, every day in cash bleeds ~4%/year of real purchasing power.
So the hurdle to deploy is LOW, not high - a position only needs a positive expected edge that beats
a guaranteed real loss. Flip the default: holding cash is the EXCEPTION you justify ("no sector or
factor offers a positive edge right now"), not the comfortable resting state. Sitting 80-90% cash
for weeks while a sector clearly leads (something there is buyable) is a FAILING posture - the skill
this book tests is harvesting the rotation, not avoiding every loss.

SHORT THE MARKET WHEN YOU HAVE A BEARISH EDGE (do not just retreat to cash): the book now holds -1x inverse ETFs - SH (S&P 500), PSQ (Nasdaq-100), DOG (Dow), RWM (Russell 2000). These are ordinary LONG buys that RISE when the market falls, so a down-view is a POSITION, not a sit-out. Distinguish two states: (a) a genuine UNKNOWN with no directional edge either way - cash is the correct, honest call there; versus (b) a real BEARISH EDGE - which means the SAME high bar you use to size down: VIX 22+ (NOT a merely high-teens VIX, which is normal) OR material credit/breadth deterioration, AND a clear macro driver pushing the broad tape lower (hawkish-Fed or inflation-acceleration talk, credit spreads widening, breadth breaking down) - where the alpha move is to BUY an inverse ETF and profit from the decline instead of parking in cash that bleeds to inflation. CRITICAL: in a low or normal-VIX tape (VIX in the teens, credit calm) do NOT short - that is a long-or-cash regime; shorting a calm or rising market is how you lose. Inverse ETFs are for a CONFIRMED down-regime only, never a hedge-by-default or a hunch. Use the -1x inverse ETFs ONLY; avoid leveraged -2x/-3x inverse - their volatility decay is a bad-quadrant risk on a 1-day-to-1-week horizon. Size a short like any other position with a defined target and stop, and cover it (sell the inverse ETF) when the down-move plays out or the regime turns - never marry a short any more than a long.

MACRO REGIME READ: the MACRO REGIME block is your risk-on/risk-off gauge - yield-curve direction (10y), credit spreads (HY vs IG), volatility (VIX), offense/defense (XLY vs XLP), breadth (IWM vs SPY), and recent sector rotation. Use it to set aggression and sector tilt for the DAYS AHEAD: in a calm risk-on tape, press into the sectors and factors with fresh momentum. Judge VIX by its ABSOLUTE level (calibrated to the last year: median ~17, 75th pct ~19, and forward SPY returns from a VIX of 18-21 were positive) - the high teens up to ~21 are NORMAL, so do not retreat just because VIX is in the high teens or rose. The empirical threshold of concern is VIX 22, where the odds of a >3% SPY drop in 10 days jump to ~40% (4x base rate). Only at VIX 22+ or on material credit/breadth deterioration should you size down and favor defensives or cash. Read where leadership is rotating and get in early on the move that is starting - do not chase the sector that already ran.

EVENT RISK - DO NOT OPEN INTO A BINARY EVENT: before opening any NEW position, check the news feed for a known binary event in the next 1-2 trading days that could invalidate the thesis - an FOMC decision, a CPI or jobs print, or upcoming earnings for the name you are considering. If one is imminent, do NOT open fresh exposure into it; wait for the event to clear and the new regime to be readable, then enter. This applies to OPENING new positions ONLY - whether to trim an existing position ahead of an event is your judgment call, but do not churn a working position just to dodge a scheduled print. The mistake to avoid is establishing brand-new exposure hours before a coin-flip that can break the thesis immediately, as happened buying XLF into a hawkish FOMC on 2026-06-17.

YOU MUST PRODUCE STRICT JSON. NO PROSE OUTSIDE THE JSON BLOCK.

OUTPUT SCHEMA:
{
  "reflection": "what your journal shows about your past performance and what you'd change",
  "market_read": "your read of the next 1-5 days",
  "gap_analysis": "what BOTH the Bull and Bear missed that affects this decision over the next days-to-week. For each proposed entry, explicitly: is there still ROOM TO RUN or has the move overshot (note: a sector trend having STARTED is not 'priced-in' - 'it already moved' alone is not a reason to pass)? is the catalyst still playing out or already spent? what must stay true over the next few days and what would break it (the exit signal)? This is your primary value-add - do not leave it shallow.",
  "addresses_bear_case": "specific paragraph addressing the strongest bear counter-arguments",
  "trades": [
    {
      "action": "buy" or "sell",
      "ticker": "AAPL",  // real tradable Alpaca ticker
      "shares": 50,       // positive integer
      "rationale": "specific data-cited reasoning (which catalyst/setup/pattern)",
      "exit_thesis": "specific gain target / stop loss / time-based exit (prose, for the journal)",
      "exit_conditions": {
        "target_pct": 2.0,              // gain target (positive number). Set it to ~HALF the upside to your thesis price target, NOT the full distance: ~20% upside to the analyst PT/fair value -> target ~10% and take the money and run. The full PT is rarely hit in the commando window before the move stalls or time-exit fires; a half-target is realistic and bankable. null if none
        "stop_pct": 1.5,                // stop loss as positive number (absolute), e.g. 1.5 = -1.5%; null if none
        "time_exit_date": "YYYY-MM-DD"  // ISO date by which the position must close (days out for a short-term trade); null if no time exit
      },
      "thesis_type": "catalyst" or "technical" or "macro" or "sentiment" or "contrarian",
      "confidence": 0.0 to 1.0
    }
  ],
  "watchlist": ["tickers you're considering for upcoming days"],
  "intraday_triggers": [
    {
      "id": "t1",                       // your label, e.g. "t1", "fed_speak"
      "type": "price" | "news" | "time",
      "ticker": "NVDA",                 // PRICE triggers only
      "op": "below" | "above" | "crosses_below" | "crosses_above",  // PRICE only
      "level": 205.0,                   // PRICE only - absolute dollar level (use for tickers in your market_snapshot)
      "level_pct": -0.05,               // PRICE only - ALTERNATIVE to level, percentage from entry of a position you're opening this cycle. -0.05 = stop at 5% below entry. +0.10 = target at 10% above entry. ALWAYS prefer level_pct over level when setting stop/target for a position you are opening today, because absolute dollar prices in your training data may not match the live entry price.
      "keywords": ["Fed", "Powell", "FOMC", "rate decision"],  // NEWS only
      "wake_at": "YYYY-MM-DDTHH:MMZ",   // TIME only - ISO UTC
      "action_intent": "specific intent if the trigger fires (the watcher's LLM call will see this)",
      "expires_at": "YYYY-MM-DDTHH:MMZ" // default end of trading day
    }
  ],
  "patterns_noted": "lessons-learned to add to your journal for future cycles",
  "uncertainty_inventory": ["3 things you wish you knew but cannot from this data feed"],
  "expected_portfolio_direction": "bullish" or "bearish" or "neutral"
}

INTRADAY TRIGGERS: You have full freedom to define up to 8 triggers per cycle that a lightweight
watcher checks during market hours. Use them aggressively when you see asymmetric setups: "if XLF
breaks $53 with volume, add", "if Fed dovishness leaks before FOMC, lever up", "if SPY -2% intraday,
buy the panic", "if a held name hits +3%, take the gain". When a trigger matches, a focused LLM call
(you, with the original intent + current state) decides: execute as planned, modify, or stand down.
Max 6 fires per day across all triggers.

CYCLE FRAMINGS: Three deliberative cycles fire each market day — MORNING (09:00 CT), MIDDAY
(11:30 CT) and AFTERNOON (14:30 CT) — and EVERY cycle runs the SAME full decision (the morning
run, repeated). There is NO monitor-only or pre-close-only mode. Each cycle, in order:

  1. THESIS CHECK ON EVERY HOLDING (the extra question per held name): is the thesis that put
     you into this position STILL intact? If a real development has broken it, EXIT. If it is
     intact, HOLD — do not churn a working position on noise. (What "the thesis" means and the
     horizon over which it must hold are set by YOUR GOAL above.)
  2. FULL RE-EVALUATION + CASH DEPLOYMENT: then scan the full candidate set and your available
     cash exactly as you would at the open. Deploy into the best opportunities that clear your
     bar, or CONSCIOUSLY hold cash with a stated reason if nothing does. "Nothing clears the bar"
     is a valid call, but it must be an ACTIVE decision every cycle, never a passive default.

Between cycles the watcher fires only on triggers you set; these three dialectic cycles are the
guaranteed full-deliberation moments where Bear gets to refute Bull.

If no trades make sense today, return {"trades": []} and explain in reflection.

FLAGGED TRIGGERS — IF YOU SEE THEM IN YOUR JOURNAL: a safety check downstream of you
flags price triggers whose levels are nonsense relative to entry (stop must
be strictly below entry but above entry × 0.5; target must be strictly above entry
and below entry × 2.0). When you see `FLAGGED_TRIGGERS` in a past journal entry, that
was YOU setting absolute dollar levels based on stale training-cutoff price anchors.
Sector ETFs move in narrow ranges — sanity-check against the live price in your
market_snapshot, not the price you remember from training."""


# ---------- agent call ----------
def call_agent(client, system, user_message, model, max_tokens, agent_name):
    t0 = time.time()
    resp = client.messages.create(
        model=model, max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )
    dt = time.time() - t0
    text = resp.content[0].text
    in_tok, out_tok = resp.usage.input_tokens, resp.usage.output_tokens
    # Sonnet 4.6 pricing
    cost = (in_tok * 3.0 + out_tok * 15.0) / 1_000_000
    log_llm_call(agent_name, model, in_tok, out_tok, cost, dt)
    log(f"  {agent_name}: in={in_tok} out={out_tok} cost=${cost:.4f} t={dt:.1f}s")
    return text, cost, dt


def parse_judge_json(text):
    """Extract JSON from judge output. Tolerates ```json ... ``` fencing."""
    m = re.search(r'\{[\s\S]*\}', text)
    if not m:
        raise ValueError(f"No JSON in judge output: {text[:300]}")
    return json.loads(m.group(0))


# ---------- trade execution ----------
def validate_and_execute(trades, state, total_value, secrets, dry_run=False):
    """Validate each trade; execute via Alpaca + record_trade if not dry_run.
       Returns list of (trade, result_dict)."""
    sys.path.insert(0, str(Path.home() / "bigclaw-ai" / "scripts"))
    from autonomous_trader import get_trading_client, MISMATCH_FLAG_PATH, verify_account_synced, post_trade_verify_or_flag
    # PRE-TRADE: active books only; self-heals stale flags
    verify_account_synced()
    from order_fill import wait_for_fill, clamp_sell_to_long
    from trade_recorder import record_trade
    from alpaca.trading.requests import MarketOrderRequest, GetAssetsRequest
    from alpaca.trading.enums import OrderSide, TimeInForce, AssetStatus

    if MISMATCH_FLAG_PATH.exists():
        log("Alpaca mismatch flag set - skipping trade execution this cycle", "WARN")
        return [(t, {"skipped": "global mismatch flag"}) for t in trades]

    client = get_trading_client()
    # Market hours check
    clock = client.get_clock()
    if not clock.is_open:
        log(f"Market closed (next open {clock.next_open}). Skipping execution.", "WARN")
        return [(t, {"skipped": "market closed"}) for t in trades]

    cash = state['current_cash']
    # Re-read holdings FRESH from the DB at execution time, NOT the cycle-start
    # snapshot. The 5-min watcher can sell a position during this cycle's ~167s
    # run; selling against the stale snapshot oversells into a SHORT.
    # Incident 2026-06-15: AAL/IWM double-sold into shorts (watcher + cycle).
    _hc = sqlite3.connect(DB_PATH, timeout=10)
    _hc.row_factory = sqlite3.Row
    holdings_by_ticker = {r['ticker']: {'ticker': r['ticker'], 'shares': r['shares'],
                                        'avg_cost': r['avg_cost']}
                          for r in _hc.execute(
                              "SELECT ticker, shares, avg_cost FROM holdings "
                              "WHERE portfolio_id=? AND shares>0", (state['id'],)).fetchall()}
    _hc.close()
    results = []

    # Process SELLS before BUYS so in-cycle sell proceeds fund in-cycle buys.
    # Without this, the Judge can't express compound rotation moves like
    # "sell A, buy B and C" — the buys see only the pre-cycle cash and may
    # be skipped as insufficient even though the sell would cover them.
    # Bug observed 2026-06-12: ETF Focus sold XLV (~$53K proceeds) then tried
    # to buy IWM + XLK; XLK was skipped despite plenty of total cash.
    trades = sorted(trades, key=lambda t: 0 if t.get('action','').lower() == 'sell' else 1)

    for tr in trades:
        ticker = tr.get('ticker', '').upper()
        action = tr.get('action', '').lower()
        shares = int(tr.get('shares', 0))

        if shares < 1 or action not in ('buy', 'sell'):
            results.append((tr, {"skipped": f"invalid: action={action} shares={shares}"}))
            continue

        # Verify ticker is tradable
        try:
            asset = client.get_asset(ticker)
            if asset.status != AssetStatus.ACTIVE or not asset.tradable:
                results.append((tr, {"skipped": f"ticker not tradable: {ticker}"}))
                continue
        except Exception as e:
            results.append((tr, {"skipped": f"ticker not found: {ticker} ({e})"}))
            continue

        # SELL: must hold enough; credit estimated proceeds to running cash
        if action == 'sell':
            held = holdings_by_ticker.get(ticker, {}).get('shares', 0)
            if held <= 0:
                results.append((tr, {"skipped": f"{ticker}: fresh holdings=0, nothing to sell (stale/duplicate sell blocked)"}))
                continue
            if shares > held:
                log(f"Clamping {ticker} sell {shares} -> {int(held)} to fresh holdings (prevents short)", "WARN")
                shares = int(held)
            _bk = clamp_sell_to_long(client, ticker, shares, allow_short=bool(tr.get('short', False)))
            if _bk <= 0:
                results.append((tr, {"skipped": f"{ticker}: not long at Alpaca (short-prevention)"}))
                continue
            shares = _bk
            # Credit estimated proceeds so subsequent buys this cycle see realistic cash.
            try:
                spot = float(yf.Ticker(ticker).fast_info['lastPrice'])
                cash += shares * spot
            except Exception:
                pass

        # BUY: cash check (use latest price)
        if action == 'buy':
            try:
                spot = float(yf.Ticker(ticker).fast_info['lastPrice'])
            except Exception:
                spot = 0
            cost = shares * spot
            if cost > cash:
                results.append((tr, {"skipped": f"insufficient cash: need ${cost:,.0f} have ${cash:,.0f}"}))
                continue
            cash -= cost  # provisional

        if dry_run:
            results.append((tr, {"dry_run": True, "would_submit": f"{action.upper()} {shares} {ticker}"}))
            continue

        # Submit to Alpaca
        try:
            req = MarketOrderRequest(
                symbol=ticker, qty=shares,
                side=OrderSide.BUY if action == 'buy' else OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            )
            order = client.submit_order(req)
            filled_qty, filled_price = wait_for_fill(
                client, order, shares, None,
                ticker=ticker, pname=PORTFOLIO_NAME,
                side='BUY' if action == 'buy' else 'SELL',
            )
            actual_value = filled_qty * filled_price
            # Write the computed target PRICE so the dashboard Target/Upside columns populate.
            # Target = entry x (1 + target_pct/100); captured on the first buy of a position.
            _tp = (tr.get('exit_conditions') or {}).get('target_pct')
            _tgt_price = round(filled_price * (1 + _tp / 100.0), 2) if (action == 'buy' and _tp) else None
            _tgt_src = f"LLM +{_tp:g}% target" if _tgt_price else None
            ok = record_trade(
                state['id'], PORTFOLIO_NAME, ticker, action, filled_qty, filled_price, actual_value,
                f"LLM-DIALECTIC: {tr.get('rationale','')[:300]}",
                order_id=str(order.id), target_price=_tgt_price, target_source=_tgt_src,
            )
            results.append((tr, {
                "filled_qty": filled_qty, "filled_price": filled_price,
                "value": actual_value, "order_id": str(order.id), "db_ok": ok,
            }))
        except Exception as e:
            log(f"Trade execution error {action} {shares} {ticker}: {e}", "ERROR")
            results.append((tr, {"error": str(e)}))

    return results


# ---------- output ----------
def append_journal(entry):
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with JOURNAL.open("a") as f:
        f.write(json.dumps(entry) + "\n")

def post_slack(channel, text, secrets):
    client = WebClient(token=secrets['SLACK_BOT_TOKEN'])
    for i in range(0, len(text), 38000):
        prefix = "" if i == 0 else f"_(continued)_\n\n"
        client.chat_postMessage(channel=channel, text=prefix + text[i:i+38000])

def save_decision_markdown(today_iso, total_value, state, market, news, peer_returns,
                            bull_text, bear_text, judge_out, exec_results,
                            cost_total, cycle_duration_sec, bull_dt=None, bear_dt=None, judge_dt=None,
                            cycle_name=None):
    """Human-readable per-cycle file with full reasoning. Browse data/llm_decisions/
       to see Bull / Bear / Decision basis and how it evolves over time."""
    DECISIONS_DIR.mkdir(parents=True, exist_ok=True)
    md = DECISIONS_DIR / (f"{today_iso}-{cycle_name}.md" if cycle_name else f"{today_iso}.md")

    cum = (total_value / state['starting_cash'] - 1) * 100
    spy = market.get('SPY', {})

    lines = [
        f"# LLM-ETF Focus — {today_iso}" + (f" — {cycle_name.upper()} cycle" if cycle_name else ""),
        "",
        f"**Portfolio value:** ${total_value:,.2f}  |  **Cash:** ${state['current_cash']:,.2f}  "
        f"|  **Cumulative return:** {cum:+.2f}%",
        f"**Cycle cost:** ${cost_total:.4f}  |  **Total cycle duration:** {cycle_duration_sec:.1f}s "
        f"(Bull {bull_dt or '?'}s, Bear {bear_dt or '?'}s, Judge {judge_dt or '?'}s)",
        "",
        "---",
        "",
        "## Market state the LLM saw",
        "",
        f"- **SPY:** 1d {spy.get('ret_1d',0):+.2f}%  /  5d {spy.get('ret_5d',0):+.2f}%  /  30d {spy.get('ret_30d',0):+.2f}%",
        "",
    ]

    # Sector ETFs
    sector_rows = [(t, market.get(t, {})) for t in SECTOR_ETFS]
    if any(m for _, m in sector_rows):
        lines += ["### Sector ETF returns (1d / 5d / 30d)", ""]
        lines += ["| ETF | 1d | 5d | 30d |", "|---|---:|---:|---:|"]
        for t, m in sorted(sector_rows, key=lambda kv: -(kv[1].get('ret_5d') or -99)):
            if not m: continue
            lines.append(f"| {t} | {m.get('ret_1d',0):+.2f}% | {m.get('ret_5d',0):+.2f}% | {m.get('ret_30d',0):+.2f}% |")
        lines.append("")

    # Factor ETFs
    factor_rows = [(t, market.get(t, {})) for t in FACTOR_ETFS]
    if any(m for _, m in factor_rows):
        lines += ["### Factor ETFs", ""]
        for t, m in factor_rows:
            if not m: continue
            lines.append(f"- **{t}**: 1d {m.get('ret_1d',0):+.2f}%  /  5d {m.get('ret_5d',0):+.2f}%  /  30d {m.get('ret_30d',0):+.2f}%")
        lines.append("")

    # Macro
    macro_rows = [(t, market.get(t, {})) for t in MACRO_ETFS if t != 'SPY']
    if any(m for _, m in macro_rows):
        lines += ["### Macro context", ""]
        for t, m in macro_rows:
            if not m: continue
            lines.append(f"- **{t}**: 1d {m.get('ret_1d',0):+.2f}%  /  5d {m.get('ret_5d',0):+.2f}%  /  30d {m.get('ret_30d',0):+.2f}%")
        lines.append("")

    # Inverse / short ETFs -- a bearish edge is a position, not cash
    inv_rows = [(t, market.get(t, {})) for t in INVERSE_ETFS]
    if any(m for _, m in inv_rows):
        lines += ["### Inverse / Short ETFs (-1x -- these RISE when the market falls)", ""]
        for t, m in inv_rows:
            if not m: continue
            lines.append(f"- **{t}**: 1d {m.get('ret_1d',0):+.2f}%  /  5d {m.get('ret_5d',0):+.2f}%  /  30d {m.get('ret_30d',0):+.2f}%")
        lines.append("")

    # Peer portfolios
    if peer_returns:
        lines += ["### Rule-based BigClaw peers (cumulative return)", ""]
        for n, r in sorted(peer_returns.items(), key=lambda kv: -(kv[1] or -99)):
            if r is None: continue
            mark = "  ← beating LLM" if r > cum else ""
            lines.append(f"- {n}: {r:+.2f}%{mark}")
        lines.append("")

    # Holdings before this cycle
    lines += [f"### Holdings at start of cycle ({len(state['holdings'])})", ""]
    if state['holdings']:
        lines += ["| Ticker | Shares | Avg Cost | Current | Unrealized % | $ |",
                  "|---|---:|---:|---:|---:|---:|"]
        for h in state['holdings']:
            lines.append(f"| {h['ticker']} | {h['shares']:.0f} | ${h['avg_cost']:.2f} | "
                         f"${h.get('current_price',0):.2f} | {h.get('unrealized_pl_pct',0):+.1f}% | "
                         f"${h.get('unrealized_pl',0):+,.0f} |")
    else:
        lines.append("_All cash, no positions._")
    lines.append("")

    # News volume
    n_alpaca = sum(len(v) for v in news.get('per_ticker', {}).values())
    lines.append(f"- **News volume fed in:** {n_alpaca} ticker-tagged Benzinga articles, "
                 f"{len(news.get('cnbc', []))} CNBC headlines, "
                 f"{len(news.get('reuters', []))} Reuters headlines.")
    lines += ["", "---", ""]

    # BULL
    lines += [
        "## 🟢 Bull Case",
        "",
        "_Sonnet #1 — strongest case FOR candidate trades. Full output, raw and uncurated._",
        "",
        bull_text,
        "",
        "---",
        "",
    ]

    # BEAR
    lines += [
        "## 🔴 Bear Case",
        "",
        "_Sonnet #2 — challenges every bull thesis with counter-evidence. Full output, raw and uncurated._",
        "",
        bear_text,
        "",
        "---",
        "",
    ]

    # JUDGE
    lines += [
        "## ⚖️ Judge Decision",
        "",
        "_Sonnet #3 — synthesizes both sides, must address the bear before deciding._",
        "",
    ]

    if judge_out.get("reflection"):
        lines += ["### Reflection on prior performance", "", judge_out["reflection"], ""]
    if judge_out.get("market_read"):
        lines += ["### Market read", "", judge_out["market_read"], ""]
    if judge_out.get("gap_analysis"):
        lines += ["### Gap analysis (what BOTH bull and bear missed)", "",
                  judge_out["gap_analysis"], ""]
    if judge_out.get("addresses_bear_case"):
        lines += ["### How the judge addressed the bear case", "",
                  judge_out["addresses_bear_case"], ""]

    trades = judge_out.get("trades", [])
    if trades:
        lines += [f"### Trades decided ({len(trades)})", ""]
        for i, t in enumerate(trades, 1):
            action = (t.get("action") or "").upper()
            tk = t.get("ticker", "?")
            sh = t.get("shares", 0)
            typ = t.get("thesis_type", "?")
            conf = t.get("confidence", "?")
            lines += [f"**{i}. {action} {sh} {tk}** — type: {typ}, confidence: {conf}", ""]
            lines += [f"- **Rationale:** {t.get('rationale','')}"]
            lines += [f"- **Exit thesis:** {t.get('exit_thesis','')}"]
            lines += [""]
    else:
        lines += ["### Trades decided", "", "_No trades this cycle._", ""]

    if judge_out.get("watchlist"):
        lines += ["### Watchlist for upcoming days", "",
                  ", ".join(judge_out["watchlist"]), ""]
    if judge_out.get("patterns_noted"):
        lines += ["### Patterns noted (added to journal)", "",
                  judge_out["patterns_noted"], ""]
    if judge_out.get("uncertainty_inventory"):
        lines += ["### Things the LLM wishes it knew but cannot", ""]
        for item in judge_out["uncertainty_inventory"]:
            lines.append(f"- {item}")
        lines.append("")
    if judge_out.get("expected_portfolio_direction"):
        lines += [f"**Expected direction:** {judge_out['expected_portfolio_direction']}", ""]

    lines += ["---", "", "## Execution", ""]
    if exec_results:
        for t, r in exec_results:
            tag = f"{(t.get('action') or '').upper()} {t.get('shares')} {t.get('ticker')}"
            if "filled_qty" in r:
                lines.append(f"- ✓ **{tag}** filled {r['filled_qty']} @ ${r['filled_price']:.2f} "
                             f"= ${r['value']:,.2f}  (order `{r['order_id']}`)")
            elif "skipped" in r:
                lines.append(f"- ⊘ **{tag}** skipped — {r['skipped']}")
            elif "dry_run" in r:
                lines.append(f"- ⊙ **{tag}** dry-run")
            elif "error" in r:
                lines.append(f"- ✗ **{tag}** ERROR — {r['error']}")
    else:
        lines.append("_No trades to execute._")

    md.write_text("\n".join(lines))

    # Maintain index README.md
    files = sorted([f for f in DECISIONS_DIR.glob("*.md") if f.name != "README.md"], reverse=True)
    idx = [
        "# LLM-ETF Focus — Decision Journal",
        "",
        "Per-cycle reasoning from the 3-Sonnet dialectic (Bull / Bear / Judge).",
        "Browse a day to see the full argument the LLMs made.",
        "",
        f"_{len(files)} cycle(s) recorded._",
        "",
        "## By date (newest first)",
        "",
    ]
    for f in files:
        idx.append(f"- [{f.stem}]({f.name})")
    (DECISIONS_DIR / "README.md").write_text("\n".join(idx))


def save_dashboard_json(judge_out, bull_text, bear_text, total_value, state, exec_results, cost_total):
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps({
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "portfolio_value": round(total_value, 2),
        "cash": round(state['current_cash'], 2),
        "cumulative_return_pct": round((total_value / state['starting_cash'] - 1) * 100, 2),
        "starting_cash": state['starting_cash'],
        "reflection": judge_out.get("reflection"),
        "market_read": judge_out.get("market_read"),
        "gap_analysis": judge_out.get("gap_analysis"),
        "addresses_bear_case": judge_out.get("addresses_bear_case"),
        "trades_decided": judge_out.get("trades", []),
        "execution_results": [{"action": t.get("action"), "ticker": t.get("ticker"),
                                "shares": t.get("shares"), "result": r}
                               for t, r in exec_results],
        "watchlist": judge_out.get("watchlist", []),
        "patterns_noted": judge_out.get("patterns_noted"),
        "uncertainty_inventory": judge_out.get("uncertainty_inventory", []),
        "expected_direction": judge_out.get("expected_portfolio_direction"),
        "bull_case_preview": (bull_text or "")[:500],
        "bear_case_preview": (bear_text or "")[:500],
        "cost_today_usd": round(cost_total, 4),
    }, indent=2))


# ---------- main ----------

def validate_triggers(triggers, db_path, pid):
    """FLAG-mode validator: stamps a `_schema_flag` field on price triggers
    whose levels are schema-nonsensical for a long position, but arms them
    anyway. The LLM learns from real outcomes via the journal rather than
    silent filtering.

    Schema check (longs only — paper account is long-only):
      crosses_below: stop should be strictly below entry but above entry * 0.5
      crosses_above: target/add should be strictly above entry but below entry * 2.0
    Triggers on unheld tickers (watch triggers) pass through unchanged.

    Resolution: if a trigger sets `level_pct` (e.g. -0.05 for -5% from entry)
    instead of `level`, this function computes the absolute level from the
    held position's entry price before checking. That lets the Judge avoid
    setting absolute dollar levels on tickers whose live price differs from
    its training-cutoff anchor.

    Returns (all_triggers_armed, [{trigger_id, reason}, ...] for flagged ones)."""
    if not triggers:
        return triggers, []
    import sqlite3 as _s
    c = _s.connect(db_path, timeout=10); c.row_factory = _s.Row
    held = {r['ticker']: float(r['avg_cost']) for r in c.execute(
        "SELECT ticker, avg_cost FROM holdings WHERE portfolio_id=? AND shares > 0", (pid,)).fetchall()}
    c.close()
    kept, flagged = [], []
    for tr in triggers:
        if tr.get("type") != "price" or not tr.get("ticker") or tr["ticker"] not in held:
            # Watch trigger or non-price — but resolve level_pct if it leaked in
            if tr.get("level_pct") is not None and tr.get("level") is None:
                flagged.append({"trigger_id": tr.get("id"),
                                "reason": f"level_pct set on unheld ticker {tr.get('ticker')} — cannot resolve"})
                continue
            kept.append(tr); continue
        entry = held[tr["ticker"]]; op = tr.get("op")
        # Resolve level_pct -> level if set
        if tr.get("level_pct") is not None:
            pct = tr["level_pct"]
            if not isinstance(pct, (int, float)) or not (-0.5 < pct < 1.0):
                flagged.append({"trigger_id": tr.get("id"),
                                "reason": f"level_pct {pct} out of range (-0.5, 1.0) for {tr['ticker']}"})
                continue
            tr = {k: v for k, v in tr.items() if k != "level_pct"}
            tr["level"] = round(entry * (1.0 + pct), 4)
        level = tr.get("level")
        if level is None or op is None:
            kept.append(tr); continue
        # Strict-ordering check with wide outer bands. Bug-class catches: stop
        # at-or-above entry on a long, target at-or-below entry on a long,
        # absurd outer values from training-cutoff price anchors. Sub-1%
        # bands pass through (legitimate tight stops are common on ETFs).
        #
        # FLAG MODE (2026-06-12): we no longer drop nonsense triggers. They
        # arm anyway. The watcher fires them, the LLM re-evaluates, the
        # outcome lands in the journal. That gives the LLM a real signal
        # ("I set a stop that fired in 2 minutes — bad") instead of a
        # silent filter. Aligned with the design call that Python provides
        # information, not rules, for these two portfolios.
        flag_reason = ""
        if op == "crosses_below" and not (entry * 0.5 < level < entry):
            flag_reason = f"stop {tr['ticker']} crosses_below ${level} (entry ${entry:.2f}) — schema says stop should be strictly below entry and above ${entry*0.5:.2f}. Armed anyway; watch for fast-fire."
        elif op == "crosses_above" and not (entry < level < entry * 2.0):
            flag_reason = f"target {tr['ticker']} crosses_above ${level} (entry ${entry:.2f}) — schema says target should be strictly above entry and below ${entry*2.0:.2f}. Armed anyway; watch for instant-fire or never-fire."
        if flag_reason:
            tr = {**tr, "_schema_flag": flag_reason}
            flagged.append({"trigger_id": tr.get("id"), "reason": flag_reason})
        kept.append(tr)
    return kept, flagged


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="No Alpaca submits, no Slack post, no DB writes for trades")
    ap.add_argument("--cycle", choices=["morning", "midday", "afternoon"], default="morning",
                    help="Which deliberative cycle this is. morning=09:00 anchor, "
                         "midday=11:30 re-evaluation, afternoon=14:30 pre-close lock")
    ap.add_argument("--observe-only", action="store_true",
                    help="Run agents but produce strategy doc only - no trade decisions")
    ap.add_argument("--channel", default=DEFAULT_CHANNEL)
    args = ap.parse_args()

    acquire_lock()
    try:
        log(f"LLM portfolio cycle - starting ({args.cycle.upper()})")
        secrets = load_secrets()
        for k in ("ANTHROPIC_API_KEY", "ALPACA_API_KEY", "ALPACA_SECRET_KEY", "SLACK_BOT_TOKEN"):
            if k not in secrets:
                write_failure_flag(f"missing secret: {k}")
                sys.exit(1)

        # Drawdown freeze check
        if DRAWDOWN_FLAG.exists():
            log("Drawdown freeze flag set. Trading paused. Resolve manually to resume.", "WARN")
            sys.exit(0)

        log("Reading portfolio + journal state...")
        state = get_portfolio_state()
        journal = read_journal_tail(n=30)
        log(f"  cash=${state['current_cash']:,.2f}  holdings={len(state['holdings'])}  journal={len(journal)} entries")

        log("Gathering market snapshot...")
        market = get_market_snapshot()
        log(f"  {len(market)} ETFs priced")

        total_value = compute_portfolio_value(state, market)
        log(f"  total_value=${total_value:,.2f}  cumulative_return={(total_value/state['starting_cash']-1)*100:+.2f}%")

        # Catastrophic drawdown
        if total_value < CATASTROPHIC_DRAWDOWN_FLOOR:
            DRAWDOWN_FLAG.parent.mkdir(parents=True, exist_ok=True)
            DRAWDOWN_FLAG.write_text(json.dumps({
                "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "total_value": total_value,
                "floor": CATASTROPHIC_DRAWDOWN_FLOOR,
                "reason": "Portfolio dropped below 50% of starting capital. Trading frozen.",
            }, indent=2))
            log("CATASTROPHIC DRAWDOWN - trading frozen. Slack alert sent.", "ERROR")
            try:
                client = WebClient(token=secrets['SLACK_BOT_TOKEN'])
                client.chat_postMessage(channel=args.channel,
                    text=f":rotating_light: *LLM Portfolio drawdown freeze* — total value ${total_value:,.0f} below ${CATASTROPHIC_DRAWDOWN_FLOOR:,.0f}. Trading paused. Resolve manually.")
            except Exception:
                pass
            sys.exit(0)

        log("Gathering news (Alpaca/Benzinga + CNBC + Reuters)...")
        held_tickers = [h['ticker'] for h in state['holdings']]
        # plus watchlist from last journal entry (if any)
        recent_watch = []
        if journal:
            recent_watch = journal[-1].get('watchlist', [])[:15] if isinstance(journal[-1].get('watchlist'), list) else []
        news_tickers = sorted(set(held_tickers + recent_watch))
        news = get_news(news_tickers, secrets)
        log(f"  Alpaca: {sum(len(v) for v in news['per_ticker'].values())} items for {len(news['per_ticker'])} tickers")
        log(f"  CNBC: {len(news['cnbc'])} | Reuters: {len(news['reuters'])}")

        peer_returns = get_peer_returns()
        today_iso = datetime.date.today().isoformat()
        state_ctx = build_state_context(state, total_value, market, news, journal,
                                         peer_returns, today_iso, cycle_name=args.cycle)
        log(f"State context: {len(state_ctx)} chars")

        anthropic_client = anthropic.Anthropic(api_key=secrets['ANTHROPIC_API_KEY'],
                                                 timeout=LLM_TIMEOUT)

        cycle_start = time.time()

        # --- BULL ---
        log("Calling BULL agent...")
        bull_msg = state_ctx + "\n\n## YOUR TASK:\nAs the BULL agent, write your case. Use the schema in your system prompt."
        bull_text, bull_cost, bull_dt = call_agent(anthropic_client, BULL_SYSTEM, bull_msg,
                                            MODEL_BULL, MAX_TOKENS_DEBATE, "bull")

        # --- BEAR ---
        log("Calling BEAR agent...")
        bear_msg = (state_ctx
                    + "\n\n## BULL AGENT'S CASE (your target to challenge):\n\n" + bull_text
                    + "\n\n## YOUR TASK:\nAs the BEAR agent, challenge each bull thesis. Use the schema in your system prompt.")
        bear_text, bear_cost, bear_dt = call_agent(anthropic_client, BEAR_SYSTEM, bear_msg,
                                            MODEL_BEAR, MAX_TOKENS_DEBATE, "bear")

        # --- JUDGE ---
        log("Calling JUDGE agent...")
        judge_msg = (state_ctx
                     + "\n\n## BULL AGENT'S CASE:\n\n" + bull_text
                     + "\n\n## BEAR AGENT'S COUNTER-CASE:\n\n" + bear_text
                     + "\n\n## YOUR TASK:\nAs the JUDGE, decide today's trades. Output strict JSON per schema in system prompt.")
        judge_text, judge_cost, judge_dt = call_agent(anthropic_client, JUDGE_SYSTEM, judge_msg,
                                              MODEL_JUDGE, MAX_TOKENS_JUDGE, "judge")

        cost_total = bull_cost + bear_cost + judge_cost
        cycle_duration = time.time() - cycle_start
        log(f"Total cycle cost: ${cost_total:.4f}  duration: {cycle_duration:.1f}s")

        try:
            judge_out = parse_judge_json(judge_text)
        except Exception as e:
            log(f"Judge JSON parse failed: {e}\n--- judge text ---\n{judge_text}\n", "ERROR")
            write_failure_flag(f"judge JSON parse error: {e}")
            sys.exit(1)

        trades = judge_out.get("trades", []) if not args.observe_only else []
        log(f"Judge decided {len(trades)} trades")

        # Execute
        exec_results = validate_and_execute(trades, state, total_value, secrets, dry_run=args.dry_run)
        # Create trailing stops immediately for any just-bought positions, so a new position is
        # never briefly flagged UNPROTECTED in the gap before the 15-min stop_check cron picks it
        # up (mirrors the rule-based trader's post-trade RULE 5.25).
        if not args.dry_run and any(t.get('action') == 'buy' and isinstance(r, dict) and r.get('filled_qty')
                                    for t, r in exec_results):
            try:
                sys.path.insert(0, str(Path.home() / "bigclaw-ai" / "scripts"))
                from trailing_stop_manager import initialize_stops
                initialize_stops()
                log("post-trade: initialized trailing stops for new positions")
            except Exception as e:
                log(f"post-trade trailing-stop init failed: {e}", "WARN")
        executed = sum(1 for _, r in exec_results if r.get("filled_qty"))
        skipped = sum(1 for _, r in exec_results if "skipped" in r or "error" in r)
        log(f"Executed: {executed}  skipped/errored: {skipped}")

        # Validate Judge-emitted intraday triggers BEFORE building the journal
        # entry. The dropped list goes into the entry so tomorrow's Judge sees
        # which of yesterday's triggers got refused as nonsense — closes the
        # recursive learning loop for the stale-price-anchor bug class.
        _raw_triggers = judge_out.get("intraday_triggers", []) or []
        _all_triggers, _flagged_triggers = validate_triggers(_raw_triggers, str(DB_PATH), state['id'])
        for _d in _flagged_triggers:
            log(f"FLAGGED suspect trigger (armed anyway) {_d['trigger_id']}: {_d['reason']}", "WARN")

        # Journal entry
        entry = {
            "date": today_iso,
            "portfolio_value_at_decision": round(total_value, 2),
            "cash_at_decision": state['current_cash'],
            "starting_holdings": [{"ticker": h['ticker'], "shares": h['shares'],
                                    "avg_cost": h['avg_cost']} for h in state['holdings']],
            "reflection": judge_out.get("reflection"),
            "market_read": judge_out.get("market_read"),
            "gap_analysis": judge_out.get("gap_analysis"),
            "addresses_bear_case": judge_out.get("addresses_bear_case"),
            "trades": trades,
            "execution_results": [{"ticker": t.get("ticker"), "action": t.get("action"),
                                    "shares": t.get("shares"), "result": r}
                                    for t, r in exec_results],
            "watchlist": judge_out.get("watchlist", []),
            "patterns_noted": judge_out.get("patterns_noted"),
            "uncertainty_inventory": judge_out.get("uncertainty_inventory", []),
            "expected_direction": judge_out.get("expected_portfolio_direction"),
            "cost_usd": round(cost_total, 4),
            "flagged_triggers": _flagged_triggers,
            "dry_run": args.dry_run,
            "observe_only": args.observe_only,
        }
        if not args.dry_run:
            append_journal(entry)

        # Output JSON for dashboard
        save_dashboard_json(judge_out, bull_text, bear_text, total_value, state, exec_results, cost_total)

        # Persist intraday triggers for the watcher to pick up.
        # Guarded against --dry-run because the pending state file is a real side effect
        # that the live watcher cron will pick up at its next poll (bug observed June 10).
        if not args.dry_run:
            try:
                pending_state = {
                    "date": today_iso,
                    "fires_today": 0,
                    "max_fires": 6,
                    "triggers": [{**t, "status": "armed"} for t in _all_triggers if t.get("id")],
                    "last_news_check": None,
                }
                pending_path = Path.home() / "bigclaw-ai" / "data" / "llm_pending_triggers.json"
                pending_path.parent.mkdir(parents=True, exist_ok=True)
                pending_path.write_text(json.dumps(pending_state, indent=2))
                log(f"Persisted {len(pending_state['triggers'])} intraday trigger(s) to {pending_path}")
            except Exception as e:
                log(f"Trigger persistence failed: {e}", "WARN")
        else:
            log(f"DRY RUN — skipping trigger persistence ({len(judge_out.get('intraday_triggers', []) or [])} triggers would have been written)")

        # Human-readable per-cycle Markdown for Curtis to browse
        try:
            save_decision_markdown(today_iso, total_value, state, market, news, peer_returns,
                                    bull_text, bear_text, judge_out, exec_results,
                                    cost_total, cycle_duration,
                                    bull_dt=round(bull_dt, 1) if bull_dt else None,
                                    bear_dt=round(bear_dt, 1) if bear_dt else None,
                                    judge_dt=round(judge_dt, 1) if judge_dt else None,
                                    cycle_name=args.cycle)
            log(f"Decision Markdown written to {DECISIONS_DIR}/{today_iso}-{args.cycle}.md")
        except Exception as e:
            log(f"Decision Markdown write failed: {e}", "WARN")

        # Slack summary
        slack_text = (f"🤖 *LLM-ETF Focus* — {today_iso}\n"
                      f"Portfolio: ${total_value:,.2f} ({(total_value/state['starting_cash']-1)*100:+.2f}% from start)  "
                      f"Cash: ${state['current_cash']:,.2f}\n"
                      f"Trades decided: {len(trades)}  Executed: {executed}  Skipped: {skipped}\n"
                      f"Cycle cost: ${cost_total:.4f}\n\n"
                      f"*Market read:* {judge_out.get('market_read','')[:400]}\n\n"
                      f"*Reflection:* {judge_out.get('reflection','')[:400]}\n")
        if trades:
            slack_text += "\n*Trades:*\n"
            for t in trades:
                slack_text += f"  • {t.get('action','').upper()} {t.get('shares')} {t.get('ticker')} — {t.get('rationale','')[:150]}\n"
                if t.get('exit_thesis'):
                    slack_text += f"      exit: {t.get('exit_thesis')[:150]}\n"
        if judge_out.get('watchlist'):
            slack_text += f"\n*Watchlist:* {', '.join(judge_out['watchlist'][:10])}\n"
        if args.dry_run:
            slack_text = "[DRY RUN] " + slack_text

        if not args.dry_run:
            try: post_slack(args.channel, slack_text, secrets)
            except Exception as e: log(f"Slack post failed: {e}", "WARN")
        else:
            print("\n=== DRY RUN OUTPUT ===\n" + slack_text)

        if FAILURE_FLAG.exists():
            FAILURE_FLAG.unlink()
        log("LLM portfolio cycle complete.")

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        log(f"FATAL: {e}\n{tb}", "ERROR")
        write_failure_flag(f"{type(e).__name__}: {e}")
        sys.exit(1)
    finally:
        release_lock()


if __name__ == "__main__":
    main()
