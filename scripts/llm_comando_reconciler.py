#!/usr/bin/env python3
"""LLM Discretionary Portfolio — Trade Closure Reconciler.

Runs daily after market close (3:30 PM CT weekdays). For each open position:
  1. Find source BUY trade in journal
  2. Extract exit conditions (target_pct, stop_pct, time_exit_date).
     If structured exit_conditions present, use directly.
     If only prose exit_thesis, run small LLM extraction and cache result.
  3. Check triggers in priority order: stop > target > time
  4. If trigger fires: SELL via Alpaca, record_trade with outcome rationale,
     append outcome record to journal

This is the verification layer that makes recursive learning possible — it
tells the LLM whether its predictions came true.

Usage:
    llm_portfolio_reconciler.py                 # production: check, close, journal, Slack
    llm_portfolio_reconciler.py --dry-run       # no Alpaca submits, no journal writes
    llm_portfolio_reconciler.py --force-time    # treat all open as time-exit (sweep mode)
"""
import argparse
import datetime
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

import warnings
warnings.filterwarnings("ignore")

import anthropic
import yfinance as yf
from slack_sdk import WebClient

PORTFOLIO_NAME = "LLM-Commando"
DEFAULT_CHANNEL = "D0ADHLUJ400"
MODEL_EXTRACTOR = "claude-sonnet-4-6"
LOCK_FILE = Path("/tmp/llm_comando_reconciler.lock")
FAILURE_FLAG = Path.home() / "bigclaw-ai" / "logs" / "LLM_COMANDO_RECONCILER_FAILED.flag"
LLM_LOG = Path.home() / "bigclaw-ai" / "logs" / "llm_calls.jsonl"
JOURNAL = Path.home() / "bigclaw-ai" / "data" / "llm_comando_journal.jsonl"
OUTCOMES = Path.home() / "bigclaw-ai" / "data" / "llm_comando_outcomes.jsonl"  # append-only closure log
DECISIONS_DIR = Path.home() / "bigclaw-ai" / "data" / "llm_comando_decisions"
DB_PATH = Path.home() / "bigclaw-ai" / "src" / "portfolios.db"


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
                log(f"Already running PID {pid} - aborting", "WARN")
                sys.exit(1)
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

def log_llm(agent, model, in_tok, out_tok, cost, dt):
    try:
        LLM_LOG.parent.mkdir(parents=True, exist_ok=True)
        with LLM_LOG.open("a") as f:
            f.write(json.dumps({
                "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "script": "llm_portfolio_reconciler.py",
                "agent": agent, "model": model,
                "input_tokens": in_tok, "output_tokens": out_tok,
                "cost_usd": round(cost, 4), "duration_sec": round(dt, 1),
            }) + "\n")
    except Exception:
        pass


# ---------- journal IO ----------
def read_journal():
    if not JOURNAL.exists(): return []
    out = []
    for line in JOURNAL.read_text().splitlines():
        line = line.strip()
        if not line: continue
        try: out.append(json.loads(line))
        except Exception: pass
    return out

def append_outcome(rec):
    OUTCOMES.parent.mkdir(parents=True, exist_ok=True)
    with OUTCOMES.open("a") as f:
        f.write(json.dumps(rec) + "\n")

def read_outcomes():
    """Return set of (origin_date, ticker) tuples for already-closed positions."""
    if not OUTCOMES.exists(): return set()
    closed = set()
    for line in OUTCOMES.read_text().splitlines():
        line = line.strip()
        if not line: continue
        try:
            r = json.loads(line)
            closed.add((r["origin_date"], r["ticker"]))
        except Exception: pass
    return closed


# ---------- state ----------
def get_open_holdings():
    """Return list of dicts: {ticker, shares, avg_cost, first_bought_at} for LLM portfolio."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    pf = conn.execute("SELECT id FROM portfolios WHERE name=?", (PORTFOLIO_NAME,)).fetchone()
    if pf is None:
        conn.close()
        raise RuntimeError(f"Portfolio {PORTFOLIO_NAME!r} not in DB")
    rows = conn.execute(
        "SELECT ticker, shares, avg_cost, first_bought_at FROM holdings "
        "WHERE portfolio_id=? AND shares>0", (pf['id'],)
    ).fetchall()
    conn.close()
    return pf['id'], [dict(r) for r in rows]


def find_origin_trade(journal, ticker):
    """Find the most recent journal entry that BOUGHT this ticker."""
    for entry in reversed(journal):
        for t in entry.get("trades", []):
            if (t.get("ticker") or "").upper() == ticker.upper() and (t.get("action") or "").lower() == "buy":
                return entry["date"], t
    return None, None


# ---------- exit conditions extraction ----------
EXTRACT_SYSTEM = """You parse trade exit theses written in prose into strict JSON conditions.

