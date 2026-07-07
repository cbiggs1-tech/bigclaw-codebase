#!/usr/bin/env python3
"""
BigClaw Autonomous Trader — Daily trading orchestration

Workflow:
1. Sync local DB with Alpaca positions (fix drift)
2. Run decision engine to generate signals + swap recommendations
3. Execute sells first across all portfolios (free cash)
4. Execute buys using available per-portfolio cash
5. Output execution summary for Slack

CASH WALL RULES (HARD — NO EXCEPTIONS):
- Each portfolio is an independent brokerage account
- A portfolio can ONLY spend its own cash (starting_cash - buys + sells)
- Cash is verified from transaction replay BEFORE every buy order
- If cost > verified cash, the buy is downsized or skipped — never overdrafted
- No borrowing between portfolios. No Alpaca buying power sharing.
- If a DB write fails, trading HALTS for that portfolio (circuit breaker)
- Sells free cash immediately; that cash is available for the next buy

Usage:
    python3 autonomous_trader.py                # Full run (analyze + execute)
    python3 autonomous_trader.py --dry-run      # Preview without executing
    python3 autonomous_trader.py --sync-only    # Just sync DB with Alpaca
    python3 autonomous_trader.py --status       # Show current state
"""

import argparse
import json
import math
import os
import re
import sqlite3

from style_gates import passes_style_gate
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from bigclaw_logging import get_logger
from bigclaw_retry import retry
from alpaca_symbols import to_alpaca, from_alpaca
from stop_cooldown import is_blocked as is_in_cooldown
from order_fill import wait_for_fill, clamp_sell_to_long
from trade_recorder import record_trade

ET = ZoneInfo("America/New_York")
logger = get_logger("trader")
DB_PATH = Path.home() / "bigclaw-ai" / "src" / "portfolios.db"
SCRIPTS_DIR = Path.home() / ".openclaw" / "workspace" / "scripts"
SIGNALS_FILE = Path.home() / "bigclaw-ai" / "docs" / "data" / "signals.json"
LOG_DIR = Path.home() / ".openclaw" / "workspace" / "logs"
LOG_FILE = LOG_DIR / "trades.log"
SECRETS_FILE = Path.home() / ".env_secrets"
UNIVERSES_FILE = Path.home() / ".openclaw" / "workspace" / "config" / "portfolio_universes.json"

# Trading rules
MIN_CASH_RESERVE_PCT = 0.02   # Keep 2% cash reserve per portfolio ($2K on $100K)
MONEY_MARKET_TICKER = "SGOV"  # Excluded from scoring/counting (legacy — no longer traded)
# SGOV sweep removed: idle cash stays as cash. Eliminates DB write failures from SGOV operations.
MAX_SINGLE_ORDER = 25000.0
# ---------------------------------------------------------------------------
# Target-price hold discipline (Phase 2 of target_price work, May 15 2026)
#
# When TRUE for a portfolio: the rotation engine HOLDS positions through
# daily score variations. Sells fire only on these triggers:
#   1. Target proximity: current_price >= target_price * 0.90 (90% of target)
#   2. Thesis break:     forward EPS estimate fell >25% over 90 days
#   3. Concentration:    position market value > 15% of portfolio total value
#
# When FALSE: current behavior — sell anything held but not in today's top 10.
#
# Default: all portfolios FALSE until validated. Innovation Fund flipped ON
# as the first test case. Flip others to True only after observing one
# trader cycle with no unexpected behavior.
# ---------------------------------------------------------------------------
TARGET_PRICE_DISCIPLINE = {
    "Value Picks": False,
    "Innovation Fund": True,   # First portfolio under target-price discipline
    "Growth Value": False,
    "Income Dividends": False,
    "Momentum Growth": False,
    "Nuclear Renaissance": False,
    "AI Defense & Autonomous": False,
}
TARGET_PROXIMITY_PCT = 0.90    # sell when within 10% of target
TARGET_EPS_BREAK_PCT = -25.0   # sell if forward EPS fell more than this %
TARGET_CONCENTRATION_LIMIT = 0.15  # trim if position > 15% of portfolio


def evaluate_target_discipline_sell(pname, ticker, current_price, target_price,
                                      shares, portfolio_total_value, fwd_eps_revision_pct=None):
    """Check whether a held position should be sold under target-price discipline.

    Returns (should_sell, reason) tuple.

    All thresholds defined at module level — change them globally there if
    discipline needs retuning. Per-portfolio enabling is via
    TARGET_PRICE_DISCIPLINE[pname].
    """
    if not TARGET_PRICE_DISCIPLINE.get(pname, False):
        return False, None

    # Trigger 1: target reached
    if target_price and current_price >= target_price * TARGET_PROXIMITY_PCT:
        return True, (f"target reached: ${current_price:.2f} >= ${target_price:.2f} "
                      f"* {TARGET_PROXIMITY_PCT}")

    # Trigger 2: thesis break (forward EPS plummeted)
    if fwd_eps_revision_pct is not None and fwd_eps_revision_pct <= TARGET_EPS_BREAK_PCT:
        return True, (f"thesis break: forward EPS fell {fwd_eps_revision_pct:.0f}% "
                      f"(threshold {TARGET_EPS_BREAK_PCT}%)")

    # Trigger 3: concentration (position > 15% of portfolio value)
    position_value = shares * current_price
    if portfolio_total_value > 0:
        pct = position_value / portfolio_total_value
        if pct > TARGET_CONCENTRATION_LIMIT:
            return True, (f"concentration: position is {pct:.0%} of portfolio "
                          f"(threshold {TARGET_CONCENTRATION_LIMIT:.0%})")

    return False, None


MAX_HOLDINGS = 10            # Max positions per portfolio
MIN_HOLDINGS = 7             # Min positions per portfolio (triggers swap/add)
MAX_POSITION_PCT = 0.20      # Max 20% of portfolio value in any one stock (monthly rebalance only)
REBALANCE_TRIM_TARGET = 0.18 # Trim overweight positions to 18%
SCORE_BUY_MINIMUM = 1         # Minimum score to deploy cash into a new position
SCORE_TRIM_THRESHOLD = -3     # Score <= -3 to trim 50% (Phase 1 safety net)
SCORE_SELL_THRESHOLD = -5     # Score <= -5 to sell 100% (Phase 1 safety net)

# BEST-IN-CLASS STRATEGY:
# Each portfolio holds the top MAX_HOLDINGS stocks by score at all times.
# If a better stock appears, sell the weakest to fund it. No loyalty to positions.
# Concentration (>20%) handled by monthly rebalance only — let winners run.
# SGOV is money market (cash equivalent) — exempt from all position rules.

# Alpaca day trade rules (Pattern Day Trader protection)
# Paper accounts have $100K+ equity, so PDT doesn't apply, but we still
# avoid churning by limiting round-trips per ticker per week.
MAX_ROUND_TRIPS_PER_WEEK = 3


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


def get_trading_client():
    secrets = load_secrets()
    api_key = secrets.get("ALPACA_API_KEY")
    secret_key = secrets.get("ALPACA_SECRET_KEY")
    if not api_key or not secret_key:
        logger.error("Missing ALPACA_API_KEY or ALPACA_SECRET_KEY")
        sys.exit(1)
    from alpaca.trading.client import TradingClient
    return TradingClient(api_key, secret_key, paper=True)


def now_et():
    return datetime.now(ET)


def log_trade(msg):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = now_et().strftime("%Y-%m-%d %H:%M ET")
    line = f"{ts} | {msg}"
    logger.info(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def db_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn

def db_execute_with_retry(func, max_retries=3, delay=2):
    """Execute a DB operation with retry on lock errors."""
    import time as _time
    for attempt in range(max_retries):
        try:
            return func()
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_retries - 1:
                logger.warning(f"DB locked, retry {attempt+1}/{max_retries} in {delay}s...")
                _time.sleep(delay)
                delay *= 2  # exponential backoff
            else:
                raise


def get_verified_cash(pid):
    """Return portfolio cash verified by replaying ALL transactions from starting_cash.
    This is the ONLY way to know how much a portfolio can spend. No shortcuts.
    Forces WAL checkpoint to ensure we see the latest committed data."""
    conn = db_conn()
    c = conn.cursor()
    # Force WAL checkpoint so we see all committed writes from other connections
    c.execute("PRAGMA wal_checkpoint(PASSIVE)")
    c.execute("SELECT starting_cash FROM portfolios WHERE id = ?", (pid,))
    row = c.fetchone()
    if not row:
        conn.close()
        return 0.0
    starting = row[0]
    c.execute("""
        SELECT COALESCE(SUM(CASE WHEN action='buy' THEN total_value ELSE 0 END), 0),
               COALESCE(SUM(CASE WHEN action='sell' THEN total_value ELSE 0 END), 0),
               COALESCE(SUM(CASE WHEN action='dividend' THEN total_value ELSE 0 END), 0)
        FROM transactions WHERE portfolio_id = ?
    """, (pid,))
    buys, sells, dividends = c.fetchone()
    conn.close()
    verified = round(starting - buys + sells + dividends, 2)
    return verified


def get_position_count(pid):
    """Return count of non-SGOV positions with shares > 0."""
    conn = db_conn()
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*) FROM holdings WHERE portfolio_id = ? AND shares > 0 AND ticker != ?",
        (pid, MONEY_MARKET_TICKER)
    )
    count = c.fetchone()[0]
    conn.close()
    return count


