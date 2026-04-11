#!/usr/bin/env python3
"""
Options Intelligence — BigClaw
Pulls options flow data from Unusual Whales for all portfolio holdings.

Data collected per ticker:
  - Max pain (nearest expiry)
  - IV rank (1-year percentile)
  - Options volume (bullish vs bearish premium, call/put ratio)

Market-wide data:
  - Sector ETF options flow (all 11 sectors)
  - Dark pool large blocks for portfolio holdings
  - Total market call/put volume

Outputs:
  - docs/data/options_flow.json  (dashboard)
  - /tmp/bigclaw_options_intel.txt (flat file for data gathers)

Zero LLM tokens. Pure Python + Unusual Whales API.

Schedule: Every 2 hours during market hours, alongside price_refresh.
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

try:
    import uw_api_extended
except ImportError:
    uw_api_extended = None

# ── Paths ─────────────────────────────────────────────────────────────────────

REPO_ROOT = os.path.expanduser("~/bigclaw-ai")
DOCS_DATA = os.path.join(REPO_ROOT, "docs", "data")
DB_PATH = os.path.join(REPO_ROOT, "src", "portfolios.db")
FLAT_FILE = "/tmp/bigclaw_options_intel.txt"

sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

ET = ZoneInfo("America/New_York")

# ── Load secrets ──────────────────────────────────────────────────────────────

def load_secrets():
    secrets = {}
    secrets_file = Path.home() / ".env_secrets"
    for line in secrets_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^export\s+", "", line)
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        secrets[k.strip()] = v.strip().strip("'\"")
    return secrets


secrets = load_secrets()
TOKEN = secrets.get("UNUSUAL_WHALES_TOKEN", "")
BASE = "https://api.unusualwhales.com/api"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "UW-CLIENT-API-ID": "100001"}

if uw_api_extended:
    uw_api_extended.init(TOKEN)

# ── Logging (use bigclaw_logging if available, else print) ────────────────────

try:
    from bigclaw_logging import get_logger
    log = get_logger("options_intel")
except ImportError:
    import logging
    log = logging.getLogger("options_intel")
    log.setLevel(logging.INFO)
    if not log.handlers:
        log.addHandler(logging.StreamHandler())

# ── API helpers ───────────────────────────────────────────────────────────────

def api_get(path, params=None, retries=2):
    """GET from Unusual Whales API with retry."""
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
                # Rate limited — back off
                wait = 2 ** attempt
                log.warning(f"Rate limited on {path}, waiting {wait}s...")
                time.sleep(wait)
                continue
            return None
        except requests.exceptions.RequestException as e:
            if attempt < retries:
                time.sleep(1)
            else:
                log.warning(f"API error on {path}: {e}")
                return None
    return None


def fmt_premium(val):
    """Format dollar amount for display."""
    v = abs(float(val))
    if v >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v / 1_000:.0f}K"
    return f"${v:.0f}"


# ── Database ──────────────────────────────────────────────────────────────────

def get_held_tickers():
    """Get all tickers currently held across active portfolios."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    c = conn.cursor()
    c.execute("""
        SELECT DISTINCT h.ticker
        FROM holdings h
        JOIN portfolios p ON h.portfolio_id = p.id
        WHERE p.is_active = 1 AND h.shares > 0
        ORDER BY h.ticker
    """)
    tickers = [r[0] for r in c.fetchall()]
    conn.close()
    return tickers


# ── Data collection functions ─────────────────────────────────────────────────

def collect_max_pain(tickers):
    """Get max pain for nearest expiry per ticker."""
    results = {}
    for i, t in enumerate(tickers):
        if i > 0 and i % 10 == 0:
            time.sleep(0.5)  # Gentle throttle every 10 calls
        data = api_get(f"stock/{t}/max-pain")
        if not data or not isinstance(data, list) or len(data) == 0:
            continue
        # First entry is nearest expiry
        entry = data[0]
        results[t] = {
            "max_pain": entry.get("max_pain"),
            "expiry": entry.get("expiry"),
            "close": entry.get("close"),
        }
    return results


