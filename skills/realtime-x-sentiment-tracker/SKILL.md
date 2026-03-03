---
name: realtime-x-sentiment-tracker
description: Real-time sentiment tracking on X (formerly Twitter) for specified stocks. Polls semantically or by keywords every 2 hours during market hours, integrates with sentiment.py for scoring, and triggers alerts on shifts greater than 5% or price thresholds. Use when needing intraday market vibe checks, sentiment-based alerts, or polling for high-vol tickers like TSLA, NVDA—perfect for proactive portfolio monitoring.
---

# Realtime X Sentiment Tracker

## Overview

This skill enables automated, real-time monitoring of X sentiment for key stocks. It polls X API for recent tweets, runs them through sentiment.py for scoring, compares to baselines, and alerts via Slack if thresholds are breached. Designed for 2-hour intervals in market hours (9:30 AM - 4:00 PM ET, Mon-Fri), with caching to minimize API calls.

## Quick Start

1. Configure tickers and thresholds in references/config.md.
2. Run the polling script: `python3 scripts/poll_x_sentiment.py --tickers TSLA,NVDA --interval 7200` (2 hours in seconds).
3. For alerts: Integrate with HEARTBEAT.md or cron—check sentiment shifts >5% or price moves ±3%.

## Core Workflow

- **Poll X:** Use X API (bearer token from ~/.env_secrets) to fetch recent tweets matching keywords/semantic queries for each ticker.
- **Score Sentiment:** Feed results into ~/bigclaw-ai/src/sentiment.py; store in JSON cache (e.g., ~/bigclaw-ai/data/last_sentiment.json).
- **Compare & Alert:** If shift >5% from last, or price threshold hit (via yfinance), send Slack message with details + conviction.
- **Cache:** Update timestamps in ~/bigclaw-ai/data/heartbeat-state.json to avoid redundant calls.

For custom polls: Override with --keywords "tesla fsd" or --semantic true.

## Resources

### scripts/
- poll_x_sentiment.py: Main script for polling, scoring, and alerting. Requires yfinance, requests, and sentiment.py.

### references/
- config.md: Default tickers (TSLA, NVDA, etc.), thresholds (>5% sentiment, ±3% price), and API endpoints.
