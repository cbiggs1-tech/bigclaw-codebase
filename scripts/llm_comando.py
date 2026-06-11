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
PORTFOLIO_NAME = "LLM-Comando"
DEFAULT_CHANNEL = "D0ADHLUJ400"
MODEL_BULL = "claude-sonnet-4-6"
MODEL_BEAR = "claude-sonnet-4-6"
MODEL_JUDGE = "claude-sonnet-4-6"
MAX_TOKENS_DEBATE = 3000     # bull / bear each
MAX_TOKENS_JUDGE = 4000
LLM_TIMEOUT = 120.0

# Safety rails (Curtis's minimum)
CATASTROPHIC_DRAWDOWN_FLOOR = 50_000.0   # USD - freeze if portfolio drops below

LOCK_FILE = Path("/tmp/llm_comando.lock")
FAILURE_FLAG = Path.home() / "bigclaw-ai" / "logs" / "LLM_COMANDO_FAILED.flag"
DRAWDOWN_FLAG = Path.home() / "bigclaw-ai" / "logs" / "LLM_COMANDO_DRAWDOWN_FREEZE.flag"
LLM_LOG = Path.home() / "bigclaw-ai" / "logs" / "llm_calls.jsonl"
JOURNAL = Path.home() / "bigclaw-ai" / "data" / "llm_comando_journal.jsonl"
OUTPUT_JSON = Path.home() / "bigclaw-ai" / "docs" / "data" / "llm_comando_portfolio.json"
DECISIONS_DIR = Path.home() / "bigclaw-ai" / "data" / "llm_comando_decisions"
DB_PATH = Path.home() / "bigclaw-ai" / "src" / "portfolios.db"

SECTOR_ETFS = ['XLK', 'XLF', 'XLE', 'XLV', 'XLI', 'XLP', 'XLY', 'XLB', 'XLU', 'XLRE', 'XLC']
FACTOR_ETFS = ['IWM', 'MTUM', 'QUAL', 'USMV', 'IWN']
MACRO_ETFS  = ['SPY', 'TLT', 'UUP', 'GLD', 'USO']


# ---------- ETF blacklist (LLM-Comando is single-stock by mandate) ----------
ETF_BLACKLIST = {
    # Broad index
    'SPY', 'QQQ', 'DIA', 'VOO', 'VTI', 'VEA', 'VWO',
    # Sector SPDRs
    'XLK', 'XLF', 'XLE', 'XLV', 'XLI', 'XLP', 'XLY', 'XLB', 'XLU', 'XLRE', 'XLC',
    # Industry / theme
    'SOXX', 'SMH', 'KRE', 'IGV', 'XHB', 'ITB', 'XME', 'XOP', 'XBI', 'IBB',
    'ARKK', 'ARKW', 'ARKQ', 'ARKG', 'ARKF', 'ARKX', 'VNQ', 'VYM', 'VTV', 'VUG',
    # Factor / smart-beta
    'IWM', 'IWN', 'IWO', 'IWP', 'IWB', 'IWS', 'IWD', 'IWF',
    'MTUM', 'QUAL', 'USMV', 'VLUE', 'SIZE', 'SPLV',
    # Bond / macro
    'TLT', 'IEF', 'SHY', 'BND', 'AGG', 'LQD', 'HYG', 'JNK',
    'UUP', 'GLD', 'SLV', 'USO', 'BNO', 'UNG',
}

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
    universe = SECTOR_ETFS + FACTOR_ETFS + MACRO_ETFS
    hist = yf.download(universe, period='3mo', progress=False, threads=True)['Close']
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
            }
        except Exception:
            pass
    return out


