#!/usr/bin/env python3
"""Lightweight trailing stop checker — runs every 15 min during market hours.

Fetches prices for held tickers, checks trailing stop triggers,
executes Alpaca sells if triggered, posts to Slack. Zero LLM cost.
"""

import argparse
import json
import re
import sqlite3
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
DB_PATH = Path.home() / "bigclaw-ai" / "src" / "portfolios.db"
SECRETS_FILE = Path.home() / ".env_secrets"
SLACK_CHANNEL = "D0ADHLUJ400"

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path.home() / "bigclaw-ai" / "src"))

from bigclaw_logging import get_logger
from trailing_stop_manager import (
    fetch_prices, check_triggers, execute_stop_sells,
    initialize_stops, ratchet_stops, remove_stale_stops,
)

logger = get_logger("stop_check")


def is_market_open():
    now = datetime.now(ET)
    if now.weekday() >= 5:
        return False
    market_open = now.replace(hour=10, minute=0, second=0)
    market_close = now.replace(hour=16, minute=0, second=0)
    return market_open <= now <= market_close


def get_held_tickers():
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    rows = conn.execute("""
        SELECT DISTINCT h.ticker FROM holdings h
        JOIN portfolios p ON p.id = h.portfolio_id
        WHERE h.shares > 0 AND p.is_active = 1
    """).fetchall()
    conn.close()
    return {r[0] for r in rows}


def load_secrets():
    secrets = {}
    for line in SECRETS_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^export\s+", "", line)
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        secrets[k.strip()] = v.strip().strip("'\"")
    return secrets


def notify_slack(sells):
    secrets = load_secrets()
    token = secrets.get("SLACK_BOT_TOKEN")
    if not token or not sells:
        return

    lines = ["\U0001f6a8 *Trailing Stop Triggered*"]
    for s in sells:
        dry = " (DRY RUN)" if s.get("dry_run") else ""
        price = s.get("price", 0)
        lines.append(
            "* *{}* | SELL {} {} @ ${:,.2f} | {}{}".format(
                s["portfolio"], s["shares"], s["ticker"], price, s["reason"], dry
            )
        )

    msg = "\n".join(lines)
    payload = json.dumps({"channel": SLACK_CHANNEL, "text": msg}).encode()
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=payload,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
        },
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        logger.info("Slack notification sent")
    except Exception as e:
        logger.warning("Slack notify failed: {}".format(e))


def assert_invariants():
    """Verify trailing-stop coverage invariant.

    Returns (unprotected, orphans) — both lists of (portfolio, ticker[, status]).
    Empty = system healthy.

    Invariant: every held non-SGOV active-portfolio position has exactly
    one active trailing stop, and no active stops exist for not-held tickers.
    Violations indicate a sell/buy code path that bypassed the stop system.
    """
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    unprotected = c.execute("""
        SELECT p.name AS portfolio, h.ticker
        FROM holdings h
        JOIN portfolios p ON p.id = h.portfolio_id
        LEFT JOIN trailing_stops ts ON ts.portfolio_id = h.portfolio_id
            AND ts.ticker = h.ticker AND ts.status = 'active'
        WHERE h.shares > 0.001 AND h.ticker != 'SGOV'
            AND p.is_active = 1 AND ts.id IS NULL
    """).fetchall()
    orphans = c.execute("""
        SELECT p.name AS portfolio, ts.ticker, ts.status
        FROM trailing_stops ts
        JOIN portfolios p ON p.id = ts.portfolio_id
        LEFT JOIN holdings h ON h.portfolio_id = ts.portfolio_id
            AND h.ticker = ts.ticker AND h.shares > 0.001
        WHERE h.portfolio_id IS NULL
    """).fetchall()
    conn.close()
    return unprotected, orphans


