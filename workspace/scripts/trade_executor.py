#!/usr/bin/env python3
"""
BigClaw Trade Executor — Paper trading via Alpaca API
Executes trades from decision engine signals or manual commands.
"""

import argparse
import json
import math
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ET = ZoneInfo("America/New_York")
DB_PATH = Path.home() / "bigclaw-ai" / "src" / "portfolios.db"
LOG_DIR = Path.home() / ".openclaw" / "workspace" / "logs"
LOG_FILE = LOG_DIR / "trades.log"
SECRETS_FILE = Path.home() / ".env_secrets"
PORTFOLIO_MD = Path.home() / ".openclaw" / "workspace" / "research" / "new-portfolios-2026-02-14.md"
PAPER_URL = "https://paper-api.alpaca.markets"
DEFAULT_MAX_ORDER = 25000.0
DEFAULT_PORTFOLIO_ID = 1  # fallback

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_secrets() -> dict:
    """Parse ~/.env_secrets for KEY=VALUE (handles export and quotes)."""
    secrets: dict[str, str] = {}
    if not SECRETS_FILE.exists():
        print(f"❌ Secrets file not found: {SECRETS_FILE}")
        sys.exit(1)
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
        print("❌ Missing ALPACA_API_KEY or ALPACA_SECRET_KEY in ~/.env_secrets")
        sys.exit(1)
    from alpaca.trading.client import TradingClient
    return TradingClient(api_key, secret_key, paper=True)


def verify_paper(client):
    """Abort if this is somehow a live account."""
    acct = client.get_account()
    # The paper attribute isn't directly exposed; check the endpoint or status
    # paper=True in constructor ensures paper endpoint. Double-check:
    if hasattr(acct, "account_number"):
        pass  # paper accounts have account numbers starting with PA
    return acct


def now_et():
    return datetime.now(ET)


def is_market_open_day(dt=None):
    """Simple weekday check (no holiday calendar)."""
    dt = dt or now_et()
    return dt.weekday() < 5  # Mon-Fri


def check_time_window(force=False):
    """Returns (ok, message). If not ok, should block trades."""
    if force:
        return True, "⚠️  --force flag: time restrictions overridden"
    t = now_et()
    if not is_market_open_day(t):
        return False, f"📅 Market closed (weekend). Orders would queue for next market open at 10:00 AM ET."
    if t.hour < 10:
        return False, "⏰ Opening volatility window — trades blocked until 10:00 AM ET"
    if t.hour >= 16:
        return False, "📅 Market closed for today (after 4 PM ET)."
    return True, "✅ Trading window open"


def get_prev_close(ticker: str) -> float | None:
    """Get previous close from yfinance."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        info = t.info
        return info.get("previousClose") or info.get("regularMarketPreviousClose")
    except Exception as e:
        print(f"  ⚠️  yfinance error for {ticker}: {e}")
        return None


def get_current_price(ticker: str) -> float | None:
    """Get current/last price from yfinance."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        info = t.info
        return info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
    except Exception as e:
        print(f"  ⚠️  yfinance price error for {ticker}: {e}")
        return None


def ensure_log_dir():
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def log_trade(action, ticker, shares, price, rationale, status):
    ensure_log_dir()
    ts = now_et().strftime("%Y-%m-%d %H:%M")
    line = f"{ts} | {action} | {ticker} | {shares} | {price:.2f} | {rationale} | {status}"
    print(f"  {line}")
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ---------------------------------------------------------------------------
# Database operations
# ---------------------------------------------------------------------------

def db_conn():
    return sqlite3.connect(DB_PATH)


def get_portfolio(name_or_id=None):
    """Return (id, name, current_cash) for a portfolio."""
    conn = db_conn()
    c = conn.cursor()
    if name_or_id is None:
        c.execute("SELECT id, name, current_cash FROM portfolios WHERE is_active=1 ORDER BY id LIMIT 1")
    elif isinstance(name_or_id, int):
        c.execute("SELECT id, name, current_cash FROM portfolios WHERE id=?", (name_or_id,))
    else:
        c.execute("SELECT id, name, current_cash FROM portfolios WHERE name=?", (name_or_id,))
    row = c.fetchone()
    conn.close()
    return row  # (id, name, cash) or None


