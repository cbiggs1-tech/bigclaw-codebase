#!/usr/bin/env python3
"""Morning Market Analysis - native BigClaw Python briefing.

Replaces OpenClaw's MMA job. Reads pre-gathered market data, calls Claude directly,
posts to Slack via slack_sdk. No third-party framework, no silent fallbacks.

Usage:
    morning_briefing.py                          # production: post to D0ADHLUJ400
    morning_briefing.py --dry-run                # stdout only, no Slack
    morning_briefing.py --channel CXXX           # override target channel
    morning_briefing.py --test-prefix            # prefix message with [TEST]
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from slack_sdk import WebClient

DATA_FILE = Path("/tmp/bigclaw_morning_data.txt")
DEFAULT_CHANNEL = "D0ADHLUJ400"
MODEL = "claude-opus-4-6"
MAX_TOKENS = 4000
LLM_TIMEOUT_SECONDS = 120.0
STALE_DATA_HOURS = 2
LOCK_FILE = Path("/tmp/morning_briefing.lock")
FAILURE_FLAG = Path.home() / "bigclaw-ai" / "logs" / "BRIEFING_FAILED.flag"
LLM_LOG = Path.home() / "bigclaw-ai" / "logs" / "llm_calls.jsonl"

PROMPT = """You are writing a morning MARKET briefing for Curtis. Today is {today}.
Below is pre-gathered market data collected by an automated script. Write a concise,
actionable briefing based ONLY on this data.

CRITICAL RULES:
- Every price, yield, percentage, and financial number in your output MUST appear
  verbatim in the data below.
- If something is not in the data, say "data unavailable" - do NOT guess, estimate,
  or use training data.
- Do NOT embellish numbers to fit a narrative. Report exactly what the data shows.

FOCUS ON:
- Portfolio snapshot (values, returns, top movers, laggards)
- Macro snapshot: oil, gold, yields, dollar, crypto - numbers from data ONLY.
  When present, call out the REGIME tells: VIX level (calm vs fear), HY-vs-IG
  credit (risk-on vs stress), and rate direction.
- Decision-engine intent (from the DECISION ENGINE section): today's PLANNED
  buys/sells, the top-scored candidates, and what executed this week.
- IV signal (from the IV SIGNAL section): the forward options read (skew/spread)
  that replaced UW. Note the overall bullish/bearish tilt and which HOLDINGS the
  options market is positioned for or against.
- Polymarket: ONLY macro / geopolitical / markets-relevant markets (wars, rates,
  the Fed, elections, the dollar). SKIP consumer / entertainment / crypto-meme
  noise entirely - do not include a market just because it exists.
- Any trade recommendations or watches

DO NOT INCLUDE: weather, calendar, email (those go in the Good Morning message).

Format for Slack: use *bold* for section headers, simple bullet lists, emoji
sparingly for emphasis. Keep it scannable - a busy operator should absorb the
headline picture in 30 seconds.

Include this disclaimer at the end:
_Paper trading only. Not investment advice._

