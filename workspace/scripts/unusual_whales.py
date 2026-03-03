#!/usr/bin/env python3
"""
Unusual Whales API Integration — BigClaw
Tracks options flow, dark pool, and congressional trades.

Usage:
  python3 unusual_whales.py                    # TSLA focus (default)
  python3 unusual_whales.py --ticker NVDA      # Any ticker
  python3 unusual_whales.py --dark-pool TSLA   # Dark pool only
  python3 unusual_whales.py --congress         # Congressional trades
  python3 unusual_whales.py --flow-alerts      # Market-wide unusual flow
  python3 unusual_whales.py --all TSLA         # Full report
"""

import os
import sys
import json
import argparse
import requests
from datetime import datetime, timezone

TOKEN = os.environ.get("UNUSUAL_WHALES_TOKEN", "")
BASE  = "https://api.unusualwhales.com/api"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def get(path, params=None):
    r = requests.get(f"{BASE}/{path}", headers=HEADERS, params=params, timeout=15)
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}: {r.text[:200]}"
    data = r.json()
    if "error" in data:
        return None, data["error"]
    return data.get("data", data), None


def fmt_premium(val):
    v = float(val)
    if v >= 1_000_000:
        return f"${v/1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v/1_000:.0f}K"
    return f"${v:.0f}"


def fmt_time(iso):
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%H:%M:%S")
    except:
        return iso


# ── Options Flow ──────────────────────────────────────────────────────────────

def options_flow(ticker, limit=15):
    print(f"\n📊 OPTIONS FLOW — {ticker}")
    print("=" * 60)

    data, err = get(f"stock/{ticker}/option-contracts", {"limit": limit})
    if err:
        print(f"  Error: {err}")
        return

    if not data:
        print("  No data returned.")
        return

    bullish = []
    bearish = []

    for c in data:
        sym = c.get("option_symbol", "")
        # Parse option symbol: TSLA260223P00400000
        try:
            side = "CALL" if "C" in sym.split(ticker)[-1][:8] else "PUT"
        except:
            side = "?"

        vol       = int(c.get("volume", 0))
        oi        = int(c.get("open_interest", 0))
        prem      = fmt_premium(c.get("total_premium", 0))
        iv        = float(c.get("implied_volatility", 0)) * 100
        ask_vol   = int(c.get("ask_volume", 0))
        bid_vol   = int(c.get("bid_volume", 0))
        sweep_vol = int(c.get("sweep_volume", 0))
        last      = c.get("last_price", "?")

        # Sentiment: ask-side = bullish, bid-side = bearish
        if ask_vol > bid_vol:
            sentiment = "🟢 Bull"
        elif bid_vol > ask_vol:
            sentiment = "🔴 Bear"
        else:
            sentiment = "⚪ Neut"

        row = {
            "symbol": sym, "side": side, "vol": vol, "oi": oi,
            "prem": prem, "iv": f"{iv:.1f}%", "sweep": sweep_vol,
            "last": last, "sentiment": sentiment
        }

        if side == "CALL":
            bullish.append(row)
        else:
            bearish.append(row)

    # Sort by volume
    bullish.sort(key=lambda x: x["vol"], reverse=True)
    bearish.sort(key=lambda x: x["vol"], reverse=True)

    total_call_prem = sum(float(c.get("total_premium", 0)) for c in data
                          if "C" in c.get("option_symbol","").split(ticker)[-1][:8])
    total_put_prem  = sum(float(c.get("total_premium", 0)) for c in data
                          if "P" in c.get("option_symbol","").split(ticker)[-1][:8])

    print(f"  Call Premium: {fmt_premium(total_call_prem)} | "
          f"Put Premium: {fmt_premium(total_put_prem)}")

    ratio = total_call_prem / total_put_prem if total_put_prem > 0 else 0
    if ratio > 1.5:
        print(f"  💪 Bullish flow dominant (C/P ratio: {ratio:.2f}x)")
    elif ratio < 0.67:
        print(f"  🐻 Bearish flow dominant (C/P ratio: {ratio:.2f}x)")
    else:
        print(f"  ⚖️  Balanced flow (C/P ratio: {ratio:.2f}x)")

    print()

    print("  TOP CALLS:")
    for r in bullish[:5]:
        print(f"    {r['symbol'][-15:]:15} | Vol:{r['vol']:>6,} | OI:{r['oi']:>6,} | "
              f"{r['prem']:>8} | IV:{r['iv']:>6} | Sweeps:{r['sweep']:>4} | {r['sentiment']}")

    print()
    print("  TOP PUTS:")
    for r in bearish[:5]:
        print(f"    {r['symbol'][-15:]:15} | Vol:{r['vol']:>6,} | OI:{r['oi']:>6,} | "
              f"{r['prem']:>8} | IV:{r['iv']:>6} | Sweeps:{r['sweep']:>4} | {r['sentiment']}")


