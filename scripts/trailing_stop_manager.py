#!/usr/bin/env python3
"""
BigClaw Trailing Stop Manager

Manages trailing stops for all portfolio holdings:
1. Initialize — create stops for holdings that don't have one
2. Ratchet — update HWM upward when price rises (stops only move UP)
3. Check triggers — sell when price <= trigger_price
4. Tighten — cut trail bands in half (used by circuit breakers)

Style-specific trail percentages:
  Value Picks:            18%  (trust the thesis)
  Innovation Fund:        18%  (volatile by nature)
  Income Dividends:       15%  (moderate protection)
  Growth Value:           12%  (GARP discipline)
  Nuclear Renaissance:    12%  (thematic structural)
  AI Defense & Autonomous:12%  (thematic structural)
  Momentum Growth:        10%  (cut losers faster)

Usage:
    python3 trailing_stop_manager.py                 # Full run
    python3 trailing_stop_manager.py --dry-run       # Preview without executing
    python3 trailing_stop_manager.py --tighten 0.5   # Cut all bands by 50%
    python3 trailing_stop_manager.py --status         # Show current stops
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo

import yfinance as yf

sys.path.insert(0, str(Path.home() / "bigclaw-ai" / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from bigclaw_logging import get_logger

ET = ZoneInfo("America/New_York")
DB_PATH = Path.home() / "bigclaw-ai" / "src" / "portfolios.db"

logger = get_logger("trailing_stops")

# Style-specific trail percentages
TRAIL_PCT = {
    "Value Picks":            0.18,
    "Innovation Fund":        0.18,
    "Income Dividends":       0.15,
    "Growth Value":           0.12,
    "Nuclear Renaissance":    0.12,
    "AI Defense & Autonomous":0.12,
    "Momentum Growth":        0.10,
}

DEFAULT_TRAIL_PCT = 0.12


def db_conn():
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.row_factory = sqlite3.Row
    return conn


def fetch_prices(tickers):
    """Batch-fetch current prices via yfinance."""
    if not tickers:
        return {}
    prices = {}
    try:
        data = yf.download(list(tickers), period="1d", progress=False, threads=True)
        if "Close" in data.columns or len(tickers) == 1:
            close = data["Close"] if len(tickers) > 1 else data[["Close"]]
            if hasattr(close, "iloc") and len(close) > 0:
                row = close.iloc[-1]
                for t in tickers:
                    col = t if t in row.index else None
                    if col and not (row[col] != row[col]):  # not NaN
                        prices[t] = float(row[col])
    except Exception as e:
        logger.warning(f"Batch fetch failed: {e}")

    # Fallback for missing
    for t in tickers:
        if t not in prices:
            try:
                info = yf.Ticker(t).fast_info
                p = getattr(info, "last_price", None) or getattr(info, "previous_close", None)
                if p:
                    prices[t] = float(p)
            except Exception:
                pass
    return prices


def get_portfolio_trail_pct(portfolio_name):
    """Return trail percentage for a given portfolio name."""
    return TRAIL_PCT.get(portfolio_name, DEFAULT_TRAIL_PCT)


def initialize_stops(dry_run=False):
    """Create trailing stop rows for any holding that doesn't have one."""
    conn = db_conn()
    c = conn.cursor()

    # Get all active holdings across all portfolios
    c.execute("""
        SELECT h.portfolio_id, p.name AS portfolio_name, h.ticker, h.shares, h.avg_cost
        FROM holdings h
        JOIN portfolios p ON p.id = h.portfolio_id
        WHERE h.shares > 0 AND p.is_active = 1
    """)
    holdings = c.fetchall()

    # Get existing active stops
    c.execute("SELECT portfolio_id, ticker FROM trailing_stops WHERE status = 'active'")
    existing = {(row["portfolio_id"], row["ticker"]) for row in c.fetchall()}

    # Find holdings without stops
    need_stops = []
    tickers_needed = set()
    for h in holdings:
        key = (h["portfolio_id"], h["ticker"])
        if key not in existing:
            need_stops.append(h)
            tickers_needed.add(h["ticker"])

    if not need_stops:
        logger.info("All holdings have trailing stops")
        conn.close()
        return 0

    # Fetch current prices for HWM initialization
    prices = fetch_prices(tickers_needed)

    created = 0
    today_str = date.today().isoformat()

    for h in need_stops:
        pid = h["portfolio_id"]
        pname = h["portfolio_name"]
        ticker = h["ticker"]
        avg_cost = h["avg_cost"]
        current = prices.get(ticker)

        if current is None:
            logger.warning(f"No price for {ticker}, skipping stop initialization")
            continue

        trail_pct = get_portfolio_trail_pct(pname)
        hwm = max(current, avg_cost)
        trigger = round(hwm * (1 - trail_pct), 4)

        if dry_run:
            logger.info(f"DRY-INIT | {pname} | {ticker} | HWM=${hwm:.2f} trail={trail_pct:.0%} trigger=${trigger:.2f}")
        else:
            # Clear any leftover non-active row for this (portfolio_id, ticker) so the new
            # active stop wins. Without this, INSERT silently fails on UNIQUE constraint.
            c.execute("DELETE FROM trailing_stops WHERE portfolio_id = ? AND ticker = ?", (pid, ticker))
            c.execute("""
                INSERT INTO trailing_stops
                (portfolio_id, ticker, high_water_mark, hwm_date, trail_pct, trigger_price)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (pid, ticker, hwm, today_str, trail_pct, trigger))
            logger.info(f"INIT | {pname} | {ticker} | HWM=${hwm:.2f} trail={trail_pct:.0%} trigger=${trigger:.2f}")

        created += 1

    if not dry_run:
        conn.commit()
    conn.close()
    logger.info(f"Initialized {created} trailing stops")
    return created


def ratchet_stops(prices=None, dry_run=False):
    """Ratchet HWM upward for any stop where current price > HWM.

    Stops only move UP — never down.
    """
    conn = db_conn()
    c = conn.cursor()

    c.execute("""
        SELECT ts.id, ts.portfolio_id, p.name AS portfolio_name,
               ts.ticker, ts.high_water_mark, ts.trail_pct, ts.trigger_price
        FROM trailing_stops ts
        JOIN portfolios p ON p.id = ts.portfolio_id
        WHERE ts.status = 'active'
    """)
    stops = c.fetchall()

    if not stops:
        conn.close()
        return 0

    # Fetch prices if not provided
    if prices is None:
        tickers = {s["ticker"] for s in stops}
        prices = fetch_prices(tickers)

    today_str = date.today().isoformat()
    ratcheted = 0

    for s in stops:
        ticker = s["ticker"]
        current = prices.get(ticker)
        if current is None:
            continue

        old_hwm = s["high_water_mark"]
        if current > old_hwm:
            new_hwm = current
            new_trigger = round(new_hwm * (1 - s["trail_pct"]), 4)

            if dry_run:
                logger.info(f"DRY-RATCHET | {s['portfolio_name']} | {ticker} | "
                          f"HWM ${old_hwm:.2f}→${new_hwm:.2f} trigger ${s['trigger_price']:.2f}→${new_trigger:.2f}")
            else:
                c.execute("""
                    UPDATE trailing_stops
                    SET high_water_mark = ?, hwm_date = ?, trigger_price = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (new_hwm, today_str, new_trigger, s["id"]))
                logger.info(f"RATCHET | {s['portfolio_name']} | {ticker} | "
                          f"HWM ${old_hwm:.2f}→${new_hwm:.2f} trigger ${s['trigger_price']:.2f}→${new_trigger:.2f}")

            ratcheted += 1

    if not dry_run:
        conn.commit()
    conn.close()
    logger.info(f"Ratcheted {ratcheted} stops upward")
    return ratcheted


