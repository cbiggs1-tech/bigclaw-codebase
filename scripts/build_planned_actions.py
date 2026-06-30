#!/usr/bin/env python3
"""Build the dashboard execution plan from the trader's OWN planning logic.

Single source of truth: this calls autonomous_trader.plan_portfolio() — the exact function
the live trader uses — so the dashboard's planned-actions panel reflects what the trader
will actually do (portfolio universe + style gate + target-price discipline), not a phantom
top-10 reimplementation that drifts. (Before June 30 2026 this file re-derived the plan with
a blanket "sell anything not in the top 10" rule, which showed sells the trader never makes —
e.g. Innovation Fund holds under target-price discipline.)

Note: covers the best-in-class optimization plan. Emergency Phase-1 safety sells (score
<= -3) are executed by the trader before optimization and are rare; they are not separately
projected here.
"""
import json
import sqlite3
import os
import sys
import logging
from pathlib import Path

DATA_DIR = os.path.expanduser("~/bigclaw-ai/docs/data")
SIGNALS_PATH = os.path.join(DATA_DIR, "signals.json")
DB_PATH = os.path.expanduser("~/bigclaw-ai/src/portfolios.db")
SCRIPTS_DIR = os.path.expanduser("~/bigclaw-ai/scripts")

MONEY_MARKET = "SGOV"
MIN_CASH_RESERVE_PCT = 0.02


def build_planned_actions():
    if not os.path.exists(SIGNALS_PATH):
        return []

    sys.path.insert(0, SCRIPTS_DIR)
    import autonomous_trader as at  # provides plan_portfolio + the real rules

    with open(SIGNALS_PATH) as f:
        data = json.load(f)
    signal_map = {s["ticker"]: s for s in data.get("signals", [])}
    portfolio_signals = data.get("portfolio_signals", {})
    with open(str(at.UNIVERSES_FILE)) as f:
        universes = json.load(f)

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    conn.row_factory = sqlite3.Row
    portfolios = conn.execute(
        "SELECT id, name, current_cash, starting_cash FROM portfolios "
        "WHERE is_active=1 AND name != 'Treasury Reserve'"
    ).fetchall()

    planned = []
    # Quiet the trader's logger while we call its planning (don't pollute autonomous_trader.log)
    trader_log = logging.getLogger("bigclaw.trader")
    prev_level = trader_log.level
    trader_log.setLevel(logging.ERROR)
    try:
        for p in portfolios:
            pid, pname = p["id"], p["name"]
            cash, starting = p["current_cash"], p["starting_cash"]
            reserve = starting * MIN_CASH_RESERVE_PCT
            try:
                to_sell, to_buy, _target = at.plan_portfolio(
                    pid, pname, starting, signal_map, portfolio_signals, universes)
            except Exception:
                continue  # skip an unplannable portfolio rather than break the whole dashboard

            # SELLS — exactly what the trader will sell (discipline / not-in-top-10)
            for s in to_sell:
                planned.append({
                    "portfolio": pname,
                    "action": "SELL",
                    "ticker": s["ticker"],
                    "shares": s.get("shares", 0),
                    "score": s.get("score", 0),
                    "reason": s.get("discipline_reason")
                              or f"Not in top 10 (score {s.get('score', 0)})",
                })

            # BUYS — cash-aware sizing over the trader's universe/gate-filtered target,
            # mirroring the trader's allocation rule (so we don't show unfundable buys).
            sgov = conn.execute(
                "SELECT shares FROM holdings WHERE portfolio_id=? AND ticker=?",
                (pid, MONEY_MARKET)).fetchone()
            sgov_cash = (sgov["shares"] * 100.44) if sgov and sgov["shares"] > 0 else 0
            sell_proceeds = sum(s.get("shares", 0) * s.get("avg_cost", 0) for s in to_sell)
            cash_available = cash + sgov_cash + sell_proceeds - reserve
            for s in to_buy:
                score = s.get("score", 0)
                alloc_pct = 0.12 if score >= 5 else 0.10 if score >= 3 else 0.08
                target_alloc = starting * alloc_pct
                is_add = bool(s.get("is_add") or s.get("held"))
                if is_add:
                    target_alloc = min(target_alloc, s.get("gap", target_alloc))
                alloc = min(target_alloc, cash_available)
                if alloc < 500:
                    continue
                planned.append({
                    "portfolio": pname,
                    "action": "ADD" if is_add else "BUY",
                    "ticker": s["ticker"],
                    "score": score,
                    "reason": f"Score {score} — {'add to position' if is_add else 'new position (top 10)'}",
                    "est_allocation": round(alloc),
                })
                cash_available -= alloc
    finally:
        trader_log.setLevel(prev_level)
        conn.close()

    # Sort: sells first, then buys by score
    planned.sort(key=lambda x: (0 if "SELL" in x["action"] else 1, -abs(x.get("score", 0))))
    return planned


def inject_planned_actions():
    if not os.path.exists(SIGNALS_PATH):
        print("  No signals.json found")
        return

    planned = build_planned_actions()

    with open(SIGNALS_PATH) as f:
        data = json.load(f)

    # Mark actions already executed today
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    today = __import__("datetime").date.today().isoformat()
    today_txns = set()
    for r in conn.execute(
        "SELECT portfolio_id, ticker, action FROM transactions WHERE date(executed_at) >= ?",
        (today,)
    ).fetchall():
        pid = r[0]
        pname_row = conn.execute("SELECT name FROM portfolios WHERE id=?", (pid,)).fetchone()
        if pname_row:
            today_txns.add((pname_row[0], r[1], r[2]))
    conn.close()

    for a in planned:
        pname = a.get("portfolio", "")
        ticker = a.get("ticker", "")
        action_type = "sell" if "SELL" in a.get("action", "") else "buy"
        if (pname, ticker, action_type) in today_txns:
            a["executed"] = True

    data["planned_actions"] = planned

    with open(SIGNALS_PATH, "w") as f:
        json.dump(data, f, indent=2, default=str)

    sells = [a for a in planned if "SELL" in a["action"]]
    buys = [a for a in planned if a["action"] in ("BUY", "ADD")]
    print(f"  Planned actions: {len(sells)} sells, {len(buys)} buys/adds across "
          f"{len(set(a['portfolio'] for a in planned))} portfolios")


if __name__ == "__main__":
    inject_planned_actions()