# ── Dark Pool ─────────────────────────────────────────────────────────────────

def dark_pool(ticker, limit=20):
    print(f"\n🌑 DARK POOL — {ticker}")
    print("=" * 60)

    data, err = get(f"darkpool/{ticker}", {"limit": limit})
    if err:
        print(f"  Error: {err}")
        return

    if not data:
        print("  No recent dark pool prints.")
        return

    total_vol   = sum(int(t.get("size", 0)) for t in data)
    total_prem  = sum(float(t.get("premium", 0)) for t in data)

    print(f"  Recent prints: {len(data)} | "
          f"Total shares: {total_vol:,} | "
          f"Total value: {fmt_premium(total_prem)}")
    print()

    # Look for large blocks
    large = [t for t in data if float(t.get("premium", 0)) >= 50_000]
    if large:
        print(f"  ⚠️  LARGE BLOCK PRINTS (≥$50K):")
        for t in sorted(large, key=lambda x: float(x.get("premium",0)), reverse=True)[:8]:
            size  = int(t.get("size", 0))
            price = float(t.get("price", 0))
            prem  = fmt_premium(t.get("premium", 0))
            time  = fmt_time(t.get("executed_at", ""))
            print(f"    {time} | {size:>6,} shares @ ${price:.2f} | {prem}")
    else:
        print("  No large block prints (≥$50K) in recent data.")
        for t in data[:5]:
            size  = int(t.get("size", 0))
            price = float(t.get("price", 0))
            prem  = fmt_premium(t.get("premium", 0))
            time  = fmt_time(t.get("executed_at", ""))
            print(f"    {time} | {size:>6,} shares @ ${price:.2f} | {prem}")


# ── Flow Alerts ───────────────────────────────────────────────────────────────

def flow_alerts(limit=20):
    print(f"\n🚨 UNUSUAL FLOW ALERTS — Market-Wide")
    print("=" * 60)

    data, err = get("option-trades/flow-alerts", {"limit": limit})
    if err:
        print(f"  Error: {err}")
        return

    if not data:
        print("  No alerts.")
        return

    # Group by bullish/bearish
    calls = [a for a in data if a.get("type") == "call"]
    puts  = [a for a in data if a.get("type") == "put"]

    print(f"  Calls: {len(calls)} | Puts: {len(puts)} | "
          f"Ratio: {'Bullish' if len(calls) > len(puts) else 'Bearish'}")
    print()

    print("  TOP CALL ALERTS:")
    for a in sorted(calls, key=lambda x: float(x.get("total_premium",0)), reverse=True)[:6]:
        prem   = fmt_premium(a.get("total_premium", 0))
        ticker = a.get("ticker", "?")
        strike = a.get("strike", "?")
        expiry = a.get("expiry", "?")
        vol    = int(a.get("volume", 0))
        sweep  = "🌊" if a.get("has_sweep") else ""
        floor  = "🏛️" if a.get("has_floor") else ""
        print(f"    {ticker:6} ${strike}C {expiry} | Vol:{vol:>6,} | {prem} {sweep}{floor}")

    print()
    print("  TOP PUT ALERTS:")
    for a in sorted(puts, key=lambda x: float(x.get("total_premium",0)), reverse=True)[:6]:
        prem   = fmt_premium(a.get("total_premium", 0))
        ticker = a.get("ticker", "?")
        strike = a.get("strike", "?")
        expiry = a.get("expiry", "?")
        vol    = int(a.get("volume", 0))
        sweep  = "🌊" if a.get("has_sweep") else ""
        floor  = "🏛️" if a.get("has_floor") else ""
        print(f"    {ticker:6} ${strike}P {expiry} | Vol:{vol:>6,} | {prem} {sweep}{floor}")


