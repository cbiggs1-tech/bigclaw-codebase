#!/usr/bin/env python3
"""Weekly Sector Rotation Report - native BigClaw Python.

Synthesizes sector/factor ETF performance + per-holding P&L + multi-source news
(Alpaca/Benzinga, CNBC RSS, Reuters via Google News) into an actionable rotation
report. Posts to Slack via slack_sdk.

Designed to run weekly on Sunday afternoon. Cost: ~$0.04/run. Data sources free.
No information from this report should drive trades during the validation window.

Usage:
    sector_rotation.py                  # production: gather, synthesize, post Slack
    sector_rotation.py --dry-run        # stdout only
    sector_rotation.py --channel CXXX   # override target channel
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

DEFAULT_CHANNEL = "D0ADHLUJ400"
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4000
LLM_TIMEOUT_SECONDS = 120.0
LOCK_FILE = Path("/tmp/sector_rotation.lock")
FAILURE_FLAG = Path.home() / "bigclaw-ai" / "logs" / "SECTOR_ROTATION_FAILED.flag"
LLM_LOG = Path.home() / "bigclaw-ai" / "logs" / "llm_calls.jsonl"
OUTPUT_JSON = Path.home() / "bigclaw-ai" / "docs" / "data" / "sector_rotation.json"

SECTOR_ETFS = {
    'XLK': 'Technology', 'XLF': 'Financials', 'XLE': 'Energy', 'XLV': 'Healthcare',
    'XLI': 'Industrials', 'XLP': 'Cons. Staples', 'XLY': 'Cons. Discretionary',
    'XLB': 'Materials', 'XLU': 'Utilities', 'XLRE': 'Real Estate', 'XLC': 'Comm. Services',
}
FACTOR_ETFS = {'IWM': 'Small Cap', 'MTUM': 'Momentum', 'QUAL': 'Quality',
               'USMV': 'Low Vol', 'IWN': 'Small Value'}
CNBC_FEEDS = {
    'Top News':   'https://www.cnbc.com/id/100003114/device/rss/rss.html',
    'Markets':    'https://www.cnbc.com/id/10000664/device/rss/rss.html',
    'Business':   'https://www.cnbc.com/id/10001147/device/rss/rss.html',
    'Earnings':   'https://www.cnbc.com/id/15839135/device/rss/rss.html',
}
REUTERS_QUERIES = ['site:reuters.com markets', 'site:reuters.com business',
                   'site:reuters.com earnings']

SYSTEM_PROMPT = """You are a senior portfolio analyst writing a weekly sector rotation report
for a multi-portfolio model run by a sophisticated investor. The reader knows the basics.

Your job:
1. Identify which SECTORS rotated IN (top 3) and OUT (top 3) over the last 5 days, with a
   one-sentence driver for each — cite specific data (returns, news, factor moves).
2. Identify any FACTOR rotation (growth vs value, small vs large, momentum vs defensive).
   Use TLT and UUP context for macro framing.
3. For each PORTFOLIO, give a 1-2 sentence read on what's driving the P&L mix — point to
   specific holdings and the news/sector context driving them.
4. Flag 2-3 specific positions where the news + sector context suggests near-term action.
5. Note 1-2 DIVERGENCES worth watching.

Keep total length under 750 words. Cite news source (Benzinga/CNBC/Reuters) when news is
the basis for a call. Format for Slack: use *bold* section headers, simple bullets, emoji
sparingly. Do NOT recommend specific trades — flag observations only. The reader is in a
validation window and will not act on this report's recommendations."""


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
                log(f"Already running as PID {pid} — aborting", "WARN")
                sys.exit(1)
            except ProcessLookupError:
                log(f"Stale lock from PID {pid} — reclaiming", "WARN")
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

