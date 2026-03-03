#!/usr/bin/env python3
"""Multi-source sentiment aggregator for BigClaw.

Sources: X/Twitter, Reddit (WSB + stocks + investing), Yahoo Finance news, Brave Search news.
Stocktwits removed (API 403 since Feb 2026).

Usage:
    source ~/.env_secrets
    python3 sentiment.py TSLA NVDA AAPL
    python3 sentiment.py TSLA --json
"""

import argparse
import json
import os
import sys
import requests
from datetime import datetime, timezone


def search_x(query, max_results=20):
    """Search X/Twitter API v2 for recent posts about a topic."""
    bearer = os.environ.get("X_BEARER_TOKEN")
    if not bearer:
        return {"source": "X/Twitter", "error": "No X_BEARER_TOKEN set", "posts": []}

    url = "https://api.twitter.com/2/tweets/search/recent"
    headers = {"Authorization": f"Bearer {bearer}"}
    params = {
        "query": f"{query} lang:en -is:retweet",
        "max_results": min(max_results, 100),
        "tweet.fields": "created_at,public_metrics,author_id",
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        if resp.status_code == 429:
            return {"source": "X/Twitter", "error": "Rate limited", "posts": []}
        if resp.status_code != 200:
            return {"source": "X/Twitter", "error": f"HTTP {resp.status_code}", "posts": []}

        data = resp.json()
        posts = []
        for tweet in data.get("data", []):
            metrics = tweet.get("public_metrics", {})
            posts.append({
                "text": tweet.get("text", ""),
                "likes": metrics.get("like_count", 0),
                "retweets": metrics.get("retweet_count", 0),
                "created": tweet.get("created_at", ""),
            })
        return {"source": "X/Twitter", "count": len(posts), "posts": posts}
    except Exception as e:
        return {"source": "X/Twitter", "error": str(e), "posts": []}


def search_reddit(ticker, subreddits=None):
    """Search multiple Reddit subreddits for mentions of a ticker."""
    if subreddits is None:
        subreddits = ["wallstreetbets", "stocks", "investing"]

    headers = {"User-Agent": "BigClawBot/1.0"}
    all_posts = []

    for sub in subreddits:
        url = f"https://www.reddit.com/r/{sub}/search.json"
        params = {"q": ticker, "sort": "new", "limit": 10, "restrict_sr": "true", "t": "week"}

        try:
            resp = requests.get(url, headers=headers, params=params, timeout=15)
            if resp.status_code != 200:
                continue

            data = resp.json()
            for child in data.get("data", {}).get("children", []):
                post = child.get("data", {})
                all_posts.append({
                    "title": post.get("title", ""),
                    "score": post.get("score", 0),
                    "comments": post.get("num_comments", 0),
                    "subreddit": sub,
                    "url": f"https://reddit.com{post.get('permalink', '')}",
                })
        except Exception:
            continue

    return {"source": "Reddit", "count": len(all_posts), "posts": all_posts}


def search_yahoo_news(ticker):
    """Get news headlines from Yahoo Finance via yfinance."""
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)
        news = stock.news or []

        posts = []
        for item in news[:10]:
            title = item.get("title", "")
            publisher = item.get("publisher", "")
            link = item.get("link", "")
            posts.append({
                "text": title,
                "publisher": publisher,
                "url": link,
            })
        return {"source": "Yahoo News", "count": len(posts), "posts": posts}
    except Exception as e:
        return {"source": "Yahoo News", "error": str(e), "posts": []}