def post_invariant_alert(unprotected, orphans):
    """Send a Slack alert when trailing-stop invariant is violated."""
    secrets = load_secrets()
    token = secrets.get("SLACK_BOT_TOKEN")
    if not token:
        return
    lines = ["\U0001f6a8 *Trailing Stop Invariant VIOLATED*"]
    if unprotected:
        lines.append("\n*Held positions WITHOUT active stop ({}):*".format(len(unprotected)))
        for r in unprotected:
            lines.append("  * {} | {}".format(r["portfolio"], r["ticker"]))
    if orphans:
        lines.append("\n*Active stops on NOT-held tickers ({}):*".format(len(orphans)))
        for r in orphans:
            lines.append("  * {} | {} ({})".format(r["portfolio"], r["ticker"], r["status"]))
    lines.append("\nA sell or buy bypassed the stop system. Investigate which code path.")
    payload = json.dumps({"channel": SLACK_CHANNEL, "text": "\n".join(lines)}).encode()
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=payload,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        logger.error("Slack invariant alert sent")
    except Exception as e:
        logger.warning("Slack invariant alert failed: {}".format(e))


def main():
    parser = argparse.ArgumentParser(description="Lightweight trailing stop checker")
    parser.add_argument("--dry-run", action="store_true", help="Preview without executing")
    parser.add_argument("--force", action="store_true", help="Run even outside market hours")
    args = parser.parse_args()

    if not args.force and not is_market_open():
        return  # Silent exit outside market hours

    # Defer to autonomous_trader if its currently running. The trader does
    # its own trailing-stop check at Step 1; running both concurrently can
    # double-sell positions (Alpaca fills both, going short). May 18 2026
    # incident: BTG double-sold within 2s, became -1836 short.
    import os as _os
    trader_lock = _os.path.expanduser(
        "~/.openclaw/workspace/logs/autonomous_trader.lock"
    )
    if _os.path.exists(trader_lock):
        # Check if lock is fresh (not stale from a crash)
        import time as _t
        lock_age = _t.time() - _os.path.getmtime(trader_lock)
        if lock_age < 1800:  # younger than 30 min = trader actively running
            logger.info(
                "Autonomous trader is running (lock age %.0fs) — "
                "deferring stop_check to avoid race condition" % lock_age
            )
            return
        else:
            logger.warning(
                "Stale autonomous_trader lockfile (age %.0fs) — "
                "proceeding with stop check" % lock_age
            )

    tickers = get_held_tickers()
    if not tickers:
        logger.info("No held tickers")
        return

    logger.info("Checking {} tickers".format(len(tickers)))
    prices = fetch_prices(tickers)
    if not prices:
        logger.warning("No prices fetched")
        return

    # Quick maintenance (lightweight)
    remove_stale_stops()
    initialize_stops()
    ratchet_stops(prices=prices)

    # Invariant check — after self-healing maintenance ran, anything still
    # broken is a real bug. Log loudly and Slack-alert. Don't halt — still
    # run check_triggers on whatever stops DO exist for actively-protected positions.
    unprotected, orphans = assert_invariants()
    if unprotected or orphans:
        logger.error(
            "INVARIANT VIOLATED: {} unprotected positions, {} orphan stops".format(
                len(unprotected), len(orphans)
            )
        )
        for r in unprotected:
            logger.error("  UNPROTECTED: {} | {}".format(r["portfolio"], r["ticker"]))
        for r in orphans:
            logger.error("  ORPHAN: {} | {} ({})".format(r["portfolio"], r["ticker"], r["status"]))
        post_invariant_alert(unprotected, orphans)

    # Check triggers
    triggered = check_triggers(prices=prices, dry_run=args.dry_run)
    if not triggered:
        logger.info("No stops triggered ({} prices checked)".format(len(prices)))
        return

    # Execute sells
    logger.info("{} stops triggered!".format(len(triggered)))
    executed = execute_stop_sells(triggered, dry_run=args.dry_run)

    # Notify
    notify_slack(executed)
    logger.info("Stop check complete: {} sells executed".format(len(executed)))


if __name__ == "__main__":
    main()