def assert_no_orphan_holdings():
    """Return list of holdings rows that violate the no-orphans invariant.

    Sell paths must DELETE the row when shares fully close out. Any row with
    shares <= 0.001 or NULL means a code path bypassed the DELETE logic.
    Empty list = healthy.
    """
    conn = db_conn()
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT p.name AS portfolio, h.ticker, h.shares
        FROM holdings h
        JOIN portfolios p ON p.id = h.portfolio_id
        WHERE h.shares <= 0.001 OR h.shares IS NULL
        ORDER BY p.name, h.ticker
    """).fetchall()
    conn.close()
    return rows


def post_orphan_alert(orphans):
    """Send Slack alert when holdings invariant is violated."""
    import json as _json
    import urllib.request as _urllib_request
    import os as _os
    token = _os.environ.get("SLACK_BOT_TOKEN", "")
    if not token:
        return
    lines = ["\U0001f6a8 *Holdings Invariant VIOLATED*"]
    lines.append(f"*Orphan rows ({len(orphans)})* — shares <= 0.001 or NULL after trader run:")
    for r in orphans:
        lines.append(f"  * {r['portfolio']} | {r['ticker']} | shares={r['shares']}")
    lines.append("\nA sell or update bypassed the DELETE logic. Investigate which code path.")
    payload = _json.dumps({"channel": "D0ADHLUJ400", "text": "\n".join(lines)}).encode()
    req = _urllib_request.Request(
        "https://slack.com/api/chat.postMessage",
        data=payload,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    try:
        _urllib_request.urlopen(req, timeout=10)
        logger.error("Slack orphan-holdings alert sent")
    except Exception as e:
        logger.warning(f"Slack orphan-holdings alert failed: {e}")


def get_portfolio_market_value(pid):
    """Return total portfolio value (cash + holdings at cost basis).
    Cost basis is used as proxy — monthly rebalance uses live prices."""
    cash = get_verified_cash(pid)
    conn = db_conn()
    c = conn.cursor()
    c.execute(
        "SELECT COALESCE(SUM(shares * avg_cost), 0) FROM holdings "
        "WHERE portfolio_id = ? AND shares > 0", (pid,)
    )
    holdings_val = c.fetchone()[0]
    conn.close()
    return cash + holdings_val



def _execute_sell_order(client, pid, pname, ticker, shares, reason, dry_run=False, allow_short=False):
    """Execute a sell order through Alpaca and record to DB.

    Single path for ALL sells. Returns dict with result or None on failure.
    On DB write failure, returns {"halted": True} to trigger circuit breaker.
    """
    import yfinance as yf
    try:
        from fundamentals_cache import get_info; info = get_info(ticker)
        est_price = info.get("currentPrice") or info.get("regularMarketPrice")
    except Exception:
        est_price = None

    if dry_run:
        price = est_price or 0
        log_trade(f"DRY-SELL | {pname} | {ticker} | {shares} shares @ ~${price:,.2f} | {reason}")
        return {"ticker": ticker, "shares": shares, "price": price, "value": shares * price, "dry_run": True}

    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    _req = shares
    shares = clamp_sell_to_long(client, to_alpaca(ticker), shares, allow_short=allow_short)
    if shares <= 0:
        log_trade(f"SELL BLOCKED | {pname} | {ticker} | not long at Alpaca (short-prevention); requested {_req}")
        return {"skipped": "no long position at Alpaca (short-prevention)"}
    if shares < _req:
        log_trade(f"SELL CLAMPED | {pname} | {ticker} | {_req} -> {shares} (live Alpaca long)")
    try:
        order = client.submit_order(MarketOrderRequest(
            symbol=to_alpaca(ticker), qty=shares, side=OrderSide.SELL, time_in_force=TimeInForce.DAY,
        ))
        filled_qty, filled_price = wait_for_fill(client, order, shares, est_price, ticker=ticker, pname=pname, side="SELL")
        actual_value = filled_qty * filled_price
        log_trade(f"SELL | {pname} | {ticker} | {filled_qty} @ ${filled_price:,.2f} = ${actual_value:,.2f} | {reason} | order={order.id}")

        db_ok = _record_trade_with_retry(
            pid, pname, ticker, "sell", filled_qty, filled_price, actual_value, reason,
            sell_all=(filled_qty >= shares), order_id=str(order.id),
        )
        if not db_ok:
            log_trade(f"CIRCUIT BREAKER | {pname} | DB write failed on SELL {ticker}")
            return {"halted": True}

        return {"ticker": ticker, "shares": filled_qty, "price": filled_price,
                "value": actual_value, "order_id": str(order.id)}

    except Exception as e:
        log_trade(f"ERROR | {pname} | SELL {ticker} | {e}")
        return None


def _execute_buy_order(client, pid, pname, ticker, alloc, reason, starting, reserve, dry_run=False):
    """Execute a buy order through Alpaca and record to DB.

    CRITICAL: Cash is verified and allocation is capped BEFORE calculating shares.
    This prevents the WAL read-visibility race where rapid sequential buys each
    see the full balance because prior commits aren't visible yet.

    Also captures analyst mean target price at entry time so the position has
    a thesis-completion sell target persisted from day one (target-price
    discipline). Stored on holdings.target_price for new positions only.
    """
    import yfinance as yf
    try:
        from fundamentals_cache import get_info; info = get_info(ticker)
        price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
        target_price = info.get("targetMeanPrice")  # captured at entry, never overwritten
    except Exception:
        price = None
        target_price = None

    if not price or price <= 0:
        log_trade(f"SKIP | {pname} | BUY {ticker} | no price data")
        return None

    # CASH WALL: Verify cash FIRST, cap allocation to available, THEN calculate shares.
    # This is the atomic sequence that prevents overspending.
    verified_cash = get_verified_cash(pid)
    available = max(0, verified_cash - reserve)

    # Cap allocation to what this portfolio can actually afford RIGHT NOW
    actual_alloc = min(alloc, available)
    if actual_alloc < 500:
        log_trade(f"SKIP | {pname} | BUY {ticker} | insufficient funds (want ${alloc:,.0f}, have ${available:,.2f})")
        return None

    num_shares = int(actual_alloc / price)
    if num_shares <= 0:
        return None

    cost = num_shares * price
    logger.info(f"ORDER SIZING: {pname} | {ticker} | {num_shares} shares @ ${price:,.2f} = ${cost:,.2f} | alloc=${alloc:,.0f} capped=${actual_alloc:,.0f} avail=${available:,.2f}")

    if dry_run:
        log_trade(f"DRY-BUY | {pname} | {ticker} | {num_shares} shares @ ${price:,.2f} = ${cost:,.2f} | {reason}")
        return {"ticker": ticker, "shares": num_shares, "price": price, "value": cost, "dry_run": True}

    # GLOBAL GUARD: Check Alpaca buying power before committing real money.
    # All 7 portfolios share one Alpaca account — this prevents collective overspend.
    try:
        _acct = client.get_account()
        _bp = float(_acct.buying_power)
        if _bp < cost + 10000:
            log_trade(f"GLOBAL LIMIT | {pname} | BUY {ticker} | Alpaca buying power ${_bp:,.0f} too low for ${cost:,.0f} order")
            return None
    except Exception:
        pass  # If we can't check, proceed with the order — per-portfolio cash wall is still enforced

    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    try:
        order = client.submit_order(MarketOrderRequest(
            symbol=to_alpaca(ticker), qty=num_shares, side=OrderSide.BUY, time_in_force=TimeInForce.DAY,
        ))
        filled_qty, filled_price = wait_for_fill(client, order, num_shares, price, ticker=ticker, pname=pname, side="BUY")
        actual_cost = filled_qty * filled_price
        log_trade(f"BUY | {pname} | {ticker} | {filled_qty} @ ${filled_price:,.2f} = ${actual_cost:,.2f} | {reason} | order={order.id}")

        # Check existing holdings for avg cost calculation
        conn = db_conn()
        c = conn.cursor()
        c.execute("SELECT shares FROM holdings WHERE portfolio_id = ? AND ticker = ?", (pid, ticker))
        existing = c.fetchone()
        conn.close()

        db_ok = _record_trade_with_retry(
            pid, pname, ticker, "buy", filled_qty, filled_price, actual_cost, reason,
            existing_shares=existing[0] if existing and existing[0] > 0 else 0,
            order_id=str(order.id),
            target_price=target_price,
            target_source="yfinance_mean" if target_price else None,
        )
        if not db_ok:
            log_trade(f"CIRCUIT BREAKER | {pname} | DB write failed on BUY {ticker}")
            return {"halted": True}

        return {"ticker": ticker, "shares": filled_qty, "price": filled_price,
                "value": actual_cost, "order_id": str(order.id)}

    except Exception as e:
        log_trade(f"ERROR | {pname} | BUY {ticker} | {e}")
        return None


# ---------------------------------------------------------------------------
# Step 1: Sync DB with Alpaca
# ---------------------------------------------------------------------------


def _record_trade_with_retry(pid, pname, ticker, action, shares, price, total_value, reason,
                              existing_shares=0, sell_all=False, max_retries=10, order_id=None,
                              target_price=None, target_source=None):
    """Back-compat wrapper. The canonical recorder is trade_recorder.record_trade."""
    return record_trade(
        pid, pname, ticker, action, shares, price, total_value, reason,
        order_id=order_id, sell_all=sell_all, max_retries=max_retries,
        target_price=target_price, target_source=target_source,
    )


def sync_with_alpaca(client):
    """Reconcile DB holdings and cash with Alpaca account state."""
    logger.info("== STEP 1: Syncing DB with Alpaca ==")

    acct = retry(lambda: client.get_account(), attempts=3, delay=5, label="alpaca.get_account")
    alpaca_equity = float(acct.equity)
    alpaca_cash = float(acct.cash)
    alpaca_buying_power = float(acct.buying_power)
    logger.info(f"Alpaca account: equity=${alpaca_equity:,.2f}, cash=${alpaca_cash:,.2f}, buying_power=${alpaca_buying_power:,.2f}")

    # Get Alpaca positions
    positions = retry(lambda: client.get_all_positions(), attempts=3, delay=5, label="alpaca.get_positions")
    alpaca_positions = {}
    for p in positions:
        alpaca_positions[from_alpaca(p.symbol)] = {
            "qty": float(p.qty),
            "avg_entry": float(p.avg_entry_price),
            "current_price": float(p.current_price),
            "market_value": float(p.market_value),
        }
    logger.info(f"Alpaca positions: {len(alpaca_positions)} tickers")

    # Get DB state
    conn = db_conn()
    c = conn.cursor()

    # Build DB aggregate: total shares per ticker across all portfolios
    c.execute("""
        SELECT h.ticker, SUM(h.shares) as total_shares
        FROM holdings h
        JOIN portfolios p ON h.portfolio_id = p.id
        WHERE p.is_active = 1 AND h.shares > 0
        GROUP BY h.ticker
    """)
    db_totals = {row[0]: row[1] for row in c.fetchall()}

    fixes = []

    # Compare DB totals vs Alpaca positions
    all_tickers = set(list(db_totals.keys()) + list(alpaca_positions.keys()))
    for ticker in sorted(all_tickers):
        db_shares = db_totals.get(ticker, 0)
        alp = alpaca_positions.get(ticker)
        alp_shares = alp["qty"] if alp else 0

        if abs(db_shares - alp_shares) > 0.01:
            fixes.append({
                "ticker": ticker,
                "db_shares": db_shares,
                "alpaca_shares": alp_shares,
                "diff": alp_shares - db_shares,
            })
            logger.warning(f"MISMATCH: {ticker} — DB={db_shares:.0f}, Alpaca={alp_shares:.0f} (diff={alp_shares - db_shares:+.0f})")

    # Recalculate portfolio cash from transactions
    c.execute("SELECT id, name, starting_cash FROM portfolios WHERE is_active = 1")
    portfolios = c.fetchall()

    for pid, pname, starting_cash in portfolios:
        # Sum all transaction values
        c.execute("""
            SELECT action, SUM(total_value) FROM transactions
            WHERE portfolio_id = ?
            GROUP BY action
        """, (pid,))
        tx_sums = {row[0]: row[1] for row in c.fetchall()}
        total_buys = tx_sums.get("buy", 0)
        total_sells = tx_sums.get("sell", 0)
        total_dividends = tx_sums.get("dividend", 0)
        calculated_cash = starting_cash - total_buys + total_sells + total_dividends

        # Get current DB cash
        c.execute("SELECT current_cash FROM portfolios WHERE id = ?", (pid,))
        db_cash = c.fetchone()[0]

        if abs(calculated_cash - db_cash) > 0.01:
            logger.warning(f"CASH FIX: {pname} — DB=${db_cash:,.2f} → calculated=${calculated_cash:,.2f}")
            c.execute("UPDATE portfolios SET current_cash = ? WHERE id = ?", (calculated_cash, pid))

    conn.commit()

    # Report share mismatches (don't auto-fix — flag for manual review)
    if fixes:
        logger.warning(f"{len(fixes)} position mismatches found between DB and Alpaca.")
        logger.warning("These may be from unfilled limit orders. Review manually.")
        # For unfilled orders: check Alpaca order history
        try:
            from alpaca.trading.requests import GetOrdersRequest
            from alpaca.trading.enums import QueryOrderStatus
            req = GetOrdersRequest(status=QueryOrderStatus.ALL, limit=100)
            orders = client.get_orders(filter=req)
            unfilled = [o for o in orders if o.status in ("expired", "canceled", "pending_cancel")]
            if unfilled:
                logger.info(f"Found {len(unfilled)} expired/canceled orders:")
                for o in unfilled[:10]:
                    logger.info(f"  {o.side} {o.qty} {from_alpaca(o.symbol)} @ {o.limit_price or 'MKT'} — {o.status} ({o.created_at.strftime('%m/%d')})")
        except Exception as e:
            logger.warning(f"Could not check order history: {e}")
    else:
        logger.info("All positions match.")

    conn.close()
    return alpaca_equity, alpaca_cash, alpaca_buying_power, fixes


# ---------------------------------------------------------------------------
# Step 2: Run Decision Engine
# ---------------------------------------------------------------------------

def run_decision_engine():
    """Run decision_engine.py --json --rescreen and return signals."""
    logger.info("== STEP 2: Running Decision Engine ==")

    # 1800s = 30 min. Decision engine grew to ~15-25 min after the May 8
    # alphabetic-bias fix lifted the candidate cap. 600s was below the new
    # floor and triggered timeouts.
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "decision_engine.py"), "--json", "--rescreen"],
        capture_output=True, text=True, timeout=1800,
        cwd=str(SCRIPTS_DIR),
        env={**os.environ},
    )

    if result.returncode != 0:
        logger.error(f"Decision engine failed (exit {result.returncode})")
        if result.stderr:
            logger.error(f"stderr: {result.stderr[-500:]}")
        return None

    try:
        data = json.loads(result.stdout)
        signals = data.get("signals", [])
        optimization = data.get("portfolio_optimization", {})
        logger.info(f"Generated {len(signals)} signals across {len(optimization)} portfolios")

        # Save signals to file for website
        SIGNALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SIGNALS_FILE, "w") as f:
            json.dump(data, f, indent=2, default=str)
        logger.info(f"Signals saved to {SIGNALS_FILE}")

        return data
    except json.JSONDecodeError as e:
        logger.error(f"Decision engine output is not valid JSON: {e}")
        return None


# ---------------------------------------------------------------------------
# Step 3: Execute Trades
# ---------------------------------------------------------------------------

def check_round_trips(ticker, portfolio_id):
    """Check if we've done too many round-trips on this ticker this week."""
    conn = db_conn()
    c = conn.cursor()
    week_ago = (now_et() - timedelta(days=7)).strftime("%Y-%m-%d")
    c.execute("""
        SELECT COUNT(DISTINCT action) FROM transactions
        WHERE portfolio_id = ? AND ticker = ? AND executed_at >= ?
    """, (portfolio_id, ticker, week_ago))
    distinct_actions = c.fetchone()[0]
    conn.close()
    # If both buy and sell in past week, that's one round trip
    return distinct_actions >= 2




