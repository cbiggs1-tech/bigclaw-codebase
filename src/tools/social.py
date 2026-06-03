"""Social sentiment tools for BigClaw AI - Stocktwits, Reddit, and X/Twitter."""

import logging
import os
import re
import time
from datetime import datetime
from typing import Optional
import requests

from .base import BaseTool

logger = logging.getLogger(__name__)

class RedditSentimentTool(BaseTool):
    """Search Reddit for stock discussions."""

    @property
    def name(self) -> str:
        return "search_reddit_stocks"

    @property
    def description(self) -> str:
        return """Search Reddit for stock discussions and sentiment.

Searches popular investing subreddits:
- r/wallstreetbets (retail traders, meme stocks)
- r/stocks (general stock discussion)
- r/investing (long-term investing)
- r/options (options trading)

Use when users ask about:
- "What's Reddit saying about GME?"
- "Any wallstreetbets posts on NVDA?"
- "What do retail traders think about Tesla?"
"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Stock ticker or company name to search for"
                },
                "subreddit": {
                    "type": "string",
                    "enum": ["wallstreetbets", "stocks", "investing", "options", "all"],
                    "description": "Which subreddit to search. 'all' searches all investing subs. Default is 'all'"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of posts to return (default 10, max 25)"
                }
            },
            "required": ["query"]
        }

    def execute(self, query: str, subreddit: str = "all", limit: int = 10) -> str:
        query = query.strip()
        limit = min(max(5, limit), 25)

        logger.info(f"Searching Reddit for '{query}' in r/{subreddit}")

        # Map subreddit choice
        if subreddit == "all":
            subreddit_param = "wallstreetbets+stocks+investing+options"
        else:
            subreddit_param = subreddit

        try:
            # Reddit JSON API (no auth required for public data)
            url = f"https://www.reddit.com/r/{subreddit_param}/search.json"
            params = {
                "q": query,
                "restrict_sr": "on",
                "sort": "relevance",
                "t": "week",  # Last week
                "limit": limit
            }
            headers = {
                "User-Agent": "BigClawBot/1.0"
            }

            response = requests.get(url, params=params, headers=headers, timeout=10)

            if response.status_code != 200:
                return f"Error searching Reddit: HTTP {response.status_code}"

            data = response.json()
            posts = data.get("data", {}).get("children", [])

            if not posts:
                return f"No recent Reddit posts found for '{query}' in the last week."

            output = f"**Reddit Search: '{query}'**\n"
            output += f"Subreddit(s): r/{subreddit_param.replace('+', ', r/')}\n"
            output += f"Found {len(posts)} posts from the last week\n\n"

            for i, post in enumerate(posts, 1):
                post_data = post.get("data", {})

                title = post_data.get("title", "No title")
                author = post_data.get("author", "deleted")
                sub = post_data.get("subreddit", "unknown")
                score = post_data.get("score", 0)
                num_comments = post_data.get("num_comments", 0)
                url = f"https://reddit.com{post_data.get('permalink', '')}"
                created_utc = post_data.get("created_utc", 0)

                # Format date
                if created_utc:
                    created = datetime.fromtimestamp(created_utc).strftime("%Y-%m-%d")
                else:
                    created = "unknown"

                # Truncate long titles
                if len(title) > 150:
                    title = title[:150] + "..."

                # Score indicator
                if score > 1000:
                    score_display = f"🔥 {score:,}"
                elif score > 100:
                    score_display = f"⬆️ {score:,}"
                else:
                    score_display = f"{score:,}"

                output += f"**{i}. {title}**\n"
                output += f"   r/{sub} | {score_display} points | {num_comments} comments | {created}\n"
                output += f"   u/{author} | {url}\n\n"

            return output

        except requests.exceptions.Timeout:
            return "Reddit request timed out. Try again."
        except Exception as e:
            logger.error(f"Reddit search error: {e}")
            return f"Error searching Reddit: {str(e)}"


class WallStreetBetsTrendingTool(BaseTool):
    """Get trending tickers from WallStreetBets."""

    @property
    def name(self) -> str:
        return "get_wsb_trending"

    @property
    def description(self) -> str:
        return """Get currently trending/hot posts from r/wallstreetbets.

