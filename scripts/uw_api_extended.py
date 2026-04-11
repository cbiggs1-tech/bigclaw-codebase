#!/usr/bin/env python3
"""
Unusual Whales Extended API — New IPS-era endpoints.

This module adds flow alerts, market tide, GEX, congress trades,
insider transactions, net premium ticks, and options screener
to BigClaw's options intelligence.

Imported by options_intelligence.py — does not replace it.
"""

import time
import requests

# Uses the same BASE and HEADERS from the importing module
BASE = "https://api.unusualwhales.com/api"
HEADERS = {}  # Set by init()


def init(token):
    """Initialize with API token."""
    global HEADERS
    HEADERS = {
        "Authorization": f"Bearer {token}",
        "UW-CLIENT-API-ID": "100001",
    }


def _get(path, params=None, retries=2):
    """GET from UW API with retry."""
    for attempt in range(retries + 1):
        try:
            r = requests.get(
                f"{BASE}/{path}", headers=HEADERS,
                params=params, timeout=15
            )
            if r.status_code == 200:
                data = r.json()
                if "error" in data:
                    return None
                return data.get("data", data)
            if r.status_code == 429:
                wait = 3 * (attempt + 1)
                time.sleep(wait)
                continue
            return None
        except Exception:
            if attempt < retries:
                time.sleep(2)
            else:
                return None
    return None


def collect_flow_alerts(tickers, min_premium=50000, limit=20):
    """Get unusual options flow alerts for portfolio tickers."""
    results = {}
    for ticker in tickers:
        data = _get("option-trades/flow-alerts", params={
            "ticker_symbol": ticker,
            "min_premium": min_premium,
            "size_greater_oi": True,
            "limit": limit,
            "is_otm": True,
        })
        if data:
            alerts = []
            for d in data[:10]:
                alerts.append({
                    "ticker": d.get("ticker_symbol", ticker),
                    "type": d.get("type", "?"),
                    "premium": d.get("total_premium", 0),
                    "size": d.get("total_size", 0),
                    "strike": d.get("strike_price", 0),
                    "expiry": d.get("expiry", ""),
                    "sentiment": d.get("sentiment", ""),
                    "executed_at": d.get("executed_at", ""),
                })
            if alerts:
                results[ticker] = alerts
        time.sleep(0.3)
    return results


def collect_market_tide():
    """Get market-wide sentiment (Market Tide)."""
    data = _get("market/market-tide", params={"interval_5m": False})
    if not data:
        return {}
    entries = data if isinstance(data, list) else [data]
    latest = entries[-1] if entries else {}
    return {
        "timestamp": latest.get("timestamp", ""),
        "net_call_premium": latest.get("net_call_premium", 0),
        "net_put_premium": latest.get("net_put_premium", 0),
        "call_volume": latest.get("call_volume", 0),
        "put_volume": latest.get("put_volume", 0),
        "entries": entries[-12:],
    }


def collect_gex_by_strike(tickers, max_tickers=10):
    """Get gamma exposure by strike for key tickers."""
    results = {}
    for ticker in tickers[:max_tickers]:
        data = _get(f"stock/{ticker}/spot-exposures/strike")
        if data:
            strikes = []
            for d in data[:20]:
                strikes.append({
                    "strike": d.get("strike", 0),
                    "call_gamma": d.get("call_gamma_oi", 0),
                    "put_gamma": d.get("put_gamma_oi", 0),
                    "net_gamma": float(d.get("call_gamma_oi", 0) or 0) + float(d.get("put_gamma_oi", 0) or 0),
                })
            if strikes:
                results[ticker] = strikes
        time.sleep(0.3)
    return results


def collect_congress_trades():
    """Get recent politician/congress trades."""
    data = _get("congress/recent-trades")
    if not data:
        return []
    trades = []
    for d in data[:20]:
        trades.append({
            "politician": d.get("politician", ""),
            "ticker": d.get("ticker", ""),
            "transaction_type": d.get("transaction_type", ""),
            "amount": d.get("amount", ""),
            "transaction_date": d.get("transaction_date", ""),
            "party": d.get("party", ""),
        })
    return trades


def collect_insider_trades(tickers):
    """Get insider transactions from UW API."""
    data = _get("insider/transactions")
    if not data:
        return []
    ticker_set = set(tickers)
    trades = []
    for d in data[:50]:
        t = d.get("ticker", "")
        trades.append({
            "ticker": t,
            "insider": d.get("insider_name", ""),
            "title": d.get("insider_title", ""),
            "transaction_type": d.get("transaction_type", ""),
            "shares": d.get("shares", 0),
            "price": d.get("price", 0),
            "value": d.get("value", 0),
            "date": d.get("transaction_date", ""),
            "is_portfolio": t in ticker_set,
        })
    return trades