def is_rebalance_day():
    """Check if today is the first trading day of the month."""
    t = now_et()
    if t.weekday() >= 5:
        return False
    # First trading day: either day 1 on a weekday, or first Monday after a weekend start
    if t.day == 1:
        return True
    if t.day == 2 and t.weekday() == 0:  # Monday the 2nd (1st was Sunday)
        return True
    if t.day == 3 and t.weekday() == 0:  # Monday the 3rd (1st was Saturday)
        return True
    return False


def check_concentration(client, dry_run=False):
    """Monthly rebalance: trim any position > MAX_POSITION_PCT to REBALANCE_TRIM_TARGET.
    Returns list of executed rebalance trades."""
    if not is_rebalance_day():
        logger.info("Not rebalance day — skipping monthly concentration rebalance")
        return []

    logger.info("== MONTHLY REBALANCE: Checking position concentration ==")

    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    import yfinance as yf

    conn = db_conn()
    c = conn.cursor()
    c.execute("SELECT id, name, current_cash, starting_cash FROM portfolios WHERE is_active = 1")
    portfolios = c.fetchall()
    conn.close()

    executed = []

    for pid, pname, cash, starting in portfolios:
        conn = db_conn()
        c = conn.cursor()
        c.execute("SELECT ticker, shares, avg_cost FROM holdings WHERE portfolio_id = ? AND shares > 0", (pid,))
        holdings = c.fetchall()
        conn.close()

        if not holdings:
            continue

        # Get current prices for all holdings
        tickers = [h[0] for h in holdings]
        prices = {}
        try:
            import yfinance as yf
            data = yf.download(tickers, period="1d", progress=False, threads=True)
            if 'Close' in data.columns or len(tickers) == 1:
                close = data['Close'] if len(tickers) > 1 else data[['Close']]
                if hasattr(close, 'iloc'):
                    row = close.iloc[-1]
                    for t in tickers:
                        col = t if t in row.index else None
                        if col and not (row[col] != row[col]):
                            prices[t] = float(row[col])
        except Exception as e:
            logger.warning(f"Price fetch for rebalance failed: {e}")
            continue

        # Calculate total portfolio value (holdings + cash)
        holdings_value = sum(h[1] * prices.get(h[0], h[2]) for h in holdings)
        total_value = holdings_value + cash

        if total_value <= 0:
            continue

        # Check each position
        for ticker, shares, avg_cost in holdings:
            # SGOV is money market — exempt from concentration limits
            if ticker == MONEY_MARKET_TICKER:
                continue

            price = prices.get(ticker)
            if not price:
                continue

            position_value = shares * price
            position_pct = position_value / total_value

            if position_pct <= MAX_POSITION_PCT:
                continue

            # Position is overweight — trim to REBALANCE_TRIM_TARGET
            target_value = total_value * REBALANCE_TRIM_TARGET
            trim_value = position_value - target_value
            trim_shares = int(trim_value / price)

            if trim_shares <= 0:
                continue

            reason = f"REBALANCE: {ticker} at {position_pct:.1%} > {MAX_POSITION_PCT:.0%} cap, trimming to {REBALANCE_TRIM_TARGET:.0%}"
            log_trade(f"REBALANCE | {pname} | {ticker} | {position_pct:.1%} -> {REBALANCE_TRIM_TARGET:.0%} | trim {trim_shares} shares")

            if dry_run:
                log_trade(f"DRY-REBALANCE | {pname} | {ticker} | {trim_shares} shares @ ${price:,.2f} | {reason}")
                executed.append({"portfolio": pname, "action": "REBALANCE-SELL", "ticker": ticker,
                                "shares": trim_shares, "price": price, "reason": reason, "dry_run": True})
                continue

            trim_shares = clamp_sell_to_long(client, to_alpaca(ticker), trim_shares)
            if trim_shares <= 0:
                log_trade(f"REBALANCE-SELL BLOCKED | {pname} | {ticker} | not long at Alpaca (short-prevention)")
                continue
            try:
                req = MarketOrderRequest(
                    symbol=to_alpaca(ticker), qty=trim_shares,
                    side=OrderSide.SELL, time_in_force=TimeInForce.DAY
                )
                order = client.submit_order(req)
                filled_qty, filled_price = wait_for_fill(
                    client, order, trim_shares, price,
                    ticker=ticker, pname=pname, side="REBALANCE-SELL"
                )
                sell_value = filled_qty * filled_price

                log_trade(f"REBALANCE-SELL | {pname} | {ticker} | {filled_qty} @ ${filled_price:,.2f} = ${sell_value:,.2f} | {reason} | order={order.id}")

                # RULE 3: Record sell with retry — Alpaca already executed
                sell_all = (max(0, int(shares) - filled_qty) == 0)
                _record_trade_with_retry(
                    pid, pname, ticker, "sell", filled_qty, filled_price, sell_value, reason,
                    sell_all=sell_all, order_id=str(order.id),
                )

                executed.append({"portfolio": pname, "action": "REBALANCE-SELL", "ticker": ticker,
                                "shares": filled_qty, "price": filled_price, "reason": reason,
                                "order_id": str(order.id)})

            except Exception as e:
                log_trade(f"ERROR | {pname} | REBALANCE {ticker} | {e}")

    if executed:
        logger.info(f"Monthly rebalance: {len(executed)} positions trimmed")
    else:
        logger.info("Monthly rebalance: all positions within concentration limits")

    return executed




