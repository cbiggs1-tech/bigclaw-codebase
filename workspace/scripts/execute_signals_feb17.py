#!/usr/bin/env python3
"""
Feb 17, 2026 — Signal-filtered trade execution
Updates SQLite DB (source of truth for virtual portfolios)
Submits to Alpaca where buying power allows
"""

import sqlite3
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
DB_PATH = Path.home() / "bigclaw-ai" / "src" / "portfolios.db"
LOG_FILE = Path.home() / ".openclaw" / "workspace" / "logs" / "trades.log"
LOG_FILE.parent.mkdir(exist_ok=True)

now = datetime.now(ET).strftime("%Y-%m-%d %H:%M ET")
results = []

def log(msg):
    results.append(msg)
    print(msg)
    with open(LOG_FILE, "a") as f:
        f.write(f"{now} | {msg}\n")

def db_sell(portfolio_id, ticker, shares_to_sell, reason):
    """Sell shares from a portfolio in the DB. Returns (shares_sold, price, proceeds)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT shares, avg_cost FROM holdings WHERE portfolio_id=? AND ticker=?", (portfolio_id, ticker))
    row = c.fetchone()
    if not row or row[0] <= 0:
        log(f"  SKIP SELL {ticker} (P{portfolio_id}) — no shares held")
        conn.close()
        return 0, 0, 0
    
    current_shares = row[0]
    avg_cost = row[1]
    actual_sell = min(shares_to_sell, current_shares)
    
    # Get current price via yfinance
    import yfinance as yf
    tk = yf.Ticker(ticker)
    price = tk.fast_info.get('lastPrice', avg_cost)
    
    proceeds = actual_sell * price
    remaining = current_shares - actual_sell
    
    if remaining <= 0.01:
        c.execute("DELETE FROM holdings WHERE portfolio_id=? AND ticker=?", (portfolio_id, ticker))
        actual_sell = current_shares
    else:
        c.execute("UPDATE holdings SET shares=? WHERE portfolio_id=? AND ticker=?", (remaining, portfolio_id, ticker))
    
    c.execute("UPDATE portfolios SET current_cash = current_cash + ? WHERE id=?", (proceeds, portfolio_id))
    c.execute("INSERT INTO transactions (portfolio_id, ticker, action, shares, price, total_value, rationale, executed_at) VALUES (?,?,?,?,?,?,?,?)",
              (portfolio_id, ticker, 'sell', actual_sell, price, proceeds, reason, now))
    conn.commit()
    conn.close()
    log(f"  SELL {actual_sell:.2f} {ticker} (P{portfolio_id}) @ ${price:.2f} = ${proceeds:,.2f} — {reason}")
    return actual_sell, price, proceeds

def db_buy(portfolio_id, ticker, shares, limit_price, reason):
    """Buy shares in a portfolio in the DB using limit price."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    cost = shares * limit_price
    c.execute("SELECT current_cash FROM portfolios WHERE id=?", (portfolio_id,))
    cash = c.fetchone()[0]
    if cost > cash:
        log(f"  SKIP BUY {shares} {ticker} (P{portfolio_id}) — cost ${cost:,.2f} > cash ${cash:,.2f}")
        conn.close()
        return 0, 0, 0
    
    # Check existing position
    c.execute("SELECT shares, avg_cost FROM holdings WHERE portfolio_id=? AND ticker=?", (portfolio_id, ticker))
    row = c.fetchone()
    if row and row[0] > 0:
        old_shares, old_cost = row
        new_shares = old_shares + shares
        new_avg = ((old_shares * old_cost) + cost) / new_shares
        c.execute("UPDATE holdings SET shares=?, avg_cost=? WHERE portfolio_id=? AND ticker=?",
                  (new_shares, new_avg, portfolio_id, ticker))
    else:
        c.execute("INSERT INTO holdings (portfolio_id, ticker, shares, avg_cost, rationale) VALUES (?,?,?,?,?)",
                  (portfolio_id, ticker, shares, limit_price, reason))
    
    c.execute("UPDATE portfolios SET current_cash = current_cash - ? WHERE id=?", (cost, portfolio_id))
    c.execute("INSERT INTO transactions (portfolio_id, ticker, action, shares, price, total_value, rationale, executed_at) VALUES (?,?,?,?,?,?,?,?)",
              (portfolio_id, ticker, 'buy', shares, limit_price, cost, reason, now))
    conn.commit()
    conn.close()
    log(f"  BUY {shares} {ticker} (P{portfolio_id}) @ ${limit_price:.2f} = ${cost:,.2f} — {reason}")
    return shares, limit_price, cost