def log_llm_call(model, in_tok, out_tok, cost, duration):
    try:
        LLM_LOG.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "script": "sector_rotation.py",
            "model": model, "input_tokens": in_tok, "output_tokens": out_tok,
            "cost_usd": round(cost, 4), "duration_sec": round(duration, 1),
        }
        with LLM_LOG.open("a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception as e:
        log(f"llm_log write failed: {e}", "WARN")


# ---------- data gathering ----------
def gather_holdings_and_etfs(secrets):
    conn = sqlite3.connect(Path.home() / "bigclaw-ai/src/portfolios.db", timeout=10)
    conn.row_factory = sqlite3.Row
    holdings = conn.execute("""
        SELECT p.name AS portfolio, h.ticker, h.shares, h.avg_cost
        FROM holdings h JOIN portfolios p ON h.portfolio_id = p.id
        WHERE p.is_active = 1 AND h.shares > 0
        ORDER BY p.name, h.ticker
    """).fetchall()
    conn.close()
    tickers = sorted({r['ticker'] for r in holdings})
    all_etfs = list(SECTOR_ETFS) + list(FACTOR_ETFS) + ['SPY', 'TLT', 'UUP']
    universe = list(set(tickers + all_etfs))
    hist = yf.download(universe, period='3mo', progress=False, threads=True)['Close']
    return holdings, tickers, hist

def ret(hist, t, n):
    try:
        if t not in hist.columns or len(hist[t]) < n + 1: return None
        return float(hist[t].iloc[-1] / hist[t].iloc[-n-1] - 1) * 100
    except Exception:
        return None

def gather_alpaca_news(tickers, secrets):
    from alpaca.data.historical.news import NewsClient
    from alpaca.data.requests import NewsRequest
    client = NewsClient(api_key=secrets['ALPACA_API_KEY'],
                        secret_key=secrets['ALPACA_SECRET_KEY'])
    start = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=2)
    out = {}
    total = 0
    for i in range(0, len(tickers), 20):
        batch = tickers[i:i+20]
        try:
            r = client.get_news(NewsRequest(symbols=",".join(batch),
                                             start=start, limit=50))
            items = []
            if hasattr(r, 'data') and isinstance(r.data, dict):
                for v in r.data.values():
                    items.extend(v if isinstance(v, list) else [v])
            for item in items:
                for sym in (getattr(item, 'symbols', None) or []):
                    if sym in batch:
                        out.setdefault(sym, []).append({
                            'time': item.created_at.isoformat()[:16],
                            'headline': item.headline,
                        })
                        total += 1
        except Exception as e:
            log(f"Alpaca news batch {i} error: {e}", "WARN")
    for sym in out:
        out[sym] = sorted(out[sym], key=lambda x: x['time'], reverse=True)[:4]
    return out, total

def gather_cnbc():
    items = []
    for name, url in CNBC_FEEDS.items():
        try:
            f = feedparser.parse(url)
            for e in f.entries[:15]:
                items.append({
                    'source': f'CNBC {name}',
                    'headline': e.get('title', ''),
                })
        except Exception as e:
            log(f"CNBC {name} error: {e}", "WARN")
    return items

def gather_reuters():
    items = []
    for q in REUTERS_QUERIES:
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}&hl=en-US&gl=US"
        try:
            f = feedparser.parse(url)
            for e in f.entries[:10]:
                items.append({
                    'source': e.get('source', {}).get('title', 'Reuters'),
                    'headline': e.get('title', ''),
                })
        except Exception as e:
            log(f"Reuters query '{q}' error: {e}", "WARN")
    return items


# ---------- prompt builder ----------
def build_prompt(holdings, tickers, hist, news_per_ticker, cnbc_items, reuters_items):
    def fmt(x):
        return f"{x:+.1f}%" if x is not None else "n/a"

    spy_5d = ret(hist, 'SPY', 5)
    sector_lines = []
    for t, name in SECTOR_ETFS.items():
        r1, r5, r30 = ret(hist,t,1), ret(hist,t,5), ret(hist,t,30)
        rel = (r5 - spy_5d) if (r5 is not None and spy_5d is not None) else None
        sector_lines.append((t, name, r1, r5, r30, rel))
    sector_lines.sort(key=lambda x: -(x[3] or -99))

    # holdings P&L
    prices_now = {t: float(hist[t].iloc[-1]) for t in tickers
                  if t in hist.columns and hist[t].iloc[-1] == hist[t].iloc[-1]}
    by_pf = {}
    for r in holdings:
        pl = (prices_now[r['ticker']] / r['avg_cost'] - 1) * 100 if prices_now.get(r['ticker']) else None
        by_pf.setdefault(r['portfolio'], []).append({
            'ticker': r['ticker'], 'avg_cost': r['avg_cost'],
            'current': prices_now.get(r['ticker']), 'pl_pct': pl,
        })

    prompt = "## Portfolio Holdings (P&L from cost basis)\n\n"
    for pf, hs in by_pf.items():
        prompt += f"**{pf}**:\n"
        for h in sorted(hs, key=lambda x: x['pl_pct'] or 0):
            prompt += f"  - {h['ticker']:<6s} {fmt(h['pl_pct'])} (${h['avg_cost']:.2f} → ${h['current'] or 0:.2f})\n"
        prompt += "\n"

    prompt += "## Sector ETF performance\n\n"
    prompt += f"{'ETF':<5s} {'Sector':<22s} {'1d':>7s} {'5d':>7s} {'30d':>7s} {'5d-SPY':>8s}\n"
    for t, name, r1, r5, r30, rel in sector_lines:
        prompt += f"{t:<5s} {name:<22s} {fmt(r1):>7s} {fmt(r5):>7s} {fmt(r30):>7s} {fmt(rel):>8s}\n"
    prompt += f"SPY   S&P 500                {fmt(ret(hist,'SPY',1)):>7s} {fmt(ret(hist,'SPY',5)):>7s} {fmt(ret(hist,'SPY',30)):>7s}\n"
    prompt += f"TLT   Long Treasuries        {fmt(ret(hist,'TLT',1)):>7s} {fmt(ret(hist,'TLT',5)):>7s} {fmt(ret(hist,'TLT',30)):>7s}\n"
    prompt += f"UUP   USD                    {fmt(ret(hist,'UUP',1)):>7s} {fmt(ret(hist,'UUP',5)):>7s} {fmt(ret(hist,'UUP',30)):>7s}\n"

    prompt += "\n## Factor ETF performance\n\n"
    for t, name in FACTOR_ETFS.items():
        prompt += f"  {t:<6s} {name:<14s} 1d={fmt(ret(hist,t,1))} 5d={fmt(ret(hist,t,5))} 30d={fmt(ret(hist,t,30))}\n"

    prompt += "\n## Per-holding news (Alpaca/Benzinga, last 2 days)\n\n"
    for sym in sorted(tickers):
        items = news_per_ticker.get(sym, [])
        if not items: continue
        prompt += f"**{sym}**:\n"
        for n in items:
            prompt += f"  - [{n['time']}] {n['headline']}\n"
        prompt += "\n"

    prompt += "\n## Broad market headlines (CNBC)\n\n"
    for n in cnbc_items[:30]:
        prompt += f"  - [{n['source']}] {n['headline']}\n"

    prompt += "\n## Broad market headlines (Reuters)\n\n"
    for n in reuters_items[:25]:
        prompt += f"  - [{n['source']}] {n['headline']}\n"

    return prompt


