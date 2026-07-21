#!/usr/bin/env python3
"""
Flatten KILL portfolios at market OPEN, record sells in DB, then is_active=0.
KEEP books are never sold (only kill-book share quantities).

Usage:
  source ~/.env_secrets
  python3 flatten_kill_portfolios.py --dry-run
  python3 flatten_kill_portfolios.py --execute
  python3 flatten_kill_portfolios.py --wait-open --execute   # block until open
  python3 flatten_kill_portfolios.py --deactivate-only
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
DB = HOME / "bigclaw-ai/src/portfolios.db"
LOG = HOME / "bigclaw-ai/logs/four_sleeve_flatten.log"

KILL = {
    "Value Picks",
    "Growth Value",
    "Income Dividends",
    "Nuclear Renaissance",
    "LLM-ETF Focus",
}


def log(msg):
    line = f"{datetime.now(timezone.utc).isoformat()} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def load_secrets():
    sec = {}
    for line in open(HOME / ".env_secrets"):
        line = line.strip()
        if line.startswith("export "):
            line = line[7:]
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            sec[k.strip()] = v.strip().strip('"').strip("'")
    return sec


def wait_until_open(client, poll=30):
    while True:
        clock = client.get_clock()
        if clock.is_open:
            log(f"Market OPEN (ts={clock.timestamp})")
            return
        log(f"Waiting for open... next_open={clock.next_open}")
        time.sleep(poll)


def deactivate_flat(conn, dry_run=False):
    for r in conn.execute(
        "SELECT id, name FROM portfolios WHERE name IN ({})".format(
            ",".join("?" * len(KILL))
        ),
        tuple(sorted(KILL)),
    ):
        still = conn.execute(
            "SELECT COUNT(*) FROM holdings WHERE portfolio_id=? AND shares!=0",
            (r["id"],),
        ).fetchone()[0]
        if still:
            log(f"SKIP deactivate {r['name']}: still {still} holdings rows")
            continue
        if dry_run:
            log(f"[dry-run] would is_active=0 {r['name']}")
        else:
            conn.execute("UPDATE portfolios SET is_active=0 WHERE id=?", (r["id"],))
            log(f"DEACTIVATED {r['name']}")
    if not dry_run:
        conn.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--deactivate-only", action="store_true")
    ap.add_argument("--wait-open", action="store_true", help="Poll until market open")
    args = ap.parse_args()
    if not (args.dry_run or args.execute or args.deactivate_only):
        print("Pass --dry-run or --execute or --deactivate-only")
        return 2

    sys.path.insert(0, str(HOME / "bigclaw-ai/scripts"))
    sec = load_secrets()
    os.environ.setdefault("ALPACA_API_KEY", sec.get("ALPACA_API_KEY", ""))
    os.environ.setdefault("ALPACA_SECRET_KEY", sec.get("ALPACA_SECRET_KEY", ""))

    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca_symbols import to_alpaca, from_alpaca
    from order_fill import wait_for_fill
    from trade_recorder import record_trade

    client = TradingClient(sec["ALPACA_API_KEY"], sec["ALPACA_SECRET_KEY"], paper=True)
    if args.wait_open:
        wait_until_open(client)

    clock = client.get_clock()
    if args.execute and not clock.is_open:
        log(f"ABORT: market closed (next open {clock.next_open}). Use --wait-open or --dry-run.")
        return 1

    conn = sqlite3.connect(str(DB), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.row_factory = sqlite3.Row

    if args.deactivate_only:
        deactivate_flat(conn, dry_run=args.dry_run)
        conn.close()
        return 0

    # Per kill-portfolio positions
    rows = conn.execute(
        """
        SELECT p.id, p.name, h.ticker, h.shares
        FROM portfolios p
        JOIN holdings h ON h.portfolio_id = p.id AND h.shares != 0
        WHERE p.name IN ({})
        ORDER BY p.name, h.ticker
        """.format(
            ",".join("?" * len(KILL))
        ),
        tuple(sorted(KILL)),
    ).fetchall()

    positions = [
        {
            "pid": r["id"],
            "name": r["name"],
            "ticker": r["ticker"],
            "shares": float(r["shares"]),
        }
        for r in rows
    ]
    log(f"Kill positions to flatten: {len(positions)}")
    for p in positions:
        log(f"  {p['name']}: {p['ticker']} x {p['shares']}")

    # Aggregate qty by ticker for Alpaca (account-level), track per-portfolio allocation
    by_ticker = {}
    for p in positions:
        by_ticker.setdefault(p["ticker"], []).append(p)

    sell_plan = {}
    for t, plist in by_ticker.items():
        sell_plan[t] = sum(x["shares"] for x in plist)
    log(f"Alpaca sell plan: {json.dumps({k: v for k, v in sorted(sell_plan.items())})}")

    if args.dry_run:
        log("[dry-run] no orders")
        deactivate_flat(conn, dry_run=True)
        conn.close()
        return 0

    apos = {from_alpaca(p.symbol): float(p.qty) for p in client.get_all_positions()}
    fills = {}  # ticker -> (filled_qty, filled_price)

    for t, want in sorted(sell_plan.items()):
        aq = apos.get(t, 0.0)
        sell_qty = int(min(aq, want)) if aq > 0 else 0
        if sell_qty <= 0:
            log(f"SKIP {t}: aq={aq} want={want}")
            continue
        try:
            req = MarketOrderRequest(
                symbol=to_alpaca(t),
                qty=sell_qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            )
            order = client.submit_order(req)
            fq, fp = wait_for_fill(
                client, order, sell_qty, None, ticker=t, pname="KILL-FLATTEN", side="SELL"
            )
            fills[t] = (float(fq), float(fp) if fp else 0.0)
            log(f"FILLED SELL {t} qty={fq} @ {fp} order={order.id}")
            time.sleep(0.8)
        except Exception as e:
            log(f"SELL FAIL {t}: {e}")

    # Record each kill-portfolio leg proportional to its shares
    for t, plist in by_ticker.items():
        if t not in fills:
            log(f"No fill for {t} — DB not updated for this ticker")
            continue
        fq, fp = fills[t]
        total_want = sum(x["shares"] for x in plist) or 1.0
        remaining = fq
        for i, p in enumerate(plist):
            # allocate filled qty across portfolios
            if i == len(plist) - 1:
                leg = remaining
            else:
                leg = int(round(fq * (p["shares"] / total_want)))
                remaining -= leg
            if leg <= 0:
                continue
            val = leg * fp
            try:
                ok = record_trade(
                    p["pid"],
                    p["name"],
                    t,
                    "sell",
                    leg,
                    fp,
                    val,
                    "4-sleeve cutover flatten 2026-07-21",
                    order_id=None,
                )
                log(f"DB record_trade {p['name']} SELL {t} x{leg} @ {fp} ok={ok}")
            except Exception as e:
                log(f"DB record FAIL {p['name']} {t}: {e}")

    # Zero any residual fractional kill holdings if flat at Alpaca for kill-only
    deactivate_flat(conn, dry_run=False)

    # Force-zero remaining kill holdings if shares still >0 but we intended full exit
    for p in positions:
        row = conn.execute(
            "SELECT shares FROM holdings WHERE portfolio_id=? AND ticker=?",
            (p["pid"], p["ticker"]),
        ).fetchone()
        if row and float(row[0] or 0) != 0:
            # only force if ticker fully gone from our sell plan fill
            if p["ticker"] in fills and fills[p["ticker"]][0] > 0:
                log(
                    f"WARN residual {p['name']} {p['ticker']} shares={row[0]} after fill — check reconcile"
                )

    still_active_with_pos = conn.execute(
        """
        SELECT p.name, COUNT(*) n FROM portfolios p
        JOIN holdings h ON h.portfolio_id=p.id AND h.shares!=0
        WHERE p.name IN ({}) GROUP BY p.name
        """.format(
            ",".join("?" * len(KILL))
        ),
        tuple(sorted(KILL)),
    ).fetchall()
    if still_active_with_pos:
        log(f"REMAINING kill holdings: {list(still_active_with_pos)}")
        log("Re-run --execute later or manual fix; NOT force-deleting holdings.")
    else:
        log("All kill books flat — deactivating")
        for name in KILL:
            conn.execute(
                "UPDATE portfolios SET is_active=0 WHERE name=?", (name,)
            )
            log(f"DEACTIVATED {name}")
        conn.commit()

    # always try deactivate for any already flat
    deactivate_flat(conn, dry_run=False)
    conn.close()
    log("Flatten pass complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
