#!/usr/bin/env python3
"""Economic & earnings calendar for BigClaw.

Usage:
    python3 economic_calendar.py --earnings TSLA NVDA AAPL
    python3 economic_calendar.py --economic
    python3 economic_calendar.py --all TSLA NVDA
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
import yfinance as yf
import requests


def get_earnings_dates(tickers):
    """Get upcoming earnings dates for tickers."""
    results = []
    for ticker in tickers:
        ticker = ticker.upper()
        try:
            stock = yf.Ticker(ticker)
            cal = stock.calendar
            if cal is not None and not (hasattr(cal, 'empty') and cal.empty):
                if isinstance(cal, dict):
                    earnings_date = cal.get('Earnings Date', [None])
                    if isinstance(earnings_date, list) and earnings_date:
                        date_str = str(earnings_date[0])
                    else:
                        date_str = str(earnings_date) if earnings_date else None

                    results.append({
                        "ticker": ticker,
                        "earnings_date": date_str,
                        "revenue_estimate": cal.get('Revenue Average', None),
                        "eps_estimate": cal.get('Earnings Average', None),
                    })
                else:
                    results.append({"ticker": ticker, "earnings_date": "Check yfinance", "note": "Format changed"})
            else:
                # Try .earnings_dates attribute
                try:
                    ed = stock.earnings_dates
                    if ed is not None and not ed.empty:
                        next_date = ed.index[0]
                        results.append({
                            "ticker": ticker,
                            "earnings_date": str(next_date.date()) if hasattr(next_date, 'date') else str(next_date),
                            "eps_estimate": float(ed.iloc[0].get('EPS Estimate', 0)) if 'EPS Estimate' in ed.columns else None,
                        })
                    else:
                        results.append({"ticker": ticker, "earnings_date": "Not available"})
                except Exception:
                    results.append({"ticker": ticker, "earnings_date": "Not available"})
        except Exception as e:
            results.append({"ticker": ticker, "error": str(e)})
    return results


def get_economic_events():
    """Get upcoming economic events from Trading Economics or similar free source."""
    # Use a simple approach - known scheduled events
    events = []

    # FOMC meeting dates 2026 (known schedule)
    fomc_dates = [
        "2026-01-27", "2026-01-28",
        "2026-03-17", "2026-03-18",
        "2026-05-05", "2026-05-06",
        "2026-06-16", "2026-06-17",
        "2026-07-28", "2026-07-29",
        "2026-09-15", "2026-09-16",
        "2026-11-03", "2026-11-04",
        "2026-12-15", "2026-12-16",
    ]

    today = datetime.now().strftime("%Y-%m-%d")
    for i in range(0, len(fomc_dates), 2):
        if fomc_dates[i+1] >= today:
            events.append({
                "event": "FOMC Meeting",
                "date": f"{fomc_dates[i]} to {fomc_dates[i+1]}",
                "importance": "High",
                "category": "Fed",
            })

    # Monthly recurring events (approximate)
    now = datetime.now()
    for month_offset in range(3):
        month = now + timedelta(days=30 * month_offset)
        m = month.strftime("%Y-%m")

        # CPI - usually 2nd week
        events.append({"event": "CPI Report", "date": f"{m} (mid-month)", "importance": "High", "category": "Inflation"})
        # Jobs report - usually 1st Friday
        events.append({"event": "Nonfarm Payrolls", "date": f"{m} (1st Friday)", "importance": "High", "category": "Employment"})
        # GDP - end of month/quarter
        if month.month in [1, 4, 7, 10]:
            events.append({"event": "GDP Report", "date": f"{m} (late month)", "importance": "High", "category": "Growth"})

    return events


def get_sec_filings(tickers, filing_type="10-K"):
    """Get recent SEC filings from EDGAR."""
    results = []
    headers = {"User-Agent": "BigClawBot/1.0 fixit@grandpapa.net"}
    start = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    end = datetime.now().strftime("%Y-%m-%d")

    for ticker in tickers:
        ticker = ticker.upper()
        try:
            api_url = f"https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&forms={filing_type}&dateRange=custom&startdt={start}&enddt={end}"
            resp = requests.get(api_url, headers=headers, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                hits = data.get("hits", {}).get("hits", [])
                filings = []
                for hit in hits[:5]:
                    src = hit.get("_source", {})
                    company = src.get("display_names", [""])[0] if src.get("display_names") else ""
                    # Only include if ticker matches
                    if ticker in company.upper():
                        filings.append({
                            "form": src.get("forms", filing_type) or filing_type,
                            "date": src.get("file_date", ""),
                            "company": company,
                        })
                results.append({"ticker": ticker, "filings": filings})
            else:
                results.append({"ticker": ticker, "filings": [], "note": f"EDGAR HTTP {resp.status_code}"})
        except Exception as e:
            results.append({"ticker": ticker, "error": str(e)})
    return results


def format_earnings(earnings):
    lines = ["📅 **Upcoming Earnings**\n"]
    for e in earnings:
        if "error" in e:
            lines.append(f"  ❌ {e['ticker']}: {e['error']}")
        else:
            date = e.get("earnings_date", "N/A")
            eps = f" | EPS est: ${e['eps_estimate']:.2f}" if e.get("eps_estimate") else ""
            rev = f" | Rev est: ${e['revenue_estimate']:,.0f}" if e.get("revenue_estimate") else ""
            lines.append(f"  📊 **{e['ticker']}** — {date}{eps}{rev}")
    return "\n".join(lines)


def format_economic(events):
    lines = ["🏛️ **Economic Calendar**\n"]
    seen = set()
    for e in events:
        key = f"{e['event']}-{e['date']}"
        if key not in seen:
            seen.add(key)
            lines.append(f"  {'🔴' if e['importance'] == 'High' else '🟡'} {e['event']} — {e['date']} [{e['category']}]")
    return "\n".join(lines)


def format_filings(filings):
    lines = ["📋 **Recent SEC Filings**\n"]
    for f in filings:
        if "error" in f:
            lines.append(f"  ❌ {f['ticker']}: {f['error']}")
        elif f.get("filings"):
            for filing in f["filings"]:
                lines.append(f"  📄 {f['ticker']} — {filing.get('form', 'N/A')} filed {filing.get('date', 'N/A')}")
        else:
            lines.append(f"  {f['ticker']}: No recent filings found")
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Economic & earnings calendar")
    parser.add_argument("tickers", nargs="*", help="Ticker symbols")
    parser.add_argument("--earnings", action="store_true", help="Show earnings dates")
    parser.add_argument("--economic", action="store_true", help="Show economic events")
    parser.add_argument("--sec", action="store_true", help="Show SEC filings")
    parser.add_argument("--sec-type", default="10-K,10-Q", help="SEC filing types")
    parser.add_argument("--all", action="store_true", help="Show everything")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    output = {}

    if args.all or args.earnings:
        if args.tickers:
            earnings = get_earnings_dates(args.tickers)
            output["earnings"] = earnings
            if not args.json:
                print(format_earnings(earnings))
                print()

    if args.all or args.economic:
        events = get_economic_events()
        output["economic"] = events
        if not args.json:
            print(format_economic(events))
            print()

    if args.all or args.sec:
        if args.tickers:
            for ft in args.sec_type.split(","):
                filings = get_sec_filings(args.tickers, ft.strip())
                output[f"sec_{ft.strip()}"] = filings
                if not args.json:
                    print(format_filings(filings))
                    print()

    if args.json:
        print(json.dumps(output, indent=2, default=str))

    if not any([args.all, args.earnings, args.economic, args.sec]):
        parser.print_help()