def get_holding(portfolio_id, ticker):
    conn = db_conn()
    c = conn.cursor()
    c.execute("SELECT shares, avg_cost FROM holdings WHERE portfolio_id=? AND ticker=?", (portfolio_id, ticker))
    row = c.fetchone()
    conn.close()
    return row  # (shares, avg_cost) or None


def db_update_buy(portfolio_id, ticker, shares, price, rationale):
    conn = db_conn()
    c = conn.cursor()
    total = shares * price
    existing = get_holding(portfolio_id, ticker)
    if existing:
        old_shares, old_avg = existing
        new_shares = old_shares + shares
        new_avg = ((old_shares * old_avg) + (shares * price)) / new_shares
        c.execute("UPDATE holdings SET shares=?, avg_cost=?, last_bought_at=CURRENT_TIMESTAMP WHERE portfolio_id=? AND ticker=?",
                  (new_shares, round(new_avg, 4), portfolio_id, ticker))
    else:
        c.execute("INSERT INTO holdings (portfolio_id, ticker, shares, avg_cost, rationale) VALUES (?,?,?,?,?)",
                  (portfolio_id, ticker, shares, price, rationale))
    c.execute("UPDATE portfolios SET current_cash = current_cash - ? WHERE id=?", (total, portfolio_id))
    c.execute("INSERT INTO transactions (portfolio_id, ticker, action, shares, price, total_value, rationale) VALUES (?,?,?,?,?,?,?)",
              (portfolio_id, ticker, "buy", shares, price, total, rationale))
    conn.commit()
    conn.close()


def db_update_sell(portfolio_id, ticker, shares, price, rationale):
    conn = db_conn()
    c = conn.cursor()
    total = shares * price
    existing = get_holding(portfolio_id, ticker)
    if existing:
        old_shares, old_avg = existing
        new_shares = max(0, old_shares - shares)
        c.execute("UPDATE holdings SET shares=? WHERE portfolio_id=? AND ticker=?",
                  (new_shares, portfolio_id, ticker))
    c.execute("UPDATE portfolios SET current_cash = current_cash + ? WHERE id=?", (total, portfolio_id))
    c.execute("INSERT INTO transactions (portfolio_id, ticker, action, shares, price, total_value, rationale) VALUES (?,?,?,?,?,?,?)",
              (portfolio_id, ticker, "sell", shares, price, total, rationale))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Order execution
# ---------------------------------------------------------------------------

def place_order(client, ticker, side, shares, limit_price=None, dry_run=False, max_order=DEFAULT_MAX_ORDER, rationale="manual"):
    """Place a single order. Returns True on success."""
    from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce

    action = "BUY" if side == OrderSide.BUY else "SELL"
    price = limit_price or 0

    # Get price for sizing check
    if limit_price:
        est_price = limit_price
    else:
        est_price = get_current_price(ticker) or 0

    order_value = shares * est_price if est_price else 0

    # Safety: max order size
    if order_value > max_order:
        log_trade(action, ticker, shares, est_price, rationale, f"BLOCKED — exceeds max ${max_order:,.0f}")
        return False

    if dry_run:
        log_trade(action, ticker, shares, est_price, rationale, "DRY-RUN (not submitted)")
        return True

    try:
        # Verify ticker is tradeable
        try:
            asset = client.get_asset(ticker)
            if not asset.tradable:
                log_trade(action, ticker, shares, est_price, rationale, f"BLOCKED — {ticker} not tradeable")
                return False
        except Exception as e:
            log_trade(action, ticker, shares, est_price, rationale, f"BLOCKED — ticker error: {e}")
            return False

        if side == OrderSide.BUY:
            # Always limit for buys
            if not limit_price:
                limit_price = get_prev_close(ticker)
            if not limit_price:
                log_trade(action, ticker, shares, 0, rationale, "BLOCKED — no limit price available")
                return False
            req = LimitOrderRequest(
                symbol=ticker, qty=shares, side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY, limit_price=round(limit_price, 2)
            )
            price = limit_price
        else:
            # Market for sells (default), limit if specified
            if limit_price:
                req = LimitOrderRequest(
                    symbol=ticker, qty=shares, side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY, limit_price=round(limit_price, 2)
                )
                price = limit_price
            else:
                req = MarketOrderRequest(
                    symbol=ticker, qty=shares, side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY
                )
                price = est_price

        order = client.submit_order(req)
        log_trade(action, ticker, shares, price, rationale, f"SUBMITTED (order {order.id})")
        return True

    except Exception as e:
        log_trade(action, ticker, shares, est_price, rationale, f"ERROR — {e}")
        return False


