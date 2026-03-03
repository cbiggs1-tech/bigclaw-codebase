#!/usr/bin/env python3
"""
BigClaw Market Monitor — Event-driven alerting system.
Checks all portfolio holdings for significant events, alerts only when something matters.
Zero AI cost when markets are quiet.
"""

import json
import os
import sys
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

import yfinance as yf
import pytz

# Paths
DB_PATH = os.path.expanduser("~/bigclaw-ai/src/portfolios.db")
STATE_PATH = os.path.expanduser("~/.openclaw/workspace/config/monitor_state.json")
ALERTS_PATH = os.path.expanduser("~/.openclaw/workspace/logs/market_alerts.json")

# Thresholds
PRICE_MOVE_HIGH = 0.03      # 3% = high severity
PRICE_MOVE_URGENT = 0.05    # 5% = urgent severity
VOLUME_SPIKE_MULT = 2.0     # 2x average volume
VIX_SPIKE_PCT = 0.15        # 15% VIX jump
PORTFOLIO_DROP_PCT = 0.02   # 2% portfolio decline
COOLDOWN_HOURS = 2          # Don't re-alert same event within 2 hours

CT = pytz.timezone("America/Chicago")
ET = pytz.timezone("US/Eastern")


def load_holdings():
    """Load all holdings grouped by portfolio from SQLite."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT p.name, h.ticker, h.shares, h.avg_cost
        FROM holdings h JOIN portfolios p ON h.portfolio_id = p.id
    """).fetchall()
    conn.close()

    holdings = {}  # ticker -> [{portfolio, shares, avg_cost}]
    for pname, ticker, shares, avg_cost in rows:
        holdings.setdefault(ticker, []).append({
            "portfolio": pname, "shares": shares, "avg_cost": avg_cost
        })
    return holdings


def load_state():
    """Load persisted state or return empty."""
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {}


def save_state(state):
    """Persist state."""
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def is_market_hours():
    """Check if US markets are currently open (loose check)."""
    now_et = datetime.now(ET)
    if now_et.weekday() >= 5:  # Weekend
        return False
    market_open = now_et.replace(hour=9, minute=25, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=5, second=0, microsecond=0)
    return market_open <= now_et <= market_close


def can_alert(state, ticker, alert_type):
    """Check cooldown — don't re-alert same ticker+type within COOLDOWN_HOURS."""
    key = f"{ticker}:{alert_type}"
    last = state.get("last_alerts", {}).get(key, 0)
    return (time.time() - last) > (COOLDOWN_HOURS * 3600)


def mark_alerted(state, ticker, alert_type):
    """Record that we alerted on this ticker+type."""
    state.setdefault("last_alerts", {})[f"{ticker}:{alert_type}"] = time.time()


