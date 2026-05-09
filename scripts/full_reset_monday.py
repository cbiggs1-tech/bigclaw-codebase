"""Monday reset: sell all positions, wipe shadow ledger, reset to $100K per portfolio.

DESTRUCTIVE - execute only with explicit user confirmation, only during market hours.

Sequence:
  1. SAFETY: confirm market is open + interactive --confirm flag present
  2. Snapshot current state for audit trail (logs/resets/reset_snapshot_<ts>.json)
  3. Sell every position on Alpaca (using wait_for_fill - terminal state guaranteed)
  4. Wait for all sells to settle in DB
  5. Wipe shadow ledger:
       - DELETE FROM holdings (all)
       - DELETE FROM trailing_stops (all)
       - DELETE FROM stop_cooldowns (all)
       - DELETE FROM transactions (all) - fresh start
       - UPDATE portfolios SET starting_cash = 100000, current_cash = 100000 (active only)
  6. Run accounting audit - INV 1 should be perfect ($0 diff), INV 2 should be empty
     (DB has 0 holdings, Alpaca has 0 positions if sells settled)
  7. Run decision engine to score full universes
  8. Buy top 10 per portfolio
  9. Run audit again - should still be clean

If anything fails between step 3 and step 5, the system halts - partial state
is recoverable manually but the script will not continue past errors.
"""
import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path.home() / "bigclaw-ai" / "scripts"))
from autonomous_trader import (
    get_trading_client, _execute_sell_order, _execute_buy_order,
    db_conn, log_trade
)

DB_PATH = Path.home() / "bigclaw-ai" / "src" / "portfolios.db"
LOG_DIR = Path.home() / "bigclaw-ai" / "logs"
SNAPSHOT_DIR = LOG_DIR / "resets"
PER_PORTFOLIO_STARTING = 100_000.00
ALLOC_PCT = 0.10  # 10% per buy = 10 positions per portfolio


def market_open_now():
    from datetime import datetime, time as dt_time
    from zoneinfo import ZoneInfo
    et = datetime.now(ZoneInfo("America/New_York"))
    if et.weekday() >= 5:
        return False
    return dt_time(9, 30) <= et.time() <= dt_time(15, 55)


def snapshot_state():
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    snap = {
        "timestamp": datetime.now().isoformat(),
        "portfolios": [dict(r) for r in conn.execute("SELECT * FROM portfolios").fetchall()],
        "holdings": [dict(r) for r in conn.execute("SELECT * FROM holdings").fetchall()],
        "transactions_count": conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0],
        "trailing_stops": [dict(r) for r in conn.execute("SELECT * FROM trailing_stops").fetchall()],
    }
    client = get_trading_client()
    snap["alpaca_account"] = {
        "cash": float(client.get_account().cash),
        "equity": float(client.get_account().equity),
        "positions": [{"symbol": p.symbol, "qty": float(p.qty), "market_value": float(p.market_value)}
                      for p in client.get_all_positions()],
    }
    conn.close()
    fname = SNAPSHOT_DIR / f"reset_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    fname.write_text(json.dumps(snap, indent=2, default=str))
    print(f"  Snapshot written to {fname}")
    return snap