def collect_iv_rank(tickers):
    """Get IV rank (1-year percentile) per ticker."""
    results = {}
    for i, t in enumerate(tickers):
        if i > 0 and i % 10 == 0:
            time.sleep(0.5)
        data = api_get(f"stock/{t}/iv-rank")
        if not data or not isinstance(data, list) or len(data) == 0:
            continue
        # Latest entry
        entry = data[-1]
        results[t] = {
            "iv_rank_1y": entry.get("iv_rank_1y"),
            "volatility": entry.get("volatility"),
            "date": entry.get("date"),
        }
    return results


def collect_options_volume(tickers):
    """Get options volume with bullish/bearish premium split per ticker."""
    results = {}
    for i, t in enumerate(tickers):
        if i > 0 and i % 10 == 0:
            time.sleep(0.5)
        data = api_get(f"stock/{t}/options-volume")
        if not data or not isinstance(data, list) or len(data) == 0:
            continue
        entry = data[0]
        call_vol = int(entry.get("call_volume", 0))
        put_vol = int(entry.get("put_volume", 0))
        call_prem = float(entry.get("call_premium", 0))
        put_prem = float(entry.get("put_premium", 0))
        bullish = float(entry.get("bullish_premium", 0))
        bearish = float(entry.get("bearish_premium", 0))

        cp_ratio = call_vol / put_vol if put_vol > 0 else 0
        bull_bear_ratio = bullish / bearish if bearish > 0 else 0

        results[t] = {
            "call_volume": call_vol,
            "put_volume": put_vol,
            "call_premium": call_prem,
            "put_premium": put_prem,
            "bullish_premium": bullish,
            "bearish_premium": bearish,
            "cp_ratio": round(cp_ratio, 2),
            "bull_bear_ratio": round(bull_bear_ratio, 2),
            "call_open_interest": int(entry.get("call_open_interest", 0)),
            "put_open_interest": int(entry.get("put_open_interest", 0)),
        }
    return results


def collect_sector_etfs():
    """Get sector ETF options flow data."""
    data = api_get("market/sector-etfs")
    if not data or not isinstance(data, list):
        return []
    results = []
    for etf in data:
        ticker = etf.get("ticker", "")
        name = etf.get("full_name", ticker)
        call_vol = int(etf.get("call_volume", 0))
        put_vol = int(etf.get("put_volume", 0))
        call_prem = float(etf.get("call_premium", 0))
        put_prem = float(etf.get("put_premium", 0))
        bullish = float(etf.get("bullish_premium", 0))
        bearish = float(etf.get("bearish_premium", 0))

        # Fund flow (in/out over last 5 days)
        flows = etf.get("in_out_flow", [])
        net_flow_5d = sum(f.get("change", 0) for f in flows) if flows else 0

        results.append({
            "ticker": ticker,
            "name": name,
            "last": etf.get("last"),
            "call_volume": call_vol,
            "put_volume": put_vol,
            "cp_ratio": round(call_vol / put_vol, 2) if put_vol > 0 else 0,
            "call_premium": call_prem,
            "put_premium": put_prem,
            "bullish_premium": bullish,
            "bearish_premium": bearish,
            "net_flow_5d": net_flow_5d,
        })
    return results


def collect_darkpool_holdings(tickers):
    """Scan recent market-wide dark pool prints for portfolio holdings."""
    data = api_get("darkpool/recent", {"limit": 200})
    if not data or not isinstance(data, list):
        return []

    ticker_set = set(tickers)
    large_prints = []
    for print_ in data:
        t = print_.get("ticker", "")
        if t not in ticker_set:
            continue
        prem = float(print_.get("premium", 0))
        if prem < 100_000:  # Only flag $100K+ prints
            continue
        large_prints.append({
            "ticker": t,
            "size": int(print_.get("size", 0)),
            "price": float(print_.get("price", 0)),
            "premium": prem,
            "executed_at": print_.get("executed_at", ""),
        })

    large_prints.sort(key=lambda x: x["premium"], reverse=True)
    return large_prints[:30]  # Top 30 largest