def check_triggers(prices=None, dry_run=False):
    """Check if any stop has been triggered (price <= trigger_price).

    Returns list of triggered stops for the caller to execute sells.
    """
    conn = db_conn()
    c = conn.cursor()

    c.execute("""
        SELECT ts.id, ts.portfolio_id, p.name AS portfolio_name,
               ts.ticker, ts.high_water_mark, ts.trail_pct, ts.trigger_price,
               h.shares, h.avg_cost
        FROM trailing_stops ts
        JOIN portfolios p ON p.id = ts.portfolio_id
        JOIN holdings h ON h.portfolio_id = ts.portfolio_id AND h.ticker = ts.ticker
        WHERE ts.status = 'active' AND h.shares > 0
    """)
    stops = c.fetchall()

    if not stops:
        conn.close()
        return []

    if prices is None:
        tickers = {s["ticker"] for s in stops}
        prices = fetch_prices(tickers)

    triggered = []

    for s in stops:
        ticker = s["ticker"]
        current = prices.get(ticker)
        if current is None:
            continue

        if current <= s["trigger_price"]:
            drawdown = (s["high_water_mark"] - current) / s["high_water_mark"] * 100
            reason = (f"Trailing stop triggered: ${current:.2f} <= ${s['trigger_price']:.2f} "
                     f"(HWM ${s['high_water_mark']:.2f}, -{drawdown:.1f}%)")

            if dry_run:
                logger.info(f"DRY-TRIGGER | {s['portfolio_name']} | SELL {ticker} | "
                          f"{s['shares']} shares | {reason}")
            else:
                # Mark stop as triggered
                c.execute("""
                    UPDATE trailing_stops
                    SET status = 'triggered', triggered_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (s["id"],))
                logger.info(f"TRIGGER | {s['portfolio_name']} | SELL {ticker} | "
                          f"{s['shares']} shares | {reason}")

            triggered.append({
                "stop_id": s["id"],
                "portfolio_id": s["portfolio_id"],
                "portfolio_name": s["portfolio_name"],
                "ticker": ticker,
                "shares": s["shares"],
                "avg_cost": s["avg_cost"],
                "current_price": current,
                "trigger_price": s["trigger_price"],
                "high_water_mark": s["high_water_mark"],
                "reason": reason,
            })

    if not dry_run:
        conn.commit()
    conn.close()

    if triggered:
        logger.info(f"{len(triggered)} trailing stops triggered")
    return triggered


def tighten_stops(factor, portfolio_id=None, dry_run=False):
    """Tighten all trailing stop bands by a factor.

    factor=0.5 means cut trail_pct in half (e.g., 18% → 9%).
    Used by circuit breakers during drawdown or panic.
    """
    conn = db_conn()
    c = conn.cursor()

    if portfolio_id:
        c.execute("""
            SELECT ts.id, p.name AS portfolio_name, ts.ticker,
                   ts.high_water_mark, ts.trail_pct, ts.trigger_price
            FROM trailing_stops ts
            JOIN portfolios p ON p.id = ts.portfolio_id
            WHERE ts.status = 'active' AND ts.portfolio_id = ?
        """, (portfolio_id,))
    else:
        c.execute("""
            SELECT ts.id, p.name AS portfolio_name, ts.ticker,
                   ts.high_water_mark, ts.trail_pct, ts.trigger_price
            FROM trailing_stops ts
            JOIN portfolios p ON p.id = ts.portfolio_id
            WHERE ts.status = 'active'
        """)

    stops = c.fetchall()
    tightened = 0

    for s in stops:
        new_trail = s["trail_pct"] * factor
        new_trigger = round(s["high_water_mark"] * (1 - new_trail), 4)

        if dry_run:
            logger.info(f"DRY-TIGHTEN | {s['portfolio_name']} | {s['ticker']} | "
                      f"trail {s['trail_pct']:.0%}→{new_trail:.0%} trigger ${s['trigger_price']:.2f}→${new_trigger:.2f}")
        else:
            c.execute("""
                UPDATE trailing_stops
                SET trail_pct = ?, trigger_price = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (new_trail, new_trigger, s["id"]))
            logger.info(f"TIGHTEN | {s['portfolio_name']} | {s['ticker']} | "
                      f"trail {s['trail_pct']:.0%}→{new_trail:.0%} trigger ${s['trigger_price']:.2f}→${new_trigger:.2f}")

        tightened += 1

    if not dry_run:
        conn.commit()
    conn.close()
    logger.info(f"Tightened {tightened} stops by factor {factor}")
    return tightened


