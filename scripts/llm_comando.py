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
MODEL_JUDGE = "claude-opus-4-8"  # A/B: Opus on Comando, Sonnet on ETF Focus
MAX_TOKENS_DEBATE = 6000     # bull / bear each (new mandatory Bear priced-in test runs longer; truncated at 3000 on 2026-06-17)
MAX_TOKENS_JUDGE = 8000     # Opus 4.8 + adaptive thinking needs headroom (thinking blocks count toward output)
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
REGIME_TICKERS = ['^VIX', 'HYG', 'LQD', '^TNX', 'IWM']  # vol / HY credit / IG credit / 10y yield / small-cap breadth - macro regime tells


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


def get_candidate_snapshot(tickers):
    """Batch fetch current price + 1d/5d/30d returns for a list of tickers via yfinance.
    Returns {ticker: {price, ret_1d, ret_5d, ret_30d}}. Silent on per-ticker errors —
    partial coverage is better than no coverage. Used for the Candidate Strength Ranking
    block so the LLM can compete held positions against fresh candidates on momentum data."""
    if not tickers:
        return {}
    try:
        hist = yf.download(list(tickers), period='3mo', progress=False, threads=True)['Close']
    except Exception as e:
        log(f"candidate_snapshot fetch failed: {e}", "WARN")
        return {}
    def _ret(series, n):
        try:
            if len(series) < n + 1: return None
            return (float(series.iloc[-1]) / float(series.iloc[-n-1]) - 1) * 100
        except Exception:
            return None
    out = {}
    try:
        if hasattr(hist, 'columns'):
            for t in tickers:
                if t not in hist.columns: continue
                try:
                    v = hist[t].dropna()
                    if len(v) < 2: continue
                    out[t] = {
                        'price': round(float(v.iloc[-1]), 2),
                        'ret_1d': _ret(v, 1),
                        'ret_5d': _ret(v, 5),
                        'ret_30d': _ret(v, 30),
                    }
                except Exception:
                    pass
        elif len(tickers) == 1:
            try:
                v = hist.dropna()
                if len(v) >= 2:
                    out[list(tickers)[0]] = {
                        'price': round(float(v.iloc[-1]), 2),
                        'ret_1d': _ret(v, 1),
                        'ret_5d': _ret(v, 5),
                        'ret_30d': _ret(v, 30),
                    }
            except Exception:
                pass
    except Exception as e:
        log(f"candidate_snapshot parsing failed: {e}", "WARN")
    return out


def get_market_snapshot():
    """Sector ETFs + factor ETFs + macro ETFs - current price + 1d/5d/30d returns."""
    universe = SECTOR_ETFS + FACTOR_ETFS + MACRO_ETFS + REGIME_TICKERS
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
    return dict(cnt.most_common(top_n))


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
def build_state_context(state, total_value, market, news, journal, peer_returns, today_iso, candidate_snapshot=None, news_maker_counts=None, cycle_name=None):
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
        _reg.append(f"  VIX {_vix['price']:.1f}  (5d {_vix.get('ret_5d') or 0:+.0f}%, 30d {_vix.get('ret_30d') or 0:+.0f}%) - vol/fear gauge")
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

    if candidate_snapshot:
        # CANDIDATE STRENGTH RANKING: the "compete" view. Held positions ranked
        # against fresh news-mentioned candidates by news intensity (24h count)
        # + momentum (1d/5d returns). Use this for the "others look better"
        # half of the sell rule. A held position with 0 news mentions next to
        # a candidate with 8 mentions and stronger momentum is a rotation signal.
        held_tickers = {h["ticker"] for h in state["holdings"]}
        held_lookup = {h["ticker"]: h for h in state["holdings"]}
        news_counts = news_maker_counts or {}
        per_ticker_news = news.get("per_ticker", {})

        # Assemble rows: held positions always shown, plus all snapshot tickers
        all_tickers = set(candidate_snapshot.keys()) | held_tickers
        rows = []
        for t in all_tickers:
            snap = candidate_snapshot.get(t, {})
            news_n = news_counts.get(t, 0)
            held = t in held_tickers
            h = held_lookup.get(t, {})
            latest = ""
            if t in per_ticker_news and per_ticker_news[t]:
                latest = per_ticker_news[t][0].get("headline", "")[:60]
            rows.append({
                "ticker": t, "held": held, "snap": snap, "news_n": news_n,
                "shares": h.get("shares"), "entry": h.get("avg_cost"),
                "unr_pct": h.get("unrealized_pl_pct"), "latest": latest,
            })
        # Sort: held first (so they're always visible at top regardless of news count),
        # then by news mention count desc, then by 1d return desc
        rows.sort(key=lambda r: (
            0 if r["held"] else 1,
            -(r["news_n"] or 0),
            -(r["snap"].get("ret_1d") or 0.0),
        ))

        lines.append(f"\n## CANDIDATE STRENGTH RANKING — held + news-makers ({len(rows)} tickers)")
        lines.append("This is your COMPETE view. Use it for the \"others look better\" half of your sell rule:")
        lines.append("  - Held position with low news intensity vs candidate with high intensity = rotation signal")
        lines.append("  - Held position dragging vs candidates rallying today = consider rotating to capture better short-term move")
        lines.append("  - Your goal is short-term gains; a thesis you bought 2 hours ago can weaken if news shifts")
        lines.append("")
        lines.append("  ★=held   ticker     shares  entry      current   1d      5d      30d     news#  latest_headline")
        for r in rows[:40]:  # cap at 40 to keep context manageable
            star = "★" if r["held"] else " "
            shares = f"{int(r['shares']):>4d}" if r.get("shares") else "   -"
            entry = f"${r['entry']:>7.2f}" if r.get("entry") else "      -"
            snap = r["snap"]
            price = f"${snap.get('price', 0):>7.2f}" if snap else "      -"
            def fmt_r(v): return f"{v:>+5.1f}%" if v is not None else "   n/a"
            r1 = fmt_r(snap.get("ret_1d")) if snap else "    -"
            r5 = fmt_r(snap.get("ret_5d")) if snap else "    -"
            r30 = fmt_r(snap.get("ret_30d")) if snap else "    -"
            news_n = f"{r['news_n']:>3d}" if r["news_n"] else "  -"
            unr_marker = f" ({r['unr_pct']:+.1f}% unrlz)" if r.get("unr_pct") is not None else ""
            line = f"  {star} {r['ticker']:<6s}  {shares}    {entry}  {price}  {r1}  {r5}  {r30}  {news_n}    {r['latest'][:55]}"
            if unr_marker:
                line += unr_marker
            lines.append(line)

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

