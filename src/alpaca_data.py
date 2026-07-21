"""Alpaca market data integration for extended hours prices.

Provides access to pre-market and after-hours stock prices
using the Alpaca Markets API.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_alpaca_client():
    """Get Alpaca REST client if credentials are configured."""
    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")

    if not api_key or not secret_key:
        logger.debug("Alpaca credentials not configured")
        return None

    try:
        from alpaca.data import StockHistoricalDataClient
        return StockHistoricalDataClient(api_key, secret_key)
    except ImportError:
        logger.warning("alpaca-py not installed - run: pip install alpaca-py")
        return None
    except Exception as e:
        logger.error(f"Failed to create Alpaca client: {e}")
        return None


def get_extended_hours_prices(tickers: list[str]) -> dict[str, dict]:
    """Get current prices including pre/post market data.

    Args:
        tickers: List of stock symbols

    Returns:
        Dict of ticker -> {price, pre_market, post_market, is_extended}
    """
    # BRK-B is not supported by Alpaca — fetch via yfinance and exclude from Alpaca request
    YFINANCE_ONLY = {"BRK-B", "BRK/B", "AKO-B", "AKO/B"}  # foreign/class-B ADRs Alpaca rejects
    yf_tickers = [t for t in tickers if t in YFINANCE_ONLY]
    alpaca_tickers = [t for t in tickers if t not in YFINANCE_ONLY]

    prices = {}

    # Fetch yfinance-only tickers first
    if yf_tickers:
        try:
            import yfinance as yf
            for t in yf_tickers:
                yf_symbol = "BRK-B" if t in ("BRK-B", "BRK/B") else t
                stock = yf.Ticker(yf_symbol)
                info = stock.fast_info
                price = getattr(info, "last_price", None) or getattr(info, "regularMarketPrice", None)
                if price:
                    prices[t] = {"price": float(price), "is_extended": False}
        except Exception as e:
            logger.error(f"yfinance fallback error for {yf_tickers}: {e}")

    if not alpaca_tickers:
        return prices

    client = get_alpaca_client()
    if not client:
        return prices

    tickers = alpaca_tickers  # only pass supported tickers to Alpaca

    try:
        from alpaca.data.requests import StockLatestQuoteRequest, StockLatestTradeRequest

        # Get latest quotes
        request = StockLatestQuoteRequest(symbol_or_symbols=tickers)
        quotes = client.get_stock_latest_quote(request)

        for ticker in tickers:
            if ticker in quotes:
                quote = quotes[ticker]
                prices[ticker] = {
                    'bid': float(quote.bid_price) if quote.bid_price else None,
                    'ask': float(quote.ask_price) if quote.ask_price else None,
                    'price': float(quote.ask_price) if quote.ask_price else None,
                    'timestamp': quote.timestamp.isoformat() if quote.timestamp else None,
                }

        # Get latest trades for more accurate prices
        trade_request = StockLatestTradeRequest(symbol_or_symbols=tickers)
        trades = client.get_stock_latest_trade(trade_request)

        for ticker in tickers:
            if ticker in trades:
                trade = trades[ticker]
                if ticker not in prices:
                    prices[ticker] = {}
                prices[ticker]['price'] = float(trade.price)
                prices[ticker]['timestamp'] = trade.timestamp.isoformat() if trade.timestamp else None

                # Check if this is extended hours
                if trade.timestamp:
                    hour = trade.timestamp.hour
                    # Pre-market: 4am-9:30am ET, Post-market: 4pm-8pm ET
                    is_extended = hour < 9 or (hour == 9 and trade.timestamp.minute < 30) or hour >= 16
                    prices[ticker]['is_extended'] = is_extended

    except Exception as e:
        logger.error(f"Error fetching Alpaca prices: {e}")

    return prices


def get_market_status() -> dict:
    """Check if market is open and get session info."""
    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")

    if not api_key or not secret_key:
        return {'is_open': False, 'session': 'unknown'}

    try:
        from alpaca.trading.client import TradingClient
        client = TradingClient(api_key, secret_key, paper=True)
        clock = client.get_clock()

        return {
            'is_open': clock.is_open,
            'next_open': clock.next_open.isoformat() if clock.next_open else None,
            'next_close': clock.next_close.isoformat() if clock.next_close else None,
            'session': 'regular' if clock.is_open else 'closed'
        }
    except Exception as e:
        logger.error(f"Error getting market status: {e}")
        return {'is_open': False, 'session': 'unknown'}


def get_best_price(ticker: str) -> Optional[float]:
    """Get the best available price for a ticker.

    Uses Alpaca for extended hours, falls back to yfinance.
    """
    # Try Alpaca first for extended hours
    alpaca_prices = get_extended_hours_prices([ticker])
    if ticker in alpaca_prices and alpaca_prices[ticker].get('price'):
        return alpaca_prices[ticker]['price']

    # Fall back to yfinance
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)
        info = stock.info
        return info.get('regularMarketPrice') or info.get('currentPrice')
    except:
        return None


if __name__ == "__main__":
    # Test the module
    import sys
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(level=logging.INFO)

    test_tickers = ["AAPL", "NVDA", "TSLA"]

    print("Testing Alpaca data...")
    print(f"Market status: {get_market_status()}")

    prices = get_extended_hours_prices(test_tickers)
    for ticker, data in prices.items():
        print(f"{ticker}: ${data.get('price', 'N/A'):.2f} (extended: {data.get('is_extended', 'N/A')})")


def get_daily_bars(tickers, start, end):
    """Daily adjusted OHLCV bars via Alpaca, shaped like yfinance's
    ``yf.download(...)`` output: a DataFrame with MultiIndex columns
    ``(Field, Ticker)`` where Field is one of Open/High/Low/Close/Volume, indexed
    by a tz-naive normalized DatetimeIndex. ``df["Close"][ticker]`` and
    ``df["Volume"][ticker]`` both work, matching what the decision engine expects.

    Alpaca is the primary source (no scraping rate-limit). Any symbols Alpaca
    cannot serve fall back to yfinance so the returned frame is complete. Returns
    None only if NO data could be obtained from either source.
    """
    import pandas as pd
    syms = sorted({t for t in (tickers or []) if t})
    if not syms:
        return None

    # yfinance uses 'BRK-B'; Alpaca uses 'BRK.B'.
    def _to_alp(s):   return s.replace("-", ".")
    def _from_alp(s): return s.replace(".", "-")

    alpaca_frame, got = None, set()
    client = get_alpaca_client()
    if client is not None:
        try:
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame
            from alpaca.data.enums import Adjustment, DataFeed
            alp_syms = [_to_alp(s) for s in syms]
            frames, BATCH = [], 200
            for i in range(0, len(alp_syms), BATCH):
                chunk = alp_syms[i:i + BATCH]
                try:
                    req = StockBarsRequest(symbol_or_symbols=chunk, timeframe=TimeFrame.Day,
                                           start=start, end=end, adjustment=Adjustment.ALL,
                                           feed=DataFeed.IEX)
                    bdf = client.get_stock_bars(req).df
                    if bdf is not None and not bdf.empty:
                        frames.append(bdf)
                except Exception as e:
                    logger.warning(f"Alpaca bars batch {i // BATCH} failed: {e}")
            if frames:
                full = pd.concat(frames)
                fields = {"Open": "open", "High": "high", "Low": "low",
                          "Close": "close", "Volume": "volume"}
                cols = {}
                for yf_field, alp_col in fields.items():
                    if alp_col not in full.columns:
                        continue
                    piv = full[alp_col].unstack(level=0)  # index=timestamp, cols=alpaca symbol
                    piv.columns = [_from_alp(c) for c in piv.columns]
                    cols[yf_field] = piv
                if cols:
                    alpaca_frame = pd.concat(cols, axis=1)  # MultiIndex (Field, Ticker)
                    got = set(alpaca_frame["Close"].columns) if "Close" in cols else set()
        except Exception as e:
            logger.warning(f"Alpaca get_daily_bars failed, using yfinance: {e}")

    # yfinance fallback for any symbols Alpaca did not return
    yf_frame, missing = None, [s for s in syms if s not in got]
    if missing:
        try:
            import yfinance as yf
            logger.info(f"get_daily_bars: yfinance fallback for {len(missing)} ticker(s): {missing[:8]}")
            raw = yf.download(missing, start=start, end=end, progress=False, auto_adjust=True)
            if raw is not None and not raw.empty:
                if isinstance(raw.columns, pd.MultiIndex):
                    yf_frame = raw
                else:  # single ticker -> build (Field, Ticker)
                    keep = [f for f in ("Open", "High", "Low", "Close", "Volume") if f in raw.columns]
                    yf_frame = pd.concat({f: raw[[f]].rename(columns={f: missing[0]}) for f in keep}, axis=1)
        except Exception as e:
            logger.warning(f"get_daily_bars yfinance fallback failed: {e}")

    parts = [f for f in (alpaca_frame, yf_frame) if f is not None]
    if not parts:
        return None

    # Normalize EACH frame's index to tz-naive normalized dates BEFORE concat. Alpaca
    # bars come back tz-AWARE (UTC); the yfinance fallback is tz-NAIVE. Concatenating the
    # two along axis=1 makes pandas compare tz-aware vs tz-naive timestamps while aligning
    # the row index, raising "Cannot compare tz-naive and tz-aware timestamps". This only
    # surfaces when BOTH sources contribute (some tickers fell to the yfinance fallback) —
    # which is why it began failing once the candidate universe grew. Apply the SAME
    # tz_convert(None).normalize() the code already trusted, but per-part, before the merge.
    def _naive_daily_index(df):
        try:
            idx = pd.to_datetime(df.index)
            if getattr(idx, "tz", None) is not None:
                idx = idx.tz_convert(None)
            df = df.copy()
            df.index = idx.normalize()
        except Exception:
            pass
        return df
    parts = [_naive_daily_index(p) for p in parts]

    try:
        prices = pd.concat(parts, axis=1) if len(parts) > 1 else parts[0]
    except Exception as e:
        # Never let a price-frame merge crash the whole decision engine. Degrade to the
        # single largest source so fetch_market_data can still proceed (and if that leaves
        # it empty, returning None triggers its own yfinance bulk-download fallback).
        logger.warning(f"get_daily_bars concat failed ({e}); using the largest single source")
        parts.sort(key=lambda p: getattr(p, "shape", (0, 0))[1], reverse=True)
        prices = parts[0] if parts else None
        if prices is None:
            return None

    # Defensive final pass: the parts are already tz-naive normalized, but re-apply in case
    # a single-part path slipped through, then sort chronologically.
    try:
        idx = pd.to_datetime(prices.index)
        if getattr(idx, "tz", None) is not None:
            idx = idx.tz_convert(None)
        prices.index = idx.normalize()
    except Exception:
        pass
    return prices.sort_index()
