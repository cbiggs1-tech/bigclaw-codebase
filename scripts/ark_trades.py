#!/usr/bin/env python3
"""
ARK Daily Trades Monitor

Fetches ARK Invest's daily trade notifications and filters
for tickers in our portfolio/watchlist.
"""

import os
import sys
import json
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

# --- Config ---
WATCHLIST = {
    "NVDA", "TSLA", "PLTR", "CRSP", "ARKK", "RBLX", "QBTS",
    "COIN", "ROKU", "SQ", "HOOD", "PATH", "DKNG", "TWLO",
    "AAPL", "AMZN", "GOOG", "GOOGL", "META", "MSFT",
}

ARK_FUNDS = ["ARKK", "ARKW", "ARKG", "ARKF", "ARKQ", "ARKX", "IZRL", "PRNT"]

HEADERS = {"User-Agent": "BigClawBot/1.0 (ARK Trade Monitor)"}


def fetch_cathiesark_trades():
    """Fetch from cathiesark.com (most reliable public source)."""
    url = "https://cathiesark.com/ark-funds-combined/trades"
    print(f"📡 Fetching trades from cathiesark.com...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"⚠️ cathiesark.com failed: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    trades = []

    # Look for trade table rows
    table = soup.find("table")
    if not table:
        # Try finding trade data in script tags (JSON)
        scripts = soup.find_all("script")
        for script in scripts:
            if script.string and "trades" in (script.string or "").lower():
                # Try to extract JSON data
                try:
                    data = json.loads(script.string)
                    return parse_json_trades(data)
                except:
                    pass
        print("⚠️ No trade table found on cathiesark.com")
        return None

    rows = table.find_all("tr")[1:]  # skip header
    for row in rows:
        cols = [td.get_text(strip=True) for td in row.find_all("td")]
        if len(cols) >= 5:
            trades.append({
                "date": cols[0] if len(cols) > 0 else "",
                "fund": cols[1] if len(cols) > 1 else "",
                "direction": cols[2] if len(cols) > 2 else "",
                "ticker": cols[3] if len(cols) > 3 else "",
                "company": cols[4] if len(cols) > 4 else "",
                "shares": cols[5] if len(cols) > 5 else "",
                "pct_of_etf": cols[6] if len(cols) > 6 else "",
            })

    return trades


def fetch_arkfunds_io_trades():
    """Try arkfunds.io API."""
    print(f"📡 Trying arkfunds.io API...")
    trades = []
    for fund in ARK_FUNDS:
        url = f"https://arkfunds.io/api/v2/etf/trades?symbol={fund}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.ok:
                data = resp.json()
                for t in data.get("trades", []):
                    trades.append({
                        "date": t.get("date", ""),
                        "fund": fund,
                        "direction": t.get("direction", ""),
                        "ticker": t.get("ticker", ""),
                        "company": t.get("company", ""),
                        "shares": str(t.get("shares", "")),
                        "pct_of_etf": str(t.get("weight", "")),
                    })
        except Exception as e:
            continue

    return trades if trades else None


def fetch_arktracker_trades():
    """Fallback: scrape ark daily email archive or alternative sources."""
    print("📡 Trying alternative trade sources...")
    # Try the ARK transparency page
    url = "https://ark-funds.com/trade-notifications"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        if resp.ok:
            soup = BeautifulSoup(resp.text, "html.parser")
            # Parse whatever format they use
            tables = soup.find_all("table")
            if tables:
                trades = []
                for table in tables:
                    for row in table.find_all("tr")[1:]:
                        cols = [td.get_text(strip=True) for td in row.find_all("td")]
                        if len(cols) >= 4:
                            trades.append({
                                "date": cols[0],
                                "fund": cols[1] if len(cols) > 1 else "",
                                "direction": cols[2] if len(cols) > 2 else "",
                                "ticker": cols[3] if len(cols) > 3 else "",
                                "company": cols[4] if len(cols) > 4 else "",
                                "shares": cols[5] if len(cols) > 5 else "",
                                "pct_of_etf": "",
                            })
                if trades:
                    return trades
    except:
        pass

    return None


def filter_watchlist(trades):
    """Filter trades for watchlist tickers."""
    if not trades:
        return [], trades or []
    matched = [t for t in trades if t.get("ticker", "").upper() in WATCHLIST]
    return matched, trades


def generate_summary(matched, all_trades, source):
    """Generate markdown summary."""
    lines = []
    today = datetime.now().strftime("%Y-%m-%d")
    lines.append(f"# 🏦 ARK Daily Trades — {today}")
    lines.append(f"**Source:** {source}")
    lines.append(f"**Total trades today:** {len(all_trades)}")
    lines.append("")

    if matched:
        lines.append("## 🚨 Watchlist Matches")
        lines.append("")
        lines.append("| Fund | Direction | Ticker | Company | Shares | % of ETF |")
        lines.append("|------|-----------|--------|---------|--------|----------|")
        for t in matched:
            direction_emoji = "🟢" if "buy" in t.get("direction", "").lower() else "🔴"
            lines.append(
                f"| {t.get('fund','')} | {direction_emoji} {t.get('direction','')} | "
                f"**{t.get('ticker','')}** | {t.get('company','')} | "
                f"{t.get('shares','')} | {t.get('pct_of_etf','')} |"
            )
        lines.append("")
    else:
        lines.append("## ✅ No watchlist trades today")
        lines.append("")

    if all_trades:
        lines.append("## 📋 All Trades")
        lines.append("")
        # Group by direction
        buys = [t for t in all_trades if "buy" in t.get("direction", "").lower()]
        sells = [t for t in all_trades if "sell" in t.get("direction", "").lower()]

        if buys:
            lines.append(f"### 🟢 Buys ({len(buys)})")
            for t in buys:
                lines.append(f"- **{t.get('ticker','')}** ({t.get('fund','')}) — {t.get('shares','')} shares — {t.get('company','')}")

        if sells:
            lines.append(f"\n### 🔴 Sells ({len(sells)})")
            for t in sells:
                lines.append(f"- **{t.get('ticker','')}** ({t.get('fund','')}) — {t.get('shares','')} shares — {t.get('company','')}")

        lines.append("")

    # Summary stats
    lines.append("## 📊 Summary")
    if all_trades:
        buys = len([t for t in all_trades if "buy" in t.get("direction", "").lower()])
        sells = len(all_trades) - buys
        funds = set(t.get("fund", "") for t in all_trades)
        tickers = set(t.get("ticker", "") for t in all_trades)
        lines.append(f"- **Buys:** {buys} | **Sells:** {sells}")
        lines.append(f"- **Funds active:** {', '.join(sorted(funds))}")
        lines.append(f"- **Unique tickers:** {len(tickers)}")
    else:
        lines.append("- No trades found (market may be closed)")

    return "\n".join(lines)


def main():
    # Try sources in order of reliability
    trades = None
    source = ""

    # 1. cathiesark.com
    trades = fetch_cathiesark_trades()
    if trades:
        source = "cathiesark.com"
    
    # 2. arkfunds.io API
    if not trades:
        trades = fetch_arkfunds_io_trades()
        if trades:
            source = "arkfunds.io API"

    # 3. Alternative sources
    if not trades:
        trades = fetch_arktracker_trades()
        if trades:
            source = "ark-funds.com"

    if not trades:
        print("⚠️ Could not fetch trades from any source.")
        print("This may be normal on weekends/holidays or if sites changed format.")
        trades = []
        source = "none (all sources unavailable)"

    matched, all_trades = filter_watchlist(trades)
    summary = generate_summary(matched, all_trades, source)

    print("\n" + summary)

    # Save
    output_dir = os.path.expanduser("~/.openclaw/workspace/research")
    os.makedirs(output_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_path = os.path.join(output_dir, f"ark-trades-{date_str}.md")
    with open(output_path, "w") as f:
        f.write(summary)
    print(f"\n💾 Saved to {output_path}")

    return summary


if __name__ == "__main__":
    main()