# ── Congressional Trades ──────────────────────────────────────────────────────

def congressional_trades(limit=15):
    print(f"\n🏛️  CONGRESSIONAL TRADES")
    print("=" * 60)

    data, err = get("congress/recent-trades", {"limit": limit})
    if err:
        print(f"  Error: {err}")
        return

    if not data:
        print("  No recent trades.")
        return

    buys  = [t for t in data if "buy" in t.get("txn_type","").lower() or "purchase" in t.get("txn_type","").lower()]
    sells = [t for t in data if "sell" in t.get("txn_type","").lower()]

    print(f"  Recent: {len(data)} trades | Buys: {len(buys)} | Sells: {len(sells)}")
    print()

    print("  BUYS:")
    for t in buys[:6]:
        name   = t.get("name", "?")
        ticker = t.get("ticker", "?")
        amt    = t.get("amounts", "?")
        date   = t.get("transaction_date", "?")
        print(f"    {date} | {name:25} | {ticker:6} | {amt}")

    print()
    print("  SELLS:")
    for t in sells[:6]:
        name   = t.get("name", "?")
        ticker = t.get("ticker", "?")
        amt    = t.get("amounts", "?")
        date   = t.get("transaction_date", "?")
        print(f"    {date} | {name:25} | {ticker:6} | {amt}")


# ── Full TSLA Report ──────────────────────────────────────────────────────────

def tsla_report():
    """Focused TSLA smart money report."""
    print("\n" + "="*60)
    print("🦀 BIGCLAW SMART MONEY REPORT — TSLA")
    print(f"   {datetime.now().strftime('%Y-%m-%d %H:%M:%S CT')}")
    print("="*60)
    options_flow("TSLA")
    dark_pool("TSLA")
    print()
    print("="*60)
    print("💡 KEY SIGNALS TO WATCH:")
    print("  • Large put sweeps on TSLA = institutional hedging / bearish bets")
    print("  • Large call sweeps = institutional bullish positioning")
    print("  • Dark pool prints ≥$500K = smart money accumulation/distribution")
    print("  • C/P ratio >1.5x = bullish sentiment | <0.67x = bearish")
    print("="*60)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not TOKEN:
        print("❌ UNUSUAL_WHALES_TOKEN not set. Run: source ~/.env_secrets")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Unusual Whales — BigClaw Integration")
    parser.add_argument("--ticker",     default="TSLA",  help="Ticker for options/dark pool")
    parser.add_argument("--flow",       action="store_true", help="Options flow for ticker")
    parser.add_argument("--dark-pool",  action="store_true", help="Dark pool for ticker")
    parser.add_argument("--flow-alerts",action="store_true", help="Market-wide flow alerts")
    parser.add_argument("--congress",   action="store_true", help="Congressional trades")
    parser.add_argument("--all",        action="store_true", help="Full report")
    args = parser.parse_args()

    any_flag = args.flow or args.dark_pool or args.flow_alerts or args.congress or args.all

    if args.all or not any_flag:
        # Default: TSLA smart money report
        tsla_report()
        return

    if args.flow:
        options_flow(args.ticker.upper())

    if args.dark_pool:
        dark_pool(args.ticker.upper())

    if args.flow_alerts:
        flow_alerts()

    if args.congress:
        congressional_trades()


if __name__ == "__main__":
    main()
