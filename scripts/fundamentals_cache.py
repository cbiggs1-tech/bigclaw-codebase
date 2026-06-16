#!/usr/bin/env python3
"""Daily-cached yfinance .info to stop Yahoo 429 rate-limiting.

The rule-based scorer/screener/gates fetch yf.Ticker(ticker).info per candidate
every run -- 100+ per-ticker scrapes that Yahoo now throttles (101 errors on
2026-06-16). But .info is fundamentals (PE, margins, ROE, analyst target,
sector) that change daily at most. So cache it.

get_info(ticker):
  - returns the cached dict if younger than MAX_AGE (default ~20h)
  - otherwise refreshes from yfinance with exponential backoff + jitter
  - if the refresh fails (e.g. 429), SERVES THE STALE CACHE (yesterday's
    fundamentals beat nothing) -- this is what makes the scorer robust to
    throttling.

Cache lives in data/fundamentals_cache.db (separate from the trading DB).
"""
import json
import os
import random
import sqlite3
import sys
import time
from pathlib import Path

CACHE_DB = Path.home() / "bigclaw-ai" / "data" / "fundamentals_cache.db"
MAX_AGE_SECONDS = 20 * 3600  # refresh at most ~once/day; next morning run repopulates


def _conn():
    CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(CACHE_DB, timeout=30)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    c.execute(
        "CREATE TABLE IF NOT EXISTS fundamentals "
        "(ticker TEXT PRIMARY KEY, info_json TEXT, fetched_at REAL)"
    )
    return c


def _read(ticker):
    try:
        c = _conn()
        row = c.execute(
            "SELECT info_json, fetched_at FROM fundamentals WHERE ticker=?", (ticker,)
        ).fetchone()
        c.close()
        if row:
            return json.loads(row[0]), row[1]
    except Exception:
        pass
    return None, 0.0


def _write(ticker, info):
    try:
        c = _conn()
        c.execute(
            "INSERT OR REPLACE INTO fundamentals (ticker, info_json, fetched_at) "
            "VALUES (?,?,?)",
            (ticker, json.dumps(info), time.time()),
        )
        c.commit()
        c.close()
    except Exception:
        pass


def _fetch(ticker):
    """Fetch .info from yfinance with exponential backoff + jitter. Raises on
    final failure so the caller can fall back to stale cache."""
    import yfinance as yf

    last = None
    for i in range(3):
        try:
            info = yf.Ticker(ticker).info
            if info and len(info) > 3:
                return info
            last = ValueError("empty .info")
        except Exception as e:
            last = e
        time.sleep((2 ** i) + random.uniform(0, 1.0))  # ~1-2, 2-3, 4-5s
    raise last if last else RuntimeError("fetch failed")


def get_info(ticker, max_age_seconds=MAX_AGE_SECONDS, force=False):
    """Cached yfinance .info. Fresh -> cache; stale/missing -> refresh; refresh
    failure -> serve stale cache (or {} if none). Never raises."""
    if not ticker:
        return {}
    ticker = ticker.upper()
    cached, fetched_at = _read(ticker)
    if cached is not None and not force and (time.time() - fetched_at) < max_age_seconds:
        return cached
    try:
        info = _fetch(ticker)
        _write(ticker, info)
        return info
    except Exception:
        return cached if cached is not None else {}


def warm(tickers, spacing=2.0):
    """Pre-fetch a list of tickers, spaced out, skipping ones already fresh.
    For an early-morning cron so the rule-based run hits an all-warm cache."""
    n = 0
    for t in tickers:
        if not t:
            continue
        t = t.upper()
        cached, fetched_at = _read(t)
        if cached is not None and (time.time() - fetched_at) < MAX_AGE_SECONDS:
            continue
        try:
            _write(t, _fetch(t))
            n += 1
        except Exception:
            pass
        time.sleep(spacing)
    return n


def _universe():
    """Holdings (all portfolios) + the shared candidate universe, for warming."""
    tickers = set()
    try:
        db = Path.home() / "bigclaw-ai" / "src" / "portfolios.db"
        c = sqlite3.connect(db, timeout=30)
        for (t,) in c.execute("SELECT DISTINCT ticker FROM holdings WHERE shares>0"):
            if t:
                tickers.add(t.upper())
        c.close()
    except Exception:
        pass
    for fn in ("portfolio_universes.json", "data/portfolio_universes.json"):
        p = Path.home() / "bigclaw-ai" / fn
        try:
            if p.exists():
                d = json.loads(p.read_text())
                def _walk(o):
                    if isinstance(o, str):
                        tickers.add(o.upper())
                    elif isinstance(o, list):
                        for x in o:
                            _walk(x)
                    elif isinstance(o, dict):
                        for x in o.values():
                            _walk(x)
                _walk(d)
        except Exception:
            pass
    return sorted(tickers)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "warm":
        u = _universe()
        print(f"Warming {len(u)} tickers...")
        got = warm(u)
        print(f"Refreshed {got} (rest already fresh or failed).")
    else:
        # quick self-test
        for t in ("AAPL", "NVDA", "XLK"):
            info = get_info(t)
            print(t, "sector:", info.get("sector"), "fwdPE:", info.get("forwardPE"),
                  "target:", info.get("targetMeanPrice"), "(fields:", len(info), ")")