def fetch_market_data(tickers):
    """Batch fetch current data for all tickers + VIX + SPY."""
    all_tickers = list(set(tickers + ["^VIX", "SPY"]))
    # Fix BRK-B for yfinance
    all_tickers = [t.replace("BRK-B", "BRK-B") for t in all_tickers]

    data = {}
    try:
        # Batch download — 1 call for current prices
        download = yf.download(all_tickers, period="1d", interval="1d", progress=False, threads=True)
        # Also need historical for SMAs and 52-week
        hist_data = {}
        tickers_obj = yf.Tickers(" ".join(all_tickers))
        for t in all_tickers:
            try:
                safe_key = t.replace("^", "")  # yf.Tickers uses cleaned keys
                ticker_obj = tickers_obj.tickers.get(safe_key) or tickers_obj.tickers.get(t)
                if ticker_obj is None:
                    continue
                hist = ticker_obj.history(period="1y")
                if hist.empty:
                    continue
                info = ticker_obj.fast_info
                current_price = hist["Close"].iloc[-1]
                prev_close = info.get("previousClose") or (hist["Close"].iloc[-2] if len(hist) > 1 else current_price)
                current_volume = hist["Volume"].iloc[-1] if "Volume" in hist else 0
                avg_volume = hist["Volume"].mean() if "Volume" in hist and len(hist) > 20 else current_volume

                sma_50 = hist["Close"].rolling(50).mean().iloc[-1] if len(hist) >= 50 else None
                sma_200 = hist["Close"].rolling(200).mean().iloc[-1] if len(hist) >= 200 else None

                high_52w = hist["Close"].max()
                low_52w = hist["Close"].min()

                data[t] = {
                    "price": float(current_price),
                    "prev_close": float(prev_close),
                    "volume": float(current_volume),
                    "avg_volume": float(avg_volume),
                    "sma_50": float(sma_50) if sma_50 is not None else None,
                    "sma_200": float(sma_200) if sma_200 is not None else None,
                    "high_52w": float(high_52w),
                    "low_52w": float(low_52w),
                }
            except Exception as e:
                print(f"  Warning: Failed to fetch {t}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"  Warning: Batch download failed: {e}", file=sys.stderr)

    return data


def check_alerts(holdings, market_data, state):
    """Run all alert checks. Returns list of alerts."""
    alerts = []
    now = datetime.now(CT)
    is_first_run = not state.get("initialized", False)

    # 1-6: Per-ticker checks
    for ticker, positions in holdings.items():
        d = market_data.get(ticker)
        if not d:
            continue

        price = d["price"]
        prev = d["prev_close"]
        if prev == 0:
            continue
        pct_change = (price - prev) / prev
        portfolio_name = positions[0]["portfolio"]  # Use first portfolio for display

        # Price moves
        if abs(pct_change) >= PRICE_MOVE_URGENT:
            if can_alert(state, ticker, "price_move_urgent"):
                direction = "up" if pct_change > 0 else "down"
                alerts.append({
                    "ticker": ticker, "type": "price_move", "severity": "urgent",
                    "message": f"{ticker} {direction} {abs(pct_change)*100:.1f}% (${prev:.2f} → ${price:.2f})",
                    "portfolio": portfolio_name
                })
                if not is_first_run:
                    mark_alerted(state, ticker, "price_move_urgent")
        elif abs(pct_change) >= PRICE_MOVE_HIGH:
            if can_alert(state, ticker, "price_move_high"):
                direction = "up" if pct_change > 0 else "down"
                alerts.append({
                    "ticker": ticker, "type": "price_move", "severity": "high",
                    "message": f"{ticker} {direction} {abs(pct_change)*100:.1f}% (${prev:.2f} → ${price:.2f})",
                    "portfolio": portfolio_name
                })
                if not is_first_run:
                    mark_alerted(state, ticker, "price_move_high")

        # SMA crossovers (compare to previous state)
        prev_state = state.get("prices", {}).get(ticker, {})
        for sma_name, sma_val in [("sma_50", d["sma_50"]), ("sma_200", d["sma_200"])]:
            if sma_val is None:
                continue
            prev_price_state = prev_state.get("price")
            if prev_price_state is not None:
                was_above = prev_price_state > sma_val
                is_above = price > sma_val
                if was_above != is_above and can_alert(state, ticker, f"{sma_name}_cross"):
                    cross_type = "above" if is_above else "below"
                    sma_label = "50-day" if "50" in sma_name else "200-day"
                    alerts.append({
                        "ticker": ticker, "type": "sma_crossover", "severity": "high",
                        "message": f"{ticker} crossed {cross_type} {sma_label} SMA (${sma_val:.2f})",
                        "portfolio": portfolio_name
                    })
                    if not is_first_run:
                        mark_alerted(state, ticker, f"{sma_name}_cross")

        # Volume spike
        if d["avg_volume"] > 0 and d["volume"] > d["avg_volume"] * VOLUME_SPIKE_MULT:
            if can_alert(state, ticker, "volume_spike"):
                mult = d["volume"] / d["avg_volume"]
                alerts.append({
                    "ticker": ticker, "type": "volume_spike", "severity": "medium",
                    "message": f"{ticker} volume {mult:.1f}x average ({d['volume']/1e6:.1f}M vs {d['avg_volume']/1e6:.1f}M avg)",
                    "portfolio": portfolio_name
                })
                if not is_first_run:
                    mark_alerted(state, ticker, "volume_spike")

        # 52-week high/low (within 1% of the extreme)
        if price >= d["high_52w"] * 0.99 and can_alert(state, ticker, "52w_high"):
            alerts.append({
                "ticker": ticker, "type": "52w_high", "severity": "high",
                "message": f"{ticker} at/near 52-week high ${price:.2f} (high: ${d['high_52w']:.2f})",
                "portfolio": portfolio_name
            })
            if not is_first_run:
                mark_alerted(state, ticker, "52w_high")
        elif price <= d["low_52w"] * 1.01 and can_alert(state, ticker, "52w_low"):
            alerts.append({
                "ticker": ticker, "type": "52w_low", "severity": "urgent",
                "message": f"{ticker} at/near 52-week low ${price:.2f} (low: ${d['low_52w']:.2f})",
                "portfolio": portfolio_name
            })
            if not is_first_run:
                mark_alerted(state, ticker, "52w_low")

    # VIX check
    vix_data = market_data.get("^VIX")
    if vix_data:
        vix_price = vix_data["price"]
        vix_prev = vix_data["prev_close"]
        if vix_prev > 0:
            vix_change = (vix_price - vix_prev) / vix_prev
            if vix_change >= VIX_SPIKE_PCT and can_alert(state, "^VIX", "vix_spike"):
                alerts.append({
                    "ticker": "VIX", "type": "vix_spike", "severity": "urgent",
                    "message": f"VIX spiked {vix_change*100:.0f}% to {vix_price:.1f}"
                })
                if not is_first_run:
                    mark_alerted(state, "^VIX", "vix_spike")

    # Portfolio-level check
    portfolio_values = {}  # portfolio -> {current, prev}
    for ticker, positions in holdings.items():
        d = market_data.get(ticker)
        if not d:
            continue
        for pos in positions:
            pname = pos["portfolio"]
            portfolio_values.setdefault(pname, {"current": 0, "prev": 0})
            portfolio_values[pname]["current"] += pos["shares"] * d["price"]
            portfolio_values[pname]["prev"] += pos["shares"] * d["prev_close"]

    for pname, vals in portfolio_values.items():
        if vals["prev"] > 0:
            pct = (vals["current"] - vals["prev"]) / vals["prev"]
            if pct <= -PORTFOLIO_DROP_PCT and can_alert(state, pname, "portfolio_drop"):
                alerts.append({
                    "ticker": pname, "type": "portfolio_drop", "severity": "high",
                    "message": f"{pname} portfolio down {abs(pct)*100:.1f}% today (${vals['prev']:,.0f} → ${vals['current']:,.0f})"
                })
                if not is_first_run:
                    mark_alerted(state, pname, "portfolio_drop")

    # On first run, suppress all alerts (just initializing)
    if is_first_run:
        return []

    return alerts


def main():
    now = datetime.now(CT)

    # Load holdings
    holdings = load_holdings()
    if not holdings:
        print("No holdings found in database.", file=sys.stderr)
        sys.exit(1)

    tickers = list(holdings.keys())
    print(f"Monitoring {len(tickers)} tickers across portfolios...", file=sys.stderr)

    # Load state
    state = load_state()

    # Fetch market data
    market_data = fetch_market_data(tickers)
    if not market_data:
        print("Failed to fetch market data.", file=sys.stderr)
        sys.exit(1)

    # Check for alerts
    alerts = check_alerts(holdings, market_data, state)

    # Build market summary
    spy = market_data.get("SPY", {})
    vix = market_data.get("^VIX", {})
    spy_change = ((spy["price"] - spy["prev_close"]) / spy["prev_close"] * 100) if spy.get("prev_close") else 0
    market_summary = {
        "spy_change": f"{spy_change:+.1f}%",
        "vix": vix.get("price", 0)
    }

    # Update state with current prices
    state["prices"] = {}
    for ticker in tickers:
        d = market_data.get(ticker)
        if d:
            state["prices"][ticker] = {
                "price": d["price"],
                "sma_50": d["sma_50"],
                "sma_200": d["sma_200"],
            }

    if not state.get("initialized"):
        state["initialized"] = True
        print(f"First run — state initialized for {len(market_data)} tickers. No alerts on first run.", file=sys.stderr)

    state["last_run"] = now.isoformat()
    save_state(state)

    # Output alerts
    if alerts:
        output = {
            "timestamp": now.strftime("%Y-%m-%dT%H:%M:%S"),
            "alerts": alerts,
            "market_summary": market_summary
        }

        # Write to log file
        os.makedirs(os.path.dirname(ALERTS_PATH), exist_ok=True)
        with open(ALERTS_PATH, "w") as f:
            json.dump(output, f, indent=2)

        # Print to stdout (for wrapper to capture)
        print(json.dumps(output, indent=2))

        print(f"\n⚠️  {len(alerts)} alert(s) triggered!", file=sys.stderr)
    else:
        print("No alerts. Markets quiet.", file=sys.stderr)


if __name__ == "__main__":
    main()
