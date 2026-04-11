#!/usr/bin/env python3
"""Build cash-aware execution plan for dashboard — Best-in-Class v3.

Logic (per portfolio):
1. Score ALL holdings + candidates from portfolio universe
2. Rank by score — top MAX_HOLDINGS are the target portfolio
3. Sell anything held that's NOT in the target
4. Buy anything in the target that's NOT held (cash permitting)
5. No loyalty to existing positions — if something better appears, swap it in
"""
import json
import sqlite3
import os
from pathlib import Path

DB_PATH = os.path.expanduser("~/bigclaw-ai/src/portfolios.db")
DATA_DIR = os.path.expanduser("~/bigclaw-ai/docs/data")
SIGNALS_PATH = os.path.join(DATA_DIR, "signals.json")

MAX_HOLDINGS = 10
SCORE_BUY_MINIMUM = 1   # Must score at least 1 to deploy cash
MIN_CASH_RESERVE_PCT = 0.02
MONEY_MARKET = "SGOV"


def build_planned_actions():
    if not os.path.exists(SIGNALS_PATH):
        return []

    with open(SIGNALS_PATH) as f:
        data = json.load(f)

    signals = data.get("signals", [])
    port_signals = data.get("portfolio_signals", {})
    signal_map = {s["ticker"]: s for s in signals}

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.row_factory = sqlite3.Row

    portfolios = conn.execute(
        "SELECT id, name, current_cash, starting_cash FROM portfolios "
        "WHERE is_active=1 AND name != 'Treasury Reserve'"
    ).fetchall()

    planned = []

    for p in portfolios:
        pid = p["id"]
        pname = p["name"]
        cash = p["current_cash"]
        starting = p["starting_cash"]
        reserve = starting * MIN_CASH_RESERVE_PCT

        # Get current non-SGOV holdings
        holdings = conn.execute(
            "SELECT ticker, shares, avg_cost FROM holdings WHERE portfolio_id=? AND shares > 0",
            (pid,),
        ).fetchall()

        psigs = port_signals.get(pname, {})
        all_scored = {}

        # Score current holdings
        for h in holdings:
            ticker = h["ticker"]
            if ticker == MONEY_MARKET:
                continue
            if ticker in psigs:
                score = psigs[ticker].get("score", 0)
            else:
                sig = signal_map.get(ticker)
                score = sig.get("score", 0) if sig else 0
            all_scored[ticker] = {
                "ticker": ticker, "score": score, "held": True,
                "shares": int(h["shares"]), "value": h["shares"] * h["avg_cost"],
                "avg_cost": h["avg_cost"],
            }

        # Score all candidates from portfolio signals
        for ticker, sig in psigs.items():
            if ticker == MONEY_MARKET or ticker in all_scored:
                continue
            score = sig.get("score", 0)
            all_scored[ticker] = {
                "ticker": ticker, "score": score, "held": False,
                "shares": 0, "value": 0, "avg_cost": 0,
            }

        # Rank by score — top MAX_HOLDINGS are the target
        ranked = sorted(all_scored.values(), key=lambda x: x["score"], reverse=True)
        target = ranked[:MAX_HOLDINGS]
        target_tickers = {s["ticker"] for s in target}

        # Sells: held but NOT in target
        for s in ranked:
            if s["held"] and s["ticker"] not in target_tickers:
                planned.append({
                    "portfolio": pname,
                    "action": "SELL",
                    "ticker": s["ticker"],
                    "shares": s["shares"],
                    "score": s["score"],
                    "reason": f"Not in top {MAX_HOLDINGS} (score {s['score']})",
                })

        # Calculate available cash (current + SGOV + sell proceeds)
        sgov = conn.execute(
            "SELECT shares FROM holdings WHERE portfolio_id=? AND ticker=?",
            (pid, MONEY_MARKET),
        ).fetchone()
        sgov_cash = (sgov["shares"] * 100.44) if sgov and sgov["shares"] > 0 else 0
        sell_proceeds = sum(
            s["shares"] * s["avg_cost"]
            for s in ranked
            if s["held"] and s["ticker"] not in target_tickers
        )
        cash_available = cash + sgov_cash + sell_proceeds - reserve

        # Buys: in target but NOT held (or held but underweight)
        for s in target:
            if s["score"] < SCORE_BUY_MINIMUM:
                continue

            # Position sizing
            if s["score"] >= 5:
                alloc_pct = 0.12
            elif s["score"] >= 3:
                alloc_pct = 0.10
            else:
                alloc_pct = 0.08
            target_alloc = starting * alloc_pct

            if s["held"]:
                # Check if underweight — only add if more than 20% below target
                if s["value"] >= target_alloc * 0.80:
                    continue  # Adequately weighted
                gap = target_alloc - s["value"]
                alloc = min(gap, cash_available)
                if alloc < 500:
                    continue
                planned.append({
                    "portfolio": pname, "action": "ADD",
                    "ticker": s["ticker"], "score": s["score"],
                    "reason": f"Score {s['score']} — add to position",
                    "est_allocation": round(alloc),
                })
                cash_available -= alloc
            else:
                # New position
                alloc = min(target_alloc, cash_available)
                if alloc < 500:
                    continue
                planned.append({
                    "portfolio": pname, "action": "BUY",
                    "ticker": s["ticker"], "score": s["score"],
                    "reason": f"Score {s['score']} — new position (top {MAX_HOLDINGS})",
                    "est_allocation": round(alloc),
                })
                cash_available -= alloc

    conn.close()

    # Sort: sells first, then buys by score
    planned.sort(key=lambda x: (
        0 if "SELL" in x["action"] else 1,
        -abs(x["score"]),
    ))

    return planned


def inject_planned_actions():
    if not os.path.exists(SIGNALS_PATH):
        print("  No signals.json found")
        return

    planned = build_planned_actions()

    with open(SIGNALS_PATH) as f:
        data = json.load(f)

    # Mark executed actions
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
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
