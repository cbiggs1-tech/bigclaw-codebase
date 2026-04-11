"""Fix executed trade tracking on dashboard.

Problem: planned_actions regenerates from scratch, so executed sells/buys disappear.
Solution: Keep a separate 'executed_trades' list in signals.json that persists for 7 days.
The dashboard shows both: current plan + this week's executed trades.
"""
import json
import sqlite3
import os
from pathlib import Path
from datetime import datetime, timedelta

DB_PATH = os.path.expanduser("~/bigclaw-ai/src/portfolios.db")
SIGNALS_PATH = os.path.expanduser("~/bigclaw-ai/docs/data/signals.json")


def build_executed_trades():
    """Build list of trades executed this week for dashboard display."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.row_factory = sqlite3.Row

    # Get trades from the last 7 days, excluding corrections and SGOV sweeps
    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    trades = conn.execute("""
        SELECT t.ticker, t.action, t.shares, t.price, t.total_value, t.rationale,
               t.executed_at, p.name as portfolio
        FROM transactions t
        JOIN portfolios p ON t.portfolio_id = p.id
        WHERE date(t.executed_at) >= ?
        AND t.rationale NOT LIKE '%CORRECTION%'
        AND t.rationale NOT LIKE '%RECONCILIATION%'
        AND t.rationale NOT LIKE '%Money market%'
        AND t.rationale NOT LIKE '%Alpaca truth%'
        AND t.ticker != 'SGOV'
        ORDER BY t.executed_at DESC
    """, (cutoff,)).fetchall()

    conn.close()

    result = []
    for t in trades:
        action = t["action"].upper()
        rationale = t["rationale"] or ""

        # Determine action label
        if "UPGRADE-SELL" in rationale or "FUND-SELL" in rationale:
            label = "UPGRADE-SELL"
        elif "SWAP" in rationale:
            label = "SWAP-SELL"
        elif action == "SELL":
            label = "SELL"
        elif action == "BUY":
            label = "BUY" if "ADD" not in rationale else "ADD"
        else:
            label = action

        result.append({
            "portfolio": t["portfolio"],
            "action": label,
            "ticker": t["ticker"],
            "shares": int(t["shares"]),
            "price": round(t["price"], 2),
            "total": round(t["total_value"], 2),
            "reason": rationale[:80],
            "date": t["executed_at"][:10] if t["executed_at"] else "",
            "executed": True,
        })

    return result


def inject_executed_trades():
    """Add executed_trades to signals.json."""
    if not os.path.exists(SIGNALS_PATH):
        return

    executed = build_executed_trades()

    with open(SIGNALS_PATH) as f:
        data = json.load(f)

    data["executed_this_week"] = executed

    with open(SIGNALS_PATH, "w") as f:
        json.dump(data, f, indent=2, default=str)

    print(f"  Executed trades this week: {len(executed)}")


if __name__ == "__main__":
    inject_executed_trades()