def plan_portfolio(pid, pname, starting, signal_map, portfolio_signals, universes):
    """Best-in-class plan (to_sell, to_buy, target) for ONE portfolio. SINGLE SOURCE OF
    TRUTH shared by the live trader (autonomous_trader) and the dashboard planned-actions
    panel (build_planned_actions). Applies the portfolio universe, the style gate, and
    target-price discipline. Pure planning: reads holdings/cash, performs NO execution
    and NO writes."""
    # 1. Get current non-SGOV holdings
    conn = db_conn()
    c = conn.cursor()
    c.execute("SELECT ticker, shares, avg_cost FROM holdings WHERE portfolio_id = ? AND shares > 0", (pid,))
    current_holdings = c.fetchall()
    conn.close()

    held_map = {}  # ticker -> {shares, avg_cost}
    for ticker, shares, avg_cost in current_holdings:
        if ticker == MONEY_MARKET_TICKER:
            continue
        held_map[ticker] = {"shares": int(shares), "avg_cost": avg_cost}

    # 2. Score ALL candidates: held + universe
    universe = universes.get(pname, {})
    if isinstance(universe, dict):
        allowed = set(universe.get("holdings", []) + universe.get("candidates", []))
    else:
        allowed = set(universe)

    port_sigs = portfolio_signals.get(pname, {})
    all_scored = {}

    # Score held stocks
    for ticker, info in held_map.items():
        if ticker in port_sigs:
            score = port_sigs[ticker].get("score", 0)
        else:
            sig = signal_map.get(ticker)
            score = sig.get("score", 0) if sig else 0
        all_scored[ticker] = {"ticker": ticker, "score": score, "held": True,
                              "shares": info["shares"], "avg_cost": info["avg_cost"]}

    # Score universe candidates (not already held)
    for ticker in allowed:
        if ticker in all_scored or ticker == MONEY_MARKET_TICKER:
            continue
        if ticker in port_sigs:
            score = port_sigs[ticker].get("score", 0)
        else:
            sig = signal_map.get(ticker)
            if not sig:
                continue
            score = sig.get("score", 0)
        # Style gate check — only for candidates, not existing holdings
        gate_info = signal_map.get(ticker, {}).get("info")
        gate_result = passes_style_gate(ticker, pname, gate_info)
        if not gate_result["pass"]:
            continue
        all_scored[ticker] = {"ticker": ticker, "score": score, "held": False,
                              "shares": 0, "avg_cost": 0}

    # 3. Rank by score — top MAX_HOLDINGS are the target portfolio
    ranked = sorted(all_scored.values(), key=lambda x: x["score"], reverse=True)
    target = ranked[:MAX_HOLDINGS]
    target_tickers = {s["ticker"] for s in target}

    logger.info(f"{pname}: {len(held_map)} held, {len(all_scored)} scored, target={[s['ticker']+'('+str(s['score'])+')' for s in target[:5]]}...")

    # 4. Determine sells: held but NOT in target
    # If TARGET_PRICE_DISCIPLINE is ON for this portfolio, replace the
    # default "not in top 10" rule with the discipline triggers.
    to_sell = []
    if TARGET_PRICE_DISCIPLINE.get(pname, False):
        # Target-price discipline mode: hold through score variations.
        # Look up target_price + portfolio_value once; eval each holding.
        conn = db_conn()
        c = conn.cursor()
        c.execute(
            "SELECT ticker, shares, target_price FROM holdings "
            "WHERE portfolio_id = ? AND shares > 0",
            (pid,),
        )
        held_with_targets = {row[0]: (int(row[1]), row[2]) for row in c.fetchall()}
        conn.close()

        # Compute portfolio total value (cash + holdings × current price)
        portfolio_total_value = 0
        cash_now = get_verified_cash(pid)
        portfolio_total_value += cash_now
        for ticker_h, (shr_h, _) in held_with_targets.items():
            sig_h = signal_map.get(ticker_h, {})
            price_h = sig_h.get("price", 0)
            portfolio_total_value += shr_h * (price_h if price_h > 0 else 0)

        for s in ranked:
            if not s["held"]:
                continue
            shares_h, target_price_h = held_with_targets.get(s["ticker"], (0, None))
            sig_h = signal_map.get(s["ticker"], {})
            current_price = sig_h.get("price", 0) if sig_h else 0
            if current_price <= 0:
                continue  # cant evaluate without price
            should_sell, reason = evaluate_target_discipline_sell(
                pname, s["ticker"], current_price, target_price_h,
                shares_h, portfolio_total_value,
                fwd_eps_revision_pct=None,  # TODO: wire forward EPS check
            )
            if should_sell:
                to_sell.append({**s, "discipline_reason": reason})
                logger.info(
                    f"{pname}: DISCIPLINE-SELL {s['ticker']} — {reason}"
                )
        logger.info(
            f"{pname}: target-price discipline ON — "
            f"{len(to_sell)} sells from {len(held_with_targets)} holdings"
        )
    else:
        # Default behavior: sell anything held but not in today's top 10
        for s in ranked:
            if s["held"] and s["ticker"] not in target_tickers:
                to_sell.append(s)
    to_sell.sort(key=lambda x: x["score"])  # Sell weakest first

    # 5. Determine buys: in target but NOT held (or held but underweight)
    to_buy = []
    for s in target:
        if s["score"] < SCORE_BUY_MINIMUM:
            continue  # Don't deploy cash into stocks scoring below minimum
        if not s["held"]:
            to_buy.append(s)
        elif s["held"]:
            # Check if underweight — use market price from signals, fall back to cost basis
            sig_price = signal_map.get(s["ticker"], {}).get("price", 0)
            existing_val = s["shares"] * (sig_price if sig_price > 0 else s["avg_cost"])
            target_alloc = starting * (0.12 if s["score"] >= 5 else 0.10 if s["score"] >= 3 else 0.08)
            if existing_val < target_alloc * 0.80:  # More than 20% underweight
                to_buy.append({**s, "is_add": True, "gap": target_alloc - existing_val})
    to_buy.sort(key=lambda x: x["score"], reverse=True)  # Buy strongest first
    return to_sell, to_buy, target