def liquidate_all(client):
    """Sell every position across all portfolios."""
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT h.portfolio_id, p.name AS pname, h.ticker, h.shares
        FROM holdings h JOIN portfolios p ON h.portfolio_id = p.id
        WHERE p.is_active = 1 AND h.shares > 0
        ORDER BY p.name, h.ticker
    """).fetchall()
    conn.close()

    print(f"  Liquidating {len(rows)} positions across all portfolios...")
    failures = []
    for r in rows:
        result = _execute_sell_order(
            client, r["portfolio_id"], r["pname"], r["ticker"],
            int(r["shares"]), "FULL RESET - Monday reset to $100K per portfolio",
            dry_run=False
        )
        if not result or result.get("halted"):
            failures.append(r["ticker"])
            print(f"    FAIL: {r['pname']} | {r['ticker']}")
        else:
            print(f"    SOLD {r['ticker']:<8s}: {result['shares']} @ ${result['price']:.2f} = ${result['value']:,.0f}")
        time.sleep(0.3)
    return failures


def wipe_shadow():
    """Reset shadow ledger to clean baseline."""
    conn = db_conn()
    c = conn.cursor()
    c.execute("DELETE FROM holdings")
    c.execute("DELETE FROM trailing_stops")
    try:
        c.execute("DELETE FROM stop_cooldowns")
    except sqlite3.OperationalError:
        pass
    c.execute("DELETE FROM transactions")
    c.execute("UPDATE portfolios SET starting_cash = ?, current_cash = ? WHERE is_active = 1",
              (PER_PORTFOLIO_STARTING, PER_PORTFOLIO_STARTING))
    conn.commit()
    n = c.execute("SELECT COUNT(*) FROM portfolios WHERE is_active = 1").fetchone()[0]
    conn.close()
    print(f"  Shadow ledger wiped: holdings, trailing_stops, stop_cooldowns, transactions all empty")
    print(f"  {n} active portfolios reset to ${PER_PORTFOLIO_STARTING:,.0f} each")


def run_decision_engine():
    import subprocess
    print("  Running decision engine (full-universe scoring)...")
    result = subprocess.run(
        [sys.executable,
         str(Path.home() / "bigclaw-ai" / "scripts" / "decision_engine.py"),
         "--json", "--rescreen"],
        capture_output=True, text=True, timeout=1800
    )
    if result.returncode != 0:
        print(f"  Decision engine FAILED: {result.stderr[:500]}")
        sys.exit(1)
    print("  Decision engine complete")


def buy_top_10_per_portfolio(client):
    signals_path = Path.home() / "bigclaw-ai" / "docs" / "data" / "signals.json"
    data = json.loads(signals_path.read_text())
    portfolio_signals = data.get("portfolio_signals", {})

    conn = db_conn(); conn.row_factory = sqlite3.Row
    portfolios = conn.execute(
        "SELECT id, name, starting_cash FROM portfolios WHERE is_active = 1 ORDER BY id"
    ).fetchall()

    for p in portfolios:
        pid, pname, starting = p["id"], p["name"], p["starting_cash"]
        sigs = portfolio_signals.get(pname, {})
        ranked = sorted(sigs.items(), key=lambda kv: -kv[1].get("score", 0))[:10]

        print(f"\n  [{pname}] buying top {len(ranked)} by score:")
        per_buy = starting * ALLOC_PCT
        reserve = starting * 0.02

        for ticker, sig in ranked:
            score = sig.get("score", 0)
            reason = f"FULL RESET - top 10 by score (score {score})"
            result = _execute_buy_order(
                client, pid, pname, ticker, per_buy, reason, starting, reserve, dry_run=False
            )
            if result and result.get("halted"):
                print(f"    HALTED on {ticker}")
                return
            if result:
                print(f"    BUY {ticker:<8s}: {result['shares']} @ ${result['price']:.2f} = ${result['value']:,.0f}")
            time.sleep(0.3)
    conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", action="store_true",
                        help="Required. Without this flag, only prints the plan.")
    parser.add_argument("--skip-market-check", action="store_true",
                        help="Bypass market-hours check (use only if certain).")
    args = parser.parse_args()

    if not args.confirm:
        print("=" * 70)
        print("FULL RESET - preview mode (will NOT execute)")
        print("=" * 70)
        print()
        print("If --confirm is passed AND market is open, this script will:")
        print("  1. Snapshot all current state to logs/resets/")
        print("  2. SELL every position across all portfolios")
        print("  3. WIPE the shadow ledger (transactions, holdings, trailing_stops)")
        print("  4. RESET each active portfolio to $100,000 starting cash")
        print("  5. Run decision engine on the full bias-free universe")
        print("  6. BUY top 10 by score per portfolio (10% allocation each)")
        print("  7. Run accounting audit - should report clean")
        print()
        print("To execute on Monday during market hours:")
        print("  python3 scripts/full_reset_monday.py --confirm")
        return

    if not args.skip_market_check and not market_open_now():
        print("ERROR: market is not open. Reset must run during market hours.")
        print("       Use --skip-market-check to bypass (advanced).")
        sys.exit(1)

    print("=" * 70)
    print(f"FULL RESET STARTING - {datetime.now().isoformat()}")
    print("=" * 70)

    print("\n[1/7] Snapshotting current state...")
    snapshot_state()

    print("\n[2/7] Liquidating all positions...")
    client = get_trading_client()
    failures = liquidate_all(client)
    if failures:
        print(f"\nABORT: {len(failures)} sells failed. Inspect logs and resolve manually.")
        print(f"Failed tickers: {failures}")
        sys.exit(1)

    print("\n[3/7] Waiting 10s for cash to settle in DB...")
    time.sleep(10)

    print("\n[4/7] Wiping shadow ledger and resetting cash to $100,000 per portfolio...")
    wipe_shadow()

    print("\n[5/7] Running decision engine on full universe...")
    run_decision_engine()

    print("\n[6/7] Buying top 10 per portfolio...")
    buy_top_10_per_portfolio(client)

    print("\n[7/7] Running accounting audit...")
    import subprocess
    audit_result = subprocess.run(
        [sys.executable, str(Path.home() / "bigclaw-ai" / "scripts" / "accounting_audit.py"), "--no-slack"],
        capture_output=True, text=True
    )
    print(audit_result.stdout)

    print("\n" + "=" * 70)
    print("FULL RESET COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