A true fact is NOT a tradeable fact. For EACH surviving Bull thesis you must run the
ALREADY-PRICED-IN test and state the result explicitly:
  (1) FRESHNESS - When did this catalyst become public? An MOU signed yesterday, an oil
      move that already happened, a headline from a prior session - the market has already
      seen it. A catalyst the tape has digested is a day-trader's enemy, not a tailwind.
  (2) PRICE REACTION - Has the stock already moved in the catalyst's direction? Check the
      market_snapshot and Candidate Strength Ranking. If price has already run on this news,
      the edge is gone: entering now is CHASING the reaction, not trading the catalyst.
      Say so, and argue reject.
  (3) DURABILITY - Is the driver durable or reflexive? Catalysts that depend on an unstable
      situation holding (war-scene oil spikes, headline-driven macro moves) can reverse on
      the next headline. Do NOT extrapolate a fluid situation forward; discount it.
A thesis that is true but already priced in, or that rests on a reflexive driver, has a
DISQUALIFYING weakness - argue the trade should be rejected, not taken late.

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

YOUR FIRST MOVE IS NOT TO ADJUDICATE - IT IS TO FIND THE GAP. The Bull and Bear are both
advocates; each argues inside the frame it was handed, and a coherent debate between two
advocates can be collectively blind to the question neither thought to raise. You are the
only seat that can see what the debate structurally cannot, and THAT is where your edge
comes from - not from scoring two cases that are both already reflected in the market's price.
Before you weigh Bull against Bear, list what is ABSENT from BOTH cases that would change
this decision. For every proposed entry you MUST answer, independently of whether either
side raised it:
  - Is the catalyst already in the price? Has the stock already moved on it? If so, taking
    the long now is chasing a played-out reaction - reject or heavily discount.
  - Is the driver durable or reflexive? What must STAY true for this to work, and how
    fragile is that condition?
  - What is the single thing that, if you are honest, would make this trade wrong - that
    neither the Bull nor the Bear named?
Only after you have named the shared omissions do you rule. A true-but-stale thesis must
not out-argue an absent-but-decisive question.

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
OBJECTIVE IS ALPHA - risk-adjusted return, not raw profit. Comando doctrine - commando raid:
enter only where there is a real, not-yet-priced-in objective (a hostage to rescue), with a
favorable reward-to-risk asymmetry you can state.

EXIT BY CONVICTION, NOT BY THE CLOCK. Before you sell ANY position you currently hold, ask yourself
ONE question: would I BUY this stock right now, at today's price, or do I prefer another opportunity
available to me? If you would still buy it, HOLD it - do NOT sell a working trade just to lock a
quick gain or because time has passed. If you would NOT buy it now - its thesis has faded, the move
is exhausted, or a clearly better trade is available - SELL it and redeploy into the better one.
That conviction test IS the entire exit rule. Holding time is irrelevant: a trade you would still
buy is held; a trade you would no longer enter is sold. Quick exits still happen on their own,
because a spent momentum move is one you would no longer buy - but the trigger is ALWAYS conviction,
never a timer, and you NEVER churn out of a name you would still buy today.

