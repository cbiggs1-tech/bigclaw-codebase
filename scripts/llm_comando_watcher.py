#!/usr/bin/env python3
"""LLM Discretionary — Intraday Trigger Watcher.

Runs every 5 minutes during market hours. Checks the pending triggers set by
this morning's Judge against current market state. Fires a focused LLM cycle
when any trigger matches.

Trigger types:
  - price: ticker + (above/below/crosses) + level
  - news:  keyword list (case-insensitive substring match in headline + summary)
  - time:  specific ISO datetime

Daily budget: max 6 trigger-fired LLM cycles. The morning planning cycle
(scripts/llm_portfolio.py at 09:00 CT) counts as separate; this script handles
all intraday adjustments.

Each fired LLM cycle is a SHORTER call (just Judge equivalent, no Bull/Bear)
because the thesis was already formed this morning. The LLM decides: execute
the originally planned action, modify it, or stand down.

Cost: ~$0.05 per fire × 6 max = $0.30/day worst case.
"""
import argparse
import datetime
import json
import os
import re
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

PORTFOLIO_NAME = "LLM-Commando"
DEFAULT_CHANNEL = "D0ADHLUJ400"
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 3000
LLM_TIMEOUT = 90.0
MAX_FIRES_PER_DAY = 100
EXEC_RETRY_CAP = 3  # re-attempt a decided-but-unfilled trade on later polls, up to this many times

PENDING_STATE = Path.home() / "bigclaw-ai" / "data" / "llm_comando_pending_triggers.json"
JOURNAL = Path.home() / "bigclaw-ai" / "data" / "llm_comando_journal.jsonl"
DECISIONS_DIR = Path.home() / "bigclaw-ai" / "data" / "llm_comando_decisions"
LLM_LOG = Path.home() / "bigclaw-ai" / "logs" / "llm_calls.jsonl"
FAILURE_FLAG = Path.home() / "bigclaw-ai" / "logs" / "LLM_COMANDO_WATCHER_FAILED.flag"
LOCK_FILE = Path("/tmp/llm_comando_watcher.lock")
DB_PATH = Path.home() / "bigclaw-ai" / "src" / "portfolios.db"


# ---------- ETF blacklist (LLM-Commando is single-stock by mandate) ----------
ETF_BLACKLIST = {
    # Broad index
    'SPY', 'QQQ', 'DIA', 'VOO', 'VTI', 'VEA', 'VWO',
    # Sector SPDRs
    'XLK', 'XLF', 'XLE', 'XLV', 'XLI', 'XLP', 'XLY', 'XLB', 'XLU', 'XLRE', 'XLC',
    # Industry / theme
    'SOXX', 'SMH', 'KRE', 'IGV', 'XHB', 'ITB', 'XME', 'XOP', 'XBI', 'IBB',
    'ARKK', 'ARKW', 'ARKQ', 'ARKG', 'ARKF', 'VNQ', 'VYM', 'VTV', 'VUG',
    # Factor / smart-beta
    'IWM', 'IWN', 'IWO', 'IWP', 'IWB', 'IWS', 'IWD', 'IWF',
    'MTUM', 'QUAL', 'USMV', 'VLUE', 'SIZE', 'SPLV',
    # Bond / macro
    'TLT', 'IEF', 'SHY', 'BND', 'AGG', 'LQD', 'HYG', 'JNK',
    'UUP', 'GLD', 'SLV', 'USO', 'BNO', 'UNG',
}

CNBC_FEEDS = [
    'https://www.cnbc.com/id/100003114/device/rss/rss.html',
    'https://www.cnbc.com/id/10000664/device/rss/rss.html',
]


def log(msg, level="INFO"):
    print(f"[{datetime.datetime.now(datetime.timezone.utc).isoformat()}] {level} {msg}")

def write_failure_flag(reason):
    try:
        FAILURE_FLAG.parent.mkdir(parents=True, exist_ok=True)
        FAILURE_FLAG.write_text(json.dumps({
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "reason": reason,
        }, indent=2))
    except Exception:
        pass

def acquire_lock():
    if LOCK_FILE.exists():
        try:
            pid = int(LOCK_FILE.read_text().strip())
            try:
                os.kill(pid, 0)
                log(f"Already running PID {pid}, exit", "WARN")
                sys.exit(0)
            except ProcessLookupError:
                pass
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

def log_llm(agent, in_tok, out_tok, cost, dt):
    try:
        LLM_LOG.parent.mkdir(parents=True, exist_ok=True)
        with LLM_LOG.open("a") as f:
            f.write(json.dumps({
                "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "script": "llm_portfolio_watcher.py",
                "agent": agent, "model": MODEL,
                "input_tokens": in_tok, "output_tokens": out_tok,
                "cost_usd": round(cost, 4), "duration_sec": round(dt, 1),
            }) + "\n")
    except Exception:
        pass