def collect_market_volume():
    """Get total market options volume."""
    data = api_get("market/total-options-volume")
    if not data or not isinstance(data, list) or len(data) == 0:
        return None
    entry = data[0]
    call_vol = int(entry.get("call_volume", 0))
    put_vol = int(entry.get("put_volume", 0))
    return {
        "call_volume": call_vol,
        "put_volume": put_vol,
        "cp_ratio": round(call_vol / put_vol, 2) if put_vol > 0 else 0,
        "call_premium": float(entry.get("call_premium", 0)),
        "put_premium": float(entry.get("put_premium", 0)),
        "date": entry.get("date"),
    }


# ── Output formatters ────────────────────────────────────────────────────────

def build_json_output(tickers, max_pain, iv_rank, opts_vol, sectors,
                      darkpool, market_vol):
    """Build the JSON file for the dashboard."""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # Per-ticker data
    ticker_data = {}
    for t in tickers:
        entry = {}
        if t in max_pain:
            entry["max_pain"] = max_pain[t]
        if t in iv_rank:
            entry["iv_rank"] = iv_rank[t]
        if t in opts_vol:
            entry["options_volume"] = opts_vol[t]
        if entry:
            ticker_data[t] = entry

    # Signals: flag notable conditions
    signals = []

    # High/low IV rank
    for t, data in iv_rank.items():
        rank = float(data.get("iv_rank_1y", 50) or 50)
        if rank >= 80:
            signals.append({
                "ticker": t, "type": "iv_high",
                "message": f"IV rank {rank:.0f}% — elevated volatility, options expensive",
            })
        elif rank <= 10:
            signals.append({
                "ticker": t, "type": "iv_low",
                "message": f"IV rank {rank:.0f}% — low volatility, options cheap",
            })

    # Max pain divergence (price far from max pain)
    for t, data in max_pain.items():
        mp = float(data.get("max_pain", 0) or 0)
        close = float(data.get("close", 0) or 0)
        if mp > 0 and close > 0:
            pct_diff = ((close - mp) / mp) * 100
            if abs(pct_diff) >= 5:
                direction = "above" if pct_diff > 0 else "below"
                signals.append({
                    "ticker": t, "type": "max_pain_divergence",
                    "message": f"Price {abs(pct_diff):.1f}% {direction} max pain ${mp} (exp {data.get('expiry', '?')})",
                    "max_pain": mp, "close": close, "pct_diff": round(pct_diff, 1),
                })

    # Strong bullish/bearish premium skew
    for t, data in opts_vol.items():
        ratio = data.get("bull_bear_ratio", 1)
        if ratio >= 2.0:
            signals.append({
                "ticker": t, "type": "bullish_flow",
                "message": f"Bullish premium {ratio:.1f}x bearish — smart money accumulating",
            })
        elif ratio > 0 and ratio <= 0.5:
            signals.append({
                "ticker": t, "type": "bearish_flow",
                "message": f"Bearish premium {1/ratio:.1f}x bullish — smart money distributing",
            })

    output = {
        "lastUpdate": now,
        "tickers": ticker_data,
        "sectors": sectors,
        "darkpool_alerts": darkpool,
        "market_volume": market_vol,
        "signals": signals,
    }


    return output


