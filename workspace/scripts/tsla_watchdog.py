#!/usr/bin/env python3
"""
TSLA Smart Money Watchdog — BigClaw
Polls Unusual Whales every 15 minutes during market hours.
Sends Slack alerts on significant signals.

Run via cron: every 15 min, 9:30 AM - 4:00 PM ET, Mon-Fri
Cron: */15 9-15 * * 1-5 (ET) — use OpenClaw cron scheduler
"""

import os
import sys
import json
import requests
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TOKEN   = os.environ.get("UNUSUAL_WHALES_TOKEN", "")
BASE    = "https://api.unusualwhales.com/api"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

# Slack channel
SLACK_CHANNEL   = "D0ADHLUJ400"
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")

# State file to avoid repeat alerts
STATE_FILE = Path.home() / ".openclaw/workspace/memory/tsla_watchdog_state.json"

# Thresholds
DARK_POOL_ALERT_THRESHOLD = 1_000_000   # $1M+ single dark pool print
PUT_SWEEP_ALERT_THRESHOLD = 2_000_000   # $2M+ put sweep (bearish signal)
CALL_SWEEP_ALERT_THRESHOLD = 2_000_000  # $2M+ call sweep (bullish signal)
CP_RATIO_BEARISH = 0.5                  # C/P ratio below this = strong bearish signal
CP_RATIO_BULLISH = 2.5                  # C/P ratio above this = strong bullish signal

ET = ZoneInfo("America/New_York")


def is_market_hours():
    now = datetime.now(ET)
    if now.weekday() >= 5:  # weekend
        return False
    market_open  = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now <= market_close


def get(path, params=None):
    try:
        r = requests.get(f"{BASE}/{path}", headers=HEADERS, params=params, timeout=15)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"
        data = r.json()
        if "error" in data:
            return None, data["error"]
        return data.get("data", data), None
    except Exception as e:
        return None, str(e)


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except:
            pass
    return {"alerts_sent": [], "last_cp_ratio": None, "last_run": None}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def alert_key(kind, detail):
    """Deduplicate alerts within a 2-hour window."""
    now = datetime.now(ET)
    window = now.strftime("%Y-%m-%d-%H")  # hour-level dedup
    return f"{kind}:{detail}:{window}"


def should_alert(state, key):
    return key not in state.get("alerts_sent", [])


def record_alert(state, key):
    alerts = state.get("alerts_sent", [])
    # Prune alerts older than 4 hours
    cutoff = (datetime.now(ET) - timedelta(hours=4)).strftime("%Y-%m-%d")
    alerts = [a for a in alerts if cutoff in a or a.split(":")[-1] >= cutoff.replace("-","")][-50:]
    alerts.append(key)
    state["alerts_sent"] = alerts


def parse_option_symbol(sym):
    """Parse option symbol like TSLA260223P00400000 → (type, strike, expiry_str)"""
    import re
    m = re.match(r"([A-Z]+)(\d{6})([CP])(\d{8})", sym)
    if not m:
        return "?", "?", "?"
    ticker, expiry, otype, strike_raw = m.groups()
    strike = int(strike_raw) / 1000
    strike_str = f"${strike:.0f}" if strike == int(strike) else f"${strike:.1f}"
    # expiry: YYMMDD → MM/DD/YY
    expiry_str = f"20{expiry[0:2]}-{expiry[2:4]}-{expiry[4:6]}"
    return otype, strike_str, expiry_str


def fmt_premium(val):
    v = float(val)
    if v >= 1_000_000:
        return f"${v/1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v/1_000:.0f}K"
    return f"${v:.0f}"


def send_slack(message):
    """Send alert to Slack DM channel."""
    timestamp = datetime.now(ET).strftime("%Y-%m-%d %H:%M ET")
    full_msg = f"[{timestamp}] {message}"

    # Log it
    log_file = Path.home() / ".openclaw/workspace/memory/tsla_alerts.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "a") as f:
        f.write(full_msg + "\n")

    # Send to Slack
    if SLACK_BOT_TOKEN:
        try:
            resp = requests.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}",
                         "Content-Type": "application/json"},
                json={"channel": SLACK_CHANNEL, "text": full_msg},
                timeout=10
            )
            result = resp.json()
            if not result.get("ok"):
                print(f"  Slack error: {result.get('error','unknown')}")
        except Exception as e:
            print(f"  Slack send failed: {e}")

    print(full_msg)