Given a free-form exit thesis, return:
{
  "target_pct": <positive number, gain target as percent>,
  "stop_pct": <positive number, stop loss as percent (absolute value)>,
  "time_exit_date": "YYYY-MM-DD" or null
}

Rules:
- target_pct: the GAIN target as a positive number. Range/midpoint: if thesis says "1.5-2.5%", use 2.0. If "3-5%", use 4.0.
- stop_pct: the loss stop as a POSITIVE number (e.g., -1.5% becomes 1.5). If thesis says "stop -2.5%" or "exit if it falls more than 2.5%", use 2.5.
- time_exit_date: parse to ISO date. "June 13" -> "2026-06-13". "within 5 days" from a known start -> compute. Use null if no specific date.
- If a field is genuinely absent or unclear, use null.

Output ONLY valid JSON. No prose."""

def extract_conditions(thesis_text, origin_date, anthropic_client):
    """Use LLM to parse prose exit thesis into structured conditions. Returns dict."""
    msg = f"Origin date of the trade: {origin_date}\n\nExit thesis prose:\n{thesis_text}\n\nReturn the JSON now."
    t0 = time.time()
    resp = anthropic_client.messages.create(
        model=MODEL_EXTRACTOR, max_tokens=300,
        system=EXTRACT_SYSTEM,
        messages=[{"role": "user", "content": msg}],
    )
    dt = time.time() - t0
    text = resp.content[0].text
    in_tok, out_tok = resp.usage.input_tokens, resp.usage.output_tokens
    cost = (in_tok * 3.0 + out_tok * 15.0) / 1_000_000
    log_llm("exit_extractor", MODEL_EXTRACTOR, in_tok, out_tok, cost, dt)
    m = re.search(r'\{[\s\S]*\}', text)
    if not m:
        raise ValueError(f"No JSON in extractor output: {text[:200]}")
    return json.loads(m.group(0))


# ---------- triggers ----------
def evaluate_triggers(entry_price, current_price, days_held, conditions):
    """Returns (trigger_name, reason_str) or (None, None) if no trigger.
       Priority order: stop > target > time."""
    target_pct = conditions.get("target_pct")
    stop_pct = conditions.get("stop_pct")
    time_exit_date = conditions.get("time_exit_date")

    pct_change = (current_price / entry_price - 1) * 100

    # Stop first (loss protection wins)
    if stop_pct is not None and pct_change <= -abs(stop_pct):
        return ("stop_hit", f"price {pct_change:+.2f}% <= -{abs(stop_pct)}% stop")

    # Target
    if target_pct is not None and pct_change >= abs(target_pct):
        return ("target_hit", f"price {pct_change:+.2f}% >= +{abs(target_pct)}% target")

    # Time exit RETIRED (2026-07-13): no clock forces a sale. Exits are conviction (the deliberative
    # Judge re-verifies every holding's entry thesis each session) or risk (stop_hit). A time horizon
    # is a lens the Judge applies, never a mechanical trigger. time_exit_date stays advisory prose only.
    _ = time_exit_date  # intentionally not enforced

    return (None, None)


# ---------- outcome record (shared by the after-close reconciler and the intraday watcher) ----------
def compute_predicted_correctly(trigger, pct, target_pct):
    if trigger == "target_hit":
        return True
    if trigger == "stop_hit":
        return False
    if trigger == "time_exit":
        if target_pct is not None and pct >= 0:
            return pct >= target_pct * 0.5  # booked at least half the target
        return False
    return None


def build_outcome(origin_date, ticker, shares, entry_price, current, days_held,
                  trigger, reason, conditions, source_trade, exec_result, dry_run,
                  source="reconciler"):
    """One closure outcome record. Single source of truth for the learning log, used by
    both reconciler.main() (after-close) and the watcher's intraday exit check."""
    exit_price = exec_result.get("filled_price", current)
    pct = (current / entry_price - 1) * 100
    return {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "origin_date": origin_date,
        "close_date": datetime.date.today().isoformat(),
        "ticker": ticker,
        "shares": shares,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "realized_pct": (exit_price / entry_price - 1) * 100,
        "days_held": days_held,
        "exit_trigger": trigger,
        "exit_reason": reason,
        "exit_conditions_used": conditions,
        "predicted_correctly": compute_predicted_correctly(trigger, pct, conditions.get("target_pct")),
        "thesis_type": source_trade.get("thesis_type"),
        "confidence": source_trade.get("confidence"),
        "original_rationale": (source_trade.get("rationale") or "")[:500],
        "original_exit_thesis": (source_trade.get("exit_thesis") or "")[:500],
        "exec_result": exec_result,
        "dry_run": dry_run,
        "source": source,
    }