A name you exit is eligible for fresh re-entry if its edge reappears - re-judged from scratch; no
loyalty to a position and no aversion to one you just sold. Reject the bad quadrant: small reward
for high risk, even if it might close green. A low-conviction trade must beat the money-market rate
or you hold cash instead. Cutting losses fast is good. Holding cash is a valid position when nothing
clears the bar. (Short-window Comando style - NOT buy-and-hold: you do not ride drawdowns for a long
thesis, but you also do not churn out of a trade you would still buy.)

NEWS-DRIVEN DISCOVERY: your candidates are the NEWS-MAKERS - the names being talked about in the last 24h - plus your held positions and watchlist. Every entry MUST rest on a citable, still-playing-out news catalyst. A stock moving on price action alone with no news behind it is a bandwagon, not a thesis - do NOT chase it, no matter how strong the chart looks. Run the news-makers hard through gap-analysis (is the move already priced in? is the catalyst still live or already spent?). If the news set is thin and nothing clears your bar, holding cash is the correct call - do NOT manufacture a trade from price momentum to avoid sitting in cash.

VOLATILITY REGIME: the MACRO REGIME block shows VIX. Use it to size your aggression this cycle. A LOW or falling VIX is a calmer tape where news-backed setups tend to follow through - you can size up modestly and act with more confidence. A HIGH or spiking VIX means whipsaw and failed moves - throttle back: raise the conviction bar, size down, favor cash. Let the volatility regime, not just the individual setup, dial how aggressive you are - but every position still needs its own news-backed catalyst.

YOU MUST PRODUCE STRICT JSON. NO PROSE OUTSIDE THE JSON BLOCK.

OUTPUT SCHEMA:
{
  "reflection": "what your journal shows about your past performance and what you'd change",
  "market_read": "your read of next 1-5 days",
  "gap_analysis": "what BOTH the Bull and Bear missed that affects today's decision. For each proposed entry, explicitly: is the catalyst already priced in? is the driver durable or reflexive? what would make this wrong that neither side named? This is your primary value-add - do not leave it shallow.",
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

INTRADAY TRIGGERS: You have full freedom to define up to 8 triggers per cycle that may fire later
today. Use them aggressively when you see asymmetric setups: "if NVDA breaks $210 with volume,
add", "if Fed dovishness leaks before FOMC, lever up tech", "if SPY -2% intraday, buy the panic".
A lightweight watcher polls every 5 min during market hours. When any trigger matches, a focused
LLM cycle (you again, with the original intent + current state) decides: execute as planned,
modify, or stand down. Max 6 fires per day across all triggers.

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

AUTONOMY (Opus 4.8 model note): you are running unattended in a paper trading
system with no human in the loop. For minor decisions (specific share counts, exact
trigger levels within the bands you choose, naming choices, formatting), pick a
reasonable value and note your reasoning in the rationale — do NOT ask for
clarification, do NOT defer, and do NOT add hedging language like "the user should
decide" or "consider whether to...". You ARE the decision-maker. For scope changes
(new strategy, abandoning a thesis mid-cycle, action outside the documented system),
be deliberate as usual. But on the routine call-the-trade decisions, commit.

If no trades make sense today, return {"trades": []} and explain in reflection.

FLAGGED TRIGGERS — IF YOU SEE THEM IN YOUR JOURNAL: a safety check downstream of you
flags price triggers whose levels are nonsense relative to entry (stop must
be strictly below entry but above entry × 0.5; target must be strictly above entry
and below entry × 2.0). When you see `FLAGGED_TRIGGERS` in a past journal entry, that
was YOU setting absolute dollar levels based on stale training-cutoff price anchors.
For tickers that have moved a lot since 2026-01 (post-IPO names, multi-baggers), the
absolute prices in your training data are not the live prices. Set tight, sensible
levels relative to the entry you're about to take, not the historical price you remember."""


# ---------- agent call ----------
# Per-million-token pricing by model id. Update when models change.
MODEL_PRICING = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-8":   (5.0, 25.0),
    "claude-opus-4-7":   (5.0, 25.0),
    "claude-opus-4-6":   (5.0, 25.0),
    "claude-haiku-4-5":  (1.0, 5.0),
}

