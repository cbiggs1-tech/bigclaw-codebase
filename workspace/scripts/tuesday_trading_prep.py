#!/usr/bin/env python3
"""Tuesday Feb 18 Trading Prep — Run at 9:45 AM ET to prepare for 10 AM execution.

Steps:
1. Fetch current prices for all new portfolio tickers
2. Recalculate share counts at live prices
3. Generate SQL with updated prices
4. Show decision engine signals for existing portfolios
5. Output execution plan for trade_executor.py commands
"""

import yfinance as yf
import sqlite3
import json
from datetime import datetime

DB_PATH = "/home/cbiggs90/bigclaw-ai/src/portfolios.db"

# ── New Portfolio Designs ──────────────────────────────────────────────────────

INCOME_DIVIDEND = {
    "name": "Income Dividends",
    "style": "Income / Dividend Growth",
    "total": 100000,
    "holdings": [
        {"ticker": "VZ",  "weight": 0.14, "rationale": "Highest sustainable yield 5.77%, 50% payout, massive FCF"},
        {"ticker": "O",   "weight": 0.13, "rationale": "Monthly REIT dividend 4.93%, 30yr streak"},
        {"ticker": "T",   "weight": 0.12, "rationale": "Rebuilt post-2022 cut, 27% payout, $12.6B FCF"},
        {"ticker": "XOM", "weight": 0.12, "rationale": "42yr Dividend Aristocrat, fortress balance sheet"},
        {"ticker": "DUK", "weight": 0.11, "rationale": "Regulated utility, 3.32% yield, stable"},
        {"ticker": "ED",  "weight": 0.11, "rationale": "37yr streak, regulated NYC utility, recession-proof"},
        {"ticker": "PG",  "weight": 0.10, "rationale": "68yr Dividend King, consumer staple moat"},
        {"ticker": "IBM", "weight": 0.09, "rationale": "29yr dividend streak, AI/hybrid cloud growth"},
        {"ticker": "JNJ", "weight": 0.08, "rationale": "63yr Dividend King, healthcare stability"},
    ]
}

MOMENTUM_GROWTH = {
    "name": "Momentum Growth",
    "style": "Momentum / Aggressive Growth",
    "total": 100000,
    "cash_reserve": 30000,  # 30% cash
    "holdings": [
        {"ticker": "DECK", "weight": 0.20, "rationale": "Strongest 3mo momentum, above both SMAs"},
        {"ticker": "GE",   "weight": 0.18, "rationale": "Above both SMAs, aerospace momentum, 18% rev growth"},
        {"ticker": "ANET", "weight": 0.15, "rationale": "Above both SMAs, 29% rev growth, AI networking"},
        {"ticker": "LLY",  "weight": 0.12, "rationale": "+63% 6mo, GLP-1 secular trend, 43% rev growth"},
        {"ticker": "AVGO", "weight": 0.05, "rationale": "Starter position, AI semiconductor leader"},
    ]
}


def get_live_prices(tickers):
    """Fetch current prices."""
    prices = {}
    for t in tickers:
        try:
            data = yf.Ticker(t).info
            price = data.get("currentPrice") or data.get("regularMarketPrice") or data.get("previousClose")
            prices[t] = round(float(price), 2) if price else None
        except Exception as e:
            print(f"  ⚠️ Failed to get price for {t}: {e}")
            prices[t] = None
    return prices


def calculate_shares(portfolio, prices):
    """Calculate share counts at live prices."""
    total = portfolio["total"]
    cash_reserve = portfolio.get("cash_reserve", 0)
    investable = total - cash_reserve
    
    results = []
    total_cost = 0
    for h in portfolio["holdings"]:
        ticker = h["ticker"]
        price = prices.get(ticker)
        if price is None:
            print(f"  ❌ No price for {ticker} — skipping")
            continue
        dollar_alloc = total * h["weight"]
        shares = int(dollar_alloc / price)
        cost = shares * price
        total_cost += cost
        results.append({
            "ticker": ticker,
            "shares": shares,
            "price": price,
            "cost": cost,
            "weight_actual": cost / total * 100,
            "rationale": h["rationale"],
        })
    
    remaining_cash = total - total_cost
    return results, remaining_cash