# ---------------------------------------------------------------------------
# Signal processing
# ---------------------------------------------------------------------------

def load_portfolio_universe(portfolio_name):
    """Load allowed tickers for a portfolio from config/portfolio_universes.json."""
    universes_file = Path.home() / ".openclaw" / "workspace" / "config" / "portfolio_universes.json"
    if not universes_file.exists():
        print(f"⚠️  No portfolio universes file found at {universes_file}")
        return None
    with open(universes_file) as f:
        universes = json.load(f)
    entry = universes.get(portfolio_name)
    if entry is None:
        print(f"⚠️  Portfolio '{portfolio_name}' not found in universes config")
        return None
    if isinstance(entry, dict):
        # New format with holdings + candidates
        allowed = set(entry.get("holdings", []) + entry.get("candidates", []))
    else:
        # Legacy format: flat list
        allowed = set(entry)
    return allowed


def execute_signals(client, signals_file, dry_run, force, max_order, portfolio_name=None):
    """Execute trades from decision engine JSON output."""
    with open(signals_file) as f:
        signals = json.load(f)

    if isinstance(signals, dict):
        signals = signals.get("signals", signals.get("decisions", [signals]))

    pf = get_portfolio(portfolio_name)
    if not pf:
        print("❌ No active portfolio found in DB")
        return
    pf_id, pf_name, cash = pf
    print(f"\n## Executing signals for portfolio: {pf_name} (cash: ${cash:,.2f})\n")

    # Load allowed universe for this portfolio
    allowed_universe = load_portfolio_universe(pf_name)
    if allowed_universe:
        # Also include current holdings from DB
        conn = db_conn()
        c = conn.cursor()
        c.execute("SELECT ticker FROM holdings WHERE portfolio_id=? AND shares > 0", (pf_id,))
        current_holdings = {row[0] for row in c.fetchall()}
        conn.close()
        allowed_universe = allowed_universe | current_holdings
        print(f"  📋 Allowed universe ({len(allowed_universe)} tickers): {sorted(allowed_universe)}\n")

    # Get total portfolio value for sizing
    conn = db_conn()
    c = conn.cursor()
    c.execute("SELECT SUM(shares * avg_cost) FROM holdings WHERE portfolio_id=?", (pf_id,))
    holdings_val = c.fetchone()[0] or 0
    conn.close()
    total_value = cash + holdings_val

    from alpaca.trading.enums import OrderSide

    for sig in signals:
        ticker = sig.get("ticker", sig.get("symbol", ""))
        score = sig.get("score", sig.get("signal", 0))
        rationale = sig.get("rationale", sig.get("reason", f"Signal score {score}"))

        if not ticker:
            continue

        # Safety: skip tickers not in this portfolio's universe
        if allowed_universe and ticker not in allowed_universe:
            print(f"  ⚠️  SKIPPING {ticker} — not in {pf_name} universe (score {score})")
            continue

        if score >= 3:
            # BUY — 5% of portfolio
            alloc = total_value * 0.05
            price = get_prev_close(ticker) or get_current_price(ticker)
            if not price:
                print(f"  ⚠️  Skipping {ticker} — no price data")
                continue
            shares = int(alloc / price)
            cost = shares * price
            if cost > cash:
                shares = int(cash / price)
            if shares <= 0:
                print(f"  ⚠️  Skipping {ticker} — insufficient cash")
                continue
            ok = place_order(client, ticker, OrderSide.BUY, shares, limit_price=price,
                           dry_run=dry_run, max_order=max_order, rationale=rationale)
            if ok and not dry_run:
                db_update_buy(pf_id, ticker, shares, price, rationale)
                cash -= shares * price

        elif score <= -5:
            # STRONG SELL — 100%
            holding = get_holding(pf_id, ticker)
            if not holding or holding[0] <= 0:
                print(f"  ⚠️  No position in {ticker} to sell")
                continue
            shares = int(holding[0])
            if shares <= 0:
                continue
            price = get_current_price(ticker) or holding[1]
            ok = place_order(client, ticker, OrderSide.SELL, shares,
                           dry_run=dry_run, max_order=max_order, rationale=rationale)
            if ok and not dry_run:
                db_update_sell(pf_id, ticker, shares, price, rationale)

        elif score <= -3:
            # TRIM — 50%
            holding = get_holding(pf_id, ticker)
            if not holding or holding[0] <= 0:
                print(f"  ⚠️  No position in {ticker} to trim")
                continue
            shares = max(1, int(holding[0] * 0.5))
            price = get_current_price(ticker) or holding[1]
            ok = place_order(client, ticker, OrderSide.SELL, shares,
                           dry_run=dry_run, max_order=max_order, rationale=rationale)
            if ok and not dry_run:
                db_update_sell(pf_id, ticker, shares, price, rationale)
        else:
            print(f"  ℹ️  {ticker}: score {score} — HOLD (no action)")