def discover_news_makers(secrets, top_n=30, hours_back=24):
    """Pull general Benzinga/Alpaca news (no symbol filter) and rank tickers
    by mention count over the last `hours_back` hours. Returns top_n most-
    mentioned tickers — "what the market is talking about today" — which is
    the right discovery surface for an LLM that reasons on citable catalysts.
    Filters out broad-market ETFs and non-stock symbols."""
    from alpaca.data.historical.news import NewsClient
    from alpaca.data.requests import NewsRequest
    from collections import Counter
    client = NewsClient(api_key=secrets['ALPACA_API_KEY'],
                        secret_key=secrets['ALPACA_SECRET_KEY'])
    start = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=hours_back)
    items = []
    try:
        next_token = None
        for _ in range(5):  # up to 5 pages * 50 = 250 items
            req = NewsRequest(start=start, limit=50)
            if next_token:
                req.page_token = next_token
            r = client.get_news(req)
            if hasattr(r, 'data') and isinstance(r.data, dict):
                for v in r.data.values():
                    items.extend(v if isinstance(v, list) else [v])
            next_token = getattr(r, 'next_page_token', None)
            if not next_token:
                break
    except Exception as e:
        log(f"news_makers discovery failed: {e}", "WARN")
        return []
    # Reuse the module-level ETF_BLACKLIST (Comando is single-stock — ETFs are wasted slots)
    cnt = Counter()
    for item in items:
        for sym in (getattr(item, 'symbols', None) or []):
            if sym and 1 < len(sym) <= 5 and sym.isalpha() and sym not in ETF_BLACKLIST:
                cnt[sym] += 1
    log(f"  news_makers scan: {len(items)} items, {len(cnt)} unique tickers mentioned")
    return [t for t, _ in cnt.most_common(top_n)]


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
def build_state_context(state, total_value, market, news, journal, peer_returns, today_iso):
    lines = []
    lines.append(f"## TODAY: {today_iso}")
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
    else:
        lines.append("\n## YOUR JOURNAL: empty (this is your first cycle)")

    return "\n".join(lines)