=====================  MARKET DATA  =====================
{data}
=====================  END DATA  ========================
"""


def log(msg, level="INFO"):
    ts = datetime.now(timezone.utc).isoformat()
    print(f"[{ts}] {level} {msg}", file=sys.stderr)


def write_failure_flag(reason):
    try:
        FAILURE_FLAG.parent.mkdir(parents=True, exist_ok=True)
        FAILURE_FLAG.write_text(
            f"{datetime.now(timezone.utc).isoformat()}  {reason}\n"
        )
        log(f"Wrote failure flag: {FAILURE_FLAG}", "WARN")
    except Exception as e:
        log(f"Could not write failure flag: {e}", "ERROR")


def acquire_lock():
    """PID-based lockfile. Reclaim if holder is dead."""
    if LOCK_FILE.exists():
        try:
            old_pid = int(LOCK_FILE.read_text().strip())
            os.kill(old_pid, 0)
            log(f"Lock held by live PID {old_pid}; skipping run", "INFO")
            return False
        except (ValueError, ProcessLookupError, PermissionError):
            log("Stale lock from dead PID; reclaiming", "WARN")
    LOCK_FILE.write_text(str(os.getpid()))
    return True


def release_lock():
    try:
        LOCK_FILE.unlink()
    except FileNotFoundError:
        pass


def read_data_file():
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Data file missing: {DATA_FILE}")
    mtime = datetime.fromtimestamp(DATA_FILE.stat().st_mtime, tz=timezone.utc)
    age_hours = (datetime.now(timezone.utc) - mtime).total_seconds() / 3600
    stale = age_hours > STALE_DATA_HOURS
    data = DATA_FILE.read_text()
    if not data.strip():
        raise ValueError(f"Data file empty: {DATA_FILE}")
    return data, age_hours, stale


def log_llm_call(prompt_tokens, completion_tokens, cost, duration_s):
    try:
        LLM_LOG.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "script": "morning_briefing",
            "model": MODEL,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "duration_s": round(duration_s, 2),
            "est_cost_usd": round(cost, 6),
        }
        with LLM_LOG.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        log(f"Could not log LLM call: {e}", "WARN")


def call_llm(data_text):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not in environment")
    client = anthropic.Anthropic(api_key=api_key, timeout=LLM_TIMEOUT_SECONDS)
    today = datetime.now().strftime("%A, %B %d, %Y")
    prompt = PROMPT.format(data=data_text, today=today)
    start = time.time()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    duration = time.time() - start
    if not resp.content or not resp.content[0].text:
        raise RuntimeError("LLM returned empty content")
    text = resp.content[0].text
    cost = (resp.usage.input_tokens / 1_000_000) * 15 + (
        resp.usage.output_tokens / 1_000_000
    ) * 75
    log_llm_call(
        resp.usage.input_tokens, resp.usage.output_tokens, cost, duration
    )
    log(
        f"LLM ok: in={resp.usage.input_tokens} out={resp.usage.output_tokens} "
        f"cost=${cost:.4f} t={duration:.1f}s"
    )
    return text


def post_slack(channel, text):
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        raise RuntimeError("SLACK_BOT_TOKEN not in environment")
    client = WebClient(token=token)
    if len(text) > 39000:
        text = text[:38900] + "\n\n_[truncated - output exceeded 39K chars]_"
    resp = client.chat_postMessage(channel=channel, text=text, mrkdwn=True)
    if not resp["ok"]:
        raise RuntimeError(f"Slack post failed: {resp}")
    log(f"Posted to Slack channel={channel} ts={resp['ts']}")
    return resp["ts"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print to stdout, don't post")
    parser.add_argument("--channel", default=DEFAULT_CHANNEL, help="Target Slack channel/DM")
    parser.add_argument("--test-prefix", action="store_true", help="Prefix briefing with [TEST]")
    args = parser.parse_args()

    if not acquire_lock():
        return 0

    try:
        data, age_hours, stale = read_data_file()
        log(f"Data file age: {age_hours:.1f}h (stale={stale})")

        briefing = call_llm(data)

        if stale:
            briefing = (
                f"*[STALE DATA - source file is {age_hours:.1f}h old]*\n\n"
                + briefing
            )
        if args.test_prefix:
            briefing = "*[TEST - new BigClaw-native briefing, validating migration]*\n\n" + briefing

        if args.dry_run:
            print("=" * 72)
            print(briefing)
            print("=" * 72)
            log("Dry-run complete; no Slack post")
            return 0

        post_slack(args.channel, briefing)
        if FAILURE_FLAG.exists():
            FAILURE_FLAG.unlink()
        log("Morning briefing delivered successfully")
        return 0

    except Exception as e:
        log(f"FAILURE: {type(e).__name__}: {e}", "ERROR")
        write_failure_flag(f"{type(e).__name__}: {e}")
        return 1
    finally:
        release_lock()


if __name__ == "__main__":
    sys.exit(main())