def collect_net_premium_ticks(tickers, max_tickers=15):
    """Get net premium flow direction per ticker."""
    results = {}
    for ticker in tickers[:max_tickers]:
        data = _get(f"stock/{ticker}/net-prem-ticks")
        if data:
            entries = data if isinstance(data, list) else [data]
            if entries:
                latest = entries[-1]
                results[ticker] = {
                    "net_premium": latest.get("net_premium", 0),
                    "call_premium": latest.get("call_premium", 0),
                    "put_premium": latest.get("put_premium", 0),
                    "timestamp": latest.get("timestamp", ""),
                }
        time.sleep(0.3)
    return results


def collect_options_screener(limit=25):
    """Get hottest option chains market-wide."""
    data = _get("screener/option-contracts", params={
        "limit": limit,
        "min_premium": 250000,
        "is_otm": True,
        "issue_types[]": "Common Stock",
        "min_volume": 500,
        "vol_greater_oi": True,
    })
    if not data:
        return []
    results = []
    for d in data[:limit]:
        results.append({
            "ticker": d.get("ticker_symbol", ""),
            "option_symbol": d.get("option_symbol", ""),
            "type": d.get("type", ""),
            "strike": d.get("strike_price", 0),
            "expiry": d.get("expiry", ""),
            "volume": d.get("volume", 0),
            "open_interest": d.get("open_interest", 0),
            "premium": d.get("ask_side_volume", 0),
            "avg_price": d.get("avg_price", 0),
        })
    return results


def collect_all(tickers):
    """Run all extended collections. Returns dict of results."""
    print("  [UW Extended] Collecting flow alerts...")
    flow_alerts = collect_flow_alerts(tickers[:20])
    print(f"    {sum(len(v) for v in flow_alerts.values())} alerts across {len(flow_alerts)} tickers")

    print("  [UW Extended] Collecting market tide...")
    market_tide = collect_market_tide()

    print("  [UW Extended] Collecting GEX by strike...")
    gex = collect_gex_by_strike(tickers[:10])
    print(f"    GEX for {len(gex)} tickers")

    print("  [UW Extended] Collecting congress trades...")
    congress = collect_congress_trades()
    print(f"    {len(congress)} congress trades")

    print("  [UW Extended] Collecting insider trades...")
    insider = collect_insider_trades(tickers)
    print(f"    {len(insider)} insider trades ({sum(1 for i in insider if i.get('is_portfolio'))} in portfolio)")

    print("  [UW Extended] Collecting net premium ticks...")
    net_premium = collect_net_premium_ticks(tickers[:15])
    print(f"    Net premium for {len(net_premium)} tickers")

    print("  [UW Extended] Collecting hottest chains...")
    hottest = collect_options_screener(limit=25)
    print(f"    {len(hottest)} hottest chains")

    return {
        "flow_alerts": flow_alerts,
        "market_tide": market_tide,
        "gex": gex,
        "congress": congress,
        "insider": insider,
        "net_premium": net_premium,
        "hottest_chains": hottest,
    }


def format_flat_sections(extended):
    """Format extended data as flat text sections for data gathers."""
    sections = []

    flow = extended.get("flow_alerts", {})
    if flow:
        sections.append("\n=== FLOW ALERTS (Whale Trades) ===")
        for ticker, alerts in flow.items():
            for a in alerts[:3]:
                prem = a.get("premium", 0)
                ptype = a.get("type", "?")
                emoji = "Bull" if ptype == "Call" else "Bear"
                sections.append(
                    f"  [{a.get('executed_at', '?')[:16]}] {emoji} {ticker} "
                    f"{ptype} ${a.get('strike', 0)} exp {a.get('expiry', '?')} | "
                    f"Premium: ${float(prem or 0):,.0f} | Size: {a.get('size', 0)}"
                )

    tide = extended.get("market_tide", {})
    if tide:
        sections.append("\n=== MARKET TIDE ===")
        nc = float(tide.get("net_call_premium", 0) or 0)
        np_ = float(tide.get("net_put_premium", 0) or 0)
        bias = "BULLISH" if nc > np_ else "BEARISH"
        sections.append(f"  Net Call: ${nc:,.0f} | Net Put: ${np_:,.0f} | Bias: {bias}")

    congress = extended.get("congress", [])
    if congress:
        sections.append("\n=== CONGRESS TRADES ===")
        for c in congress[:10]:
            sections.append(
                f"  {c.get('politician', '?')} ({c.get('party', '?')}) "
                f"{c.get('transaction_type', '?')} {c.get('ticker', '?')} | "
                f"{c.get('amount', '?')} | {c.get('transaction_date', '?')}"
            )

    insider = extended.get("insider", [])
    portfolio_insider = [i for i in insider if i.get("is_portfolio")]
    if portfolio_insider:
        sections.append("\n=== INSIDER TRADES (Portfolio Holdings) ===")
        for i in portfolio_insider[:10]:
            sections.append(
                f"  {i.get('insider', '?')} ({i.get('title', '?')}) "
                f"{i.get('transaction_type', '?')} {i.get('ticker', '?')} | "
                f"{i.get('shares', 0)} shares @ ${i.get('price', 0)} | {i.get('date', '?')}"
            )

    return "\n".join(sections) if sections else ""