# ---------- state ----------
def load_state():
    today_iso = datetime.date.today().isoformat()
    if PENDING_STATE.exists():
        try:
            state = json.loads(PENDING_STATE.read_text())
            if state.get("date") != today_iso:
                # New day - reset fires_today but keep triggers if they're for today
                state["date"] = today_iso
                state["fires_today"] = 0
                state["last_news_check"] = None
                # Drop expired triggers
                today_start = datetime.datetime.combine(
                    datetime.date.today(),
                    datetime.time(0, 0, tzinfo=datetime.timezone.utc),
                )
                state["triggers"] = [
                    t for t in state.get("triggers", [])
                    if (t.get("status") == "armed"
                        and not _expired(t, today_start))
                ]
            return state
        except Exception as e:
            log(f"State load failed: {e} - starting fresh", "WARN")
    return {
        "date": today_iso, "fires_today": 0, "max_fires": MAX_FIRES_PER_DAY,
        "triggers": [], "last_news_check": None,
    }

def save_state(state):
    PENDING_STATE.parent.mkdir(parents=True, exist_ok=True)
    PENDING_STATE.write_text(json.dumps(state, indent=2))

def _expired(trigger, now):
    exp = trigger.get("expires_at")
    if not exp: return False
    try:
        return datetime.datetime.fromisoformat(exp.replace("Z", "+00:00")) <= now
    except Exception:
        return False

SELL_INTENT_WORDS = ("sell", "trim", "stop", "exit", "close", "lighten", "reduce", "cut")

def _is_sell_intent(trigger):
    """Return True if the trigger's action_intent looks like a sell/exit action."""
    intent = (trigger.get("action_intent") or "").lower()
    return any(w in intent for w in SELL_INTENT_WORDS)

def cleanup_obsolete_triggers(state, current_holdings):
    """Mark as obsolete any price-stop trigger referencing a ticker we no longer hold.

    Called both pre-evaluation (catches stale state from earlier today) and post-execution
    (catches triggers made stale by the trade we just did)."""
    held_set = {h["ticker"].upper() for h in current_holdings}
    n_obsoleted = 0
    for trig in state.get("triggers", []):
        if trig.get("status") not in ("armed", "retrying"):
            continue
        ttype = trig.get("type")
        if ttype != "price":
            continue
        ticker = (trig.get("ticker") or "").upper()
        if not ticker:
            continue
        if _is_sell_intent(trig) and ticker not in held_set:
            trig["status"] = "obsolete_position_closed"
            trig["obsoleted_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            n_obsoleted += 1
    return n_obsoleted


# ---------- trigger evaluation ----------
def check_price_trigger(trigger):
    """Returns (matched, evidence_str) or (False, '')."""
    ticker = (trigger.get("ticker") or "").upper()
    op = trigger.get("op", "")
    level = trigger.get("level")
    if not ticker or level is None: return False, ""
    try:
        spot = float(yf.Ticker(ticker).fast_info["lastPrice"])
    except Exception as e:
        return False, f"price fetch failed: {e}"
    if op == "below" and spot <= level:
        return True, f"{ticker} at ${spot:.2f} <= ${level}"
    if op == "above" and spot >= level:
        return True, f"{ticker} at ${spot:.2f} >= ${level}"
    if op in ("crosses", "crosses_below", "crosses_above"):
        # without prior-tick state we treat crosses as "is now past"
        if op == "crosses_below" and spot <= level: return True, f"{ticker} crossed below ${level} (now ${spot:.2f})"
        if op == "crosses_above" and spot >= level: return True, f"{ticker} crossed above ${level} (now ${spot:.2f})"
        if op == "crosses": return True, f"{ticker} crossed ${level} (now ${spot:.2f})"
    return False, ""

def fetch_news_since(since_iso):
    """Pull recent headlines from CNBC RSS + Reuters via Google News.
       Returns list of dicts: {time, source, headline, summary}."""
    since_dt = None
    if since_iso:
        try: since_dt = datetime.datetime.fromisoformat(since_iso.replace("Z", "+00:00"))
        except Exception: pass
    items = []
    # CNBC
    for url in CNBC_FEEDS:
        try:
            f = feedparser.parse(url)
            for e in f.entries[:25]:
                t = e.get("published_parsed")
                if t and since_dt:
                    when = datetime.datetime(*t[:6], tzinfo=datetime.timezone.utc)
                    if when <= since_dt: continue
                items.append({
                    "source": "CNBC",
                    "time": e.get("published", "")[:25],
                    "headline": e.get("title", ""),
                    "summary": re.sub(r'<[^>]+>', '', e.get("summary", ""))[:400],
                })
        except Exception:
            pass
    # Reuters via Google News for breaking-news queries
    for q in ["site:reuters.com Fed", "site:reuters.com Powell", "site:reuters.com markets"]:
        try:
            url = f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}&hl=en-US&gl=US"
            f = feedparser.parse(url)
            for e in f.entries[:10]:
                items.append({
                    "source": e.get("source", {}).get("title", "Reuters"),
                    "time": e.get("published", "")[:25],
                    "headline": e.get("title", ""),
                    "summary": "",
                })
        except Exception:
            pass
    return items