# ---------- close execution ----------
def execute_close(ticker, shares, reason_str, pid, dry_run, secrets):
    """Submit SELL via Alpaca; record via canonical record_trade. Returns result dict."""
    sys.path.insert(0, str(Path.home() / "bigclaw-ai" / "scripts"))
    from autonomous_trader import get_trading_client, MISMATCH_FLAG_PATH, verify_account_synced
    verify_account_synced()  # pre-trade guard: set kill-switch if Alpaca is desynced from the DB
    from order_fill import wait_for_fill
    from trade_recorder import record_trade
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce

    if MISMATCH_FLAG_PATH.exists():
        return {"skipped": "global mismatch flag"}

    client = get_trading_client()
    clock = client.get_clock()
    if not clock.is_open and not dry_run:
        # Market closed: a DAY order cannot fill and is canceled. Do not submit a futile
        # order or fabricate a closure — signal not-filled so the caller leaves it open.
        return {"market_closed": True, "filled_qty": 0, "filled_price": 0.0}

    if dry_run:
        return {"dry_run": True, "would_sell": f"{shares} {ticker}", "reason": reason_str}

    try:
        order = client.submit_order(MarketOrderRequest(
            symbol=ticker, qty=int(shares),
            side=OrderSide.SELL, time_in_force=TimeInForce.DAY,
        ))
        filled_qty, filled_price = wait_for_fill(
            client, order, int(shares), None,
            ticker=ticker, pname=PORTFOLIO_NAME, side="SELL",
        )
        value = filled_qty * filled_price
        ok = record_trade(
            pid, PORTFOLIO_NAME, ticker, "sell", filled_qty, filled_price, value,
            f"LLM-RECONCILER: {reason_str}",
            order_id=str(order.id),
        )
        return {
            "filled_qty": filled_qty, "filled_price": filled_price,
            "value": value, "order_id": str(order.id), "db_ok": ok,
        }
    except Exception as e:
        return {"error": str(e)}