def execute_trades(client, data, dry_run=False, seed_mode=False):
    """Execute trades: Phase 1 safety sells, then best-in-class optimization per portfolio."""
    logger.info("== STEP 3: Executing Trades ==")

    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce

    # Check market hours
    t = now_et()
    if t.weekday() >= 5:
        logger.info("Market closed (weekend). Skipping execution.")
        return []
    if t.hour < 10 or t.hour >= 16:
        logger.info(f"Outside trading window (10 AM - 4 PM ET). Current: {t.strftime('%I:%M %p ET')}")
        return []

    signals = data.get("signals", [])
    signal_map = {s["ticker"]: s for s in signals}
    portfolio_signals = data.get("portfolio_signals", {})

    # Load portfolio universes
    with open(UNIVERSES_FILE) as f:
        universes = json.load(f)

    conn = db_conn()
    c = conn.cursor()
    c.execute("SELECT id, name, current_cash, starting_cash FROM portfolios WHERE is_active = 1")
    portfolios = c.fetchall()
    conn.close()

    executed = []
    halted_portfolios = set()  # Circuit breaker: portfolios with DB write failures

    # --- PHASE 1: SAFETY SELLS (score <= -3 or -5) ---
    # These are emergency exits — run before optimization. Optimization handles everything else.
    logger.info("--- Phase 1: Safety Sells ---")
    for pid, pname, cash, starting in portfolios:
        conn = db_conn()
        c = conn.cursor()
        c.execute("SELECT ticker, shares, avg_cost FROM holdings WHERE portfolio_id = ? AND shares > 0", (pid,))
        holdings = c.fetchall()
        conn.close()

        for ticker, shares, avg_cost in holdings:
            if ticker == MONEY_MARKET_TICKER:
                continue
            sig = signal_map.get(ticker)
            if not sig:
                continue

            score = sig.get("score", 0)
            shares = int(shares)

            sell_shares = 0
            reason = ""

            if score <= SCORE_SELL_THRESHOLD:
                sell_shares = shares
                reason = f"EMERGENCY SELL ALL (score {score})"
            elif score <= SCORE_TRIM_THRESHOLD:
                sell_shares = max(1, shares // 2)
                reason = f"SAFETY TRIM 50% (score {score})"
            if sell_shares <= 0:
                continue

            if check_round_trips(ticker, pid):
                log_trade(f"SKIP | {pname} | {ticker} | round-trip limit reached this week")
                continue

            result = _execute_sell_order(client, pid, pname, ticker, sell_shares, reason, dry_run)
            if result and result.get("halted"):
                halted_portfolios.add(pid)
                break
            if result:
                executed.append({"portfolio": pname, "action": "SAFETY-SELL", "ticker": ticker,
                                "shares": result["shares"], "price": result["price"], "reason": reason,
                                **({} if dry_run else {"order_id": result.get("order_id", "")})})

    # --- TRAILING STOP CHECK (between sells and buys) ---
    logger.info("--- Trailing Stop Check ---")
    try:
        from trailing_stop_manager import run_full_cycle as run_trailing_stops
        stop_triggered = run_trailing_stops(dry_run=dry_run)
        for st in stop_triggered:
            pid_stop = st["portfolio_id"]
            ticker_stop = st["ticker"]
            shares_stop = st["shares"]
            price_stop = st["current_price"]
            reason_stop = st["reason"]

            if dry_run:
                log_trade(f"DRY-STOP-SELL | {st['portfolio_name']} | {ticker_stop} | "
                         f"{shares_stop} shares @ ${price_stop:,.2f} | {reason_stop}")
                executed.append({"portfolio": st["portfolio_name"], "action": "STOP-SELL",
                                "ticker": ticker_stop, "shares": shares_stop,
                                "price": price_stop, "reason": reason_stop, "dry_run": True})
                continue

            shares_stop = clamp_sell_to_long(client, to_alpaca(ticker_stop), int(shares_stop))
            if shares_stop <= 0:
                log_trade(f"STOP-SELL BLOCKED | {st['portfolio_name']} | {ticker_stop} | not long at Alpaca (short-prevention)")
                continue
            try:
                req = MarketOrderRequest(
                    symbol=to_alpaca(ticker_stop), qty=int(shares_stop),
                    side=OrderSide.SELL, time_in_force=TimeInForce.DAY,
                )
                order = client.submit_order(req)
                filled_qty, filled_price = wait_for_fill(
                    client, order, int(shares_stop), price_stop,
                    ticker=ticker_stop,
                    pname=st.get("portfolio_name", ""), side="STOP-SELL"
                )
                sell_value = filled_qty * filled_price

                log_trade(f"STOP-SELL | {st['portfolio_name']} | {ticker_stop} | "
                         f"{filled_qty} @ ${filled_price:,.2f} = ${sell_value:,.2f} | {reason_stop} | order={order.id}")

                # Compute sell_all from actual fill (was hardcoded True before May 9)
                _stop_sell_all = (filled_qty >= int(shares_stop))
                _record_trade_with_retry(
                    pid_stop, st["portfolio_name"], ticker_stop, "sell",
                    filled_qty, filled_price, sell_value, reason_stop,
                    sell_all=_stop_sell_all,
                    order_id=str(order.id),
                )

                executed.append({"portfolio": st["portfolio_name"], "action": "STOP-SELL",
                                "ticker": ticker_stop, "shares": filled_qty,
                                "price": filled_price, "reason": reason_stop,
                                "order_id": str(order.id)})

            except Exception as e:
                log_trade(f"ERROR | {st['portfolio_name']} | STOP-SELL {ticker_stop} | {e}")

    except Exception as e:
        logger.error(f"Trailing stop check failed (non-fatal): {e}")

    # (Pre-buy SGOV liquidation is now handled inside optimize_portfolio)



    # --- BEST-IN-CLASS OPTIMIZATION (per portfolio) ---
    # For each portfolio: rank everything, hold the top 10, sell the rest, buy what's missing.
    logger.info("--- Best-in-Class Optimization ---")

    for pid, pname, _, starting in portfolios:
        if pid in halted_portfolios:
            logger.warning(f"{pname}: HALTED — skipping (circuit breaker)")
            continue
        if pname == "Treasury Reserve":
            continue

        reserve = starting * MIN_CASH_RESERVE_PCT

        to_sell, to_buy, target = plan_portfolio(pid, pname, starting, signal_map, portfolio_signals, universes)

        if not to_sell and not to_buy:
            logger.info(f"{pname}: portfolio is optimal — no changes needed")
            continue

        logger.info(f"{pname}: {len(to_sell)} sells, {len(to_buy)} buys planned")

        # 6. Execute ALL sells first — frees cash and position slots
        for s in to_sell:
            if pid in halted_portfolios:
                break
            ticker = s["ticker"]
            shares = s["shares"]

            if check_round_trips(ticker, pid):
                log_trade(f"SKIP | {pname} | SELL {ticker} | round-trip limit")
                continue

            reason = f"Not in top {MAX_HOLDINGS} (score {s['score']})"
            result = _execute_sell_order(client, pid, pname, ticker, shares, reason, dry_run)
            if result and result.get("halted"):
                halted_portfolios.add(pid)
                break
            if result:
                executed.append({"portfolio": pname, "action": "OPTIMIZATION-SELL", "ticker": ticker,
                                "shares": result["shares"], "price": result["price"], "reason": reason,
                                **({} if dry_run else {"order_id": result.get("order_id", "")})})

        if pid in halted_portfolios:
            continue

        # 7. Global buying power safety check — stop if Alpaca is running low
        try:
            _acct = client.get_account()
            _buying_power = float(_acct.buying_power)
            if _buying_power < 10000:
                log_trade(f"GLOBAL LIMIT | {pname} | Alpaca buying power ${_buying_power:,.2f} < $10K — skipping buys")
                continue
        except Exception:
            pass

        # 8. CANSLIM M rule: market must be in confirmed uptrend (SPY > 200-day SMA)
        if pname == "Momentum Growth" and to_buy:
            try:
                import yfinance as yf
                spy = yf.Ticker("SPY").history(period="250d")
                if len(spy) >= 200:
                    spy_close = spy["Close"]
                    sma200 = spy_close.rolling(200).mean().iloc[-1]
                    if spy_close.iloc[-1] < sma200:
                        logger.info(f"{pname}: SPY below 200-day SMA — CANSLIM M rule blocks new buys")
                        to_buy = [s for s in to_buy if s["held"]]  # Only allow adds to existing, no new positions
            except Exception as e:
                logger.warning(f"SPY trend check failed (non-fatal): {e}")

        # Execute buys in score order (strongest first)
        for s in to_buy:
            if pid in halted_portfolios:
                break
            ticker = s["ticker"]

            if check_round_trips(ticker, pid):
                log_trade(f"SKIP | {pname} | BUY {ticker} | round-trip limit")
                continue

            blocked, reason_block = is_in_cooldown(pid, pname, ticker, s.get("score"))
            if blocked:
                log_trade(f"SKIP | {pname} | BUY {ticker} | {reason_block}")
                continue

            # Position sizing
            if s["score"] >= 5:
                alloc_pct = 0.12
            elif s["score"] >= 3:
                alloc_pct = 0.10
            else:
                alloc_pct = 0.08
            target_alloc = starting * alloc_pct

            # If adding to existing position, only buy the gap
            if s.get("is_add"):
                target_alloc = min(target_alloc, s.get("gap", target_alloc))

            if target_alloc < 500:
                continue

            is_add = s.get("is_add", False) or s["held"]
            reason = f"Top {MAX_HOLDINGS} (score {s['score']}) — {'add to position' if is_add else 'new position'}"
            result = _execute_buy_order(client, pid, pname, ticker, target_alloc, reason, starting, reserve, dry_run)
            if result and result.get("halted"):
                halted_portfolios.add(pid)
                break
            if result and not result.get("dry_run"):
                executed.append({"portfolio": pname, "action": "ADD" if is_add else "BUY", "ticker": ticker,
                                "shares": result["shares"], "price": result["price"], "reason": reason,
                                "order_id": result.get("order_id", "")})
                # Delay between buys — ensures DB commit is visible to next get_verified_cash()
                import time
                time.sleep(2)
            elif result:
                executed.append({"portfolio": pname, "action": "ADD" if is_add else "BUY", "ticker": ticker,
                                "shares": result["shares"], "price": result["price"], "reason": reason, "dry_run": True})

    # POST-TRADE: Idle cash stays as cash (SGOV sweep removed)

    # RULE 5: Post-trade reconciliation
    try:
        reconcile_with_alpaca(client)
    except Exception as e:
        logger.error(f"Post-trade reconciliation failed: {e}")

    # RULE 5.25: Initialize trailing stops for any newly-bought positions.
    # Without this, new positions are unprotected for up to 15 minutes
    # (until the next stop_check cron fires).
    try:
        from trailing_stop_manager import initialize_stops as _init_stops
        _init_stops()
    except Exception as e:
        logger.error(f"Post-trade trailing-stop init failed: {e}")

    # RULE 5.5: Holdings invariant assertion
    # Sell paths should DELETE rows when position fully closes. If we find
    # rows with shares <= 0.001 here, a code path bypassed the DELETE logic.
    try:
        orphans = assert_no_orphan_holdings()
        if orphans:
            logger.error(f"HOLDINGS INVARIANT VIOLATED: {len(orphans)} orphan rows")
            for o in orphans:
                logger.error(f"  ORPHAN: {o['portfolio']} | {o['ticker']} | shares={o['shares']}")
            post_orphan_alert(orphans)
    except Exception as e:
        logger.error(f"Orphan-holdings check failed: {e}")

    # RULE 6: Post-trade compliance verification
    # Verify each portfolio conforms to design: holds its top-scoring stocks,
    # within position count limits, cash accounting is correct.
    logger.info("--- Post-Trade Compliance Check ---")
    conn = db_conn()
    c = conn.cursor()
    c.execute("SELECT id, name, starting_cash FROM portfolios WHERE is_active = 1")
    all_ports = c.fetchall()
    conn.close()
    violations = []
    for _pid, _pname, _starting in all_ports:
        if _pname == "Treasury Reserve":
            continue

        # Position count check
        pos_count = get_position_count(_pid)
        if pos_count > MAX_HOLDINGS:
            violations.append(f"{_pname}: {pos_count} positions (max {MAX_HOLDINGS})")
        if pos_count < MIN_HOLDINGS and pos_count > 0:
            violations.append(f"{_pname}: only {pos_count} positions (min {MIN_HOLDINGS}) — universe may be too restrictive")

        # Cash accounting check
        verified = get_verified_cash(_pid)
        conn = db_conn()
        c = conn.cursor()
        c.execute("SELECT current_cash FROM portfolios WHERE id = ?", (_pid,))
        db_cash = c.fetchone()[0]
        conn.close()
        if abs(verified - db_cash) > 1:
            violations.append(f"{_pname}: cash mismatch DB=${db_cash:,.2f} vs replay=${verified:,.2f}")

        # Best-in-class check: are we holding our top-ranked stocks?
        # Re-score to see what we SHOULD hold vs what we DO hold
        _port_sigs = portfolio_signals.get(_pname, {})
        _universe = universes.get(_pname, {})
        if isinstance(_universe, dict):
            _allowed = set(_universe.get("holdings", []) + _universe.get("candidates", []))
        else:
            _allowed = set(_universe)

        _scores = {}
        for _tk, _psig in _port_sigs.items():
            if _tk != MONEY_MARKET_TICKER:
                _scores[_tk] = _psig.get("score", 0)
        for _tk in _allowed:
            if _tk not in _scores and _tk != MONEY_MARKET_TICKER:
                _sig = signal_map.get(_tk)
                if _sig:
                    _scores[_tk] = _sig.get("score", 0)

        _target_top = sorted(_scores.items(), key=lambda x: x[1], reverse=True)[:MAX_HOLDINGS]
        _target_set = {t[0] for t in _target_top if t[1] >= SCORE_BUY_MINIMUM}

        conn = db_conn()
        c = conn.cursor()
        c.execute("SELECT ticker FROM holdings WHERE portfolio_id = ? AND shares > 0 AND ticker != ?",
                  (_pid, MONEY_MARKET_TICKER))
        _held_set = {row[0] for row in c.fetchall()}
        conn.close()

        _should_hold = _target_set - _held_set
        _should_sell = _held_set - _target_set
        if _should_hold:
            violations.append(f"{_pname}: should hold but doesn't: {', '.join(sorted(_should_hold))}")
        if _should_sell:
            violations.append(f"{_pname}: holds but shouldn't: {', '.join(sorted(_should_sell))}")

    if violations:
        logger.warning(f"COMPLIANCE REPORT ({len(violations)} items):")
        for v in violations:
            logger.warning(f"  {v}")
        log_trade(f"COMPLIANCE | {len(violations)} items: {'; '.join(violations[:5])}")
    else:
        logger.info("All portfolios in compliance with best-in-class design")

    return executed


# ---------------------------------------------------------------------------
# Step 4: Summary
# ---------------------------------------------------------------------------


def post_trade_sync_check(client):
    """Re-check DB vs Alpaca after trades to find remaining mismatches only."""
    logger.info("== Post-trade sync check ==")
    positions = retry(lambda: client.get_all_positions(), attempts=3, delay=5, label="alpaca.post_check")
    alpaca_positions = {}
    for p in positions:
        alpaca_positions[from_alpaca(p.symbol)] = float(p.qty)

    conn = db_conn()
    c = conn.cursor()
    c.execute("""
        SELECT h.ticker, SUM(h.shares) as total_shares
        FROM holdings h
        JOIN portfolios p ON h.portfolio_id = p.id
        WHERE p.is_active = 1 AND h.shares > 0
        GROUP BY h.ticker
    """)
    db_totals = {row[0]: row[1] for row in c.fetchall()}
    conn.close()

    remaining = []
    all_tickers = set(list(db_totals.keys()) + list(alpaca_positions.keys()))
    for ticker in sorted(all_tickers):
        db_shares = db_totals.get(ticker, 0)
        alp_shares = alpaca_positions.get(ticker, 0)
        if abs(db_shares - alp_shares) > 0.01:
            remaining.append({
                "ticker": ticker,
                "db_shares": db_shares,
                "alpaca_shares": alp_shares,
                "diff": alp_shares - db_shares,
            })
            logger.warning(f"POST-TRADE MISMATCH: {ticker} -- DB={db_shares:.0f}, Alpaca={alp_shares:.0f}")

    if not remaining:
        logger.info("Post-trade: all positions match.")
    else:
        logger.warning(f"Post-trade: {len(remaining)} mismatches remain.")
    return remaining


def format_summary(executed, sync_fixes, dry_run=False):
    """Format execution summary for stdout (Slack posting)."""
    lines = []
    mode = "DRY RUN" if dry_run else "LIVE"
    lines.append(f"**Autonomous Trading Report ({mode})** — {now_et().strftime('%B %d, %Y %I:%M %p ET')}\n")

    if sync_fixes:
        lines.append(f"**Sync:** {len(sync_fixes)} position mismatches found")
        for fix in sync_fixes[:5]:
            lines.append(f"  - {fix['ticker']}: DB={fix['db_shares']:.0f}, Alpaca={fix['alpaca_shares']:.0f}")
        lines.append("")

    sells = [e for e in executed if e["action"] == "SELL"]
    buys = [e for e in executed if e["action"] == "BUY"]

    if sells:
        lines.append(f"**Sells ({len(sells)}):**")
        for e in sells:
            lines.append(f"  - {e['portfolio']}: SELL {e['shares']} {e['ticker']} @ ${e['price']:,.2f} — {e['reason']}")
        lines.append("")

    if buys:
        lines.append(f"**Buys ({len(buys)}):**")
        for e in buys:
            lines.append(f"  - {e['portfolio']}: BUY {e['shares']} {e['ticker']} @ ${e['price']:,.2f} — {e['reason']}")
        lines.append("")

    if not sells and not buys:
        lines.append("No trades executed today. All positions are within score thresholds.\n")

    total_sell = sum(e["shares"] * (e["price"] or 0) for e in sells)
    total_buy = sum(e["shares"] * (e["price"] or 0) for e in buys)
    lines.append(f"**Totals:** Sold ${total_sell:,.2f} | Bought ${total_buy:,.2f} | Net ${total_sell - total_buy:+,.2f}")

    return "\n".join(lines)


def show_status(client):
    """Show current state of everything."""
    acct = client.get_account()
    logger.info(f"Alpaca Account: equity=${float(acct.equity):,.2f}, cash=${float(acct.cash):,.2f}, buying_power=${float(acct.buying_power):,.2f}")

    positions = client.get_all_positions()
    logger.info(f"Alpaca Positions ({len(positions)}):")
    for p in sorted(positions, key=lambda x: from_alpaca(x.symbol)):
        pl_pct = float(p.unrealized_plpc) * 100
        logger.info(f"  {from_alpaca(p.symbol):6s} {float(p.qty):6.0f} shares @ ${float(p.avg_entry_price):8.2f} → ${float(p.current_price):8.2f}  {pl_pct:+6.1f}%")

    conn = db_conn()
    c = conn.cursor()
    c.execute("SELECT id, name, current_cash FROM portfolios WHERE is_active = 1 ORDER BY id")
    portfolios = c.fetchall()
    logger.info(f"DB Portfolios ({len(portfolios)}):")
    for pid, pname, cash in portfolios:
        c.execute("SELECT ticker, shares FROM holdings WHERE portfolio_id = ? AND shares > 0 ORDER BY ticker", (pid,))
        holdings = c.fetchall()
        tickers = ", ".join(f"{t}({s:.0f})" for t, s in holdings)
        logger.info(f"  {pid}. {pname}: cash=${cash:,.2f} | {tickers}")
    conn.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------



def reconcile_with_alpaca(client):
    """RULE 5: Post-trade reconciliation. Compare DB vs Alpaca, create missing transactions.

    This runs AFTER all trades complete. If Alpaca has shares the DB doesn't,
    we create the missing buy transaction. If DB has shares Alpaca doesn't,
    we create the missing sell transaction.
    """
    logger.info("== POST-TRADE RECONCILIATION ==")

    positions = retry(lambda: client.get_all_positions(), attempts=3, delay=5, label="alpaca.reconcile")
    alpaca = {from_alpaca(p.symbol): {"qty": float(p.qty), "avg_entry": float(p.avg_entry_price),
                         "current_price": float(p.current_price)} for p in positions}

    conn = db_conn()
    c = conn.cursor()

    # Get DB totals per ticker across all portfolios
    c.execute("""
        SELECT h.ticker, SUM(h.shares) as db_total
        FROM holdings h JOIN portfolios p ON h.portfolio_id = p.id
        WHERE p.is_active = 1
        GROUP BY h.ticker
    """)
    db_totals = {row[0]: row[1] for row in c.fetchall()}

    mismatches = []
    for ticker in set(list(alpaca.keys()) + list(db_totals.keys())):
        db_shares = db_totals.get(ticker, 0)
        alp_shares = alpaca.get(ticker, {}).get("qty", 0)
        if abs(db_shares - alp_shares) > 0.01:
            mismatches.append({
                "ticker": ticker,
                "db": db_shares,
                "alpaca": alp_shares,
                "diff": alp_shares - db_shares,
            })

    if not mismatches:
        logger.info("Reconciliation: ALL POSITIONS MATCH — DB and Alpaca are in sync")
        conn.close()
        return True

    # Classify mismatches: minor (<=5% or <=2 shares) vs critical
    minor = []
    critical = []
    for m in mismatches:
        diff = abs(m["diff"])
        db_sh = max(m["db"], 1)
        pct_off = diff / db_sh if db_sh > 0 else diff
        if diff <= 2 or (pct_off <= 0.05 and diff <= 5):
            minor.append(m)
        else:
            critical.append(m)

    if minor:
        logger.warning(f"Reconciliation: {len(minor)} minor mismatches (rounding/timing — no action needed)")
        for m in minor:
            logger.warning(f"  {m['ticker']}: DB={m['db']:.0f} Alpaca={m['alpaca']:.0f} diff={m['diff']:+.0f}")

    if not critical:
        logger.info(f"Reconciliation: no critical mismatches — system is healthy")
        conn.close()
        return True

    # Critical mismatches — something is seriously wrong
    logger.error(f"RECONCILIATION FAILED: {len(critical)} CRITICAL mismatches")
    for m in critical:
        logger.error(f"  {m['ticker']}: DB={m['db']:.0f} Alpaca={m['alpaca']:.0f} diff={m['diff']:+.0f}")

    # Write flag file to halt next trading session
    import json as _json
    MISMATCH_FLAG_PATH.write_text(_json.dumps(critical, indent=2))
    logger.error(f"Mismatch flag written — trading halted until resolved")

    # Post to Slack
    try:
        import json, urllib.request, os
        secrets = {}
        with open(os.path.expanduser("~/.env_secrets")) as f:
            for line in f:
                line = line.strip()
                if line.startswith("export "): line = line[7:]
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    secrets[k.strip()] = v.strip().strip('"')
        token = secrets.get("SLACK_BOT_TOKEN", "")
        if token:
            msg = ":rotating_light: *BigClaw TRADING HALTED — Critical Alpaca Mismatch*\n"
            msg += f"{len(critical)} critical mismatches (>{'>'}5% or >{'>'}2 shares):\n"
            for m in critical[:10]:
                msg += f"  {m['ticker']}: DB={m['db']:.0f} Alpaca={m['alpaca']:.0f} ({m['diff']:+.0f})\n"
            if len(critical) > 10:
                msg += f"  ... and {len(critical) - 10} more\n"
            if minor:
                msg += f"\n{len(minor)} minor mismatches (rounding — ignored)\n"
            msg += "\n*Trading halted. Investigate and clear flag to resume:*\n"
            msg += "`rm ~/bigclaw-ai/logs/ALPACA_MISMATCH.flag`"
            payload = json.dumps({"channel": "D0ADHLUJ400", "text": msg}).encode()
            req = urllib.request.Request(
                "https://slack.com/api/chat.postMessage",
                data=payload,
                headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass

    conn.close()
    return False  # Mismatches found


def main():
    parser = argparse.ArgumentParser(description="BigClaw Autonomous Trader")
    parser.add_argument("--dry-run", action="store_true", help="Preview without executing")
    parser.add_argument("--sync-only", action="store_true", help="Just sync DB with Alpaca")
    parser.add_argument("--status", action="store_true", help="Show current state")
    parser.add_argument("--seed", action="store_true", help="Initial deployment: lower buy threshold to score >= 2")
    args = parser.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # LOCK: Prevent double execution. If another instance is running, exit immediately.
    # This protects against duplicate cron jobs, OpenClaw double-triggers, or manual overlap.
    lock_file = LOG_DIR / "autonomous_trader.lock"
    if lock_file.exists():
        # Check if the lock is stale (older than 30 minutes = something crashed)
        import time as _t
        lock_age = _t.time() - lock_file.stat().st_mtime
        if lock_age < 1800:  # 30 minutes
            log_trade("=== BLOCKED: Another instance is already running (lock file exists) ===")
            logger.error("Another autonomous_trader instance is running. Exiting to prevent double execution.")
            sys.exit(0)
        else:
            logger.warning(f"Stale lock file found ({lock_age:.0f}s old) — removing and proceeding")
            lock_file.unlink()

    # Create lock file
    lock_file.write_text(str(os.getpid()))
    try:
        _run_main(args)
    finally:
        # Always remove lock file when done
        if lock_file.exists():
            lock_file.unlink()


# Single source of truth for the mismatch flag path. Both accounting_audit.py
# and the post-trade sync inside this file write to this same file. Importers
# should reference this constant rather than reconstructing the path — the
# May 22 2026 incident was caused by hardcoding the wrong directory.
MISMATCH_FLAG_PATH = Path.home() / "bigclaw-ai" / "logs" / "ALPACA_MISMATCH.flag"


def verify_account_synced(halt_threshold=5):
    """PRE-TRADE GUARD (2026-07-07, after Alpaca wiped paper-account positions). Before any
    trading, confirm the live Alpaca account still holds what the DB thinks it holds. If many
    DB-held tickers are MISSING at Alpaca (the signature of an Alpaca-side account reset), set
    the global MISMATCH kill-switch and return False so callers HALT instead of selling into a
    phantom book (which opens unintended shorts). Tolerates small per-position fill lag; does
    NOT auto-clear the flag (resuming is manual); fails OPEN on a transient check error."""
    try:
        if MISMATCH_FLAG_PATH.exists():
            return False  # already halted
        client = get_trading_client()
        apos = {}
        for p in client.get_all_positions():
            apos[from_alpaca(p.symbol)] = float(p.qty)
        conn = db_conn(); c = conn.cursor()
        c.execute("SELECT ticker, SUM(shares) FROM holdings WHERE shares != 0 GROUP BY ticker")
        dbsum = dict(c.fetchall())
        conn.close()
        held = [t for t, sh in dbsum.items() if sh]
        missing = [t for t in held if abs(apos.get(t, 0)) < 0.5]
        if len(missing) >= halt_threshold:
            reason = ("PRE-TRADE GUARD: %d/%d DB positions missing at Alpaca (e.g. %s) - likely an "
                      "Alpaca account reset/liquidation. Trading auto-halted; reconcile before clearing "
                      "this flag." % (len(missing), len(held), sorted(missing)[:8]))
            MISMATCH_FLAG_PATH.parent.mkdir(parents=True, exist_ok=True)
            MISMATCH_FLAG_PATH.write_text(json.dumps({"ts": now_et().isoformat(), "reason": reason}, indent=2))
            logger.error("PRE-TRADE GUARD TRIPPED: %d/%d DB positions missing at Alpaca. Kill-switch set." % (len(missing), len(held)))
            try:
                sec = load_secrets()
                from slack_sdk import WebClient
                WebClient(token=sec["SLACK_BOT_TOKEN"]).chat_postMessage(
                    channel="D0ADHLUJ400", text=":rotating_light: *PRE-TRADE GUARD HALT* - " + reason)
            except Exception:
                pass
            return False
        return True
    except Exception as e:
        logger.warning("verify_account_synced check failed (allowing trade): %s" % e)
        return True


def _post_slack_simple(text):
    """Best-effort Slack post for guard messages. Never raises."""
    try:
        import json as _json, urllib.request as _ur
        secrets = {}
        with open(os.path.expanduser("~/.env_secrets")) as f:
            for line in f:
                line = line.strip()
                if line.startswith("export "): line = line[7:]
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    secrets[k.strip()] = v.strip().strip('"').strip("'")
        token = secrets.get("SLACK_BOT_TOKEN", "")
        if not token:
            return
        payload = _json.dumps({"channel": "D0ADHLUJ400", "text": text}).encode()
        req = _ur.Request(
            "https://slack.com/api/chat.postMessage",
            data=payload,
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        )
        _ur.urlopen(req, timeout=10)
    except Exception:
        pass


def _live_mismatch_check(client):
    """Compare DB total shares vs Alpaca positions per ticker.

    Returns list of {ticker, db, alpaca, diff} for entries that differ by
    more than 0.5 shares. Empty list means clean. Used by the startup
    guard to decide whether a stale flag can be self-cleared.
    """
    positions = retry(lambda: client.get_all_positions(), attempts=3, delay=5,
                      label="alpaca.guard_check")
    alpaca_map = {from_alpaca(p.symbol): float(p.qty) for p in positions}

    conn = db_conn()
    c = conn.cursor()
    c.execute("""
        SELECT h.ticker, SUM(h.shares) AS total
        FROM holdings h JOIN portfolios p ON h.portfolio_id = p.id
        WHERE p.is_active = 1 AND h.shares > 0
        GROUP BY h.ticker
    """)
    db_map = {row[0]: float(row[1]) for row in c.fetchall()}
    conn.close()

    all_tickers = set(db_map) | set(alpaca_map)
    out = []
    for t in sorted(all_tickers):
        d, a = db_map.get(t, 0.0), alpaca_map.get(t, 0.0)
        if abs(a - d) > 0.5:
            out.append({"ticker": t, "db": d, "alpaca": a, "diff": a - d})
    return out


def _run_main(args):
    """Actual main logic — called inside lock."""

    # MARKET-HOURS GUARD: skip on holidays/weekends. Cron fires Mon-Fri but
    # doesn't know about US market holidays. Without this check the trader
    # would submit orders to a closed market — Alpaca rejects them, but only
    # after lots of error noise. Clean exit before any state mutation.
    if not args.dry_run and not args.status:
        try:
            _clock_client = get_trading_client()
            _clock = _clock_client.get_clock()
            if not _clock.is_open:
                log_trade(f"=== SKIP: market closed (next open {_clock.next_open}) ===")
                logger.info(f"Market closed. Next open: {_clock.next_open}. Skipping cycle.")
                _post_slack_simple(
                    f":calendar: *BigClaw trader skipped* — market closed today. "
                    f"Next open: `{_clock.next_open}`"
                )
                sys.exit(0)
        except SystemExit:
            raise
        except Exception as e:
            # Don't block trading on a transient clock-check failure.
            # Holidays are rare; network blips are not.
            logger.warning(f"Market clock check failed ({e}). Proceeding anyway.")

    # MISMATCH GUARD (self-healing): if a prior run wrote the flag, re-verify
    # against live Alpaca before refusing to trade. Stale flags from already-
    # resolved mismatches now clear themselves instead of silently halting.
    if not args.dry_run and not args.status:
        verify_account_synced()
    if MISMATCH_FLAG_PATH.exists() and not args.dry_run and not args.status:
        try:
            _guard_client = get_trading_client()
            remaining = _live_mismatch_check(_guard_client)
        except Exception as e:
            log_trade(f"=== BLOCKED: mismatch flag exists and re-verify failed ({e}) — trading halted ===")
            logger.error(f"Could not re-check Alpaca state: {e}")
            _post_slack_simple(
                f":rotating_light: *BigClaw trader BLOCKED* — mismatch flag exists "
                f"and re-verify failed: `{e}`. Manual investigation required."
            )
            sys.exit(1)

        if not remaining:
            # Flag is stale — state has been reconciled. Self-clear.
            try:
                MISMATCH_FLAG_PATH.unlink()
            except FileNotFoundError:
                pass
            log_trade("=== SELF-HEAL: stale mismatch flag cleared (DB and Alpaca now match) ===")
            logger.info("Mismatch flag was stale; DB and Alpaca match. Proceeding.")
            _post_slack_simple(
                ":white_check_mark: *BigClaw trader self-healed* — stale mismatch flag "
                "cleared at startup. DB and Alpaca match. Proceeding with this cycle."
            )
        else:
            # Real mismatches remain. Block, but loudly.
            log_trade("=== BLOCKED: Alpaca mismatch flag exists AND mismatches confirmed live ===")
            logger.error(f"Live re-check found {len(remaining)} mismatches:")
            for m in remaining[:10]:
                logger.error(f"  {m['ticker']}: DB={m['db']:.0f} Alpaca={m['alpaca']:.0f} diff={m['diff']:+.0f}")
            details = "\n".join(
                f"  {m['ticker']}: DB={m['db']:.0f} Alpaca={m['alpaca']:.0f} ({m['diff']:+.0f})"
                for m in remaining[:10]
            )
            _post_slack_simple(
                f":rotating_light: *BigClaw trader BLOCKED today* — {len(remaining)} live mismatches:\n"
                f"```\n{details}\n```\n"
                f"Flag at `{MISMATCH_FLAG_PATH}`. Resolve, then trader auto-clears next cycle."
            )
            sys.exit(1)

    log_trade("=== Autonomous Trader started ===")

    client = get_trading_client()

    if args.status:
        show_status(client)
        return

    # Step 1: Sync
    equity, cash, buying_power, sync_fixes = sync_with_alpaca(client)

    if args.sync_only:
        logger.info("Sync complete. Use --status to review.")
        return

    # Step 2: Decision Engine
    data = run_decision_engine()
    if not data:
        log_trade("=== Aborted: Decision engine failed ===")
        sys.exit(1)

    # Step 2.5: Monthly rebalance (first trading day of month)
    rebalance_trades = check_concentration(client, dry_run=args.dry_run)

    # Step 3: Execute
    executed = execute_trades(client, data, dry_run=args.dry_run, seed_mode=args.seed)
    executed.extend(rebalance_trades)  # Include rebalance trades in summary

    # Step 4: Post-trade sync -- only report mismatches that persist after trades
    remaining_mismatches = post_trade_sync_check(client)

    # Step 5: Summary
    summary = format_summary(executed, remaining_mismatches, dry_run=args.dry_run)
    logger.info(f"\n{summary}")

    # Also save summary for cron to post
    summary_file = Path("/tmp/bigclaw_trade_summary.txt")
    summary_file.write_text(summary)

    log_trade(f"=== Autonomous Trader complete: {len(executed)} trades ===")

    # Refresh dashboard with post-trade data
    if executed:
        try:
            logger.info("Refreshing dashboard with post-trade data...")
            import subprocess
            subprocess.run(
                ["python3", "-c",
                 "import sys; sys.path.insert(0,/home/cbiggs90/bigclaw-ai/src); "
                 "from export_dashboard import export_dashboard; export_dashboard()"],
                timeout=300, cwd="/home/cbiggs90/bigclaw-ai/src",
                capture_output=True
            )
            # Also regenerate planned actions
            subprocess.run(
                ["python3", "build_planned_actions.py"],
                timeout=30, cwd="/home/cbiggs90/.openclaw/workspace/scripts",
                capture_output=True
            )
            logger.info("Dashboard refreshed with executed trades")
        except Exception as e:
            logger.warning(f"Post-trade dashboard refresh failed (non-fatal): {e}")


if __name__ == "__main__":
    main()