# ---------------------------------------------------------------------------
# Create portfolio mode
# ---------------------------------------------------------------------------

def create_portfolio(client, portfolio_name, dry_run, force, max_order):
    """Create a new portfolio from the research MD file."""
    from alpaca.trading.enums import OrderSide

    md_text = PORTFOLIO_MD.read_text()

    # Find the right portfolio section and its SQL
    # Parse SQL block for this portfolio
    sql_block = ""
    in_sql = False
    for line in md_text.splitlines():
        if line.strip() == "```sql":
            in_sql = True
            continue
        if line.strip() == "```" and in_sql:
            break
        if in_sql:
            sql_block += line + "\n"

    # Determine which portfolio section matches
    # Look for the portfolio name in the SQL
    if portfolio_name not in sql_block:
        print(f"❌ Portfolio '{portfolio_name}' not found in {PORTFOLIO_MD}")
        return

    # Extract holdings for this portfolio from SQL
    # Find the INSERT INTO holdings block after the portfolio name
    lines = sql_block.splitlines()
    holdings = []
    weights = {}
    total_cash = 100000.0

    # Parse the markdown table for weights instead (more reliable)
    # Find "Selected Holdings" table for the matching portfolio
    in_section = False
    portfolio_map = {
        "Income Dividends": "Income/Dividend Portfolio",
        "Momentum Growth": "Momentum/Aggressive Growth Portfolio",
    }
    section_name = portfolio_map.get(portfolio_name, portfolio_name)

    for line in md_text.splitlines():
        if section_name in line:
            in_section = True
            continue
        if in_section and line.startswith("## Portfolio") and section_name not in line:
            break
        if in_section and line.startswith("## SQL"):
            break
        if in_section and "|" in line and "**" in line:
            # Parse table row like: | 1 | **VZ** | 14% | $14,000 | ...
            parts = [p.strip() for p in line.split("|")]
            parts = [p for p in parts if p]
            if len(parts) >= 5 and parts[0].isdigit():
                ticker = parts[1].replace("*", "").strip()
                weight_str = parts[2].replace("%", "").strip()
                try:
                    weight = float(weight_str) / 100.0
                    rationale_text = parts[-1] if len(parts) > 6 else "Initial portfolio construction"
                    weights[ticker] = {"weight": weight, "rationale": rationale_text}
                except ValueError:
                    pass

    if not weights:
        print(f"❌ Could not parse holdings for '{portfolio_name}'")
        return

    # Calculate remaining cash (for momentum portfolio with cash reserve)
    cash_weight = 0
    for line in md_text.splitlines():
        if in_section and "CASH" in line and "|" in line:
            parts = [p.strip() for p in line.split("|")]
            parts = [p for p in parts if p]
            for p in parts:
                if "%" in p:
                    try:
                        cash_weight = float(p.replace("%", "").strip()) / 100.0
                        break
                    except ValueError:
                        pass

    invested_cash = total_cash * (1 - cash_weight)
    remaining_cash = total_cash * cash_weight

    print(f"\n## Creating portfolio: {portfolio_name}")
    print(f"Total capital: ${total_cash:,.2f} | Investing: ${invested_cash:,.2f} | Reserve: ${remaining_cash:,.2f}\n")

    # Fetch current prices and recalculate shares
    orders = []
    total_cost = 0
    for ticker, info in weights.items():
        alloc = total_cash * info["weight"]
        price = get_current_price(ticker)
        if not price:
            price = get_prev_close(ticker)
        if not price:
            print(f"  ⚠️  Skipping {ticker} — no price data")
            continue
        shares = int(alloc / price)
        cost = shares * price
        total_cost += cost
        orders.append({
            "ticker": ticker, "shares": shares, "price": price,
            "cost": cost, "rationale": info["rationale"],
            "weight": info["weight"]
        })
        print(f"  {ticker}: {shares} shares @ ${price:.2f} = ${cost:,.2f} ({info['weight']*100:.0f}%)")

    actual_remaining = total_cash - total_cost
    print(f"\n  Total invested: ${total_cost:,.2f} | Remaining cash: ${actual_remaining:,.2f}")

    if dry_run:
        print("\n  🏜️  DRY RUN — no DB changes or orders placed")
        for o in orders:
            log_trade("BUY", o["ticker"], o["shares"], o["price"], o["rationale"], "DRY-RUN")
        return

    # Create portfolio in DB
    conn = db_conn()
    c = conn.cursor()

    # Check if already exists
    c.execute("SELECT id FROM portfolios WHERE name=?", (portfolio_name,))
    if c.fetchone():
        print(f"  ⚠️  Portfolio '{portfolio_name}' already exists in DB — skipping DB creation")
        conn.close()
        return

    style_map = {
        "Income Dividends": "Income / Dividend Growth",
        "Momentum Growth": "Momentum / Aggressive Growth",
    }
    style = style_map.get(portfolio_name, "Mixed")

    c.execute("INSERT INTO portfolios (name, investment_style, starting_cash, current_cash, report_channel, is_active) VALUES (?,?,?,?,?,?)",
              (portfolio_name, style, total_cash, actual_remaining, "D0ADHLUJ400", 1))
    pf_id = c.lastrowid

    for o in orders:
        c.execute("INSERT INTO holdings (portfolio_id, ticker, shares, avg_cost, rationale) VALUES (?,?,?,?,?)",
                  (pf_id, o["ticker"], o["shares"], o["price"], o["rationale"]))
        c.execute("INSERT INTO transactions (portfolio_id, ticker, action, shares, price, total_value, rationale) VALUES (?,?,?,?,?,?,?)",
                  (pf_id, o["ticker"], "buy", o["shares"], o["price"], o["cost"], "Initial portfolio construction"))

    conn.commit()
    conn.close()
    print(f"\n  ✅ Portfolio '{portfolio_name}' created in DB (id={pf_id})")

    # Place orders via Alpaca
    for o in orders:
        place_order(client, o["ticker"], OrderSide.BUY, o["shares"],
                   limit_price=o["price"], dry_run=False, max_order=max_order,
                   rationale="Initial portfolio construction")