# ---------- main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force-time", action="store_true",
                    help="Treat all open positions as time-exit (sweep mode for manual close)")
    ap.add_argument("--channel", default=DEFAULT_CHANNEL)
    args = ap.parse_args()

    acquire_lock()
    try:
        log("Reconciler starting")
        secrets = load_secrets()
        for k in ("ANTHROPIC_API_KEY", "ALPACA_API_KEY", "ALPACA_SECRET_KEY", "SLACK_BOT_TOKEN"):
            if k not in secrets:
                write_failure_flag(f"missing secret: {k}")
                sys.exit(1)

        pid, holdings = get_open_holdings()
        log(f"Open positions: {len(holdings)}")
        if not holdings:
            log("No open positions to reconcile. Done.")
            return

        journal = read_journal()
        already_closed = read_outcomes()  # don't double-close
        log(f"Journal entries: {len(journal)}, already-closed records: {len(already_closed)}")

        # Get current prices
        tickers = [h["ticker"] for h in holdings]
        prices = {}
        for t in tickers:
            try:
                prices[t] = float(yf.Ticker(t).fast_info["lastPrice"])
            except Exception as e:
                log(f"Could not price {t}: {e}", "WARN")

        anthropic_client = anthropic.Anthropic(api_key=secrets['ANTHROPIC_API_KEY'], timeout=60.0)

        actions = []
        closures_for_slack = []

        for h in holdings:
            tk = h["ticker"]
            if tk not in prices:
                log(f"  {tk}: skipped (no price)", "WARN")
                continue
            entry_price = h["avg_cost"]
            shares = h["shares"]
            current = prices[tk]
            pct = (current / entry_price - 1) * 100

            origin_date, source_trade = find_origin_trade(journal, tk)
            if source_trade is None:
                log(f"  {tk}: no journal origin found — skipping (manual position?)", "WARN")
                continue

            if (origin_date, tk) in already_closed:
                log(f"  {tk}: already in outcomes log, but still in DB holdings — skipping anomaly", "WARN")
                continue

            # Compute days held
            try:
                d0 = datetime.date.fromisoformat(origin_date)
                days_held = (datetime.date.today() - d0).days
            except Exception:
                days_held = None

            # Get exit conditions: prefer structured, fall back to LLM-extract from prose
            conditions = source_trade.get("exit_conditions")
            if not conditions:
                prose = source_trade.get("exit_thesis", "")
                if not prose:
                    log(f"  {tk}: no exit_thesis at all — skipping", "WARN")
                    continue
                try:
                    conditions = extract_conditions(prose, origin_date, anthropic_client)
                    log(f"  {tk}: LLM-extracted conditions: {conditions}")
                except Exception as e:
                    log(f"  {tk}: extraction failed: {e}", "WARN")
                    continue

            # Force time exit if requested
            if args.force_time:
                trigger, reason = ("time_exit", "FORCE-TIME sweep mode")
            else:
                trigger, reason = evaluate_triggers(entry_price, current, days_held, conditions)

            log(f"  {tk}: entry ${entry_price:.2f} -> ${current:.2f} ({pct:+.2f}%), "
                f"days_held={days_held}, trigger={trigger}")

            if trigger is None:
                continue  # still open

            log(f"    -> CLOSING: {reason}")
            exec_result = execute_close(tk, shares, reason, pid, args.dry_run, secrets)

            # Integrity gate: a closure outcome MUST reflect a real fill. If the sell did
            # not fill (market closed, timeout/cancel, mismatch flag), leave the position
            # OPEN and retry next run — never fabricate a -100% phantom closure (the PODD/
            # MTUM orphan bug). dry-run is exempt (it never fills by design).
            _filled = exec_result.get("filled_qty", 0) or 0
            if not args.dry_run and _filled <= 0:
                log(f"  {tk}: exit '{trigger}' fired but sell did NOT fill ({exec_result}); "
                    f"leaving position open, no outcome recorded.", "WARN")
                continue

            outcome = build_outcome(origin_date, tk, shares, entry_price, current,
                                    days_held, trigger, reason, conditions, source_trade,
                                    exec_result, args.dry_run, source="reconciler")
            predicted_correctly = outcome["predicted_correctly"]
            if not args.dry_run:
                append_outcome(outcome)
            actions.append(outcome)

            closures_for_slack.append(
                f"  • {tk}: {trigger} — ${entry_price:.2f} → ${outcome['exit_price']:.2f} "
                f"({outcome['realized_pct']:+.2f}%, {days_held}d held)  "
                f"{'✓ thesis correct' if predicted_correctly else '✗ thesis wrong'}"
            )

        # Slack summary
        if actions and not args.dry_run:
            try:
                today_iso = datetime.date.today().isoformat()
                msg = f"🔄 *LLM Reconciler — {today_iso}*\n"
                msg += f"Closed {len(actions)} position(s):\n"
                msg += "\n".join(closures_for_slack)
                msg += f"\n\n_Outcomes written to data/llm_outcomes.jsonl — visible to next cycle's LLM._"
                WebClient(token=secrets['SLACK_BOT_TOKEN']).chat_postMessage(
                    channel=args.channel, text=msg
                )
            except Exception as e:
                log(f"Slack post failed: {e}", "WARN")

        if actions:
            log(f"Reconciler: closed {len(actions)} position(s)")
        else:
            log("Reconciler: no triggers fired this run")

        if FAILURE_FLAG.exists():
            FAILURE_FLAG.unlink()

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
