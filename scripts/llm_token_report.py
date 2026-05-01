"""Daily LLM token-usage aggregator.

Reads ~/bigclaw-ai/logs/llm_calls.jsonl, summarizes the previous day's
calls by script, posts a digest to Slack DM. Alerts loudly if any single
script exceeded 1M tokens/day or $5/day — those are signals a new heavy
consumer crept in.

Cron: 0 6 * * * (daily 6 AM CT)
"""
import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

LOG_PATH = Path.home() / "bigclaw-ai" / "logs" / "llm_calls.jsonl"
SLACK_CHANNEL = "D0ADHLUJ400"
TOKEN_ALERT_THRESHOLD = 1_000_000   # tokens per script per day
COST_ALERT_THRESHOLD = 5.0          # USD per script per day


def load_calls(date_str):
    """Yield call entries from log whose ts falls on date_str (YYYY-MM-DD)."""
    if not LOG_PATH.exists():
        return
    with LOG_PATH.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("ts", "")[:10] == date_str:
                    yield entry
            except Exception:
                continue


def aggregate(entries):
    """Group by script. Returns (per_script_summary, totals)."""
    by_script = defaultdict(lambda: {
        "calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0
    })
    for e in entries:
        s = by_script[e.get("script", "unknown")]
        s["calls"] += 1
        s["input_tokens"] += int(e.get("prompt_tokens", 0))
        s["output_tokens"] += int(e.get("completion_tokens", 0))
        s["cost_usd"] += float(e.get("est_cost_usd", 0))

    totals = {
        "calls": sum(s["calls"] for s in by_script.values()),
        "input_tokens": sum(s["input_tokens"] for s in by_script.values()),
        "output_tokens": sum(s["output_tokens"] for s in by_script.values()),
        "cost_usd": sum(s["cost_usd"] for s in by_script.values()),
    }
    return dict(by_script), totals


def find_alerts(per_script):
    """Return list of (script, reason) tuples for threshold violations."""
    alerts = []
    for name, s in per_script.items():
        total_tokens = s["input_tokens"] + s["output_tokens"]
        if total_tokens > TOKEN_ALERT_THRESHOLD:
            alerts.append((name, f"{total_tokens:,} tokens (>{TOKEN_ALERT_THRESHOLD:,})"))
        if s["cost_usd"] > COST_ALERT_THRESHOLD:
            alerts.append((name, f"${s['cost_usd']:.2f} (>${COST_ALERT_THRESHOLD:.2f})"))
    return alerts


def format_message(date_str, per_script, totals, alerts):
    """Build the Slack-bound text."""
    if not per_script:
        return None  # nothing to report; suppress

    lines = [f"*LLM Token Usage — {date_str}*"]
    if alerts:
        lines.append("\n:rotating_light: *Threshold violations:*")
        for name, reason in alerts:
            lines.append(f"  * `{name}`: {reason}")

    lines.append(f"\n*Totals:* {totals['calls']} calls, "
                 f"{totals['input_tokens']:,}+{totals['output_tokens']:,} tokens, "
                 f"${totals['cost_usd']:.4f}")

    lines.append("\n*By script:*")
    sorted_scripts = sorted(per_script.items(),
                            key=lambda x: x[1]["cost_usd"], reverse=True)
    for name, s in sorted_scripts:
        lines.append(
            f"  `{name}`: {s['calls']} calls, "
            f"{s['input_tokens']:,}+{s['output_tokens']:,} tokens, "
            f"${s['cost_usd']:.4f}"
        )
    return "\n".join(lines)


def post_slack(text):
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        print("SLACK_BOT_TOKEN not set; printing instead:")
        print(text)
        return
    payload = json.dumps({"channel": SLACK_CHANNEL, "text": text}).encode()
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"Slack post failed: {e}")


def main():
    # Default: report yesterday (run as 6 AM cron, summarize prior day)
    target_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    if len(sys.argv) > 1:
        target_date = sys.argv[1]  # allow manual date override

    entries = list(load_calls(target_date))
    per_script, totals = aggregate(entries)
    alerts = find_alerts(per_script)
    msg = format_message(target_date, per_script, totals, alerts)
    if msg is None:
        print(f"No LLM calls logged for {target_date}; nothing to report.")
        return
    print(msg)
    print()
    post_slack(msg)


if __name__ == "__main__":
    main()
