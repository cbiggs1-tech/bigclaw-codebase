#!/usr/bin/env python3
"""Verified stock quote for BigClaw. Returns all fields needed for analysis.

Usage:
    python3 stock_quote.py TSLA
    python3 stock_quote.py TSLA NVDA AAPL --json
"""

import argparse
import json
import sys
from datetime import datetime, timezone

def get_quote(ticker):
    """Pull complete verified quote from yfinance."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        fi = t.fast_info
        info = t.info or {}

        last_price = fi.get('lastPrice', None)
        prev_close = fi.get('previousClose', None)

        if last_price is None:
            return {"ticker": ticker, "error": "No price data from yfinance"}

        change_pct = ((last_price / prev_close) - 1) * 100 if prev_close else None
        change_dollar = last_price - prev_close if prev_close else None

        result = {
            "ticker": ticker,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "source": "yfinance",
            "price": round(last_price, 2),
            "previous_close": round(prev_close, 2) if prev_close else None,
            "change_pct": round(change_pct, 2) if change_pct else None,
            "change_dollar": round(change_dollar, 2) if change_dollar else None,
            "volume": fi.get('lastVolume', None),
            "avg_volume": info.get('averageVolume', None),
            "market_cap": fi.get('marketCap', None),
            "fifty_two_week_low": fi.get('yearLow', None),
            "fifty_two_week_high": fi.get('yearHigh', None),
            "trailing_pe": info.get('trailingPE', None),
            "forward_pe": info.get('forwardPE', None),
            "trailing_eps": info.get('trailingEps', None),
            "forward_eps": info.get('forwardEps', None),
            "dividend_yield": info.get('dividendYield', None),
            "beta": info.get('beta', None),
            "debt_to_equity": info.get('debtToEquity', None),
            "free_cashflow": info.get('freeCashflow', None),
            "analyst_target": info.get('targetMeanPrice', None),
        }
        return result
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


def format_quote(q):
    """Human-readable format."""
    if "error" in q:
        return f"ERROR {q['ticker']}: {q['error']}"

    lines = []
    lines.append(f"=== {q['ticker']} ({q['source']}, {q['timestamp_utc'][:19]}Z) ===")
    lines.append(f"  Price: ${q['price']}  |  Prev Close: ${q['previous_close']}")
    lines.append(f"  Change: {q['change_dollar']:+.2f} ({q['change_pct']:+.2f}%)")

    vol = q.get('volume')
    avg_vol = q.get('avg_volume')
    if vol:
        vol_str = f"{vol:,.0f}"
        if avg_vol and avg_vol > 0:
            vol_str += f" ({vol/avg_vol*100:.0f}% of avg {avg_vol:,.0f})"
        lines.append(f"  Volume: {vol_str}")

    mc = q.get('market_cap')
    if mc:
        if mc >= 1e12:
            lines.append(f"  Market Cap: ${mc/1e12:.2f}T")
        elif mc >= 1e9:
            lines.append(f"  Market Cap: ${mc/1e9:.2f}B")

    low52 = q.get('fifty_two_week_low')
    high52 = q.get('fifty_two_week_high')
    if low52 and high52:
        lines.append(f"  52W Range: ${low52:.2f} - ${high52:.2f}")

    tpe = q.get('trailing_pe')
    fpe = q.get('forward_pe')
    if tpe:
        pe_str = f"  P/E (trailing): {tpe:.1f}"
        if fpe:
            pe_str += f"  |  P/E (forward): {fpe:.1f}"
        lines.append(pe_str)

    teps = q.get('trailing_eps')
    feps = q.get('forward_eps')
    if teps:
        eps_str = f"  EPS (trailing): ${teps:.2f}"
        if feps:
            eps_str += f"  |  EPS (forward): ${feps:.2f}"
        lines.append(eps_str)

    beta = q.get('beta')
    if beta:
        lines.append(f"  Beta: {beta:.2f}")

    dte = q.get('debt_to_equity')
    if dte:
        lines.append(f"  Debt/Equity: {dte:.1f}%")

    fcf = q.get('free_cashflow')
    if fcf:
        if abs(fcf) >= 1e9:
            lines.append(f"  Free Cash Flow: ${fcf/1e9:.2f}B")
        else:
            lines.append(f"  Free Cash Flow: ${fcf/1e6:.0f}M")

    at = q.get('analyst_target')
    if at:
        lines.append(f"  Analyst Target (mean): ${at:.2f}")

    dy = q.get('dividend_yield')
    if dy:
        lines.append(f"  Dividend Yield: {dy*100:.2f}%")

    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verified stock quote")
    parser.add_argument("tickers", nargs="+", help="Ticker symbols")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    results = []
    for ticker in args.tickers:
        results.append(get_quote(ticker.upper()))

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(format_quote(r))
            print()