def search_brave_news(ticker):
    """Search Brave for recent news headlines about a ticker."""
    api_key = os.environ.get("BRAVE_API_KEY")
    if not api_key:
        return {"source": "Brave News", "error": "No BRAVE_API_KEY set", "posts": []}

    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    }
    params = {
        "q": f"{ticker} stock news",
        "count": 10,
        "freshness": "pw",  # past week
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        if resp.status_code != 200:
            return {"source": "Brave News", "error": f"HTTP {resp.status_code}", "posts": []}

        data = resp.json()
        posts = []
        for result in data.get("web", {}).get("results", [])[:10]:
            title = result.get("title", "")
            desc = result.get("description", "")
            posts.append({
                "text": f"{title}. {desc}",
                "title": title,
                "url": result.get("url", ""),
            })
        return {"source": "Brave News", "count": len(posts), "posts": posts}
    except Exception as e:
        return {"source": "Brave News", "error": str(e), "posts": []}


def simple_sentiment_score(text):
    """Basic sentiment scoring. Returns -1 to 1."""
    positive = ["bull", "buy", "long", "moon", "rocket", "up", "green", "calls", "pump",
                "breakout", "surge", "rally", "strong", "beat", "growth", "upgrade",
                "soar", "gain", "profit", "optimistic", "outperform", "positive"]
    negative = ["bear", "sell", "short", "crash", "dump", "down", "red", "puts", "drop",
                "plunge", "weak", "miss", "decline", "downgrade", "fear", "tank",
                "loss", "risk", "warn", "cut", "pessimistic", "underperform", "negative"]

    text_lower = text.lower()
    pos_count = sum(1 for w in positive if w in text_lower)
    neg_count = sum(1 for w in negative if w in text_lower)
    total = pos_count + neg_count
    if total == 0:
        return 0
    return round((pos_count - neg_count) / total, 2)


def analyze_ticker(ticker):
    """Run full sentiment analysis for a ticker across all sources."""
    ticker = ticker.upper()
    results = {
        "ticker": ticker,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sources": {}
    }

    # X/Twitter
    x_data = search_x(f"${ticker} OR #{ticker}")
    results["sources"]["twitter"] = x_data
    x_scores = [simple_sentiment_score(p["text"]) for p in x_data.get("posts", [])]

    # Reddit (multiple subs)
    reddit_data = search_reddit(ticker)
    results["sources"]["reddit"] = reddit_data
    reddit_scores = [simple_sentiment_score(p["title"]) for p in reddit_data.get("posts", [])]

    # Yahoo Finance news
    yahoo_data = search_yahoo_news(ticker)
    results["sources"]["yahoo"] = yahoo_data
    yahoo_scores = [simple_sentiment_score(p["text"]) for p in yahoo_data.get("posts", [])]

    # Brave Search news
    brave_data = search_brave_news(ticker)
    results["sources"]["brave"] = brave_data
    brave_scores = [simple_sentiment_score(p["text"]) for p in brave_data.get("posts", [])]

    # Weighted composite
    # Social (X + Reddit) = 50%, News (Yahoo + Brave) = 50%
    social_scores = x_scores + reddit_scores
    news_scores = yahoo_scores + brave_scores

    social_avg = sum(social_scores) / len(social_scores) if social_scores else 0
    news_avg = sum(news_scores) / len(news_scores) if news_scores else 0

    # Weight by availability
    if social_scores and news_scores:
        composite = round(social_avg * 0.5 + news_avg * 0.5, 2)
    elif social_scores:
        composite = round(social_avg, 2)
    elif news_scores:
        composite = round(news_avg, 2)
    else:
        composite = 0

    results["sentiment"] = {
        "composite_score": composite,
        "social_avg": round(social_avg, 2) if social_scores else None,
        "news_avg": round(news_avg, 2) if news_scores else None,
        "twitter_avg": round(sum(x_scores) / len(x_scores), 2) if x_scores else None,
        "reddit_avg": round(sum(reddit_scores) / len(reddit_scores), 2) if reddit_scores else None,
        "yahoo_avg": round(sum(yahoo_scores) / len(yahoo_scores), 2) if yahoo_scores else None,
        "brave_avg": round(sum(brave_scores) / len(brave_scores), 2) if brave_scores else None,
        "label": "Bullish" if composite > 0.15 else "Bearish" if composite < -0.15 else "Neutral",
    }

    return results


def format_output(results):
    """Format analysis results for display."""
    lines = []
    for r in results:
        ticker = r["ticker"]
        s = r["sentiment"]
        label = s["label"]
        emoji = "🟢" if label == "Bullish" else "🔴" if label == "Bearish" else "⚪"

        lines.append(f"{emoji} **{ticker}** — {label} (score: {s['composite_score']:+.2f})")

        parts = []
        if s.get("twitter_avg") is not None:
            parts.append(f"X: {s['twitter_avg']:+.2f}")
        if s.get("reddit_avg") is not None:
            parts.append(f"Reddit: {s['reddit_avg']:+.2f}")
        if s.get("yahoo_avg") is not None:
            parts.append(f"Yahoo: {s['yahoo_avg']:+.2f}")
        if s.get("brave_avg") is not None:
            parts.append(f"News: {s['brave_avg']:+.2f}")

        src_counts = []
        for name, src in r["sources"].items():
            if "error" in src:
                src_counts.append(f"{name}: ⚠️ {src['error']}")
            else:
                src_counts.append(f"{name}: {src.get('count', 0)} posts")

        if parts:
            lines.append(f"   {' | '.join(parts)}")
        lines.append(f"   Sources: {', '.join(src_counts)}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-source sentiment analysis")
    parser.add_argument("tickers", nargs="+", help="Ticker symbols to analyze")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    try:
        results = []
        for ticker in args.tickers:
            print(f"Analyzing {ticker.upper()}...", file=sys.stderr)
            results.append(analyze_ticker(ticker))

        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(format_output(results))
    except Exception as e:
        error_out = {"error": "Sentiment fetch failed", "reason": str(e), "tickers": args.tickers}
        print(json.dumps(error_out, indent=2), file=sys.stderr)
        print(f"ERROR: Sentiment analysis failed — {e}")
        sys.exit(1)