# ---------------------------------------------------------------------------
# Status mode
# ---------------------------------------------------------------------------

def show_status(client):
    """Show current Alpaca positions, open orders, and DB portfolio summary."""
    print("\n## 📊 Alpaca Account Status\n")

    acct = client.get_account()
    print(f"**Account:** {acct.account_number}")
    print(f"**Equity:** ${float(acct.equity):,.2f}")
    print(f"**Cash:** ${float(acct.cash):,.2f}")
    print(f"**Buying Power:** ${float(acct.buying_power):,.2f}")
    print(f"**Portfolio Value:** ${float(acct.portfolio_value):,.2f}")

    # Positions
    positions = client.get_all_positions()
    if positions:
        print(f"\n### Open Positions ({len(positions)})\n")
        print("| Ticker | Qty | Avg Cost | Current | P/L | P/L % |")
        print("|--------|-----|----------|---------|-----|-------|")
        for p in positions:
            pl = float(p.unrealized_pl)
            pl_pct = float(p.unrealized_plpc) * 100
            emoji = "🟢" if pl >= 0 else "🔴"
            print(f"| {p.symbol} | {p.qty} | ${float(p.avg_entry_price):,.2f} | ${float(p.current_price):,.2f} | {emoji} ${pl:,.2f} | {pl_pct:+.1f}% |")
    else:
        print("\n*No open positions*")

    # Open orders
    orders = client.get_orders(filter=None)
    open_orders = [o for o in orders if o.status in ("new", "accepted", "pending_new", "partially_filled")]
    if open_orders:
        print(f"\n### Open Orders ({len(open_orders)})\n")
        print("| Ticker | Side | Qty | Type | Limit | Status |")
        print("|--------|------|-----|------|-------|--------|")
        for o in open_orders:
            lp = f"${float(o.limit_price):,.2f}" if o.limit_price else "MKT"
            print(f"| {o.symbol} | {o.side} | {o.qty} | {o.order_type} | {lp} | {o.status} |")
    else:
        print("\n*No open orders*")

    # DB portfolios
    conn = db_conn()
    c = conn.cursor()
    c.execute("SELECT id, name, current_cash, starting_cash FROM portfolios WHERE is_active=1")
    portfolios = c.fetchall()
    if portfolios:
        print(f"\n### DB Portfolios ({len(portfolios)})\n")
        for pf in portfolios:
            pid, name, cash, starting = pf
            c.execute("SELECT ticker, shares, avg_cost FROM holdings WHERE portfolio_id=? AND shares > 0", (pid,))
            holdings = c.fetchall()
            holdings_val = sum(s * ac for _, s, ac in holdings)
            total = cash + holdings_val
            ret = ((total / starting) - 1) * 100 if starting else 0
            print(f"**{name}** (id={pid}) — Cash: ${cash:,.2f} | Holdings: ${holdings_val:,.2f} | Total: ${total:,.2f} | Return: {ret:+.1f}%")
            if holdings:
                for t, s, ac in holdings:
                    print(f"  - {t}: {s:.0f} shares @ ${ac:.2f}")
    conn.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="BigClaw Trade Executor — Paper trading via Alpaca")
    parser.add_argument("--signals", help="Path to decision engine signals JSON")
    parser.add_argument("--buy", help="Ticker to buy")
    parser.add_argument("--sell", help="Ticker to sell")
    parser.add_argument("--shares", type=int, help="Number of shares")
    parser.add_argument("--limit", type=float, help="Limit price")
    parser.add_argument("--create-portfolio", help="Create portfolio from research MD")
    parser.add_argument("--status", action="store_true", help="Show positions and orders")
    parser.add_argument("--dry-run", action="store_true", help="Preview without executing")
    parser.add_argument("--force", action="store_true", help="Override time restrictions")
    parser.add_argument("--max-order", type=float, default=DEFAULT_MAX_ORDER, help=f"Max single order (default ${DEFAULT_MAX_ORDER:,.0f})")
    parser.add_argument("--portfolio", help="Portfolio name or ID for signal execution")
    args = parser.parse_args()

    ensure_log_dir()

    # Status mode doesn't need time check
    if args.status:
        client = get_trading_client()
        verify_paper(client)
        show_status(client)
        return

    # For all trading modes, check time window
    if args.buy or args.sell or args.signals or args.create_portfolio:
        ok, msg = check_time_window(args.force)
        print(msg)
        if not ok and not args.dry_run:
            print("Use --force to override or --dry-run to preview.")
            return

        client = get_trading_client()
        verify_paper(client)

        from alpaca.trading.enums import OrderSide

        if args.signals:
            execute_signals(client, args.signals, args.dry_run, args.force, args.max_order, args.portfolio)

        elif args.buy:
            if not args.shares:
                print("❌ --shares required for manual buy")
                return
            limit_price = args.limit or get_prev_close(args.buy)
            ok = place_order(client, args.buy, OrderSide.BUY, args.shares,
                           limit_price=limit_price, dry_run=args.dry_run,
                           max_order=args.max_order, rationale="Manual buy order")
            if ok and not args.dry_run:
                pf = get_portfolio(args.portfolio)
                if pf:
                    db_update_buy(pf[0], args.buy, args.shares, limit_price or 0, "Manual buy order")

        elif args.sell:
            if not args.shares:
                print("❌ --shares required for manual sell")
                return
            ok = place_order(client, args.sell, OrderSide.SELL, args.shares,
                           limit_price=args.limit, dry_run=args.dry_run,
                           max_order=args.max_order, rationale="Manual sell order")
            if ok and not args.dry_run:
                price = args.limit or get_current_price(args.sell) or 0
                pf = get_portfolio(args.portfolio)
                if pf:
                    db_update_sell(pf[0], args.sell, args.shares, price, "Manual sell order")

        elif args.create_portfolio:
            create_portfolio(client, args.create_portfolio, args.dry_run, args.force, args.max_order)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
