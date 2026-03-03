# HEARTBEAT.md

## Market Hours Checks (9:30 AM - 4:00 PM ET, Mon-Fri)

Rotate through these every heartbeat (~30 min default poll):

1. **Sentiment Pulse:** Run `python3 ~/bigclaw-ai/src/sentiment.py TSLA NVDA PLTR AAPL MSFT` – compare to last (store in ~/bigclaw-ai/data/last_sentiment.json). Alert if any ticker shifts >10% in sentiment score.

2. **Portfolio Rule Check:** Run `python3 ~/bigclaw-ai/src/portfolio_report.py --check-rules` – flag if trailing stops hit or buy signals trigger. Propose actions per SOUL.md.

3. **X/News Scan:** Use web_search for "breaking news [ticker]" on top holdings – summarize if high-impact (e.g., earnings surprise, geopolitical hit).

4. **Global Headline Monitor:** Fetch major financial headlines using the finance-news skill (or web_search for "major market headlines last 24 hours"). Alert on high-impact items (geopolitical escalations, macro data, key earnings) with synthesis and portfolio implications.

- If nothing urgent: HEARTBEAT_OK
- If alert: Send concise Slack update with details + conviction.

Update ~/bigclaw-ai/data/heartbeat-state.json with timestamps/results to avoid spam.