BULL_SYSTEM = """You are the BULL agent in a 3-agent dialectical trading decision system.

Your job: For each candidate trade opportunity in today's data, build the strongest possible
case FOR the trade. Be aggressive. Look for asymmetric upside. Find what other traders might
be missing. Identify catalysts, technical setups, sentiment shifts, sector momentum, or
mean-reversion opportunities.

ANTI-CHEATING:
- Your training data ends January 2026. Today is provided in the data. Trust ONLY the data feed.
- Every factual claim must be cited from the data feed. Saying "Apple announced X" without it
  appearing in the news feed is hallucination.
- Every thesis must reference specific data: a sector move, a headline, a P&L pattern, a divergence.

STRATEGY MANDATE — INDIVIDUAL STOCKS ONLY, NEVER ETFs:
This portfolio is specifically designed for individual single-stock picks. ETFs (XLK, XLV, XLF, SPY,
IWM, MTUM, USMV, etc.) are NOT acceptable candidates except in genuine hedging cases. Look for
named single-stock theses backed by company-specific catalysts: earnings beats/misses, analyst
upgrades, product launches, regulatory events, insider buying, news-driven price action, M&A,
guidance changes. The data feed includes per-ticker news from Benzinga for an expanded candidate
universe — use it aggressively. If you only see a sector theme but cannot identify a specific
named stock to express it, say so honestly and recommend cash. Defaulting to ETFs is analytical
laziness and is forbidden.

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

Your job: Read the BULL agent's case, then build the strongest possible case AGAINST each
bull thesis. Be skeptical. Look for counter-evidence. Find hidden risks. Argue why each
trade is wrong, late, or already priced in. Identify what the bull missed.

ANTI-CHEATING:
- Your training data ends January 2026. Today is provided in the data. Trust ONLY the data feed.
- Every factual claim must be cited from the data feed.
- Don't be contrarian for its own sake - if a bull thesis is genuinely strong and you cannot
  find weakness, say so honestly. The JUDGE needs your real assessment, not theatrical opposition.

ETF VETO:
If the Bull proposed any ETF candidate, you must veto it outright and identify which specific stock
within the basket would express the thesis with better asymmetry. Name the specific stock and argue
why the basket is inferior (greater idiosyncratic upside, cleaner catalyst, better risk/reward).
If the Bull defaulted to ETFs because they couldn't identify a specific name, call out the lazy
reasoning and recommend cash instead.

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

ANTI-CHEATING (these are mechanical, you will be checked):
- Every factual claim cited from the data feed only
- Every ticker must be a real ticker (verified before trade submits)
- Cannot spend more cash than current_cash provided
- No hallucinated news, analysts, or earnings

YOUR FEEDBACK LOOP: Each cycle you read your journal. The exit_thesis field on each past
trade tells you whether your prediction came true. Patterns of wrong predictions should
change your behavior. Don't just keep doing what didn't work.

YOUR GOAL: Beat SPY and beat the 7 rule-based BigClaw portfolios over the next weeks BY PICKING INDIVIDUAL STOCKS.

STRICT STOCK PREFERENCE — NEVER DEFAULT TO ETFs:
This portfolio is the LLM-Comando experiment: individual-stock theses ONLY. ETFs (any ticker starting
with X- or factor ETFs like MTUM/QUAL/USMV/IWM) must NOT appear in your trades unless you have an
extraordinary explicit hedging rationale. If the Bear successfully argued for a specific stock within
an ETF basket, take that specific stock. If you find yourself reaching for an ETF, hold cash and watch
instead. Cash is a position. Lazy ETF basket trades are forbidden — the parallel LLM-ETF Focus
portfolio handles those by design.
Short-term focus (1-day to 1-week horizon mostly). Quick profits OK. Cutting losses OK.
Holding cash OK if no high-conviction opportunities.

YOU MUST PRODUCE STRICT JSON. NO PROSE OUTSIDE THE JSON BLOCK.

OUTPUT SCHEMA:
{
  "reflection": "what your journal shows about your past performance and what you'd change",
  "market_read": "your read of next 1-5 days",
  "addresses_bear_case": "specific paragraph addressing the strongest bear counter-arguments",
  "trades": [
    {
      "action": "buy" or "sell",
      "ticker": "AAPL",  // real tradable Alpaca ticker
      "shares": 50,       // positive integer
      "rationale": "specific data-cited reasoning (which catalyst/setup/pattern)",
      "exit_thesis": "specific gain target / stop loss / time-based exit (prose, for the journal)",
      "exit_conditions": {
        "target_pct": 2.0,              // gain target as positive number, e.g. 2.5 = +2.5%; null if none
        "stop_pct": 1.5,                // stop loss as positive number (absolute), e.g. 1.5 = -1.5%; null if none
        "time_exit_date": "YYYY-MM-DD"  // ISO date by which position must close; null if no time exit
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
      "level": 205.0,                   // PRICE only
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

INTRADAY TRIGGERS: You have full freedom to define up to 8 triggers per cycle that may fire later
today. Use them aggressively when you see asymmetric setups: "if NVDA breaks $210 with volume,
add", "if Fed dovishness leaks before FOMC, lever up tech", "if SPY -2% intraday, buy the panic".
A lightweight watcher polls every 5 min during market hours. When any trigger matches, a focused
LLM cycle (you again, with the original intent + current state) decides: execute as planned,
modify, or stand down. Max 6 fires per day across all triggers.

If no trades make sense today, return {"trades": []} and explain in reflection."""


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
    from autonomous_trader import get_trading_client, MISMATCH_FLAG_PATH
    from order_fill import wait_for_fill
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
    holdings_by_ticker = {h['ticker']: h for h in state['holdings']}
    results = []

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

        # HARD ENFORCEMENT: LLM-Comando is single-stock by mandate. Reject any ETF buy.
        if action == 'buy' and ticker in ETF_BLACKLIST:
            log(f"REJECTED ETF buy: {ticker} (LLM-Comando is single-stock only)", "WARN")
            results.append((tr, {"skipped": f"ETF rejected: {ticker} (LLM-Comando is single-stock only)"}))
            continue

        # SELL: must hold enough
        if action == 'sell':
            held = holdings_by_ticker.get(ticker, {}).get('shares', 0)
            if shares > held:
                results.append((tr, {"skipped": f"cannot sell {shares} of {ticker} (hold {held})"}))
                continue

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
            ok = record_trade(
                state['id'], PORTFOLIO_NAME, ticker, action, filled_qty, filled_price, actual_value,
                f"LLM-DIALECTIC: {tr.get('rationale','')[:300]}",
                order_id=str(order.id),
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
                            cost_total, cycle_duration_sec, bull_dt=None, bear_dt=None, judge_dt=None):
    """Human-readable per-cycle file with full reasoning. Browse data/llm_decisions/
       to see Bull / Bear / Decision basis and how it evolves over time."""
    DECISIONS_DIR.mkdir(parents=True, exist_ok=True)
    md = DECISIONS_DIR / f"{today_iso}.md"

    cum = (total_value / state['starting_cash'] - 1) * 100
    spy = market.get('SPY', {})

    lines = [
        f"# LLM-Comando — {today_iso}",
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
        "# LLM-Comando — Decision Journal",
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
    """Drop price triggers whose levels are nonsensical vs current entry.
    For longs (paper account is long-only):
      crosses_below: level in (entry*0.5, entry*0.99) -- stop must be below entry but above wipeout
      crosses_above: level in (entry*1.01, entry*2.0) -- target/add must be above entry but reachable
    Triggers on unheld tickers (watch triggers) pass through unchanged.
    Returns (kept_triggers, [{trigger_id, reason}, ...])."""
    if not triggers:
        return triggers, []
    import sqlite3 as _s
    c = _s.connect(db_path, timeout=10); c.row_factory = _s.Row
    held = {r['ticker']: float(r['avg_cost']) for r in c.execute(
        "SELECT ticker, avg_cost FROM holdings WHERE portfolio_id=? AND shares > 0", (pid,)).fetchall()}
    c.close()
    kept, dropped = [], []
    for tr in triggers:
        if tr.get("type") != "price" or not tr.get("ticker") or tr["ticker"] not in held:
            kept.append(tr); continue
        entry = held[tr["ticker"]]; level = tr.get("level"); op = tr.get("op")
        if level is None or op is None:
            kept.append(tr); continue
        ok, reason = True, ""
        if op == "crosses_below" and not (entry * 0.5 < level < entry * 0.99):
            ok = False
            reason = f"stop {tr['ticker']} crosses_below ${level} (entry ${entry:.2f}) outside ${entry*0.5:.2f}..${entry*0.99:.2f}"
        elif op == "crosses_above" and not (entry * 1.01 < level < entry * 2.0):
            ok = False
            reason = f"target {tr['ticker']} crosses_above ${level} (entry ${entry:.2f}) outside ${entry*1.01:.2f}..${entry*2.0:.2f}"
        if ok:
            kept.append(tr)
        else:
            dropped.append({"trigger_id": tr.get("id"), "reason": reason})
    return kept, dropped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="No Alpaca submits, no Slack post, no DB writes for trades")
    ap.add_argument("--observe-only", action="store_true",
                    help="Run agents but produce strategy doc only - no trade decisions")
    ap.add_argument("--channel", default=DEFAULT_CHANNEL)
    args = ap.parse_args()

    acquire_lock()
    try:
        log("LLM portfolio cycle - starting")
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
        recent_watch = []
        if journal:
            recent_watch = journal[-1].get('watchlist', [])[:15] if isinstance(journal[-1].get('watchlist'), list) else []

        # LLM-Comando discovery: top news-mentioned tickers in the last 24h.
        # The LLM reasons on citable catalysts — rank candidates by news volume,
        # not price movement (Curtis 2026-06-11: "News is information. A stock
        # moving with no news, the LLM can't sort out logically anyway").
        news_makers = discover_news_makers(secrets, top_n=30, hours_back=24)
        if news_makers:
            log(f"  Top news-makers (first 10): {news_makers[:10]}")
        else:
            log("  news_makers empty — falling back to held + watchlist only", "WARN")

        news_tickers = sorted(set(held_tickers + recent_watch + news_makers))
        news = get_news(news_tickers, secrets)
        log(f"  Alpaca: {sum(len(v) for v in news['per_ticker'].values())} items for {len(news['per_ticker'])} tickers")
        log(f"  CNBC: {len(news['cnbc'])} | Reuters: {len(news['reuters'])}")

        peer_returns = get_peer_returns()
        today_iso = datetime.date.today().isoformat()
        state_ctx = build_state_context(state, total_value, market, news, journal,
                                         peer_returns, today_iso)
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
        executed = sum(1 for _, r in exec_results if r.get("filled_qty"))
        skipped = sum(1 for _, r in exec_results if "skipped" in r or "error" in r)
        log(f"Executed: {executed}  skipped/errored: {skipped}")

        # Journal entry
        entry = {
            "date": today_iso,
            "portfolio_value_at_decision": round(total_value, 2),
            "cash_at_decision": state['current_cash'],
            "starting_holdings": [{"ticker": h['ticker'], "shares": h['shares'],
                                    "avg_cost": h['avg_cost']} for h in state['holdings']],
            "reflection": judge_out.get("reflection"),
            "market_read": judge_out.get("market_read"),
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
                triggers = judge_out.get("intraday_triggers", []) or []
                triggers, _dropped_triggers = validate_triggers(triggers, str(DB_PATH), state['id'])
                for _d in _dropped_triggers:
                    log(f"DROPPED nonsense trigger {_d['trigger_id']}: {_d['reason']}", "WARN")
                pending_state = {
                    "date": today_iso,
                    "fires_today": 0,
                    "max_fires": 6,
                    "triggers": [{**t, "status": "armed"} for t in triggers if t.get("id")],
                    "last_news_check": None,
                }
                pending_path = Path.home() / "bigclaw-ai" / "data" / "llm_comando_pending_triggers.json"
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
                                    judge_dt=round(judge_dt, 1) if judge_dt else None)
            log(f"Decision Markdown written to {DECISIONS_DIR}/{today_iso}.md")
        except Exception as e:
            log(f"Decision Markdown write failed: {e}", "WARN")

        # Slack summary
        slack_text = (f"🎯 *LLM-Comando* — {today_iso}\n"
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