def get_existing_portfolio_ids():
    """Get current portfolio IDs from DB."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM portfolios WHERE is_active = 1")
    portfolios = cur.fetchall()
    conn.close()
    return portfolios


def generate_sql(portfolio_name, style, holdings, remaining_cash, next_id):
    """Generate SQL for new portfolio."""
    lines = []
    lines.append(f"-- Portfolio {next_id}: {portfolio_name}")
    lines.append(f"INSERT INTO portfolios (name, investment_style, starting_cash, current_cash, report_channel, is_active)")
    lines.append(f"VALUES ('{portfolio_name}', '{style}', 100000, {remaining_cash:.2f}, 'D0ADHLUJ400', 1);")
    lines.append("")
    
    for h in holdings:
        lines.append(f"INSERT INTO holdings (portfolio_id, ticker, shares, avg_cost, rationale)")
        lines.append(f"VALUES ({next_id}, '{h['ticker']}', {h['shares']}, {h['price']}, '{h['rationale']}');")
    lines.append("")
    
    date = datetime.now().strftime('%Y-%m-%d')
    for h in holdings:
        lines.append(f"INSERT INTO transactions (portfolio_id, ticker, action, shares, price, rationale, executed_at)")
        lines.append(f"VALUES ({next_id}, '{h['ticker']}', 'buy', {h['shares']}, {h['price']}, 'Initial portfolio construction', '{date}');")
    
    return "\n".join(lines)


def generate_executor_commands(holdings, portfolio_name):
    """Generate trade_executor.py commands."""
    cmds = []
    for h in holdings:
        cmds.append(f"python3 trade_executor.py --buy {h['ticker']} --shares {h['shares']} --dry-run")
    return cmds


def main():
    print("=" * 60)
    print("📊 TUESDAY TRADING PREP — Feb 18, 2026")
    print("=" * 60)
    
    # Get all tickers
    all_tickers = set()
    for h in INCOME_DIVIDEND["holdings"]:
        all_tickers.add(h["ticker"])
    for h in MOMENTUM_GROWTH["holdings"]:
        all_tickers.add(h["ticker"])
    
    print(f"\n🔍 Fetching live prices for {len(all_tickers)} tickers...")
    prices = get_live_prices(sorted(all_tickers))
    
    for t, p in sorted(prices.items()):
        print(f"  {t}: ${p}")
    
    # Existing portfolios
    print(f"\n📋 Existing Portfolios:")
    existing = get_existing_portfolio_ids()
    for pid, name in existing:
        print(f"  [{pid}] {name}")
    next_id = max(p[0] for p in existing) + 1 if existing else 1
    
    # Income/Dividend
    print(f"\n{'='*60}")
    print(f"💰 PORTFOLIO {next_id}: {INCOME_DIVIDEND['name']}")
    print(f"{'='*60}")
    holdings_inc, cash_inc = calculate_shares(INCOME_DIVIDEND, prices)
    for h in holdings_inc:
        print(f"  {h['ticker']:5s} | {h['shares']:4d} shares @ ${h['price']:>8.2f} = ${h['cost']:>10,.2f} ({h['weight_actual']:.1f}%)")
    print(f"  {'CASH':5s} | {'':4s}        {'':>8s}   ${cash_inc:>10,.2f} ({cash_inc/100000*100:.1f}%)")
    print(f"  Total: ${sum(h['cost'] for h in holdings_inc) + cash_inc:,.2f}")
    
    # Momentum Growth
    print(f"\n{'='*60}")
    print(f"🚀 PORTFOLIO {next_id+1}: {MOMENTUM_GROWTH['name']}")
    print(f"{'='*60}")
    holdings_mom, cash_mom = calculate_shares(MOMENTUM_GROWTH, prices)
    for h in holdings_mom:
        print(f"  {h['ticker']:5s} | {h['shares']:4d} shares @ ${h['price']:>8.2f} = ${h['cost']:>10,.2f} ({h['weight_actual']:.1f}%)")
    print(f"  {'CASH':5s} | {'':4s}        {'':>8s}   ${cash_mom:>10,.2f} ({cash_mom/100000*100:.1f}%)")
    print(f"  Total: ${sum(h['cost'] for h in holdings_mom) + cash_mom:,.2f}")
    
    # SQL
    print(f"\n{'='*60}")
    print("📝 SQL STATEMENTS")
    print(f"{'='*60}")
    sql_inc = generate_sql(INCOME_DIVIDEND["name"], INCOME_DIVIDEND["style"], holdings_inc, cash_inc, next_id)
    sql_mom = generate_sql(MOMENTUM_GROWTH["name"], MOMENTUM_GROWTH["style"], holdings_mom, cash_mom, next_id+1)
    print(sql_inc)
    print()
    print(sql_mom)
    
    # Executor commands
    print(f"\n{'='*60}")
    print("🔧 TRADE EXECUTOR COMMANDS (dry-run)")
    print(f"{'='*60}")
    print(f"\n# Create portfolios first:")
    print(f"python3 trade_executor.py --create-portfolio \"{INCOME_DIVIDEND['name']}\" --style \"{INCOME_DIVIDEND['style']}\"")
    print(f"python3 trade_executor.py --create-portfolio \"{MOMENTUM_GROWTH['name']}\" --style \"{MOMENTUM_GROWTH['style']}\"")
    print(f"\n# Then execute SQL directly (trade_executor doesn't handle initial bulk buys well):")
    print(f"sqlite3 {DB_PATH} < income_dividend.sql")
    print(f"sqlite3 {DB_PATH} < momentum_growth.sql")
    print(f"\n# Then place Alpaca orders:")
    for h in holdings_inc:
        print(f"python3 trade_executor.py --buy {h['ticker']} --shares {h['shares']} --dry-run")
    for h in holdings_mom:
        print(f"python3 trade_executor.py --buy {h['ticker']} --shares {h['shares']} --dry-run")
    
    # Save SQL files
    with open("/tmp/income_dividend.sql", "w") as f:
        f.write(sql_inc)
    with open("/tmp/momentum_growth.sql", "w") as f:
        f.write(sql_mom)
    print(f"\n✅ SQL saved to /tmp/income_dividend.sql and /tmp/momentum_growth.sql")
    print(f"\n⚠️  REMINDER: Run decision_engine.py for existing portfolio signals before executing trades!")


if __name__ == "__main__":
    main()