def remove_stale_stops():
    """Delete trailing stop rows for holdings that no longer exist.

    Was previously marking rows as status='stale' but leaving them in the table —
    the stale rows then blocked new INSERTs (UNIQUE constraint), which left
    re-bought positions unprotected. Now actually removes them.
    """
    conn = db_conn()
    c = conn.cursor()
    c.execute("""
        DELETE FROM trailing_stops
        WHERE NOT EXISTS (
            SELECT 1 FROM holdings h
            WHERE h.portfolio_id = trailing_stops.portfolio_id
              AND h.ticker = trailing_stops.ticker
              AND h.shares > 0
        )
    """)
    removed = c.rowcount
    conn.commit()
    conn.close()
    if removed:
        logger.info(f"Removed {removed} trailing stops for sold positions")
    return removed


def show_status():
    """Print current trailing stop status."""
    conn = db_conn()
    c = conn.cursor()
    c.execute("""
        SELECT ts.*, p.name AS portfolio_name
        FROM trailing_stops ts
        JOIN portfolios p ON p.id = ts.portfolio_id
        WHERE ts.status = 'active'
        ORDER BY p.name, ts.ticker
    """)
    stops = c.fetchall()
    conn.close()

    if not stops:
        print("No active trailing stops.")
        return

    # Fetch current prices
    tickers = {s["ticker"] for s in stops}
    prices = fetch_prices(tickers)

    print(f"\n{'Portfolio':<25} {'Ticker':<8} {'HWM':>10} {'Trail':>7} {'Trigger':>10} {'Current':>10} {'Buffer':>8}")
    print("-" * 85)

    for s in stops:
        current = prices.get(s["ticker"])
        if current:
            buffer_pct = (current - s["trigger_price"]) / current * 100
            buffer_str = f"{buffer_pct:+.1f}%"
            current_str = f"${current:,.2f}"
        else:
            buffer_str = "N/A"
            current_str = "N/A"

        print(f"{s['portfolio_name']:<25} {s['ticker']:<8} ${s['high_water_mark']:>9,.2f} "
              f"{s['trail_pct']:>6.0%} ${s['trigger_price']:>9,.2f} {current_str:>10} {buffer_str:>8}")

    print(f"\nTotal: {len(stops)} active trailing stops")