def db_remove_holding(portfolio_id, ticker, reason):
    """Fully remove a holding and return cash to portfolio."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT shares, avg_cost FROM holdings WHERE portfolio_id=? AND ticker=?", (portfolio_id, ticker))
    row = c.fetchone()
    if not row or row[0] <= 0:
        conn.close()
        return
    shares, avg_cost = row
    
    import yfinance as yf
    tk = yf.Ticker(ticker)
    price = tk.fast_info.get('lastPrice', avg_cost)
    proceeds = shares * price
    
    c.execute("DELETE FROM holdings WHERE portfolio_id=? AND ticker=?", (portfolio_id, ticker))
    c.execute("UPDATE portfolios SET current_cash = current_cash + ? WHERE id=?", (proceeds, portfolio_id))
    c.execute("INSERT INTO transactions (portfolio_id, ticker, action, shares, price, total_value, rationale, executed_at) VALUES (?,?,?,?,?,?,?,?)",
              (portfolio_id, ticker, 'sell', shares, price, proceeds, reason, now))
    conn.commit()
    conn.close()
    log(f"  SELL (full) {shares:.2f} {ticker} (P{portfolio_id}) @ ${price:.2f} = ${proceeds:,.2f} — {reason}")

# =========================================================================
# EXECUTION PLAN
# =========================================================================

log("=" * 70)
log(f"TRADING EXECUTION — {now}")
log("=" * 70)

# --- 1. ACTIVE PORTFOLIOS (1-3) — Signal-based sells ---
log("\n📉 PORTFOLIO 1-3 SELLS (Decision Engine Signals)")

# Portfolio 1 (Value Picks): Sell V (-4, 100%)
db_remove_holding(1, 'V', 'Signal -4: sell 100%')

# Portfolio 2 (Innovation Fund): Sell RBLX (-5, 100%)
db_remove_holding(2, 'RBLX', 'Signal -5: sell 100%')

# Portfolio 2: Trim CRSP (-3, 50%)
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("SELECT shares FROM holdings WHERE portfolio_id=2 AND ticker='CRSP'")
r = c.fetchone()
conn.close()
if r and r[0] > 0:
    db_sell(2, 'CRSP', r[0] * 0.5, 'Signal -3: trim 50%')

# Portfolio 2: Trim QBTS (-3, 50%)
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("SELECT shares FROM holdings WHERE portfolio_id=2 AND ticker='QBTS'")
r = c.fetchone()
conn.close()
if r and r[0] > 0:
    db_sell(2, 'QBTS', r[0] * 0.5, 'Signal -3: trim 50%')

# Portfolio 3: Trim MSFT (-3, 50%)
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("SELECT shares FROM holdings WHERE portfolio_id=3 AND ticker='MSFT'")
r = c.fetchone()
conn.close()
if r and r[0] > 0:
    db_sell(3, 'MSFT', r[0] * 0.5, 'Signal -3: trim 50%')

# --- 2. INCOME DIVIDENDS (#4) — Signal-filtered ---
log("\n📊 PORTFOLIO 4 (Income Dividends) — Signal Filter")
log("  SKIP: T (score -1, overbought RSI 81), DUK (score 0), IBM (score 0)")

# Remove T, DUK, IBM positions (already bought but signals say skip)
db_remove_holding(4, 'T', 'Signal -1: overbought RSI 81, removing position')
db_remove_holding(4, 'DUK', 'Signal 0: below threshold, removing position')
db_remove_holding(4, 'IBM', 'Signal 0: below threshold, removing position')

# Verify remaining buys exist: VZ(+2), O(+5), XOM(+2), ED(+6), PG(+1), JNJ(+5)
# These should already be in DB from prior setup
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
for ticker in ['VZ', 'O', 'XOM', 'ED', 'PG', 'JNJ']:
    c.execute("SELECT shares FROM holdings WHERE portfolio_id=4 AND ticker=?", (ticker,))
    r = c.fetchone()
    if r:
        log(f"  HOLD {ticker}: {r[0]:.0f} shares (already positioned)")
    else:
        log(f"  WARNING: {ticker} not in portfolio 4!")
conn.close()

# --- 3. MOMENTUM GROWTH (#5) — All signals positive ---
log("\n🚀 PORTFOLIO 5 (Momentum Growth) — All Signals Positive")
log("  All positions already established: DECK(+5), GE(+2), ANET(+5), LLY(+1), AVGO(+1)")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
for ticker in ['DECK', 'GE', 'ANET', 'LLY', 'AVGO']:
    c.execute("SELECT shares FROM holdings WHERE portfolio_id=5 AND ticker=?", (ticker,))
    r = c.fetchone()
    if r:
        log(f"  HOLD {ticker}: {r[0]:.0f} shares")
    else:
        log(f"  WARNING: {ticker} not in portfolio 5!")
conn.close()

# --- 4. NUCLEAR RENAISSANCE (#6) — Signal-filtered ---
log("\n☢️ PORTFOLIO 6 (Nuclear Renaissance) — Signal Filter")
log("  SKIP: CEG (-5, death cross), VST (-5, death cross)")

# Remove CEG and VST (signal says skip)
db_remove_holding(6, 'CEG', 'Signal -5: death cross, removing position')
db_remove_holding(6, 'VST', 'Signal -5: death cross, removing position')

# Verify remaining: GEV(+5), CCJ(+3), BWXT(+2), TLN(+2)
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
for ticker in ['GEV', 'CCJ', 'BWXT', 'TLN']:
    c.execute("SELECT shares FROM holdings WHERE portfolio_id=6 AND ticker=?", (ticker,))
    r = c.fetchone()
    if r:
        log(f"  HOLD {ticker}: {r[0]:.0f} shares")
    else:
        log(f"  WARNING: {ticker} not in portfolio 6!")
conn.close()

# --- 5. AI DEFENSE (#7) — Signal-filtered ---
log("\n🛡️ PORTFOLIO 7 (AI Defense) — Signal Filter")
log("  SKIP: BAH (-5, death cross), AVAV (-2), LDOS (0)")
log("  REDUCE: PLTR (+1 but borderline — half size)")

# Remove BAH, AVAV, LDOS
db_remove_holding(7, 'BAH', 'Signal -5: death cross, removing position')
db_remove_holding(7, 'AVAV', 'Signal -2: removing position')
db_remove_holding(7, 'LDOS', 'Signal 0: below threshold, removing position')

# Trim PLTR to half size
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("SELECT shares FROM holdings WHERE portfolio_id=7 AND ticker='PLTR'")
r = c.fetchone()
conn.close()
if r and r[0] > 0:
    db_sell(7, 'PLTR', r[0] * 0.5, 'Signal +1 borderline: reduce to half size')

# Verify remaining: NOC(+4), TXT(+4), RTX(+3), LMT(+3), KTOS(+1 reduced), LHX(+1), GD(+1)
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
for ticker in ['NOC', 'TXT', 'RTX', 'LMT', 'KTOS', 'LHX', 'GD']:
    c.execute("SELECT shares FROM holdings WHERE portfolio_id=7 AND ticker=?", (ticker,))
    r = c.fetchone()
    if r:
        log(f"  HOLD {ticker}: {r[0]:.0f} shares")
    else:
        log(f"  WARNING: {ticker} not in portfolio 7!")
conn.close()

# --- SUMMARY ---
log("\n" + "=" * 70)
log("PORTFOLIO SUMMARY (Post-Execution)")
log("=" * 70)

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("SELECT id, name, current_cash FROM portfolios ORDER BY id")
for pid, name, cash in c.fetchall():
    c2 = conn.cursor()
    c2.execute("SELECT SUM(shares * avg_cost) FROM holdings WHERE portfolio_id=? AND shares > 0", (pid,))
    holdings_val = c2.fetchone()[0] or 0
    total = cash + holdings_val
    log(f"  P{pid} {name}: Cash ${cash:,.2f} | Holdings ~${holdings_val:,.2f} | Total ~${total:,.2f}")
conn.close()

log("\n⚠️ NOTE: DB is source of truth for virtual portfolios.")
log("Alpaca paper account ($100K) cannot hold all 7 portfolios simultaneously.")
log("Cash from removed positions held for re-entry when signals improve.")