def build_flat_file(tickers, max_pain, iv_rank, opts_vol, sectors,
                    darkpool, market_vol):
    """Build flat text file for morning/afternoon data gathers."""
    now_et = datetime.now(ET).strftime("%Y-%m-%d %H:%M ET")
    lines = []
    lines.append(f"=== OPTIONS INTELLIGENCE — {now_et} ===")
    lines.append("")

    # Market-wide summary
    if market_vol:
        cp = market_vol.get("cp_ratio", 0)
        bias = "BULLISH" if cp > 1.1 else "BEARISH" if cp < 0.9 else "NEUTRAL"
        lines.append(f"MARKET OPTIONS: Call vol {market_vol['call_volume']:,} | "
                     f"Put vol {market_vol['put_volume']:,} | "
                     f"C/P {cp:.2f} ({bias})")
        lines.append(f"  Call premium: {fmt_premium(market_vol['call_premium'])} | "
                     f"Put premium: {fmt_premium(market_vol['put_premium'])}")
        lines.append("")

    # Sector flow
    if sectors:
        lines.append("--- SECTOR OPTIONS FLOW ---")
        for s in sorted(sectors, key=lambda x: x.get("net_flow_5d", 0), reverse=True):
            cp = s.get("cp_ratio", 0)
            flow = s.get("net_flow_5d", 0)
            flow_str = f"+{flow:,}" if flow >= 0 else f"{flow:,}"
            lines.append(f"  {s['name']:25} | C/P {cp:.2f} | "
                         f"5d flow: {flow_str} | "
                         f"Bull: {fmt_premium(s['bullish_premium'])} / "
                         f"Bear: {fmt_premium(s['bearish_premium'])}")
        lines.append("")

    # Per-ticker notable signals
    notable = []
    for t in tickers:
        notes = []
        if t in iv_rank:
            rank = float(iv_rank[t].get("iv_rank_1y", 50) or 50)
            if rank >= 80 or rank <= 10:
                notes.append(f"IV rank {rank:.0f}%")
        if t in max_pain:
            mp = float(max_pain[t].get("max_pain", 0) or 0)
            close = float(max_pain[t].get("close", 0) or 0)
            if mp > 0 and close > 0:
                pct = ((close - mp) / mp) * 100
                if abs(pct) >= 5:
                    notes.append(f"max pain ${mp:.0f} ({pct:+.1f}%)")
        if t in opts_vol:
            ratio = opts_vol[t].get("bull_bear_ratio", 1)
            if ratio >= 2.0:
                notes.append(f"bull/bear {ratio:.1f}x")
            elif ratio > 0 and ratio <= 0.5:
                notes.append(f"bear/bull {1/ratio:.1f}x")
        if notes:
            notable.append((t, notes))

    if notable:
        lines.append("--- NOTABLE TICKER SIGNALS ---")
        for t, notes in notable:
            lines.append(f"  {t:6} | {' | '.join(notes)}")
        lines.append("")

    # Dark pool large blocks
    if darkpool:
        lines.append("--- DARK POOL BLOCKS (PORTFOLIO HOLDINGS) ---")
        for dp in darkpool[:10]:
            lines.append(f"  {dp['ticker']:6} | {dp['size']:>7,} shares @ "
                         f"${dp['price']:.2f} = {fmt_premium(dp['premium'])}")
        lines.append("")

    # Full per-ticker table
    lines.append("--- FULL OPTIONS DATA ---")
    lines.append(f"  {'Ticker':6} | {'IV Rank':>8} | {'MaxPain':>8} | "
                 f"{'C/P Vol':>7} | {'Bull/Bear':>9} | {'CallPrem':>10} | {'PutPrem':>10}")
    lines.append("  " + "-" * 78)
    for t in tickers:
        iv_str = "--"
        if t in iv_rank:
            iv_val = iv_rank[t].get("iv_rank_1y")
            iv_str = f"{float(iv_val):.0f}%" if iv_val else "--"

        mp_str = "--"
        if t in max_pain:
            mp_val = max_pain[t].get("max_pain")
            mp_str = f"${float(mp_val):.0f}" if mp_val else "--"

        cp_str = "--"
        bb_str = "--"
        cprem_str = "--"
        pprem_str = "--"
        if t in opts_vol:
            ov = opts_vol[t]
            cp_str = f"{ov['cp_ratio']:.2f}"
            bb_str = f"{ov['bull_bear_ratio']:.2f}"
            cprem_str = fmt_premium(ov["call_premium"])
            pprem_str = fmt_premium(ov["put_premium"])

        lines.append(f"  {t:6} | {iv_str:>8} | {mp_str:>8} | "
                     f"{cp_str:>7} | {bb_str:>9} | {cprem_str:>10} | {pprem_str:>10}")

    lines.append("")
    lines.append(f"=== END OPTIONS INTELLIGENCE ===")
    return "\n".join(lines)