# ---------------------------------------------------------------------------
# Shared Alpaca sell execution for triggered stops
# ---------------------------------------------------------------------------

SECRETS_FILE = Path.home() / ".env_secrets"
LOG_DIR = Path.home() / ".openclaw" / "workspace" / "logs"
LOG_FILE = LOG_DIR / "trades.log"


def _load_secrets():
    """Load secrets from ~/.env_secrets."""
    import re
    secrets = {}
    for line in SECRETS_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^export\s+", "", line)
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        secrets[k.strip()] = v.strip().strip("'\"" )
    return secrets


def _log_trade(msg):
    """Append to trades.log."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(ET).strftime("%Y-%m-%d %H:%M ET")
    line = f"{ts} | {msg}"
    logger.info(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def execute_stop_sells(triggered, dry_run=False):
    """Execute Alpaca market sells for triggered trailing stops.

    Args:
        triggered: list from check_triggers() — each dict has portfolio_id,
                   portfolio_name, ticker, shares, current_price, reason, etc.
        dry_run: if True, log but don't execute

    Returns:
        list of executed sell dicts
    """
    if not triggered:
        return []

    import time
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce

    secrets = _load_secrets()
    client = TradingClient(
        secrets.get("ALPACA_API_KEY"), secrets.get("ALPACA_SECRET_KEY"), paper=True
    )

    executed = []
    for st in triggered:
        pid = st["portfolio_id"]
        pname = st["portfolio_name"]
        ticker = st["ticker"]
        shares = int(st["shares"])
        price = st["current_price"]
        reason = st["reason"]

        if dry_run:
            _log_trade(f"DRY-STOP-SELL | {pname} | {ticker} | {shares} shares @ ${price:,.2f} | {reason}")
            executed.append({"portfolio": pname, "action": "STOP-SELL", "ticker": ticker,
                            "shares": shares, "price": price, "reason": reason, "dry_run": True})
            continue

        try:
            req = MarketOrderRequest(
                symbol=ticker, qty=shares,
                side=OrderSide.SELL, time_in_force=TimeInForce.DAY,
            )
            order = client.submit_order(req)
            time.sleep(1)
            updated = client.get_order_by_id(str(order.id))
            status = str(updated.status).lower()
            filled_qty = int(float(updated.filled_qty or 0)) if "filled" in status else shares
            filled_price = float(updated.filled_avg_price or price) if "filled" in status else price
            sell_value = filled_qty * filled_price

            _log_trade(f"STOP-SELL | {pname} | {ticker} | {filled_qty} @ ${filled_price:,.2f} = ${sell_value:,.2f} | {reason} | order={order.id}")

            conn = db_conn()
            c = conn.cursor()
            c.execute("DELETE FROM holdings WHERE portfolio_id = ? AND ticker = ?", (pid, ticker))
            c.execute("DELETE FROM trailing_stops WHERE portfolio_id = ? AND ticker = ?", (pid, ticker))
            c.execute("UPDATE portfolios SET current_cash = current_cash + ? WHERE id = ?", (sell_value, pid))
            c.execute("INSERT INTO transactions (portfolio_id, ticker, action, shares, price, total_value, rationale) VALUES (?,?,?,?,?,?,?)",
                     (pid, ticker, "sell", filled_qty, filled_price, sell_value, reason))
            conn.commit()
            conn.close()

            executed.append({"portfolio": pname, "action": "STOP-SELL", "ticker": ticker,
                            "shares": filled_qty, "price": filled_price, "reason": reason,
                            "order_id": str(order.id)})

        except Exception as e:
            _log_trade(f"ERROR | {pname} | STOP-SELL {ticker} | {e}")
            logger.error(f"Stop sell failed for {ticker}: {e}")

    return executed


def run_full_cycle(prices=None, dry_run=False, tighten_factor=None):
    """Run the complete trailing stop cycle.

    Called by autonomous_trader and price_refresh.
    Returns list of triggered stops (for autonomous_trader to execute sells).
    """
    logger.info(f"Trailing stop cycle starting (dry_run={dry_run})")

    # Clean up stale stops first
    if not dry_run:
        remove_stale_stops()

    # Initialize stops for new holdings
    initialize_stops(dry_run=dry_run)

    # Tighten if requested (circuit breaker)
    if tighten_factor is not None:
        tighten_stops(tighten_factor, dry_run=dry_run)

    # Ratchet HWM upward
    ratchet_stops(prices=prices, dry_run=dry_run)

    # Check for triggered stops
    triggered = check_triggers(prices=prices, dry_run=dry_run)

    logger.info(f"Trailing stop cycle complete: {len(triggered)} triggered")
    return triggered


def main():
    parser = argparse.ArgumentParser(description="BigClaw Trailing Stop Manager")
    parser.add_argument("--dry-run", action="store_true", help="Preview without executing")
    parser.add_argument("--tighten", type=float, help="Tighten factor (e.g., 0.5 = cut bands in half)")
    parser.add_argument("--portfolio", type=int, help="Portfolio ID to tighten (with --tighten)")
    parser.add_argument("--status", action="store_true", help="Show current stop status")
    parser.add_argument("--init-only", action="store_true", help="Only initialize new stops")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if args.tighten:
        tighten_stops(args.tighten, portfolio_id=args.portfolio, dry_run=args.dry_run)
        return

    if args.init_only:
        initialize_stops(dry_run=args.dry_run)
        return

    # Full cycle
    triggered = run_full_cycle(dry_run=args.dry_run)

    if triggered:
        print(f"\n⚠️  {len(triggered)} trailing stops triggered:")
        for t in triggered:
            print(f"  {t['portfolio_name']} | SELL {t['ticker']} | "
                  f"{t['shares']} shares @ ${t['current_price']:.2f} | {t['reason']}")
    else:
        print("No trailing stops triggered.")


if __name__ == "__main__":
    main()
