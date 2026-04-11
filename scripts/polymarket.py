#!/usr/bin/env python3
"""Polymarket prediction market data fetcher for BigClaw.

Usage:
    python3 polymarket.py --search "fed rate"
    python3 polymarket.py --trending
    python3 polymarket.py --trending --category business
    python3 polymarket.py --market-movers   # Finance-relevant markets
"""

import argparse
import json
import requests
from datetime import datetime


GAMMA_API = "https://gamma-api.polymarket.com/markets"
FINANCE_KEYWORDS = [
    "fed", "rate", "inflation", "recession", "gdp", "stock", "market",
    "economy", "earnings", "tariff", "trade", "treasury", "debt",
    "s&p", "nasdaq", "dow", "bitcoin", "btc", "crypto", "oil",
    "gold", "dollar", "currency", "unemployment", "jobs"
]


def fetch_markets(limit=50):
    """Fetch open markets from Polymarket Gamma API."""
    resp = requests.get(GAMMA_API, params={"closed": "false", "limit": limit}, timeout=15)
    resp.raise_for_status()
    return resp.json()


def parse_market(market):
    """Parse a market into a clean dict."""
    question = market.get("question", "Unknown")
    outcome_prices = market.get("outcomePrices", "")
    outcomes = market.get("outcomes", "")
    volume = float(market.get("volume", 0) or 0)
    liquidity = float(market.get("liquidity", 0) or 0)
    end_date = market.get("endDate", "")

    # Parse outcomes
    odds = []
    try:
        if outcome_prices and outcomes:
            prices = json.loads(outcome_prices) if isinstance(outcome_prices, str) else outcome_prices
            outcome_list = json.loads(outcomes) if isinstance(outcomes, str) else outcomes
            for name, price in zip(outcome_list, prices):
                odds.append({"outcome": name, "probability": round(float(price) * 100, 1)})
    except Exception:
        pass

    # Format volume
    if volume >= 1_000_000:
        vol_str = f"${volume/1_000_000:.1f}M"
    elif volume >= 1000:
        vol_str = f"${volume/1000:.0f}K"
    else:
        vol_str = f"${volume:.0f}"

    # Format end date
    end_str = "Ongoing"
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            end_str = end_dt.strftime("%b %d, %Y")
        except Exception:
            end_str = end_date[:10]

    return {
        "question": question,
        "odds": odds,
        "volume": volume,
        "volume_str": vol_str,
        "liquidity": liquidity,
        "end_date": end_str,
    }


def search_markets(query, limit=10):
    """Search for markets matching a query."""
    markets = fetch_markets(limit=100)
    query_lower = query.lower()
    results = []
    for m in markets:
        q = m.get("question", "").lower()
        d = m.get("description", "").lower()
        if query_lower in q or query_lower in d:
            results.append(parse_market(m))
            if len(results) >= limit:
                break
    return results


def trending_markets(category="all", limit=10):
    """Get trending markets by volume."""
    markets = fetch_markets(limit=100)
    parsed = [parse_market(m) for m in markets]
    parsed.sort(key=lambda x: x["volume"], reverse=True)

    if category != "all":
        category_keywords = {
            "politics": ["election", "trump", "biden", "president", "congress", "senate", "vote"],
            "crypto": ["bitcoin", "btc", "ethereum", "eth", "crypto", "solana"],
            "sports": ["nfl", "nba", "mlb", "super bowl", "championship"],
            "business": FINANCE_KEYWORDS,
        }
        keywords = category_keywords.get(category, [])
        if keywords:
            parsed = [m for m in parsed if any(kw in m["question"].lower() for kw in keywords)]

    return parsed[:limit]


def market_movers(limit=10):
    """Get finance-relevant prediction markets for morning reports."""
    markets = fetch_markets(limit=100)
    parsed = []
    for m in markets:
        q = m.get("question", "").lower()
        if any(kw in q for kw in FINANCE_KEYWORDS):
            parsed.append(parse_market(m))

    parsed.sort(key=lambda x: x["volume"], reverse=True)
    return parsed[:limit]


def format_output(markets, title="Polymarket"):
    """Format markets for display."""
    if not markets:
        return f"No markets found.\n"

    lines = [f"🔮 {title}", f"Found {len(markets)} markets\n"]
    for i, m in enumerate(markets, 1):
        odds_str = " | ".join(f"{o['outcome']}: {o['probability']:.0f}%" for o in m["odds"]) if m["odds"] else "No odds"
        lines.append(f"{i}. {m['question']}")
        lines.append(f"   📊 {odds_str}")
        lines.append(f"   💰 Volume: {m['volume_str']} | Ends: {m['end_date']}")
        lines.append("")

    lines.append("Prices = crowd-sourced probabilities (65¢ = 65% chance)")
    return "\n".join(lines)


def format_json(markets):
    """Output as JSON for programmatic use."""
    return json.dumps(markets, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Polymarket prediction market data")
    parser.add_argument("--search", type=str, help="Search query")
    parser.add_argument("--trending", action="store_true", help="Get trending markets")
    parser.add_argument("--market-movers", action="store_true", help="Finance-relevant markets")
    parser.add_argument("--category", type=str, default="all", choices=["all", "politics", "crypto", "sports", "business"])
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    try:
        if args.search:
            markets = search_markets(args.search, args.limit)
            title = f"Polymarket: '{args.search}'"
        elif args.market_movers:
            markets = market_movers(args.limit)
            title = "Polymarket: Finance & Macro"
        elif args.trending:
            markets = trending_markets(args.category, args.limit)
            title = f"Polymarket Trending ({args.category.title()})"
        else:
            parser.print_help()
            exit(1)

        if args.json:
            print(format_json(markets))
        else:
            print(format_output(markets, title))

    except Exception as e:
        print(f"Error: {e}")
        exit(1)
