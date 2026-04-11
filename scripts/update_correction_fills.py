"""Check correction sell fills and update DB with actual Alpaca prices.

Run after market open to:
1. Get actual fill prices from Alpaca for the 11 correction sells + IEF buy
2. Update transaction records with real prices
3. Recalculate portfolio cash
4. Verify all 3 overdrawn portfolios now have positive cash
5. Post results to Slack
"""
import sqlite3
import json
import urllib.request
from pathlib import Path
from datetime import datetime

DB = Path.home() / "bigclaw-ai" / "src" / "portfolios.db"

secrets = {}
for line in Path.home().joinpath(".env_secrets").read_text().splitlines():
    line = line.strip()
    if line.startswith("export "):
        line = line[7:]
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        secrets[k.strip()] = v.strip().strip('"')

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus

client = TradingClient(secrets["ALPACA_API_KEY"], secrets["ALPACA_SECRET_KEY"], paper=True)

# Get recent orders
orders = client.get_orders(GetOrdersRequest(status=QueryOrderStatus.ALL, limit=30))

print("=" * 70)
print("CORRECTION FILL CHECK")
print("=" * 70)

# Find our correction sells and IEF buy
correction_orders = []
for o in orders:
    created = o.created_at
    if created and created.strftime("%Y-%m-%d") == "2026-04-03":
        correction_orders.append(o)

print(f"\nOrders from today: {len(correction_orders)}")
print(f"{'Ticker':6s} {'Side':5s} {'Qty':>5s} {'Status':20s} {'Fill Qty':>8s} {'Fill Price':>10s}")
print("-" * 60)

fills = []
pending = []
for o in correction_orders:
    status = str(o.status)
    filled_qty = float(o.filled_qty or 0)
    filled_price = float(o.filled_avg_price) if o.filled_avg_price else 0
    side = "SELL" if "SELL" in str(o.side).upper() else "BUY"

    print(f"{o.symbol:6s} {side:5s} {str(o.qty):>5s} {status:20s} {filled_qty:>8.0f} ${filled_price:>9.2f}")

    if "FILLED" in status.upper():
        fills.append({
            "symbol": o.symbol,
            "side": side,
            "qty": int(filled_qty),
            "price": filled_price,
            "total": filled_qty * filled_price,
            "order_id": str(o.id),
        })
    else:
        pending.append(o.symbol)

if pending:
    print(f"\nWARNING: {len(pending)} orders not yet filled: {pending}")
    print("Run this script again after market open.")

if not fills:
    print("\nNo fills to process yet.")
    exit(0)

# Update DB transactions with actual fill prices
print(f"\n{'='*70}")
print("UPDATING DB WITH ACTUAL FILL PRICES")
print(f"{'='*70}")

conn = sqlite3.connect(str(DB), timeout=30)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=30000")
conn.row_factory = sqlite3.Row

updated = 0
for fill in fills:
    # Find the matching correction transaction
    # Match on: ticker, action, shares, and rationale containing CORRECTION
    action = "sell" if fill["side"] == "SELL" else "buy"
    rows = conn.execute("""
        SELECT id, price, total_value FROM transactions
        WHERE ticker = ? AND action = ? AND shares = ?
        AND (rationale LIKE '%CORRECTION%' OR rationale LIKE '%parking%')
        ORDER BY executed_at DESC LIMIT 1
    """, (fill["symbol"], action, fill["qty"])).fetchall()

    if rows:
        txn = rows[0]
        old_price = txn["price"]
        new_total = fill["qty"] * fill["price"]

        if abs(old_price - fill["price"]) > 0.01:
            conn.execute(
                "UPDATE transactions SET price = ?, total_value = ? WHERE id = ?",
                (fill["price"], round(new_total, 2), txn["id"]),
            )
            updated += 1
            print(f"  {fill['symbol']:6s} {action:5s} {fill['qty']:>5d} sh: ${old_price:.2f} -> ${fill['price']:.2f}")
        else:
            print(f"  {fill['symbol']:6s} {action:5s} {fill['qty']:>5d} sh: price OK (${fill['price']:.2f})")
    else:
        print(f"  {fill['symbol']:6s} {action:5s} {fill['qty']:>5d} sh: NO MATCHING TRANSACTION FOUND")

conn.commit()
print(f"\n{updated} prices updated")

# Recalculate cash for all portfolios
print(f"\n{'='*70}")
print("RECALCULATING PORTFOLIO CASH")
print(f"{'='*70}")

portfolios = conn.execute("SELECT id, name, starting_cash FROM portfolios WHERE is_active=1").fetchall()
all_ok = True
for p in portfolios:
    row = conn.execute("""
        SELECT COALESCE(SUM(CASE WHEN action='buy' THEN total_value ELSE 0 END), 0) as buys,
               COALESCE(SUM(CASE WHEN action='sell' THEN total_value ELSE 0 END), 0) as sells
        FROM transactions WHERE portfolio_id = ?
    """, (p["id"],)).fetchone()
    correct_cash = p["starting_cash"] - row["buys"] + row["sells"]
    conn.execute("UPDATE portfolios SET current_cash = ? WHERE id = ?",
                 (round(correct_cash, 2), p["id"]))
    status = "OK" if correct_cash >= 0 else "STILL OVERDRAWN"
    if correct_cash < 0:
        all_ok = False
    print(f"  {p['name']:25s} cash=${correct_cash:>10,.2f}  {status}")

conn.commit()
conn.close()

# Post to Slack
print(f"\n{'='*70}")
print("POSTING TO SLACK")
print(f"{'='*70}")

token = secrets.get("SLACK_BOT_TOKEN", "")
if token:
    msg = ":white_check_mark: *Correction Fills Processed*\n"
    msg += f"{len(fills)} orders filled, {updated} prices updated in DB.\n"
    if all_ok:
        msg += "All portfolios have positive cash. Books are clean."
    else:
        msg += ":warning: Some portfolios still overdrawn — check manually."
    payload = json.dumps({"channel": "D0ADHLUJ400", "text": msg}).encode()
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=payload,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        print("Slack notification sent")
    except Exception as e:
        print(f"Slack failed: {e}")

print("\nDone. Run audit_all_portfolios.py to verify.")
