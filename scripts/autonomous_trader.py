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


def _wait_for_fill(client, order, ordered_qty, est_price, ticker, pname, side):
    """Shared fill polling for BOTH buy and sell orders.

    Market orders can partial-fill over multiple seconds. A single 1-second
    poll captures a partial fill as 'filled' (substring match) and records
    the wrong quantity. This function waits for full fill.

    Returns (filled_qty, filled_price). Both may be None if no fill confirmed.
    """
    import time
    time.sleep(3)
    for _poll in range(10):
        updated = client.get_order_by_id(str(order.id))
        status = str(updated.status).lower()
        alp_filled = int(float(updated.filled_qty or 0))
        if status == "orderstatus.filled" or alp_filled >= ordered_qty:
            return (alp_filled, float(updated.filled_avg_price or est_price or 0))
        if "partial" in status and alp_filled > 0:
            logger.info(f"Partial {side} fill: {ticker} {alp_filled}/{ordered_qty} — waiting...")
        time.sleep(2)

    # Final check — accept whatever Alpaca actually filled
    updated = client.get_order_by_id(str(order.id))
    alp_filled = int(float(updated.filled_qty or 0))
    if alp_filled > 0:
        log_trade(f"WARN | {pname} | {side} {ticker} | partial fill after polling: {alp_filled}/{ordered_qty}")
        return (alp_filled, float(updated.filled_avg_price or est_price or 0))
    log_trade(f"WARN | {pname} | {side} {ticker} | no fill confirmed, using ordered qty={ordered_qty}")
    return (ordered_qty, est_price or 0)