def check_news_trigger(trigger, fresh_items):
    """Returns (matched, list_of_matching_items) or (False, [])."""
    keywords = [k.lower() for k in (trigger.get("keywords") or [])]
    if not keywords or not fresh_items: return False, []
    matched = []
    for item in fresh_items:
        text = (item["headline"] + " " + item.get("summary", "")).lower()
        for kw in keywords:
            if kw in text:
                matched.append(item)
                break
    return (len(matched) > 0), matched[:5]

def check_time_trigger(trigger):
    wake = trigger.get("wake_at")
    if not wake: return False, ""
    try:
        wake_dt = datetime.datetime.fromisoformat(wake.replace("Z", "+00:00"))
        now = datetime.datetime.now(datetime.timezone.utc)
        if now >= wake_dt:
            return True, f"now {now.isoformat()[:16]} >= wake_at {wake}"
    except Exception:
        pass
    return False, ""


# ---------- portfolio state for prompt ----------
def get_portfolio_state():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    pf = conn.execute("SELECT id, current_cash FROM portfolios WHERE name=?",
                      (PORTFOLIO_NAME,)).fetchone()
    h = conn.execute("SELECT ticker, shares, avg_cost FROM holdings WHERE portfolio_id=? AND shares>0",
                     (pf["id"],)).fetchall() if pf else []
    conn.close()
    return pf, [dict(r) for r in h]


# ---------- focused LLM trigger response ----------
TRIGGER_SYSTEM = """You are the LLM Discretionary trader. One or more intraday triggers you set
this morning have fired. You decide what to do for each.

FOR EACH FIRED TRIGGER YOU MUST DECIDE:
- "execute" — execute the action_intent as originally planned (or adapt it lightly)
- "modify"  — execute a different action (the situation evolved beyond your morning plan)
- "stand_down" — the conditions you anticipated don't match reality, don't act

ANTI-CHEATING:
- Every factual claim must cite the data feed below
- Training cutoff is January 2026 - trust ONLY the current state and news provided
- No invented analyst calls, earnings, or events

OUTPUT — STRICT JSON, NO PROSE:
{
  "decisions": [
    {
      "trigger_id": "t1",
      "decision": "execute" | "modify" | "stand_down",
      "rationale": "specific data-cited reasoning",
      "trades": [
        {"action": "buy"|"sell", "ticker": "...", "shares": N,
         "rationale": "...", "exit_thesis": "...",
         "exit_conditions": {"target_pct": 2.0, "stop_pct": 1.5, "time_exit_date": "YYYY-MM-DD"},
         "thesis_type": "...", "confidence": 0.0-1.0}
      ]
    }
  ],
  "patterns_noted": "lessons-learned"
}

If you stand down for all fired triggers, return decisions array with stand_down entries and empty trades."""