def check_dark_pool(state):
    """Alert on large TSLA dark pool prints."""
    data, err = get("darkpool/TSLA", {"limit": 30})
    if err or not data:
        return []

    alerts = []
    for print_ in data:
        prem = float(print_.get("premium", 0))
        if prem < DARK_POOL_ALERT_THRESHOLD:
            continue

        size  = int(print_.get("size", 0))
        price = float(print_.get("price", 0))
        time_ = print_.get("executed_at", "")
        key   = alert_key("darkpool", f"{size}@{price:.2f}")

        if should_alert(state, key):
            msg = (f"🌑 *TSLA Dark Pool Block:* {size:,} shares @ ${price:.2f} "
                   f"= {fmt_premium(prem)} | {time_[-8:-1]} ET")
            alerts.append((key, msg))

    return alerts


def check_options_flow(state):
    """Alert on significant put/call sweeps and C/P ratio shifts."""
    data, err = get("stock/TSLA/option-contracts", {"limit": 30})
    if err or not data:
        return []

    alerts = []
    total_call_prem = 0
    total_put_prem  = 0
    today = datetime.now(ET).strftime("%y%m%d")

    for c in data:
        sym     = c.get("option_symbol", "")
        is_call = f"C" in sym.split("TSLA")[-1][:8] if "TSLA" in sym else False
        is_put  = not is_call
        prem    = float(c.get("total_premium", 0))
        sweeps  = int(c.get("sweep_volume", 0))
        vol     = int(c.get("volume", 0))
        ask_vol = int(c.get("ask_volume", 0))
        bid_vol = int(c.get("bid_volume", 0))

        if is_call:
            total_call_prem += prem
        else:
            total_put_prem += prem

        # Large sweep alert
        otype, strike_str, expiry_str = parse_option_symbol(sym)
        if is_put and prem >= PUT_SWEEP_ALERT_THRESHOLD and ask_vol > bid_vol * 0.8:
            key = alert_key("put_sweep", sym)
            if should_alert(state, key):
                msg = (f"🐻 *TSLA Large Put Flow:* {strike_str}P exp {expiry_str} | "
                       f"Vol:{vol:,} | Sweeps:{sweeps:,} | {fmt_premium(prem)} premium")
                alerts.append((key, msg))

        if is_call and prem >= CALL_SWEEP_ALERT_THRESHOLD and ask_vol > bid_vol:
            key = alert_key("call_sweep", sym)
            if should_alert(state, key):
                msg = (f"🐂 *TSLA Large Call Flow:* {strike_str}C exp {expiry_str} | "
                       f"Vol:{vol:,} | Sweeps:{sweeps:,} | {fmt_premium(prem)} premium")
                alerts.append((key, msg))

    # C/P ratio check
    if total_put_prem > 0:
        cp_ratio = total_call_prem / total_put_prem
        prev_ratio = state.get("last_cp_ratio")
        state["last_cp_ratio"] = cp_ratio

        if cp_ratio <= CP_RATIO_BEARISH:
            key = alert_key("cp_ratio_bearish", f"{cp_ratio:.2f}")
            if should_alert(state, key):
                msg = (f"⚠️ *TSLA Options Sentiment: BEARISH* | "
                       f"C/P ratio {cp_ratio:.2f}x (put premium dominating) | "
                       f"Call: {fmt_premium(total_call_prem)} vs Put: {fmt_premium(total_put_prem)}")
                alerts.append((key, msg))

        elif cp_ratio >= CP_RATIO_BULLISH:
            key = alert_key("cp_ratio_bullish", f"{cp_ratio:.2f}")
            if should_alert(state, key):
                msg = (f"💪 *TSLA Options Sentiment: BULLISH* | "
                       f"C/P ratio {cp_ratio:.2f}x (call premium dominating) | "
                       f"Call: {fmt_premium(total_call_prem)} vs Put: {fmt_premium(total_put_prem)}")
                alerts.append((key, msg))

    return alerts


def main():
    if not TOKEN:
        print("❌ UNUSUAL_WHALES_TOKEN not set.")
        sys.exit(1)

    if not is_market_hours():
        print("Outside market hours — skipping.")
        sys.exit(0)

    state = load_state()
    now   = datetime.now(ET).strftime("%Y-%m-%d %H:%M ET")
    print(f"🔍 TSLA Watchdog running at {now}")

    all_alerts = []
    all_alerts.extend(check_dark_pool(state))
    all_alerts.extend(check_options_flow(state))

    if all_alerts:
        print(f"\n🚨 {len(all_alerts)} alert(s) to send:")
        for key, msg in all_alerts:
            send_slack(msg)
            record_alert(state, key)
            print(f"  → {msg}")
    else:
        print("✅ No significant signals. All quiet on TSLA.")

    state["last_run"] = now
    save_state(state)


if __name__ == "__main__":
    main()