WallStreetBets (WSB) is known for:
- Meme stocks (GME, AMC, etc.)
- YOLO trades and options plays
- Retail investor sentiment

Use when users ask about:
- "What's hot on WSB?"
- "What are retail traders buying?"
- "Any meme stocks trending?"
"""

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of posts to return (default 10, max 25)"
                }
            },
            "required": []
        }

    def execute(self, limit: int = 10) -> str:
        limit = min(max(5, limit), 25)

        logger.info(f"Fetching trending from r/wallstreetbets")

        try:
            # Get hot posts from WSB
            url = "https://www.reddit.com/r/wallstreetbets/hot.json"
            params = {"limit": limit + 2}  # Extra to skip stickied
            headers = {"User-Agent": "BigClawBot/1.0"}

            response = requests.get(url, params=params, headers=headers, timeout=10)

            if response.status_code != 200:
                return f"Error fetching WSB: HTTP {response.status_code}"

            data = response.json()
            posts = data.get("data", {}).get("children", [])

            # Filter out stickied posts
            posts = [p for p in posts if not p.get("data", {}).get("stickied", False)][:limit]

            if not posts:
                return "No posts found on r/wallstreetbets."

            # Extract ticker mentions
            ticker_pattern = r'\$([A-Z]{1,5})\b|\b([A-Z]{2,5})\b'
            ticker_counts = {}

            output = "**🚀 r/wallstreetbets - Hot Posts**\n\n"

            for i, post in enumerate(posts, 1):
                post_data = post.get("data", {})

                title = post_data.get("title", "No title")
                score = post_data.get("score", 0)
                num_comments = post_data.get("num_comments", 0)
                flair = post_data.get("link_flair_text", "")
                url = f"https://reddit.com{post_data.get('permalink', '')}"

                # Find ticker mentions in title
                matches = re.findall(ticker_pattern, title)
                tickers_found = []
                for match in matches:
                    ticker = match[0] or match[1]
                    if ticker and len(ticker) >= 2 and ticker not in ["THE", "AND", "FOR", "ARE", "NOT", "YOU", "ALL", "CAN", "HAD", "HER", "WAS", "ONE", "OUR", "OUT", "HAS", "HIS", "HOW", "MAN", "NEW", "NOW", "OLD", "SEE", "WAY", "WHO", "BOY", "DID", "GET", "HIM", "LET", "PUT", "SAY", "SHE", "TOO", "USE"]:
                        tickers_found.append(ticker)
                        ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1

                # Score indicator
                if score > 5000:
                    score_display = f"🔥🔥 {score:,}"
                elif score > 1000:
                    score_display = f"🔥 {score:,}"
                else:
                    score_display = f"⬆️ {score:,}"

                # Truncate title
                if len(title) > 120:
                    title = title[:120] + "..."

                flair_display = f"[{flair}] " if flair else ""

                output += f"**{i}. {flair_display}{title}**\n"
                output += f"   {score_display} | {num_comments} comments"
                if tickers_found:
                    output += f" | Tickers: {', '.join(set(tickers_found))}"
                output += f"\n   {url}\n\n"

            # Add trending tickers summary
            if ticker_counts:
                sorted_tickers = sorted(ticker_counts.items(), key=lambda x: x[1], reverse=True)[:5]
                trending = ", ".join([f"${t[0]} ({t[1]})" for t in sorted_tickers])
                output = output.replace("**🚀 r/wallstreetbets - Hot Posts**\n\n",
                                       f"**🚀 r/wallstreetbets - Hot Posts**\n\n**Trending Tickers:** {trending}\n\n")

            return output

        except requests.exceptions.Timeout:
            return "Reddit request timed out. Try again."
        except Exception as e:
            logger.error(f"WSB error: {e}")
            return f"Error fetching WSB data: {str(e)}"
