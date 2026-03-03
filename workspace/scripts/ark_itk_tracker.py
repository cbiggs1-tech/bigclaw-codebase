#!/usr/bin/env python3
"""
ARK Invest ITK with Cathie Wood — Friday Transcript Summarizer

Searches YouTube for the latest "ITK with Cathie Wood" video,
fetches the transcript, and produces a markdown summary with
key themes and portfolio-relevant ticker mentions.
"""

import re
import sys
import json
import requests
from datetime import datetime, timedelta
from youtube_transcript_api import YouTubeTranscriptApi

# --- Config ---
WATCHLIST = ["NVDA", "TSLA", "PLTR", "CRSP", "ARKK", "RBLX", "QBTS",
             "COIN", "ROKU", "SQ", "HOOD", "PATH", "DKNG", "TWLO"]
ARK_CHANNEL_ID = "UCKTunqv-V_jXQCInY-iCIkQ"  # ARK Invest YouTube
SEARCH_QUERY = "ITK Cathie Wood"
MAX_RESULTS = 5

# Themed keyword groups for extraction
THEME_KEYWORDS = {
    "Macro / Economy": [
        "inflation", "deflation", "gdp", "recession", "employment", "jobs",
        "payroll", "consumer", "sentiment", "fed", "interest rate", "yield",
        "treasury", "saving rate", "delinquency", "housing", "mortgage",
        "cpi", "pce", "wage", "unemployment", "fiscal", "tariff", "tax"
    ],
    "AI / Technology": [
        "artificial intelligence", "ai ", "machine learning", "autonomous",
        "robotics", "software", "saas", "platform", "cloud", "gpu", "chip",
        "semiconductor", "quantum", "agentic", "llm", "transformer"
    ],
    "Crypto / Digital Assets": [
        "bitcoin", "btc", "ethereum", "crypto", "blockchain", "defi",
        "digital asset", "stablecoin", "layer zero", "solana"
    ],
    "Genomics / Health": [
        "crispr", "genomic", "gene edit", "multiomics", "sequencing",
        "biotech", "therapy", "drug", "fda", "clinical trial"
    ],
    "Energy / Mobility": [
        "ev ", "electric vehicle", "battery", "solar", "energy storage",
        "autonomous driving", "robotaxi", "ride-hail"
    ],
    "Market Positioning": [
        "conviction", "buying", "selling", "accumulating", "trimming",
        "volatility", "correction", "selloff", "opportunity", "valuation",
        "bubble", "wall of worry", "risk-off", "risk-on"
    ],
}


def search_youtube_itk(api_key=None):
    """Search for latest ITK video. Uses scraping if no API key."""
    # Try YouTube Data API first
    if api_key:
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "part": "snippet",
            "channelId": ARK_CHANNEL_ID,
            "q": SEARCH_QUERY,
            "order": "date",
            "maxResults": MAX_RESULTS,
            "type": "video",
            "key": api_key,
        }
        resp = requests.get(url, params=params, timeout=15)
        if resp.ok:
            items = resp.json().get("items", [])
            for item in items:
                title = item["snippet"]["title"]
                if "itk" in title.lower() or "in the know" in title.lower():
                    vid_id = item["id"]["videoId"]
                    pub = item["snippet"]["publishedAt"][:10]
                    return vid_id, title, pub
            # Fall back to first result
            if items:
                item = items[0]
                return item["id"]["videoId"], item["snippet"]["title"], item["snippet"]["publishedAt"][:10]

    # Fallback: scrape YouTube search results
    print("No YouTube API key — using search scrape fallback...")
    search_url = "https://www.youtube.com/results"
    params = {"search_query": f"ARK Invest ITK Cathie Wood", "sp": "CAI%253D"}  # sort by date
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36"}
    resp = requests.get(search_url, params=params, headers=headers, timeout=15)

    # Extract video IDs from the page
    video_ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', resp.text)
    titles = re.findall(r'"title":\{"runs":\[\{"text":"(.*?)"\}', resp.text)

    seen = set()
    results = []
    for vid, title in zip(video_ids, titles):
        if vid not in seen:
            seen.add(vid)
            results.append((vid, title))
        if len(results) >= 10:
            break

    for vid, title in results:
        tl = title.lower()
        if "itk" in tl or "in the know" in tl or "cathie" in tl:
            return vid, title, "unknown"

    if results:
        return results[0][0], results[0][1], "unknown"

    return None, None, None


def get_transcript(video_id):
    """Fetch transcript for a YouTube video."""
    ytt_api = YouTubeTranscriptApi()
    transcript = ytt_api.fetch(video_id)
    # Combine all snippets
    full_text = " ".join(snippet.text for snippet in transcript)
    return full_text