def fire_llm_response(fired_triggers, journal_tail, secrets, pf_state, market_snapshot, fresh_news):
    pf, holdings = pf_state
    lines = [f"## TIME: {datetime.datetime.now(datetime.timezone.utc).isoformat()}"]
    lines.append(f"\n## YOUR PORTFOLIO")
    lines.append(f"  Cash: ${pf['current_cash']:,.2f}")
    lines.append(f"  Holdings ({len(holdings)}):")
    for h in holdings:
        try:
            spot = float(yf.Ticker(h['ticker']).fast_info["lastPrice"])
        except Exception:
            spot = h['avg_cost']
        pct = (spot / h['avg_cost'] - 1) * 100
        lines.append(f"    {h['ticker']:<6s} {h['shares']:>4.0f} @ ${h['avg_cost']:.2f}  now ${spot:.2f} ({pct:+.2f}%)")

    lines.append(f"\n## THIS MORNING you set these triggers, and the following just fired:")
    for ft in fired_triggers:
        t = ft["trigger"]
        lines.append(f"\n  Trigger ID: {t.get('id')}")
        lines.append(f"    Type: {t.get('type')}")
        if t.get("type") == "price":
            lines.append(f"    Condition: {t.get('ticker')} {t.get('op')} ${t.get('level')}")
        elif t.get("type") == "news":
            lines.append(f"    Keywords watched: {', '.join(t.get('keywords', []))}")
        elif t.get("type") == "time":
            lines.append(f"    Wake at: {t.get('wake_at')}")
        lines.append(f"    Your original intent: {t.get('action_intent','')}")
        lines.append(f"    FIRED because: {ft.get('evidence','')}")
        if ft.get("matched_news"):
            lines.append(f"    Matched news (most recent):")
            for it in ft["matched_news"][:3]:
                lines.append(f"      [{it.get('source','?')}] {it.get('headline','')}")
                if it.get("summary"):
                    lines.append(f"        {it['summary'][:300]}")

    if market_snapshot:
        lines.append(f"\n## CURRENT MARKET SNAPSHOT")
        for t, m in market_snapshot.items():
            lines.append(f"  {t}: ${m['price']:.2f}  1d {m.get('ret_1d',0):+.2f}%  5d {m.get('ret_5d',0):+.2f}%")

    if journal_tail:
        lines.append(f"\n## YOUR JOURNAL (last 5 cycles, condensed):")
        for e in journal_tail[-5:]:
            lines.append(f"\n  --- {e.get('date','?')} ({e.get('type','daily')}) ---")
            for tr in e.get("trades", [])[:3]:
                lines.append(f"    {tr.get('action','?').upper()} {tr.get('shares')} {tr.get('ticker')}: {(tr.get('rationale') or '')[:150]}")

    if fresh_news:
        lines.append(f"\n## OTHER RECENT NEWS (last 5 min poll):")
        for n in fresh_news[:8]:
            lines.append(f"  [{n.get('source','?')}] {n.get('headline','')}")

    lines.append(f"\n## YOUR TASK")
    lines.append("Decide for each fired trigger above. Output strict JSON per the schema in your system prompt.")

    user_msg = "\n".join(lines)
    client = anthropic.Anthropic(api_key=secrets["ANTHROPIC_API_KEY"], timeout=LLM_TIMEOUT)
    t0 = time.time()
    resp = client.messages.create(
        model=MODEL, max_tokens=MAX_TOKENS,
        system=TRIGGER_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    dt = time.time() - t0
    text = resp.content[0].text
    in_tok, out_tok = resp.usage.input_tokens, resp.usage.output_tokens
    cost = (in_tok * 3.0 + out_tok * 15.0) / 1_000_000
    log_llm("trigger_response", in_tok, out_tok, cost, dt)
    log(f"  LLM response: in={in_tok} out={out_tok} cost=${cost:.4f} t={dt:.1f}s")
    m = re.search(r'\{[\s\S]*\}', text)
    if not m:
        raise ValueError(f"No JSON in response: {text[:300]}")
    return json.loads(m.group(0)), cost, user_msg, text


# ---------- market snapshot ----------
def market_snapshot():
    tickers = ["SPY", "XLK", "XLF", "XLE", "XLV", "MTUM", "QQQ"]
    out = {}
    try:
        hist = yf.download(tickers, period="5d", progress=False, threads=True)["Close"]
        for t in tickers:
            if t not in hist.columns: continue
            try:
                price = float(hist[t].iloc[-1])
                r1 = float(hist[t].iloc[-1] / hist[t].iloc[-2] - 1) * 100 if len(hist[t]) >= 2 else 0
                r5 = float(hist[t].iloc[-1] / hist[t].iloc[0] - 1) * 100 if len(hist[t]) >= 5 else 0
                out[t] = {"price": price, "ret_1d": r1, "ret_5d": r5}
            except Exception:
                pass
    except Exception as e:
        log(f"market_snapshot error: {e}", "WARN")
    return out


# ---------- trade execution (reuse) ----------
def execute_trades(trades, pf_id, dry_run, secrets):
    sys.path.insert(0, str(Path.home() / "bigclaw-ai" / "scripts"))
    from autonomous_trader import get_trading_client, MISMATCH_FLAG_PATH, verify_account_synced
    verify_account_synced()  # pre-trade guard: set kill-switch if Alpaca is desynced from the DB
    from order_fill import wait_for_fill, clamp_sell_to_long
    from trade_recorder import record_trade
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce, AssetStatus

    results = []
    if MISMATCH_FLAG_PATH.exists():
        return [(t, {"skipped": "mismatch flag"}) for t in trades]
    client = get_trading_client()
    clock = client.get_clock()
    if not clock.is_open:
        return [(t, {"skipped": "market closed"}) for t in trades]

    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    cash_row = conn.execute("SELECT current_cash FROM portfolios WHERE id=?", (pf_id,)).fetchone()
    cash = cash_row["current_cash"] if cash_row else 0
    holdings = {r["ticker"]: r["shares"] for r in conn.execute(
        "SELECT ticker, shares FROM holdings WHERE portfolio_id=? AND shares>0", (pf_id,)
    ).fetchall()}
    conn.close()

    for tr in trades:
        ticker = (tr.get("ticker") or "").upper()
        action = (tr.get("action") or "").lower()
        shares = int(tr.get("shares", 0))
        if shares < 1 or action not in ("buy", "sell"):
            results.append((tr, {"skipped": f"invalid: action={action} shares={shares}"}))
            continue
        try:
            asset = client.get_asset(ticker)
            if asset.status != AssetStatus.ACTIVE or not asset.tradable:
                results.append((tr, {"skipped": f"not tradable: {ticker}"}))
                continue
        except Exception as e:
            results.append((tr, {"skipped": f"ticker not found: {ticker}"}))
            continue

        # HARD ENFORCEMENT: LLM-Commando is single-stock by mandate. Reject any ETF buy.
        if action == 'buy' and ticker in ETF_BLACKLIST:
            log(f"REJECTED ETF buy: {ticker} (LLM-Commando is single-stock only)", "WARN")
            results.append((tr, {"skipped": f"ETF rejected: {ticker} (LLM-Commando is single-stock only)"}))
            continue
        if action == "sell":
            if shares > holdings.get(ticker, 0):
                results.append((tr, {"skipped": f"cannot sell {shares} {ticker} (hold {holdings.get(ticker,0)})"}))
                continue
            _bk = clamp_sell_to_long(client, ticker, shares, allow_short=bool(tr.get("short", False)))
            if _bk <= 0:
                results.append((tr, {"skipped": f"{ticker}: not long at Alpaca (short-prevention)"}))
                continue
            shares = _bk
        if action == "buy":
            try: spot = float(yf.Ticker(ticker).fast_info["lastPrice"])
            except Exception: spot = 0
            if shares * spot > cash:
                results.append((tr, {"skipped": f"insufficient cash"}))
                continue
            cash -= shares * spot

        if dry_run:
            results.append((tr, {"dry_run": True, "would_submit": f"{action.upper()} {shares} {ticker}"}))
            continue
        try:
            order = client.submit_order(MarketOrderRequest(
                symbol=ticker, qty=shares,
                side=OrderSide.BUY if action == "buy" else OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            ))
            filled_qty, filled_price = wait_for_fill(
                client, order, shares, None,
                ticker=ticker, pname=PORTFOLIO_NAME,
                side="BUY" if action == "buy" else "SELL",
            )
            value = filled_qty * filled_price
            ok = record_trade(pf_id, PORTFOLIO_NAME, ticker, action, filled_qty, filled_price, value,
                              f"LLM-WATCHER: {(tr.get('rationale') or '')[:300]}",
                              order_id=str(order.id))
            results.append((tr, {"filled_qty": filled_qty, "filled_price": filled_price,
                                 "value": value, "order_id": str(order.id), "db_ok": ok}))
        except Exception as e:
            results.append((tr, {"error": str(e)}))
    return results


# ---------- intraday mechanical exits (take-the-money-and-run) ----------
def check_mechanical_exits(dry_run, secrets, channel):
    """Every poll, sell any holding that has hit its target/stop/time exit NOW, instead of
    waiting for the once-a-day after-close reconciler. Reuses the reconciler's trigger logic,
    outcome format, and outcomes log (single source of truth); executes via the watcher's
    clamped short-safe path; records a closure ONLY on a real fill (the integrity gate)."""
    import llm_comando_reconciler as recon
    sys.path.insert(0, str(Path.home() / "bigclaw-ai" / "scripts"))
    from autonomous_trader import get_trading_client, MISMATCH_FLAG_PATH, verify_account_synced
    verify_account_synced()  # pre-trade guard: set kill-switch if Alpaca is desynced from the DB
    from order_fill import wait_for_fill, clamp_sell_to_long
    from trade_recorder import record_trade
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    import json as _json, datetime as _dt
    _CDFILE = Path.home() / "bigclaw-ai" / "data" / "llm_comando_exit_cooldown.json"; _CDMIN = 30
    try: _cd = _json.loads(_CDFILE.read_text()) if _CDFILE.exists() else {}
    except Exception: _cd = {}

    if MISMATCH_FLAG_PATH.exists():
        log("mechanical exits: mismatch flag set — skipping", "WARN")
        return
    pf, holdings = get_portfolio_state()
    if not pf or not holdings:
        return
    pid = pf["id"]
    journal = recon.read_journal()
    already_closed = recon.read_outcomes()
    client = get_trading_client()
    slack_lines = []
    for h in holdings:
        tk = h["ticker"]; entry = h["avg_cost"]; held = int(h["shares"])
        if held < 1:
            continue
        try:
            current = float(yf.Ticker(tk).fast_info["lastPrice"])
        except Exception as e:
            log(f"  exit-check {tk}: price fail {e}", "WARN")
            continue
        origin_date, source_trade = recon.find_origin_trade(journal, tk)
        if source_trade is None:
            continue
        if (origin_date, tk) in already_closed:
            continue
        conditions = source_trade.get("exit_conditions")
        if not conditions:
            continue  # prose-only: leave to the after-close reconciler (it LLM-extracts)
        try:
            d0 = datetime.date.fromisoformat(origin_date)
            days_held = (datetime.date.today() - d0).days
        except Exception:
            days_held = None
        trigger, reason = recon.evaluate_triggers(entry, current, days_held, conditions)
        if trigger is None:
            continue
        log(f"  MECHANICAL EXIT {tk}: {reason} (entry ${entry:.2f} -> ${current:.2f})")
        _lf = _cd.get(tk)
        if _lf and (_dt.datetime.now(_dt.timezone.utc) - _dt.datetime.fromisoformat(_lf)).total_seconds() < _CDMIN*60:
            log(f"  exit {tk}: {_CDMIN}m exit-cooldown active since last fire — skip", "WARN")
            continue
        if dry_run:
            slack_lines.append(f"  - [DRY] {tk}: {trigger} - {reason}")
            continue
        bk = clamp_sell_to_long(client, tk, held, allow_short=False)
        if bk <= 0:
            log(f"  exit {tk}: not long at Alpaca — skip", "WARN")
            continue
        try:
            order = client.submit_order(MarketOrderRequest(
                symbol=tk, qty=int(bk), side=OrderSide.SELL, time_in_force=TimeInForce.DAY))
            filled_qty, filled_price = wait_for_fill(
                client, order, int(bk), None, ticker=tk, pname=PORTFOLIO_NAME, side="SELL")
        except Exception as e:
            log(f"  exit {tk}: order error {e}", "WARN")
            continue
        # Integrity gate: record a closure ONLY if the sell actually filled.
        if int(filled_qty or 0) <= 0:
            log(f"  exit {tk}: '{trigger}' fired but did NOT fill — leaving open to retry", "WARN")
            continue
        value = filled_qty * filled_price
        record_trade(pid, PORTFOLIO_NAME, tk, "sell", filled_qty, filled_price, value,
                     f"LLM-WATCHER-EXIT: {reason}", order_id=str(order.id))
        _cd[tk] = _dt.datetime.now(_dt.timezone.utc).isoformat()
        try: _CDFILE.write_text(_json.dumps(_cd))
        except Exception: pass
        exec_result = {"filled_qty": filled_qty, "filled_price": filled_price,
                       "value": value, "order_id": str(order.id)}
        outcome = recon.build_outcome(origin_date, tk, filled_qty, entry, current, days_held,
                                      trigger, reason, conditions, source_trade, exec_result,
                                      dry_run, source="watcher")
        recon.append_outcome(outcome)
        already_closed.add((origin_date, tk))
        ok = "OK" if outcome["predicted_correctly"] else "X"
        slack_lines.append(f"  - {tk}: {trigger} - ${entry:.2f} -> ${filled_price:.2f} "
                           f"({outcome['realized_pct']:+.2f}%, {days_held}d) [{ok}]")
    if slack_lines:
        head = ":running: *Intraday Exit - take-the-money-and-run*" if not dry_run \
            else ":running: *[DRY] Intraday Exit check*"
        try:
            WebClient(token=secrets['SLACK_BOT_TOKEN']).chat_postMessage(
                channel=channel, text=head + "\n" + "\n".join(slack_lines))
        except Exception as e:
            log(f"exit slack failed: {e}", "WARN")


# ---------- main ----------
import sqlite3
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--channel", default=DEFAULT_CHANNEL)
    args = ap.parse_args()

    acquire_lock()
    try:
        secrets = load_secrets()
        for k in ("ANTHROPIC_API_KEY", "ALPACA_API_KEY", "ALPACA_SECRET_KEY", "SLACK_BOT_TOKEN"):
            if k not in secrets:
                write_failure_flag(f"missing secret: {k}")
                sys.exit(1)

        # Market hours gate (first, so the mechanical-exit check below runs in-hours)
        sys.path.insert(0, str(Path.home() / "bigclaw-ai" / "scripts"))
        from autonomous_trader import get_trading_client
        client = get_trading_client()
        if not client.get_clock().is_open and not args.dry_run:
            return  # quiet exit; cron fires every 5 min

        # MECHANICAL EXIT CHECK - runs EVERY poll, independent of pending triggers.
        # Intraday take-the-money-and-run: book a position the moment it hits its target/
        # stop/time exit, instead of waiting for the once-a-day after-close reconciler.
        try:
            check_mechanical_exits(args.dry_run, secrets, args.channel)
        except Exception as e:
            log(f"mechanical exit check error: {e}", "WARN")

        state = load_state()
        # Event-driven holdings scan runs even when no Judge triggers are armed.
        if state["fires_today"] >= state.get("max_fires", MAX_FIRES_PER_DAY):
            log(f"daily fire budget exhausted ({state['fires_today']}/{state.get('max_fires')})")
            return
        # Also respect shared radar/event daily budget
        try:
            import llm_comando_news as _nb
            _rem, _ = _nb.event_fire_budget()
            if _rem <= 0:
                log("shared event fire budget exhausted — skip LLM fires")
                # still allow mechanical exits only (already ran above)
                return
        except Exception:
            pass

        # PRE-FLIGHT: invalidate sell-intent price triggers referencing positions we no longer hold.
        # Catches the case where an earlier trigger fire (or the morning script or manual action)
        # closed the position, but the original stop trigger is still armed against the now-empty ticker.
        _, current_holdings_preflight = get_portfolio_state()
        n_obs = cleanup_obsolete_triggers(state, current_holdings_preflight)
        if n_obs:
            log(f"Cleanup: marked {n_obs} stale sell-intent trigger(s) as obsolete (no position to act on)")
            save_state(state)

        n_armed = sum(1 for t in state['triggers'] if t.get('status') in ('armed', 'retrying'))
        log(f"Watcher poll - {n_armed} triggers armed ({len(state['triggers'])} total), "
            f"{state['fires_today']}/{state.get('max_fires')} fires used today")

        # Refresh news once per poll (deduped via last_news_check timestamp)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        fresh_items = fetch_news_since(state.get("last_news_check"))
        log(f"  news polled: {len(fresh_items)} items since last check")

        # Evaluate each armed trigger
        fired = []

        # HOLDINGS THESIS-BREAK: new Alpaca news on a held ticker -> synthetic fire (no pre-armed trigger required)
        try:
            import llm_comando_news as _nh
            _rem2, _fst = _nh.event_fire_budget()
            if _rem2 > 0:
                _, _holds2 = get_portfolio_state()
                _held2 = {h["ticker"].upper() for h in _holds2}
                _start2 = None
                if state.get("last_news_check"):
                    _start2 = _nh._parse_iso(state.get("last_news_check"))
                if _start2 is None:
                    _start2 = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=15)
                _items2 = _nh.fetch_alpaca_news(secrets, start=_start2, limit_pages=2)
                _seen = set(state.get("seen_news_ids") or [])
                _new_h = []
                for _it in _items2:
                    _iid = _it.get("id") or (_it.get("time", "") + _it.get("headline", "")[:50])
                    if _iid in _seen:
                        continue
                    _seen.add(_iid)
                    for _sym in _it.get("symbols") or []:
                        if _sym in _held2:
                            _new_h.append((_sym, _it))
                state["seen_news_ids"] = list(_seen)[-800:]
                # group by ticker
                _byh = {}
                for _sym, _it in _new_h:
                    _byh.setdefault(_sym, []).append(_it)
                for _sym, _its in _byh.items():
                    fired.append({
                        "trigger": {
                            "id": f"holdnews_{_sym}",
                            "type": "news",
                            "keywords": [_sym],
                            "action_intent": (
                                f"Re-verify WHY-BOUGHT thesis for {_sym} on this news. "
                                f"SELL if thesis breaking/spent; hold if intact/strengthened; "
                                f"optional add only if thesis strongly reinforced and not extended."
                            ),
                            "status": "armed",
                        },
                        "evidence": f"{len(_its)} new headline(s) on held {_sym}",
                        "matched_news": [
                            {"source": x.get("source"), "headline": x.get("headline"), "summary": x.get("summary")}
                            for x in _its[:3]
                        ],
                    })
                if _byh:
                    log(f"  holdings news fires: {list(_byh.keys())}")
        except Exception as _hne:
            log(f"holdings news scan: {_hne}", "WARN")

        for trig in state["triggers"]:
            st = trig.get("status")
            if st not in ("armed", "retrying"): continue
            if _expired(trig, datetime.datetime.now(datetime.timezone.utc)):
                trig["status"] = "expired"; continue
            if st == "retrying":
                # A prior decided trade did not fill - re-fire (re-runs the LLM with fresh
                # data so conviction is re-validated) without needing the condition to re-match.
                fired.append({"trigger": trig, "evidence":
                    f"execution retry (attempt {trig.get('exec_attempts', 0)}/{EXEC_RETRY_CAP})"})
                continue

            ttype = trig.get("type")
            if ttype == "price":
                m, ev = check_price_trigger(trig)
                if m: fired.append({"trigger": trig, "evidence": ev})
            elif ttype == "news":
                m, matched_items = check_news_trigger(trig, fresh_items)
                if m:
                    ev = f"{len(matched_items)} matching item(s): " + "; ".join(
                        f"[{it.get('source','?')}] {it.get('headline','')[:80]}" for it in matched_items[:2]
                    )
                    fired.append({"trigger": trig, "evidence": ev, "matched_news": matched_items})
            elif ttype == "time":
                m, ev = check_time_trigger(trig)
                if m: fired.append({"trigger": trig, "evidence": ev})

        state["last_news_check"] = now_iso

        if not fired:
            save_state(state)
            return

        log(f"FIRED: {len(fired)} trigger(s) — calling LLM")

        # Get portfolio + market state
        pf_state = get_portfolio_state()
        market = market_snapshot()
        # Journal tail
        journal_tail = []
        if JOURNAL.exists():
            for line in JOURNAL.read_text().splitlines()[-10:]:
                try: journal_tail.append(json.loads(line))
                except Exception: pass

        # Fire one LLM call covering all fired triggers
        try:
            response, cost, prompt_used, raw_response = fire_llm_response(
                fired, journal_tail, secrets, pf_state, market, fresh_items
            )
        except Exception as e:
            log(f"LLM call failed: {e}", "ERROR")
            write_failure_flag(f"LLM fail: {e}")
            save_state(state)
            sys.exit(1)

        decisions = response.get("decisions", [])
        log(f"LLM produced {len(decisions)} decision(s)")

        # Execute trades per decision
        all_exec = []
        slack_lines = []
        for d in decisions:
            trig_id = d.get("trigger_id")
            dec = d.get("decision", "stand_down")
            rationale = d.get("rationale", "")
            trades = d.get("trades", []) if dec != "stand_down" else []
            exec_results = execute_trades(trades, pf_state[0]["id"], args.dry_run, secrets) if trades else []
            all_exec.append({"trigger_id": trig_id, "decision": dec, "rationale": rationale,
                              "trades": trades, "exec_results": [
                                  {"trade": t, "result": r} for t, r in exec_results
                              ]})
            # Execution-aware trigger lifecycle. A decided trade that was submitted but did NOT
            # fully fill (e.g. a market order that didn't fill at the volatile open) must NOT
            # silently consume the trigger - keep it 'retrying' so a later poll re-attempts the
            # exit (re-running the LLM, which re-validates conviction and re-clamps to the live
            # long position via clamp_sell_to_long, so it can never oversell or open a short).
            underfilled = [
                (t, r) for t, r in exec_results
                if ("filled_qty" in r) and int(r.get("filled_qty", 0) or 0) < int(t.get("shares", 0) or 0)
            ]
            executed = sum(1 for _, r in exec_results if r.get("filled_qty"))
            for trig in state["triggers"]:
                if trig.get("id") != trig_id:
                    continue
                trig["last_decision"] = dec
                if dec == "stand_down":
                    trig["status"] = "stood_down"; trig["consumed_at"] = now_iso
                elif underfilled:
                    attempts = int(trig.get("exec_attempts", 0)) + 1
                    trig["exec_attempts"] = attempts
                    trig["last_attempt_at"] = now_iso
                    if attempts >= EXEC_RETRY_CAP:
                        trig["status"] = "consumed"; trig["consumed_at"] = now_iso
                        trig["exec_failed"] = True
                    else:
                        trig["status"] = "retrying"
                else:
                    trig["status"] = "consumed"; trig["consumed_at"] = now_iso
                break
            # Slack line - loudly flag any decided trade that did NOT fill (position still held).
            slack_lines.append(f"  • Trigger `{trig_id}` → *{dec.upper()}* ({executed}/{len(trades)} trades): "
                                f"{rationale[:200]}")
            _trig = next((x for x in state["triggers"] if x.get("id") == trig_id), {})
            for t, r in underfilled:
                fq = int(r.get("filled_qty", 0) or 0); sh = int(t.get("shares", 0) or 0)
                att = int(_trig.get("exec_attempts", 0))
                tail = (f"*GAVE UP after {att} attempts - position STILL HELD, MANUAL ACTION NEEDED.*"
                        if _trig.get("status") == "consumed"
                        else f"will retry next poll (attempt {att}/{EXEC_RETRY_CAP}).")
                slack_lines.append(
                    f"  ⚠️ *EXECUTION FAILED* - {t.get('action','').upper()} {sh} {t.get('ticker')} "
                    f"filled {fq}/{sh} (order did not fill); {tail}")

        state["fires_today"] = state.get("fires_today", 0) + 1

        # POST-EXECUTION CLEANUP: if any sell just executed, invalidate triggers protecting positions
        # that no longer exist. Prevents the next poll from firing the LLM for stale stops.
        _, holdings_after = get_portfolio_state()
        n_obs_post = cleanup_obsolete_triggers(state, holdings_after)
        if n_obs_post:
            log(f"Post-execution cleanup: marked {n_obs_post} now-stale trigger(s) as obsolete")

        save_state(state)

        # Journal entry
        if not args.dry_run:
            entry = {
                "date": datetime.date.today().isoformat(),
                "type": "trigger_response",
                "ts": now_iso,
                "fires_today": state["fires_today"],
                "fired_triggers": [{"id": f["trigger"].get("id"), "type": f["trigger"].get("type"),
                                     "evidence": f.get("evidence","")} for f in fired],
                "decisions": all_exec,
                "patterns_noted": response.get("patterns_noted"),
                "cost_usd": round(cost, 4),
            }
            with JOURNAL.open("a") as f:
                f.write(json.dumps(entry) + "\n")

        # Slack
        try:
            msg = f"⚡ *LLM-Commando — Intraday Trigger Fire*\n"
            msg += f"_{state['fires_today']}/{state.get('max_fires')} fires used today, cost ${cost:.4f}_\n\n"
            msg += "\n".join(slack_lines)
            if response.get("patterns_noted"):
                msg += f"\n\n*Patterns noted:* {response['patterns_noted'][:300]}"
            WebClient(token=secrets['SLACK_BOT_TOKEN']).chat_postMessage(channel=args.channel, text=msg)
        except Exception as e:
            log(f"Slack post failed: {e}", "WARN")

        # Append a section to today's decision Markdown for browsability
        try:
            today_iso = datetime.date.today().isoformat()
            md_path = DECISIONS_DIR / f"{today_iso}.md"
            if md_path.exists():
                with md_path.open("a") as f:
                    f.write(f"\n\n---\n\n## ⚡ Intraday Trigger Fire — {now_iso[11:16]} UTC\n\n")
                    f.write(f"*Fire {state['fires_today']}/{state.get('max_fires')} of the day. Cost ${cost:.4f}.*\n\n")
                    for d in all_exec:
                        f.write(f"### Trigger `{d['trigger_id']}` → **{d['decision'].upper()}**\n\n")
                        f.write(f"**Rationale:** {d['rationale']}\n\n")
                        for tr in d.get("trades", []):
                            f.write(f"- {tr.get('action','').upper()} {tr.get('shares')} {tr.get('ticker')}: "
                                    f"{(tr.get('rationale') or '')[:300]}\n")
                            if tr.get("exit_thesis"):
                                f.write(f"  - exit: {tr['exit_thesis'][:300]}\n")
                        f.write("\n")
        except Exception as e:
            log(f"MD append failed: {e}", "WARN")

        if FAILURE_FLAG.exists(): FAILURE_FLAG.unlink()

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
