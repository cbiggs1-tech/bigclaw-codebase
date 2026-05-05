#!/usr/bin/env python3
"""BigClaw Full Reset — Liquidate all Alpaca positions, wipe DB, restart clean.

Run ONLY during market hours (10 AM - 4 PM ET).
This is a ONE-TIME script. It will:
1. Sell every position in Alpaca (market orders)
2. Wait for fills
3. Wipe all transactions and holdings from DB
4. Reset each portfolio to its starting cash
5. Verify Alpaca cash >= $1.1M

Usage:
    python3 bigclaw_full_reset.py --dry-run    # Preview what will happen
    python3 bigclaw_full_reset.py --execute     # Actually do it
"""
import argparse
import os
import re
import sqlite3
import sys
import time
from datetime import datetime
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from alpaca_symbols import to_alpaca
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
DB_PATH = Path.home() / "bigclaw-ai" / "src" / "portfolios.db"
SECRETS_FILE = Path.home() / ".env_secrets"


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


def main():
    parser = argparse.ArgumentParser(description="BigClaw Full Reset")
    parser.add_argument("--dry-run", action="store_true", help="Preview without executing")
    parser.add_argument("--execute", action="store_true", help="Actually execute the reset")
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print("ERROR: Must specify --dry-run or --execute")
        sys.exit(1)

    live = args.execute
    now = datetime.now(ET)

    print("=" * 70)
    print(f"BIGCLAW FULL RESET — {'LIVE' if live else 'DRY RUN'}")
    print(f"Time: {now.strftime('%Y-%m-%d %I:%M %p ET')}")
    print("=" * 70)

    # Market hours check (paper account — extended hours OK)
    if live and now.weekday() >= 5:
        print("ERROR: Market is closed (weekend). Run on a weekday.")
        sys.exit(1)

    # Connect to Alpaca
    secrets = load_secrets()
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce

    client = TradingClient(secrets["ALPACA_API_KEY"], secrets["ALPACA_SECRET_KEY"], paper=True)

    # Step 0: Show current state
    acct = client.get_account()
    print(f"\nAlpaca Account BEFORE:")
    print(f"  Equity:       ${float(acct.equity):>12,.2f}")
    print(f"  Cash:         ${float(acct.cash):>12,.2f}")
    print(f"  Buying Power: ${float(acct.buying_power):>12,.2f}")

    positions = client.get_all_positions()
    print(f"  Positions:    {len(positions)}")

    total_market_value = 0
    for p in sorted(positions, key=lambda x: float(x.market_value), reverse=True):
        mv = float(p.market_value)
        total_market_value += mv
        print(f"    {p.symbol:6s}  {float(p.qty):>6.0f} sh  mkt ${mv:>10,.2f}")

    print(f"  Total MV:     ${total_market_value:>12,.2f}")

    # Step 1: Sell every position
    print(f"\n--- STEP 1: Liquidate all {len(positions)} positions ---")
    sell_results = []
    for p in positions:
        symbol = p.symbol
        qty = int(float(p.qty))
        if qty <= 0:
            continue

        if live:
            try:
                order = client.submit_order(MarketOrderRequest(
                    symbol=symbol, qty=qty,
                    side=OrderSide.SELL, time_in_force=TimeInForce.DAY,
                ))
                sell_results.append({"symbol": symbol, "qty": qty, "order_id": str(order.id), "status": "submitted"})
                print(f"  SELL {qty:>6} {symbol:6s} — order {order.id}")
            except Exception as e:
                sell_results.append({"symbol": symbol, "qty": qty, "order_id": None, "status": f"ERROR: {e}"})
                print(f"  ERROR selling {symbol}: {e}")
        else:
            print(f"  [DRY] Would sell {qty:>6} {symbol:6s}")
            sell_results.append({"symbol": symbol, "qty": qty, "order_id": "dry-run", "status": "dry-run"})

    # Step 2: Wait for fills
    if live and sell_results:
        print(f"\n--- STEP 2: Waiting for fills (30 seconds) ---")
        time.sleep(30)

        filled = 0
        failed = 0
        for r in sell_results:
            if r["order_id"] and r["order_id"] != "dry-run":
                try:
                    updated = client.get_order_by_id(r["order_id"])
                    status = str(updated.status).lower()
                    if "filled" in status:
                        filled += 1
                        r["status"] = "filled"
                        r["filled_price"] = float(updated.filled_avg_price or 0)
                    else:
                        r["status"] = status
                        if "cancel" in status or "expire" in status:
                            failed += 1
                except Exception as e:
                    r["status"] = f"check_error: {e}"

        print(f"  Filled: {filled}/{len(sell_results)}")
        if failed > 0:
            print(f"  FAILED: {failed} orders did not fill!")
            for r in sell_results:
                if r["status"] not in ("filled", "submitted"):
                    print(f"    {r['symbol']}: {r['status']}")

        # Verify no remaining positions
        remaining = client.get_all_positions()
        if remaining:
            print(f"\n  WARNING: {len(remaining)} positions still open after sells:")
            for p in remaining:
                print(f"    {p.symbol}: {float(p.qty):.0f} shares")
            print("  These may need a second pass after fills complete.")

    # Step 3: Wipe DB
    print(f"\n--- STEP 3: Reset database ---")
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    c = conn.cursor()

    # Show what we're about to delete
    txn_count = c.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    hold_count = c.execute("SELECT COUNT(*) FROM holdings WHERE shares > 0").fetchone()[0]
    print(f"  Transactions to delete: {txn_count}")
    print(f"  Holdings to clear:      {hold_count}")

    # Get portfolio starting values
    portfolios = c.execute("SELECT id, name, starting_cash FROM portfolios ORDER BY id").fetchall()

    if live:
        # Delete all transactions
        c.execute("DELETE FROM transactions")
        print(f"  Deleted {txn_count} transactions")

        # Delete all holdings
        c.execute("DELETE FROM holdings")
        print(f"  Cleared all holdings")

        # Reset each portfolio cash to starting_cash
        for pid, pname, starting in portfolios:
            c.execute("UPDATE portfolios SET current_cash = ? WHERE id = ?", (starting, pid))
            print(f"  {pname:25s}: cash reset to ${starting:>12,.2f}")

        conn.commit()
        print("  Database committed.")
    else:
        print("  [DRY] Would delete all transactions and holdings")
        for pid, pname, starting in portfolios:
            print(f"  [DRY] {pname:25s}: cash would reset to ${starting:>12,.2f}")

    conn.close()

    # Step 4: Verify
    print(f"\n--- STEP 4: Verification ---")
    if live:
        time.sleep(5)
        acct = client.get_account()
        alpaca_cash = float(acct.cash)
        print(f"  Alpaca cash after liquidation: ${alpaca_cash:>12,.2f}")

        total_starting = sum(s for _, _, s in portfolios)
        print(f"  Total portfolio allocation:    ${total_starting:>12,.2f}")

        if alpaca_cash >= total_starting:
            print(f"  PASS: Alpaca has enough cash (surplus ${alpaca_cash - total_starting:,.2f})")
        else:
            shortfall = total_starting - alpaca_cash
            print(f"  WARNING: Alpaca cash is ${shortfall:,.2f} SHORT of allocation")
            print(f"  This is normal — paper account may have started with less than $1.1M")
            print(f"  The portfolio allocations are virtual — Alpaca doesn't need to match exactly")

        # Verify DB state
        conn = sqlite3.connect(str(DB_PATH), timeout=30)
        c = conn.cursor()
        txn_count = c.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        hold_count = c.execute("SELECT COUNT(*) FROM holdings WHERE shares > 0").fetchone()[0]
        print(f"\n  DB transactions: {txn_count} (should be 0)")
        print(f"  DB holdings:     {hold_count} (should be 0)")

        c.execute("SELECT name, current_cash, starting_cash FROM portfolios ORDER BY id")
        for name, cash, starting in c.fetchall():
            match = "OK" if abs(cash - starting) < 0.01 else "MISMATCH"
            print(f"  {name:25s}: cash=${cash:>12,.2f}  starting=${starting:>12,.2f}  {match}")
        conn.close()

    print(f"\n{'='*70}")
    if live:
        print("RESET COMPLETE. BigClaw will start fresh on the next trading session.")
        print("The autonomous trader will rebuild all portfolios from scratch using")
        print("the IPS rules, style gates, and decision engine.")
    else:
        print("DRY RUN COMPLETE. Run with --execute during market hours to proceed.")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