def extract_themes(text):
    """Extract themed sections based on keyword density."""
    text_lower = text.lower()
    sentences = re.split(r'(?<=[.!?])\s+', text)
    theme_excerpts = {}

    for theme, keywords in THEME_KEYWORDS.items():
        relevant = []
        for sentence in sentences:
            sl = sentence.lower()
            if any(kw in sl for kw in keywords):
                clean = sentence.strip()
                if len(clean) > 30 and clean not in relevant:
                    relevant.append(clean)
        if relevant:
            theme_excerpts[theme] = relevant[:8]  # top 8 per theme

    return theme_excerpts


def find_ticker_mentions(text):
    """Find mentions of watchlist tickers."""
    mentions = {}
    text_upper = text.upper()
    # Also check common name mappings
    name_map = {
        "NVIDIA": "NVDA", "TESLA": "TSLA", "PALANTIR": "PLTR",
        "CRISPR": "CRSP", "ROBLOX": "RBLX", "COINBASE": "COIN",
        "ROKU": "ROKU", "BLOCK": "SQ", "ROBINHOOD": "HOOD",
        "DRAFTKINGS": "DKNG", "TWILIO": "TWLO", "QUANTUM": "QBTS",
    }

    for ticker in WATCHLIST:
        # Check direct ticker mention
        pattern = r'\b' + ticker + r'\b'
        count = len(re.findall(pattern, text_upper))
        if count:
            mentions[ticker] = count

    for name, ticker in name_map.items():
        if ticker in WATCHLIST:
            pattern = r'\b' + name + r'\b'
            count = len(re.findall(pattern, text_upper))
            if count:
                mentions[ticker] = mentions.get(ticker, 0) + count

    return mentions


def generate_summary(video_id, title, pub_date, transcript, themes, ticker_mentions):
    """Generate markdown summary."""
    lines = []
    lines.append(f"# 📺 ARK ITK Summary — {title}")
    lines.append(f"**Video:** https://youtu.be/{video_id}")
    lines.append(f"**Published:** {pub_date}")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    # Ticker alerts
    if ticker_mentions:
        lines.append("## 🚨 Portfolio Ticker Mentions")
        for ticker, count in sorted(ticker_mentions.items(), key=lambda x: -x[1]):
            lines.append(f"- **{ticker}** — mentioned {count}x")
        lines.append("")

    # Themes
    if themes:
        lines.append("## 📊 Key Themes")
        for theme, excerpts in themes.items():
            lines.append(f"\n### {theme}")
            for ex in excerpts[:5]:
                # Truncate long excerpts
                if len(ex) > 200:
                    ex = ex[:200] + "..."
                lines.append(f"- {ex}")
        lines.append("")

    # Stats
    word_count = len(transcript.split())
    lines.append("## 📈 Transcript Stats")
    lines.append(f"- **Word count:** {word_count:,}")
    lines.append(f"- **Themes detected:** {len(themes)}")
    lines.append(f"- **Portfolio tickers mentioned:** {len(ticker_mentions)}")
    lines.append("")

    return "\n".join(lines)


def main():
    import os

    # Try to load YouTube API key
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        secrets_file = os.path.expanduser("~/.env_secrets")
        if os.path.exists(secrets_file):
            with open(secrets_file) as f:
                for line in f:
                    if line.startswith("export YOUTUBE_API_KEY="):
                        api_key = line.split("=", 1)[1].strip().strip('"').strip("'")

    print("🔍 Searching for latest ITK video...")
    video_id, title, pub_date = search_youtube_itk(api_key)

    if not video_id:
        print("❌ Could not find an ITK video")
        sys.exit(1)

    print(f"📺 Found: {title} ({video_id})")

    print("📝 Fetching transcript...")
    try:
        transcript = get_transcript(video_id)
    except Exception as e:
        print(f"❌ Transcript unavailable: {e}")
        sys.exit(1)

    print("🔬 Analyzing themes...")
    themes = extract_themes(transcript)

    print("🎯 Checking ticker mentions...")
    ticker_mentions = find_ticker_mentions(transcript)

    summary = generate_summary(video_id, title, pub_date, transcript, themes, ticker_mentions)
    print("\n" + summary)

    # Save to file
    output_dir = os.path.expanduser("~/.openclaw/workspace/research")
    os.makedirs(output_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_path = os.path.join(output_dir, f"ark-itk-{date_str}.md")
    with open(output_path, "w") as f:
        f.write(summary)
    print(f"\n💾 Saved to {output_path}")

    return summary


if __name__ == "__main__":
    main()