def call_agent(client, system, user_message, model, max_tokens, agent_name, thinking=None):
    """Run one agent call. Pass thinking={"type":"adaptive"} for the Judge to enable
    adaptive thinking (recommended on Opus 4.8 for synthesis tasks).
    Cost is computed from MODEL_PRICING; falls back to Sonnet rates if model unknown."""
    t0 = time.time()
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user_message}],
    }
    if thinking is not None:
        kwargs["thinking"] = thinking
    resp = client.messages.create(**kwargs)
    dt = time.time() - t0
    # Extract text — adaptive thinking returns thinking blocks before text;
    # we only want the text content for the prompt-following output.
    text = ""
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            text += block.text
    if not text:
        # Fallback: legacy single-block response
        text = resp.content[0].text if resp.content else ""
    if getattr(resp, 'stop_reason', None) == 'max_tokens':
        log(f"  {agent_name}: TRUNCATED — hit max_tokens ceiling. Output may be incomplete.", "WARN")
    in_tok, out_tok = resp.usage.input_tokens, resp.usage.output_tokens
    in_rate, out_rate = MODEL_PRICING.get(model, (3.0, 15.0))
    cost = (in_tok * in_rate + out_tok * out_rate) / 1_000_000
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
    # Bug observed 2026-06-12: ETF Focus sold XLV (~$53K) then tried to buy
    # IWM + XLK; XLK was skipped despite plenty of total cash because the
    # validator used the pre-cycle cash snapshot.
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

        # HARD ENFORCEMENT: LLM-Comando is single-stock by mandate. Reject any ETF buy.
        if action == 'buy' and ticker in ETF_BLACKLIST:
            log(f"REJECTED ETF buy: {ticker} (LLM-Comando is single-stock only)", "WARN")
            results.append((tr, {"skipped": f"ETF rejected: {ticker} (LLM-Comando is single-stock only)"}))
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
                            cost_total, cycle_duration_sec, bull_dt=None, bear_dt=None, judge_dt=None,
                            cycle_name=None):
    """Human-readable per-cycle file with full reasoning. Browse data/llm_decisions/
       to see Bull / Bear / Decision basis and how it evolves over time."""
    DECISIONS_DIR.mkdir(parents=True, exist_ok=True)
    md = DECISIONS_DIR / (f"{today_iso}-{cycle_name}.md" if cycle_name else f"{today_iso}.md")

    cum = (total_value / state['starting_cash'] - 1) * 100
    spy = market.get('SPY', {})

    lines = [
        f"# LLM-Comando — {today_iso}" + (f" — {cycle_name.upper()} cycle" if cycle_name else ""),
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
        recent_watch = []
        if journal:
            recent_watch = journal[-1].get('watchlist', [])[:15] if isinstance(journal[-1].get('watchlist'), list) else []

        # LLM-Comando discovery: top news-mentioned tickers in the last 24h.
        # The LLM reasons on citable catalysts — rank candidates by news volume,
        # not price movement (Curtis 2026-06-11: "News is information. A stock
        # moving with no news, the LLM can't sort out logically anyway").
        news_maker_counts = discover_news_makers(secrets, top_n=30, hours_back=24)
        news_makers = list(news_maker_counts.keys())
        if news_makers:
            top10 = list(news_maker_counts.items())[:10]
            log(f"  Top news-makers (first 10): " + ", ".join(f"{t}({c})" for t, c in top10))
        else:
            log("  news_makers empty — falling back to held + watchlist only", "WARN")

        news_tickers = sorted(set(held_tickers + recent_watch + news_makers))
        news = get_news(news_tickers, secrets)
        log(f"  Alpaca: {sum(len(v) for v in news['per_ticker'].values())} items for {len(news['per_ticker'])} tickers")
        log(f"  CNBC: {len(news['cnbc'])} | Reuters: {len(news['reuters'])}")

        # Live snapshot for the candidate universe: price + 1d/5d/30d returns.
        # Feeds the Candidate Strength Ranking block so the LLM can compete
        # held positions against fresh candidates on momentum + news intensity.
        candidate_snapshot = get_candidate_snapshot(news_tickers)
        log(f"  Candidate snapshot: {len(candidate_snapshot)}/{len(news_tickers)} tickers priced")

        peer_returns = get_peer_returns()
        today_iso = datetime.date.today().isoformat()
        state_ctx = build_state_context(state, total_value, market, news, journal,
                                         peer_returns, today_iso, candidate_snapshot=candidate_snapshot,
                                         news_maker_counts=news_maker_counts, cycle_name=args.cycle)
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
                                              MODEL_JUDGE, MAX_TOKENS_JUDGE, "judge",
                                              thinking={"type": "adaptive"})

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
                                    judge_dt=round(judge_dt, 1) if judge_dt else None,
                                    cycle_name=args.cycle)
            log(f"Decision Markdown written to {DECISIONS_DIR}/{today_iso}-{args.cycle}.md")
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
