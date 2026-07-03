#!/usr/bin/env python3
"""Pre-market data-stream pre-flight — runs before each trading day.

Verifies the data streams trading depends on (Alpaca trading API, Alpaca market data,
Alpaca news, yfinance) and posts a GREEN / CAUTION / RED light to Slack, so a dead feed
is caught at the door instead of after a cycle already reasoned on a blank snapshot
(July 3 2026: yfinance returned all-NaN and both LLM portfolios ran blind). Also writes
data/data_preflight_status.json for other scripts to gate on.
"""
import os
import sys
import json
import datetime
from pathlib import Path

CHANNEL = "D0ADHLUJ400"
STATUS_FILE = Path.home() / "bigclaw-ai" / "data" / "data_preflight_status.json"
HOME = Path.home() / "bigclaw-ai"


def check_alpaca_trading():
    try:
        sys.path.insert(0, str(HOME / "scripts"))
        from autonomous_trader import get_trading_client
        c = get_trading_client()
        acct = c.get_account()
        clock = c.get_clock()
        nxt = clock.next_open.strftime("%m-%d %H:%MZ") if clock.next_open else "?"
        return "UP", f"equity ${float(acct.equity):,.0f}, mkt {'OPEN' if clock.is_open else 'closed'}, next open {nxt}"
    except Exception as e:
        return "DOWN", f"{type(e).__name__}: {str(e)[:90]}"


def check_alpaca_data():
    try:
        sys.path.insert(0, str(HOME / "src"))
        from alpaca_data import get_daily_bars
        end = datetime.date.today()
        start = end - datetime.timedelta(days=15)
        df = get_daily_bars(["SPY", "XLK"], start, end)
        close = df["Close"] if df is not None else None
        if close is None or "SPY" not in close.columns:
            return "DOWN", "no SPY frame from Alpaca"
        s = close["SPY"].dropna()
        if len(s) == 0:
            return "DOWN", "SPY all-NaN"
        return "UP", f"SPY ${float(s.iloc[-1]):.2f} ({len(s)}d)"
    except Exception as e:
        return "DOWN", f"{type(e).__name__}: {str(e)[:90]}"


def check_alpaca_news():
    try:
        from alpaca.data.historical.news import NewsClient
        from alpaca.data.requests import NewsRequest
        c = NewsClient(api_key=os.environ["ALPACA_API_KEY"], secret_key=os.environ["ALPACA_SECRET_KEY"])
        end = datetime.datetime.now(datetime.timezone.utc)
        start = end - datetime.timedelta(hours=24)
        res = c.get_news(NewsRequest(symbols="SPY", start=start, end=end, limit=10))
        n = len(res.data.get("news", []))
        return ("UP" if n > 0 else "DEGRADED"), f"{n} SPY items/24h"
    except Exception as e:
        return "DOWN", f"{type(e).__name__}: {str(e)[:90]}"


def check_yfinance():
    # Mirror the LLM portfolios' ACTUAL usage: a BULK multi-symbol 1y download, which is
    # what throttles/NaNs. A single-symbol fetch can pass while the bulk call fails (the
    # July 3 failure mode), so a single-symbol check would give a false green.
    try:
        import warnings
        warnings.filterwarnings("ignore")
        import yfinance as yf
        syms = ["SPY", "XLK", "XLF", "XLV", "XLE", "SH", "PSQ", "IWM", "GLD", "TLT", "MTUM", "XLU"]
        hist = yf.download(syms, period="1y", progress=False, threads=True)["Close"]
        good = [t for t in syms if t in getattr(hist, "columns", []) and hist[t].notna().any()]
        bad = [t for t in syms if t not in good]
        if not good:
            return "DOWN", f"bulk download all-NaN (0/{len(syms)}) — LLM snapshot would be BLANK"
        if len(bad) > len(syms) // 4:
            return "DEGRADED", f"bulk partial: {len(good)}/{len(syms)} ok, missing {bad}"
        return "UP", f"bulk {len(good)}/{len(syms)} ok (SPY ${float(hist['SPY'].dropna().iloc[-1]):.2f})"
    except Exception as e:
        return "DOWN", f"{type(e).__name__}: {str(e)[:90]}"


def main():
    # (name, (status, detail), criticality)
    results = [
        ("Alpaca trading", check_alpaca_trading(), "CRITICAL"),
        ("Alpaca market data", check_alpaca_data(), "CRITICAL"),
        ("Alpaca news", check_alpaca_news(), "DEGRADED"),
        ("yfinance", check_yfinance(), "IMPORTANT"),  # ETFs come from Alpaca; yfinance = ^VIX/^TNX regime read + current LLM snapshot
    ]
    critical_down = [n for n, (st, _), crit in results if crit == "CRITICAL" and st == "DOWN"]
    yf_down = any(n == "yfinance" and st == "DOWN" for n, (st, _), _ in results)

    if critical_down:
        light, verdict = ":red_circle:", f"RED — Alpaca is down ({', '.join(critical_down)}). Automated trading is NOT trustworthy today; check before the 10:00 run."
    elif yf_down:
        light, verdict = ":large_yellow_circle:", ("CAUTION — yfinance is down. ETF/sector/inverse data is fine via Alpaca, but the "
                                                   "^VIX/^TNX regime read is degraded, and the LLM-portfolio snapshot runs blank until the "
                                                   "Alpaca-fallback ships. Trader (rule-based, Alpaca-priced) is unaffected.")
    else:
        light, verdict = ":large_green_circle:", "GREEN — all data streams healthy."

    icon = {"UP": ":white_check_mark:", "DEGRADED": ":large_yellow_circle:", "DOWN": ":x:"}
    today = datetime.datetime.now(datetime.timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    lines = [f"{light} *BigClaw Data Pre-Flight — {today}*", verdict, ""]
    for name, (st, detail), crit in results:
        lines.append(f"  {icon.get(st, ':grey_question:')} *{name}*: {detail}")

    # persist status
    try:
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATUS_FILE.write_text(json.dumps({
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "verdict": ("RED" if critical_down else "CAUTION" if yf_down else "GREEN"),
            "streams": {n: {"status": st, "detail": d, "criticality": c} for n, (st, d), c in results},
        }, indent=2))
    except Exception:
        pass

    msg = "\n".join(lines)
    print(msg)
    try:
        from slack_sdk import WebClient
        WebClient(token=os.environ["SLACK_BOT_TOKEN"]).chat_postMessage(channel=CHANNEL, text=msg)
    except Exception as e:
        print(f"Slack post failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
