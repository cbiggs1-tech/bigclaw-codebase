#!/usr/bin/env python3
"""Fetch SEC Form 4 insider trading data from OpenInsider.com"""
import sys
import json
import argparse
import requests
from bs4 import BeautifulSoup

BASE_URL = "http://openinsider.com/search"

def fetch_insider_trades(ticker, limit=10):
    headers = {"User-Agent": "Mozilla/5.0 (compatible; BigClawBot/1.0)"}
    try:
        resp = requests.get(BASE_URL, params={"q": ticker}, headers=headers, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")
        table = soup.find("table", class_="tinytable")
        if not table:
            print("[]")
            return

        rows = table.find_all("tr")
        if len(rows) < 2:
            print("[]")
            return

        # Parse header
        header_cells = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]
        col_map = {}
        for i, h in enumerate(header_cells):
            key = h.replace("\xa0", " ").lower()
            if "filing" in key and "date" in key: col_map["filing_date"] = i
            elif "trade" in key and "date" in key: col_map["trade_date"] = i
            elif key == "ticker": col_map["ticker"] = i
            elif "insider" in key: col_map["insider_name"] = i
            elif key == "title": col_map["title"] = i
            elif "trade" in key and "type" in key: col_map["trade_type"] = i
            elif key == "price": col_map["price"] = i
            elif key == "qty": col_map["qty"] = i
            elif key == "value": col_map["value"] = i

        results = []
        for row in rows[1:limit+1]:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cells) < max(col_map.values(), default=0) + 1:
                continue
            entry = {}
            for field, idx in col_map.items():
                entry[field] = cells[idx]
            results.append(entry)

        print(json.dumps(results, indent=2))

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Fetch insider trades from OpenInsider")
    parser.add_argument("ticker", help="Stock ticker (e.g. TSLA)")
    parser.add_argument("--limit", type=int, default=10, help="Max results")
    args = parser.parse_args()
    fetch_insider_trades(args.ticker, args.limit)

if __name__ == "__main__":
    main()
