#!/usr/bin/env python3
"""One-shot remediation for the 2026-06-15 watcher/cycle double-sell incident.

Flattens the unintended short positions (AAL in LLM-Comando, IWM in LLM-ETF
Focus) by buying to cover ONLY the actual short quantity currently at Alpaca.
Books each cover as an is_correction cash debit in the per-portfolio DB; holdings
are left flat (the cover offsets the phantom sell, it does not open a long).
Cash settles naturally to (current - cover cost).

IDEMPOTENT: covers only live short qty; no-op if a symbol is already flat.
Safe to run more than once. Use --dry-run to preview without ordering.
"""
import os, sys, argparse, sqlite3, datetime
from pathlib import Path

REPO = Path.home() / "bigclaw-ai"
DB_PATH = REPO / "src" / "portfolios.db"
sys.path.insert(0, str(REPO / "scripts"))

TARGETS = [
    {"symbol": "AAL", "pid": 10, "name": "LLM-Comando",   "channel": "D0ADHLUJ400"},
    {"symbol": "IWM", "pid": 9,  "name": "LLM-ETF Focus",  "channel": "D0ADHLUJ400"},
]
MAX_COVER_QTY = 2000  # sanity ceiling; above this -> skip + manual review

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    from autonomous_trader import get_trading_client
    from order_fill import wait_for_fill
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce

    client = get_trading_client()
    clock = client.get_clock()
    summary = []

    if not args.dry_run and not clock.is_open:
        print(f"Market CLOSED (next open {clock.next_open}); aborting. Cover needs an open market.")
        return

    for t in TARGETS:
        sym, pid, name = t["symbol"], t["pid"], t["name"]
        try:
            pos = client.get_open_position(sym)
            qty = float(pos.qty)
            cur_price = float(getattr(pos, "current_price", 0) or 0)
        except Exception:
            qty, cur_price = 0.0, 0.0
        if qty >= 0:
            line = f"{name}/{sym}: not short (qty={qty}) -> skip (already flat)."
            print(line); summary.append(line); continue
        cover = int(abs(qty))
        if cover > MAX_COVER_QTY:
            line = f"{name}/{sym}: short {cover} exceeds ceiling {MAX_COVER_QTY} -> SKIP, manual review."
            print(line); summary.append(line); continue
        if args.dry_run:
            est = cover * (cur_price or 0)
            line = f"[DRY] {name}/{sym}: would BUY {cover} to cover (~${est:,.0f}); debit cash + is_correction txn; holdings stay flat."
            print(line); summary.append(line); continue

        order = client.submit_order(MarketOrderRequest(
            symbol=sym, qty=cover, side=OrderSide.BUY, time_in_force=TimeInForce.DAY))
        filled_qty, filled_price = wait_for_fill(client, order, cover, cur_price or None,
                                                 ticker=sym, pname=name, side="BUY")
        value = round(filled_qty * filled_price, 2)
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.execute("UPDATE portfolios SET current_cash = current_cash - ? WHERE id=?", (value, pid))
        conn.execute(
            "INSERT INTO transactions (portfolio_id,ticker,action,shares,price,total_value,"
            "rationale,executed_at,order_id,is_correction) VALUES (?,?,?,?,?,?,?,?,?,1)",
            (pid, sym, "buy", filled_qty, filled_price, value,
             "Cover unintended short from 2026-06-15 watcher/cycle double-sell incident",
             datetime.datetime.now(datetime.timezone.utc).isoformat(), str(order.id)))
        conn.commit(); conn.close()
        line = f"{name}/{sym}: COVERED {filled_qty} @ ${filled_price} (${value:,.2f}); cash debited, holdings flat."
        print(line); summary.append(line)

    tok = os.environ.get("SLACK_BOT_TOKEN")
    if tok and not args.dry_run:
        try:
            from slack_sdk import WebClient
            WebClient(token=tok).chat_postMessage(channel="D0ADHLUJ400",
                text="*Short-cover remediation (2026-06-15 incident)*\n" + "\n".join(summary))
        except Exception as e:
            print("slack skip:", e)

if __name__ == "__main__":
    main()
