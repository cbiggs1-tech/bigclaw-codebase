#!/usr/bin/env python3
"""
Unusual Whales API Integration — BigClaw
Tracks options flow, dark pool, GEX, market tide, insider & congressional trades.

Usage:
  python3 unusual_whales.py                    # TSLA focus (default)
  python3 unusual_whales.py --ticker NVDA      # Any ticker
  python3 unusual_whales.py --dark-pool        # Dark pool only
  python3 unusual_whales.py --congress         # Congressional trades
  python3 unusual_whales.py --flow-alerts      # Market-wide unusual flow
  python3 unusual_whales.py --gex              # Gamma exposure for ticker
  python3 unusual_whales.py --gex --ticker SPY # GEX for specific ticker
  python3 unusual_whales.py --tide             # Market tide (net premium)
  python3 unusual_whales.py --insiders         # SEC Form 4 insider trades
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

    buys  = [t for t in data if "buy" in str(t.get("txn_type","")).lower() or "purchase" in str(t.get("txn_type","")).lower()]
    sells = [t for t in data if "sell" in str(t.get("txn_type","")).lower()]

    print(f"  Recent: {len(data)} trades | Buys: {len(buys)} | Sells: {len(sells)}")
    print()

    print("  BUYS:")
    for t in buys[:6]:
        name   = str(t.get("name") or "Unknown")
        ticker = str(t.get("ticker") or "N/A")
        amt    = str(t.get("amounts") or "?")
        date   = str(t.get("transaction_date") or "?")
        print(f"    {date} | {name:25} | {ticker:6} | {amt}")

    print()
    print("  SELLS:")
    for t in sells[:6]:
        name   = str(t.get("name") or "Unknown")
        ticker = str(t.get("ticker") or "N/A")
        amt    = str(t.get("amounts") or "?")
        date   = str(t.get("transaction_date") or "?")
        print(f"    {date} | {name:25} | {ticker:6} | {amt}")

    # Summary: sector breakdown and net direction
    all_tickers = [str(t.get("ticker") or "") for t in data if t.get("ticker")]
    buy_tickers = [str(t.get("ticker") or "") for t in buys if t.get("ticker")]
    sell_tickers = [str(t.get("ticker") or "") for t in sells if t.get("ticker")]

    print()
    print("  SUMMARY:")
    ratio = len(buys) / max(len(sells), 1)
    if ratio > 1.5:
        print(f"    📈 Net BUY bias ({len(buys)}B / {len(sells)}S, ratio {ratio:.1f}x)")
    elif ratio < 0.67:
        print(f"    📉 Net SELL bias ({len(buys)}B / {len(sells)}S, ratio {ratio:.1f}x)")
    else:
        print(f"    ⚖️  Balanced ({len(buys)}B / {len(sells)}S, ratio {ratio:.1f}x)")

    # Most-traded tickers
    from collections import Counter
    ticker_counts = Counter(all_tickers)
    top = ticker_counts.most_common(5)
    if top:
        print(f"    Most active: {', '.join(f'{t}({c})' for t, c in top)}")

    # Portfolio overlap check
    portfolio_tickers = {
        "TSLA", "NVDA", "PLTR", "GE", "AVGO", "LLY", "NOC", "RTX", "CCJ",
        "GEV", "BWXT", "TLN", "DECK", "ANET", "VZ", "O", "XOM", "ED",
        "PG", "JNJ", "KO", "LMT", "KTOS", "TXT", "GD", "LHX", "MSFT",
        "AAPL", "AMZN", "GOOG", "META"
    }
    overlap_buys = [t for t in buy_tickers if t in portfolio_tickers]
    overlap_sells = [t for t in sell_tickers if t in portfolio_tickers]
    if overlap_buys or overlap_sells:
        print(f"    ⚠️  PORTFOLIO OVERLAP:")
        if overlap_buys:
            print(f"      Congress BUYING: {', '.join(set(overlap_buys))}")
        if overlap_sells:
            print(f"      Congress SELLING: {', '.join(set(overlap_sells))}")


# ── Gamma Exposure (GEX) ─────────────────────────────────────────────────────

def greek_exposure(ticker, days=5):
    print(f"\n⚡ GAMMA EXPOSURE (GEX) — {ticker}")
    print("=" * 60)

    data, err = get(f"stock/{ticker}/greek-exposure")
    if err:
        print(f"  Error: {err}")
        return

    if not data:
        print("  No GEX data available.")
        return

    # Get last N days
    recent = data[-days:] if len(data) >= days else data

    # Latest day for headline
    latest = recent[-1]
    call_gamma = float(latest.get("call_gamma", 0))
    put_gamma = float(latest.get("put_gamma", 0))
    net_gamma = call_gamma + put_gamma
    call_delta = float(latest.get("call_delta", 0))
    put_delta = float(latest.get("put_delta", 0))
    net_delta = call_delta + put_delta

    print(f"  Date: {latest.get('date', '?')}")
    print()
    print(f"  NET GAMMA: {net_gamma:>+15,.0f}")
    print(f"    Call Gamma: {call_gamma:>+15,.0f}")
    print(f"    Put Gamma:  {put_gamma:>+15,.0f}")
    print()
    print(f"  NET DELTA: {net_delta:>+15,.0f}")
    print(f"    Call Delta: {call_delta:>+15,.0f}")
    print(f"    Put Delta:  {put_delta:>+15,.0f}")

    # Interpret
    print()
    if net_gamma > 0:
        print("  📌 POSITIVE GAMMA — Dealers are long gamma.")
        print("     → Market makers hedge by selling rallies & buying dips")
        print("     → Expect MEAN REVERSION / range-bound / low volatility")
        print("     → Price likely pinned near current level")
    else:
        print("  ⚠️  NEGATIVE GAMMA — Dealers are short gamma.")
        print("     → Market makers hedge by buying rallies & selling dips")
        print("     → Expect AMPLIFIED MOVES / high volatility")
        print("     → Breakouts more likely, watch for acceleration")

    # Trend over last N days
    print()
    print(f"  {days}-DAY GEX TREND:")
    for d in recent:
        date = d.get("date", "?")
        cg = float(d.get("call_gamma", 0))
        pg = float(d.get("put_gamma", 0))
        ng = cg + pg
        bar = "+" * min(int(abs(ng) / max(abs(net_gamma), 1) * 20), 30) if ng > 0 else \
              "-" * min(int(abs(ng) / max(abs(net_gamma), 1) * 20), 30)
        print(f"    {date} | Net: {ng:>+12,.0f} | {bar}")


# ── Market Tide (Net Premium) ────────────────────────────────────────────────

def market_tide():
    print(f"\n🌊 MARKET TIDE — Net Premium Flow")
    print("=" * 60)

    data, err = get("market/market-tide")
    if err:
        print(f"  Error: {err}")
        return

    if not data:
        print("  No market tide data.")
        return

    # Latest readings
    latest = data[-1]
    net_call = float(latest.get("net_call_premium", 0))
    net_put = float(latest.get("net_put_premium", 0))
    net_vol = int(latest.get("net_volume", 0))
    net_total = net_call + net_put

    print(f"  Latest: {latest.get('timestamp', '?')}")
    print()
    print(f"  Net Call Premium: {fmt_premium(abs(net_call)):>10} {'🟢' if net_call > 0 else '🔴'}")
    print(f"  Net Put Premium:  {fmt_premium(abs(net_put)):>10} {'🟢' if net_put > 0 else '🔴'}")
    print(f"  Net Total:        {fmt_premium(abs(net_total)):>10} {'🟢 BULLISH' if net_total > 0 else '🔴 BEARISH'}")
    print(f"  Net Volume:       {net_vol:>10,}")

    # Intraday trend (last 10 ticks)
    ticks = data[-10:] if len(data) >= 10 else data
    print()
    print("  INTRADAY FLOW:")

    call_trend = []
    put_trend = []
    for t in ticks:
        ts = t.get("timestamp", "")
        try:
            time_str = datetime.fromisoformat(ts).strftime("%H:%M")
        except:
            time_str = ts[-8:-3] if len(ts) > 8 else ts

        nc = float(t.get("net_call_premium", 0))
        np_ = float(t.get("net_put_premium", 0))
        total = nc + np_
        call_trend.append(nc)
        put_trend.append(np_)

        direction = "🟢" if total > 0 else "🔴"
        print(f"    {time_str} | Calls: {fmt_premium(abs(nc)):>8} | "
              f"Puts: {fmt_premium(abs(np_)):>8} | Net: {fmt_premium(abs(total)):>8} {direction}")

    # Summary
    print()
    total_calls = sum(call_trend)
    total_puts = sum(put_trend)
    session_net = total_calls + total_puts
    if session_net > 0:
        print(f"  📈 SESSION BIAS: BULLISH — net {fmt_premium(session_net)} call premium inflow")
    else:
        print(f"  📉 SESSION BIAS: BEARISH — net {fmt_premium(abs(session_net))} put premium inflow")


# ── Insider Trades (SEC Form 4) ──────────────────────────────────────────────

def insider_trades(limit=25):
    print(f"\n📋 SEC FORM 4 — Insider Trades")
    print("=" * 60)

    data, err = get("insider/transactions")
    if err:
        print(f"  Error: {err}")
        return

    if not data:
        print("  No recent insider transactions.")
        return

    data = data[:limit]

    buys = [t for t in data if t.get("transaction_code") in ("P", "A")]  # Purchase, Award
    sells = [t for t in data if t.get("transaction_code") in ("S", "D", "F")]  # Sale, Disposition, Tax

    print(f"  Recent: {len(data)} filings | Buys: {len(buys)} | Sells: {len(sells)}")
    print()

    def fmt_insider(t):
        ticker = t.get("ticker") or "?"
        name = (t.get("owner_name") or "Unknown")[:25]
        title = (t.get("officer_title") or t.get("security_title") or "")[:20]
        amt = int(t.get("amount") or 0)
        price = t.get("price") or "?"
        date = t.get("filing_date", "?")
        shares_after = int(t.get("shares_owned_after", 0))
        is_officer = t.get("is_officer", False)
        is_director = t.get("is_director", False)
        is_10pct = t.get("is_ten_percent_owner", False)

        role = []
        if is_officer: role.append("Officer")
        if is_director: role.append("Director")
        if is_10pct: role.append("10%+ Owner")
        role_str = "/".join(role) if role else "Other"

        # Notional value
        try:
            notional = abs(amt) * float(price)
            notional_str = fmt_premium(notional)
        except:
            notional_str = "?"

        return (f"    {date} | {ticker:6} | {name:25} | {role_str:15} | "
                f"{amt:>+8,} shares @ ${price} ({notional_str}) | "
                f"Owns after: {shares_after:,}")

    print("  BUYS (insider accumulation):")
    for t in buys[:8]:
        print(fmt_insider(t))

    if not buys:
        print("    (none in recent filings)")

    print()
    print("  SELLS (insider distribution):")
    for t in sells[:8]:
        print(fmt_insider(t))

    if not sells:
        print("    (none in recent filings)")

    # Notable signals
    print()
    print("  SIGNALS:")

    # Large transactions (>$500K notional)
    large = []
    for t in data:
        try:
            notional = abs(int(t.get("amount", 0))) * float(t.get("price", 0))
            if notional >= 500_000:
                large.append((t, notional))
        except:
            pass

    if large:
        print(f"    ⚠️  {len(large)} LARGE TRANSACTIONS (≥$500K):")
        for t, notional in sorted(large, key=lambda x: -x[1])[:5]:
            code = "BUY" if t.get("transaction_code") in ("P", "A") else "SELL"
            print(f"      {t.get('ticker','?'):6} | {t.get('owner_name','?')[:25]:25} | "
                  f"{code} {fmt_premium(notional)}")

    # Officers/directors buying (strongest signal)
    officer_buys = [t for t in buys if t.get("is_officer") or t.get("is_director")]
    if officer_buys:
        tickers = list(set(t.get("ticker", "?") for t in officer_buys))
        print(f"    💡 C-Suite/Director BUYING: {', '.join(tickers)}")

    # 10b5-1 plans (pre-planned, less informative)
    planned = [t for t in data if t.get("is_10b5_1")]
    if planned:
        print(f"    ℹ️  {len(planned)} trades under 10b5-1 plans (pre-scheduled, less signal)")

    # Portfolio overlap
    portfolio_tickers = {
        "TSLA", "NVDA", "PLTR", "GE", "AVGO", "LLY", "NOC", "RTX", "CCJ",
        "GEV", "BWXT", "TLN", "DECK", "ANET", "VZ", "O", "XOM", "ED",
        "PG", "JNJ", "KO", "LMT", "KTOS", "TXT", "GD", "LHX", "MSFT",
        "AAPL", "AMZN", "GOOG", "META"
    }
    overlap = [t for t in data if t.get("ticker") in portfolio_tickers]
    if overlap:
        print(f"    ⚠️  PORTFOLIO OVERLAP:")
        for t in overlap:
            code = "BUY" if t.get("transaction_code") in ("P", "A") else "SELL"
            print(f"      {t.get('ticker','?'):6} | {t.get('owner_name','?')[:25]:25} | {code}")


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
    parser.add_argument("--ticker",     default="TSLA",  help="Ticker for options/dark pool/GEX")
    parser.add_argument("--flow",       action="store_true", help="Options flow for ticker")
    parser.add_argument("--dark-pool",  action="store_true", help="Dark pool for ticker")
    parser.add_argument("--flow-alerts",action="store_true", help="Market-wide flow alerts")
    parser.add_argument("--congress",   action="store_true", help="Congressional trades")
    parser.add_argument("--gex",        action="store_true", help="Gamma exposure for ticker")
    parser.add_argument("--tide",       action="store_true", help="Market tide (net premium flow)")
    parser.add_argument("--insiders",   action="store_true", help="SEC Form 4 insider trades")
    parser.add_argument("--all",        action="store_true", help="Full report")
    args = parser.parse_args()

    any_flag = (args.flow or args.dark_pool or args.flow_alerts or args.congress
                or args.gex or args.tide or args.insiders or args.all)

    if args.all or not any_flag:
        # Default: TSLA smart money report
        tsla_report()
        return

    if args.flow:
        options_flow(args.ticker.upper())

    if args.dark_pool:
        dark_pool(args.ticker.upper())

    if args.gex:
        greek_exposure(args.ticker.upper())

    if args.tide:
        market_tide()

    if args.insiders:
        insider_trades()

    if args.flow_alerts:
        flow_alerts()

    if args.congress:
        congressional_trades()


if __name__ == "__main__":
    main()
