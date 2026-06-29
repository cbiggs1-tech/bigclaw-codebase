#!/usr/bin/env python3
"""Post the weekly ARK ITK summary to Slack natively — replaces the flaky OpenClaw
agent-turn cron (which kept failing 'Message failed' on a weak model and added nothing,
since it was only asked to cat the file verbatim). The tracker (system cron) writes
/tmp/bigclaw_ark_itk.txt; this reads it, extracts the markdown summary, and posts it.
No LLM in the loop. Exit non-zero on failure so the cron/health check can see it.
"""
import os
import sys
from pathlib import Path

SRC = "/tmp/bigclaw_ark_itk.txt"
CHANNEL = "D0ADHLUJ400"


def extract_summary(text: str) -> str:
    lines = text.splitlines()
    # Start at the first markdown header (drops the tracker's progress prints).
    start = next((i for i, l in enumerate(lines) if l.lstrip().startswith("# ")), 0)
    body = [l for l in lines[start:] if not l.lstrip().startswith("\U0001F4BE")]  # drop the trailing "Saved to" line
    return "\n".join(body).strip().replace("\\u0026", "&")


def main() -> None:
    p = Path(SRC)
    if not p.exists() or p.stat().st_size == 0:
        print(f"ERROR: {SRC} missing or empty", file=sys.stderr)
        sys.exit(1)
    summary = extract_summary(p.read_text())
    if len(summary) < 50:
        print("ERROR: extracted ARK summary too short — tracker likely failed", file=sys.stderr)
        sys.exit(1)
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        print("ERROR: SLACK_BOT_TOKEN not in environment", file=sys.stderr)
        sys.exit(1)
    from slack_sdk import WebClient
    client = WebClient(token=token)
    for i in range(0, len(summary), 38000):  # Slack ~40k/msg cap; summary is small but be safe
        client.chat_postMessage(channel=CHANNEL, text=summary[i:i + 38000])
    print(f"ARK ITK summary posted to Slack ({len(summary)} chars)")


if __name__ == "__main__":
    main()