# ── Git push ──────────────────────────────────────────────────────────────────

def git_push():
    """Commit and push options_flow.json only."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    json_path = os.path.join(DOCS_DATA, "options_flow.json")

    os.chdir(REPO_ROOT)
    subprocess.run(["git", "add", json_path], check=True)
    result = subprocess.run(["git", "diff", "--cached", "--quiet"])
    if result.returncode == 0:
        print("No options data changes to push")
        return
    subprocess.run(
        ["git", "commit", "-m", f"Options intelligence {now}"],
        check=True,
    )
    subprocess.run(["git", "push"], check=True)
    print(f"Pushed options intelligence at {now}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not TOKEN:
        print("UNUSUAL_WHALES_TOKEN not set. Run: source ~/.env_secrets")
        sys.exit(1)

    now_et = datetime.now(ET)
    print(f"Options Intelligence starting at {now_et.strftime('%Y-%m-%d %H:%M ET')}")

    # Get tickers
    tickers = get_held_tickers()
    print(f"Collecting data for {len(tickers)} held tickers...")

    # Collect per-ticker data (3 API calls per ticker)
    print("  Fetching max pain...")
    max_pain = collect_max_pain(tickers)
    print(f"    Got max pain for {len(max_pain)}/{len(tickers)} tickers")

    print("  Fetching IV rank...")
    iv_rank = collect_iv_rank(tickers)
    print(f"    Got IV rank for {len(iv_rank)}/{len(tickers)} tickers")

    print("  Fetching options volume...")
    opts_vol = collect_options_volume(tickers)
    print(f"    Got options volume for {len(opts_vol)}/{len(tickers)} tickers")

    # Market-wide data (3 API calls total)
    print("  Fetching sector ETF flow...")
    sectors = collect_sector_etfs()
    print(f"    Got {len(sectors)} sector ETFs")

    print("  Fetching dark pool blocks for holdings...")
    darkpool = collect_darkpool_holdings(tickers)
    print(f"    Found {len(darkpool)} large prints in portfolio holdings")

    print("  Fetching total market options volume...")
    market_vol = collect_market_volume()

    # Extended UW API data (flow alerts, GEX, congress, etc.)
    extended = {}
    if uw_api_extended:
        try:
            extended = uw_api_extended.collect_all(tickers)
        except Exception as e:
            print(f"  Extended UW API failed (non-fatal): {e}")

    # Build outputs
    json_output = build_json_output(
        tickers, max_pain, iv_rank, opts_vol, sectors, darkpool, market_vol
    )

    # Merge extended UW data into JSON output
    if extended:
        for k, v in extended.items():
            if v:
                json_output[k] = v

    flat_output = build_flat_file(
        tickers, max_pain, iv_rank, opts_vol, sectors, darkpool, market_vol
    )

    # Append extended data to flat file
    if uw_api_extended and extended:
        ext_text = uw_api_extended.format_flat_sections(extended)
        if ext_text:
            flat_output += "\n" + ext_text

    # Write JSON for dashboard
    json_path = os.path.join(DOCS_DATA, "options_flow.json")
    with open(json_path, "w") as f:
        json.dump(json_output, f, indent=2)
    print(f"Wrote {os.path.getsize(json_path) / 1024:.0f} KB to {json_path}")

    # Write flat file for data gathers
    with open(FLAT_FILE, "w") as f:
        f.write(flat_output)
    print(f"Wrote {len(flat_output)} bytes to {FLAT_FILE}")

    # Print signal summary
    signals = json_output.get("signals", [])
    if signals:
        print(f"\n  Notable signals ({len(signals)}):")
        for s in signals[:10]:
            print(f"    {s['ticker']:6} | {s['type']:20} | {s['message']}")
        if len(signals) > 10:
            print(f"    ... and {len(signals) - 10} more")
    else:
        print("\n  No notable signals")

    # Git push
    try:
        git_push()
    except Exception as e:
        log.warning(f"Git push failed (non-fatal): {e}")
        print(f"Git push failed: {e}")

    print("\nOptions Intelligence complete.")


if __name__ == "__main__":
    main()
