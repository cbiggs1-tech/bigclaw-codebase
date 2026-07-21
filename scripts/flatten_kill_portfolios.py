#!/usr/bin/env python3
"""
Flatten KILL portfolios at market OPEN, then is_active=0.
KEEP books are never sold.

Usage:
  source ~/.env_secrets
  python3 flatten_kill_portfolios.py --dry-run
  python3 flatten_kill_portfolios.py --execute
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--deactivate-only", action="store_true", help="Only set is_active=0 if already flat")
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

    client = TradingClient(sec["ALPACA_API_KEY"], sec["ALPACA_SECRET_KEY"], paper=True)
    clock = client.get_clock()
    if args.execute and not clock.is_open:
        log(f"ABORT: market closed (next open {clock.next_open}). Use --dry-run or wait.")
        return 1

    conn = sqlite3.connect(str(DB), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT p.id, p.name, h.ticker, h.shares, h.avg_cost
        FROM portfolios p
        LEFT JOIN holdings h ON h.portfolio_id = p.id AND h.shares != 0
        WHERE p.name IN ({})
        ORDER BY p.name, h.ticker
        """.format(",".join("?" * len(KILL))),
        tuple(sorted(KILL)),
    ).fetchall()

    by_pid = {}
    for r in rows:
        by_pid.setdefault(r["id"], {"name": r["name"], "positions": []})
        if r["ticker"] and r["shares"]:
            by_pid[r["id"]]["positions"].append(
                {"ticker": r["ticker"], "shares": float(r["shares"])}
            )

    log(f"Kill portfolios: {sorted(KILL)}")
    for pid, info in by_pid.items():
        log(f"  {info['name']}: {len(info['positions'])} positions")

    if args.deactivate_only or (args.execute and all(not i["positions"] for i in by_pid.values())):
        for pid, info in by_pid.items():
            still = conn.execute(
                "SELECT COUNT(*) FROM holdings WHERE portfolio_id=? AND shares!=0", (pid,)
            ).fetchone()[0]
            if still:
                log(f"SKIP deactivate {info['name']}: still {still} holdings")
                continue
            if args.dry_run:
                log(f"[dry-run] would is_active=0 {info['name']}")
            else:
                conn.execute("UPDATE portfolios SET is_active=0 WHERE id=?", (pid,))
                log(f"DEACTIVATED {info['name']}")
        conn.commit()
        conn.close()
        return 0

    # Account-level Alpaca: sum shares to sell per ticker = sum across KILL books only.
    # KEEP books may share a ticker (e.g. NBIX) — sell only the kill-book quantity.
    sell_by_ticker = {}
    for pid, info in by_pid.items():
        for pos in info["positions"]:
            t = pos["ticker"]
            sell_by_ticker[t] = sell_by_ticker.get(t, 0.0) + float(pos["shares"])

    log(f"Sell quantities (kill books only): {json.dumps(sell_by_ticker, sort_keys=True)}")

    if args.dry_run:
        log("[dry-run] no orders")
        conn.close()
        return 0

    from alpaca_symbols import to_alpaca, from_alpaca
    from trade_recorder import record_trade

    apos = {from_alpaca(p.symbol): float(p.qty) for p in client.get_all_positions()}
    for t, want in sorted(sell_by_ticker.items()):
        aq = apos.get(t, 0.0)
        sell_qty = min(aq, want) if aq > 0 else 0.0
        # integer shares for market orders
        sell_qty = int(sell_qty)
        if sell_qty <= 0:
            log(f"SKIP {t}: nothing to sell aq={aq} want={want}")
            continue
        sym = to_alpaca(t)
        try:
            order = MarketOrderRequest(
                symbol=sym,
                qty=sell_qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            )
            o = client.submit_order(order)
            log(f"SELL submitted {t} qty={sell_qty} order={o.id}")
            time.sleep(2.0)
        except Exception as e:
            log(f"SELL FAIL {t}: {e}")

    log("Orders submitted. After fills: reconcile kill portfolio holdings to 0, then --deactivate-only.")
    log("Recommend: run accounting reconcile or zero kill holdings via dedicated follow-up.")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
