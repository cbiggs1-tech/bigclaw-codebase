#!/usr/bin/env python3
"""Fetch key macro/commodity prices for morning briefing.

Outputs real prices to stdout so the LLM doesn't have to guess.
"""

import yfinance as yf
from bigclaw_logging import get_logger
from bigclaw_retry import retry

log = get_logger("macro_prices")

TICKERS = {
    'CL=F': 'WTI Crude Oil',
    'GC=F': 'Gold',
    'SI=F': 'Silver',
    '^TNX': '10-Year Treasury Yield',
    '^TYX': '30-Year Treasury Yield',
    '^VIX': 'VIX (volatility / fear gauge)',
    'HYG': 'High-Yield Credit ETF (HYG)',
    'LQD': 'Investment-Grade Credit ETF (LQD)',
    'DX-Y.NYB': 'US Dollar Index',
    'BTC-USD': 'Bitcoin',
    'ETH-USD': 'Ethereum',
}

def main():
    tickers = list(TICKERS.keys())
    try:
        data = retry(
            lambda: yf.download(tickers, period="2d", progress=False, threads=True),
            attempts=2, delay=5, label="yfinance macro download"
        )
    except Exception as e:
        log.error(f"Batch fetch failed after retries: {e}")
        print(f"Batch fetch failed: {e}")
        return

    if 'Close' not in data.columns:
        log.error("No data returned from yfinance")
        print("No data returned")
        return

    close = data['Close']
    if len(close) < 1:
        log.error("No rows returned from yfinance")
        print("No rows returned")
        return

    fetched = 0
    print("=== MACRO PRICES (real-time via yfinance) ===")
    for sym, name in TICKERS.items():
        try:
            current = float(close[sym].iloc[-1])
            fetched += 1
            if len(close) >= 2:
                prev = float(close[sym].iloc[-2])
                chg = ((current - prev) / prev) * 100 if prev > 0 else 0
                print(f"{name}: ${current:,.2f} ({chg:+.1f}%)")
            else:
                print(f"{name}: ${current:,.2f}")
        except Exception as e:
            log.warning(f"Failed to get {name} ({sym}): {e}")
    print("=== END MACRO PRICES ===")
    log.info(f"Fetched {fetched}/{len(TICKERS)} macro prices")


if __name__ == '__main__':
    main()