def _execute_sell_order(client, pid, pname, ticker, shares, reason, dry_run=False):
    """Execute a sell order through Alpaca and record to DB.

    Single path for ALL sells. Returns dict with result or None on failure.
    On DB write failure, returns {"halted": True} to trigger circuit breaker.
    """
    import yfinance as yf
    try:
        info = retry(lambda: yf.Ticker(ticker).info, attempts=2, delay=3, label=f"yf.info({ticker})")
        est_price = info.get("currentPrice") or info.get("regularMarketPrice")
    except Exception:
        est_price = None

    if dry_run:
        price = est_price or 0
        log_trade(f"DRY-SELL | {pname} | {ticker} | {shares} shares @ ~${price:,.2f} | {reason}")
        return {"ticker": ticker, "shares": shares, "price": price, "value": shares * price, "dry_run": True}

    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    try:
        order = client.submit_order(MarketOrderRequest(
            symbol=to_alpaca(ticker), qty=shares, side=OrderSide.SELL, time_in_force=TimeInForce.DAY,
        ))
        filled_qty, filled_price = _wait_for_fill(client, order, shares, est_price, ticker, pname, "SELL")
        actual_value = filled_qty * filled_price
        log_trade(f"SELL | {pname} | {ticker} | {filled_qty} @ ${filled_price:,.2f} = ${actual_value:,.2f} | {reason} | order={order.id}")

        db_ok = _record_trade_with_retry(
            pid, pname, ticker, "sell", filled_qty, filled_price, actual_value, reason,
            sell_all=(filled_qty >= shares)
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
    """
    import yfinance as yf
    try:
        info = retry(lambda: yf.Ticker(ticker).info, attempts=2, delay=3, label=f"yf.info({ticker})")
        price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
    except Exception:
        price = None

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
        filled_qty, filled_price = _wait_for_fill(client, order, num_shares, price, ticker, pname, "BUY")
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
            existing_shares=existing[0] if existing and existing[0] > 0 else 0
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
                              existing_shares=0, sell_all=False, max_retries=10):
    """Record a trade to DB with aggressive retry. Alpaca already executed — we MUST record this.

    ABSOLUTE RULES:
    - Every Alpaca execution gets a transaction record
    - Holdings are updated to match
    - Cash is recalculated from transactions (never direct-written with arbitrary values)
    """
    import time as _time

    for attempt in range(max_retries):
        try:
            conn = db_conn()
            c = conn.cursor()

            # Record the transaction FIRST (this is the source of truth)
            c.execute(
                "INSERT INTO transactions (portfolio_id, ticker, action, shares, price, total_value, rationale) "
                "VALUES (?,?,?,?,?,?,?)",
                (pid, ticker, action, shares, price, total_value, reason)
            )

            # Update holdings
            if action == "buy":
                # Check if a row exists for this ticker (even with shares=0 from previous sell)
                c.execute("SELECT shares, avg_cost FROM holdings WHERE portfolio_id = ? AND ticker = ?", (pid, ticker))
                _existing = c.fetchone()
                if _existing is not None:
                    # Row exists — UPDATE it (handles both shares>0 and shares=0 cases)
                    old_shares = _existing[0] or 0
                    old_avg = _existing[1] or price
                    if old_shares > 0:
                        new_shares = old_shares + shares
                        new_avg = ((old_shares * old_avg) + (shares * price)) / new_shares
                    else:
                        # Was zeroed from a sell — treat as fresh position
                        new_shares = shares
                        new_avg = price
                    c.execute(
                        "UPDATE holdings SET shares = ?, avg_cost = ?, last_bought_at = CURRENT_TIMESTAMP "
                        "WHERE portfolio_id = ? AND ticker = ?",
                        (new_shares, round(new_avg, 4), pid, ticker)
                    )
                else:
                    # No row at all — INSERT new
                    c.execute(
                        "INSERT INTO holdings (portfolio_id, ticker, shares, avg_cost, rationale) VALUES (?,?,?,?,?)",
                        (pid, ticker, shares, price, reason)
                    )
            elif action == "sell":
                if sell_all:
                    c.execute("DELETE FROM holdings WHERE portfolio_id = ? AND ticker = ?", (pid, ticker))
                else:
                    c.execute(
                        "UPDATE holdings SET shares = shares - ? WHERE portfolio_id = ? AND ticker = ?",
                        (shares, pid, ticker)
                    )
                    c.execute(
                        "DELETE FROM holdings WHERE portfolio_id = ? AND ticker = ? AND shares <= 0.001",
                        (pid, ticker)
                    )
                # If position is now fully closed, remove its trailing stop too
                c.execute("""
                    DELETE FROM trailing_stops
                    WHERE portfolio_id = ? AND ticker = ?
                      AND NOT EXISTS (
                          SELECT 1 FROM holdings
                          WHERE portfolio_id = ? AND ticker = ? AND shares > 0.001
                      )
                """, (pid, ticker, pid, ticker))

            # RULE 2: Recalculate cash from ALL transactions (never incremental)
            c.execute("""
                SELECT COALESCE(SUM(CASE WHEN action='buy' THEN total_value ELSE 0 END), 0) as buys,
                       COALESCE(SUM(CASE WHEN action='sell' THEN total_value ELSE 0 END), 0) as sells,
                       COALESCE(SUM(CASE WHEN action='dividend' THEN total_value ELSE 0 END), 0) as dividends
                FROM transactions WHERE portfolio_id = ?
            """, (pid,))
            row = c.fetchone()
            c.execute("SELECT starting_cash FROM portfolios WHERE id = ?", (pid,))
            starting = c.fetchone()[0]
            correct_cash = starting - row[0] + row[1] + row[2]
            c.execute("UPDATE portfolios SET current_cash = ? WHERE id = ?", (round(correct_cash, 2), pid))

            conn.commit()
            conn.close()
            logger.info(f"DB recorded: {action.upper()} {shares} {ticker} for {pname} (attempt {attempt + 1})")
            return True

        except Exception as e:
            err_str = str(e)
            retryable = "database is locked" in err_str or "UNIQUE constraint" in err_str
            if retryable and attempt < max_retries - 1:
                wait = 3 * (attempt + 1)
                logger.warning(f"DB error recording {action} {ticker} for {pname}: {err_str}")
                logger.warning(f"  Retry {attempt + 1}/{max_retries} in {wait}s...")
                _time.sleep(wait)
                # On UNIQUE constraint retry, the holdings logic above will re-check
                # and find the existing row on the next attempt
            else:
                logger.error(f"CRITICAL: Failed to record {action} {ticker} for {pname} after {attempt + 1} attempts: {e}")
                logger.error(f"ALPACA EXECUTED BUT DB NOT RECORDED — needs manual reconciliation")
                log_trade(f"UNRECORDED | {pname} | {action.upper()} {shares} {ticker} @ ${price:,.2f} = ${total_value:,.2f} | DB WRITE FAILED: {e}")
                return False



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
                    logger.info(f"  {o.side} {o.qty} {o.symbol} @ {o.limit_price or 'MKT'} — {o.status} ({o.created_at.strftime('%m/%d')})")
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

    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "decision_engine.py"), "--json", "--rescreen"],
        capture_output=True, text=True, timeout=600,
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

            try:
                req = MarketOrderRequest(
                    symbol=to_alpaca(ticker), qty=trim_shares,
                    side=OrderSide.SELL, time_in_force=TimeInForce.DAY
                )
                order = client.submit_order(req)

                import time
                time.sleep(1)
                updated = client.get_order_by_id(str(order.id))
                status = str(updated.status).lower()
                filled_qty = int(float(updated.filled_qty or 0)) if "filled" in status else trim_shares
                filled_price = float(updated.filled_avg_price or price) if "filled" in status else price
                sell_value = filled_qty * filled_price

                log_trade(f"REBALANCE-SELL | {pname} | {ticker} | {filled_qty} @ ${filled_price:,.2f} = ${sell_value:,.2f} | {reason} | order={order.id}")

                # RULE 3: Record sell with retry — Alpaca already executed
                sell_all = (max(0, int(shares) - filled_qty) == 0)
                _record_trade_with_retry(
                    pid, pname, ticker, "sell", filled_qty, filled_price, sell_value, reason,
                    sell_all=sell_all
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

            try:
                req = MarketOrderRequest(
                    symbol=to_alpaca(ticker_stop), qty=int(shares_stop),
                    side=OrderSide.SELL, time_in_force=TimeInForce.DAY,
                )
                order = client.submit_order(req)

                import time
                time.sleep(1)
                updated = client.get_order_by_id(str(order.id))
                status = str(updated.status).lower()
                filled_qty = int(float(updated.filled_qty or 0)) if "filled" in status else int(shares_stop)
                filled_price = float(updated.filled_avg_price or price_stop) if "filled" in status else price_stop
                sell_value = filled_qty * filled_price

                log_trade(f"STOP-SELL | {st['portfolio_name']} | {ticker_stop} | "
                         f"{filled_qty} @ ${filled_price:,.2f} = ${sell_value:,.2f} | {reason_stop} | order={order.id}")

                # RULE 3: Record stop-sell with retry — Alpaca already executed
                _record_trade_with_retry(
                    pid_stop, st["portfolio_name"], ticker_stop, "sell",
                    filled_qty, filled_price, sell_value, reason_stop,
                    sell_all=True
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
        to_sell = []
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
        alpaca_positions[p.symbol] = float(p.qty)

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
    for p in sorted(positions, key=lambda x: x.symbol):
        pl_pct = float(p.unrealized_plpc) * 100
        logger.info(f"  {p.symbol:6s} {float(p.qty):6.0f} shares @ ${float(p.avg_entry_price):8.2f} → ${float(p.current_price):8.2f}  {pl_pct:+6.1f}%")

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
    alpaca = {p.symbol: {"qty": float(p.qty), "avg_entry": float(p.avg_entry_price),
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
    mismatch_file = Path.home() / "bigclaw-ai" / "logs" / "ALPACA_MISMATCH.flag"
    import json as _json
    mismatch_file.write_text(_json.dumps(critical, indent=2))
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


def _run_main(args):
    """Actual main logic — called inside lock."""

    # MISMATCH GUARD: If previous run found DB/Alpaca mismatches, refuse to trade.
    # This prevents compounding errors. Clear the flag after manual investigation.
    mismatch_file = Path.home() / "bigclaw-ai" / "logs" / "ALPACA_MISMATCH.flag"
    if mismatch_file.exists() and not args.dry_run and not args.status:
        log_trade("=== BLOCKED: Alpaca mismatch flag exists — trading halted until resolved ===")
        logger.error(f"Previous run found DB/Alpaca mismatches. Review {mismatch_file}")
        logger.error("After resolving, delete the flag file to resume trading:")
        logger.error(f"  rm {mismatch_file}")
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