# ---------- LLM ----------
def call_llm(prompt, secrets):
    client = anthropic.Anthropic(api_key=secrets['ANTHROPIC_API_KEY'],
                                 timeout=LLM_TIMEOUT_SECONDS)
    t0 = time.time()
    resp = client.messages.create(
        model=MODEL, max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    dt = time.time() - t0
    text = resp.content[0].text
    in_tok, out_tok = resp.usage.input_tokens, resp.usage.output_tokens
    cost = (in_tok * 3.0 + out_tok * 15.0) / 1_000_000
    log_llm_call(MODEL, in_tok, out_tok, cost, dt)
    log(f"LLM ok: in={in_tok} out={out_tok} cost=${cost:.4f} t={dt:.1f}s")
    return text, cost


# ---------- output ----------
def post_slack(channel, text, secrets):
    client = WebClient(token=secrets['SLACK_BOT_TOKEN'])
    chunks = []
    for i in range(0, len(text), 38000):
        chunks.append(text[i:i+38000])
    for i, c in enumerate(chunks):
        prefix = "" if i == 0 else f"_(part {i+1}/{len(chunks)})_\n\n"
        client.chat_postMessage(channel=channel, text=prefix + c)
    log(f"Posted to Slack channel={channel}")

def save_json(text, cost):
    try:
        OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_JSON.write_text(json.dumps({
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "model": MODEL,
            "cost_usd": round(cost, 4),
            "report_markdown": text,
        }, indent=2))
        log(f"Wrote {OUTPUT_JSON}")
    except Exception as e:
        log(f"Could not write JSON: {e}", "WARN")


# ---------- main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--channel", default=DEFAULT_CHANNEL)
    ap.add_argument("--test-prefix", action="store_true")
    args = ap.parse_args()

    acquire_lock()
    try:
        log("Sector rotation report — starting")
        secrets = load_secrets()
        for k in ("ANTHROPIC_API_KEY", "ALPACA_API_KEY", "ALPACA_SECRET_KEY", "SLACK_BOT_TOKEN"):
            if k not in secrets:
                write_failure_flag(f"missing secret: {k}")
                sys.exit(1)

        log("Gathering ETF + holdings data...")
        holdings, tickers, hist = gather_holdings_and_etfs(secrets)
        log(f"  {len(tickers)} held tickers, {len(holdings)} positions")

        log("Gathering Alpaca/Benzinga news...")
        news, n_total = gather_alpaca_news(tickers, secrets)
        log(f"  {n_total} articles, {len(news)}/{len(tickers)} tickers covered")

        log("Gathering CNBC RSS...")
        cnbc = gather_cnbc()
        log(f"  {len(cnbc)} CNBC headlines")

        log("Gathering Reuters via Google News...")
        reuters = gather_reuters()
        log(f"  {len(reuters)} Reuters headlines")

        prompt = build_prompt(holdings, tickers, hist, news, cnbc, reuters)
        log(f"Prompt size: {len(prompt)} chars")

        log("Calling Claude...")
        text, cost = call_llm(prompt, secrets)

        header = f"📊 *Sector Rotation Report* — {datetime.date.today().strftime('%a %b %d %Y')}\n"
        header += f"_Sources: Benzinga ({n_total} articles, {len(news)}/{len(tickers)} tickers) + CNBC ({len(cnbc)}) + Reuters ({len(reuters)}); cost ${cost:.4f}_\n"
        header += "_Validation-window note: observations only — no trades from this report._\n\n"
        body = ("[TEST] " if args.test_prefix else "") + header + text

        if args.dry_run:
            log("DRY RUN — would post:")
            print("\n" + "="*78)
            print(body)
            print("="*78)
        else:
            post_slack(args.channel, body, secrets)
            save_json(body, cost)
            if FAILURE_FLAG.exists():
                FAILURE_FLAG.unlink()

        log("Sector rotation report delivered successfully")
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
