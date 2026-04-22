#!/usr/bin/env python3
"""Weekly Research Session - native BigClaw Python.

Replaces OpenClaw's Weekly Research Session. Reads the research rotation README
and existing files, asks Opus to research the next topic, writes a markdown
document to the research directory, posts a summary to Slack.

No pre-gathered data file - Opus synthesizes from training data. Web search
tool can be added later if current-events freshness becomes critical.

Usage:
    weekly_research.py                         # production
    weekly_research.py --dry-run               # stdout only, no file write, no Slack
    weekly_research.py --channel CXXX          # override target
    weekly_research.py --test-prefix           # prefix Slack summary with [TEST]
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from slack_sdk import WebClient

RESEARCH_DIR = Path.home() / ".openclaw" / "workspace" / "memory" / "research"
DEFAULT_CHANNEL = "D0ADHLUJ400"
MODEL = "claude-opus-4-6"
MAX_TOKENS = 8000
LLM_TIMEOUT_SECONDS = 300.0
LOCK_FILE = Path("/tmp/weekly_research.lock")
FAILURE_FLAG = Path.home() / "bigclaw-ai" / "logs" / "WEEKLY_RESEARCH_FAILED.flag"
LLM_LOG = Path.home() / "bigclaw-ai" / "logs" / "llm_calls.jsonl"

SYSTEM_PROMPT = """You are BigClaw's weekly research agent. Your mission is to research
and synthesize knowledge that helps Curtis Biggs understand the economic and
philosophical challenges coming from AI disruption, so he can prepare himself and
his family for the world ahead.

You write for an intelligent non-expert who wants to ACT on the information, not
just read it. Favor practical insight over academic depth. Ruthlessly synthesize.
Cut fluff. When you cite a claim, name the source."""

USER_PROMPT_TEMPLATE = """Here is the current research rotation and what has been covered:

# Rotation README
{readme}

# Existing research files
{file_listing}

Your task:
1. Pick the NEXT topic to research. If a topic is marked "planned" in the README,
   that is next. If all topics are complete, propose the next most valuable topic in
   the same spirit (AI disruption, economic resilience, philosophy of work, etc.) and
   note that you're extending the rotation.
2. Write a high-quality markdown document on that topic (target 1500-3000 words).
   Structure: intro, 3-5 substantive sections, practical implications, further reading.
   Cite sources inline as you make claims.
3. Produce a short Slack summary (under 2500 chars) with: the topic covered, the 3
   most important findings, and what should come next week.

Output your response as JSON between the markers <JSON> and </JSON>. The JSON must
have exactly these fields:

{{
  "topic_slug": "kebab-case-filename-without-extension",
  "topic_title": "Human-Readable Title",
  "markdown": "Full markdown document body (no frontmatter, just the content)",
  "slack_summary": "The summary to post, formatted for Slack (*bold*, bullets)"
}}

Put NOTHING outside the <JSON></JSON> markers."""


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


def collect_research_state():
    if not RESEARCH_DIR.exists():
        raise FileNotFoundError(f"Research dir missing: {RESEARCH_DIR}")
    readme_path = RESEARCH_DIR / "README.md"
    readme = readme_path.read_text() if readme_path.exists() else "(README.md missing)"
    files = sorted(p.name for p in RESEARCH_DIR.iterdir() if p.suffix == ".md")
    return readme, "\n".join(f"- {f}" for f in files)


def log_llm_call(prompt_tokens, completion_tokens, cost, duration_s):
    try:
        LLM_LOG.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "script": "weekly_research",
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


def call_llm(readme, file_listing):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not in environment")
    client = anthropic.Anthropic(api_key=api_key, timeout=LLM_TIMEOUT_SECONDS)
    user_prompt = USER_PROMPT_TEMPLATE.format(readme=readme, file_listing=file_listing)
    start = time.time()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
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


def parse_response(text):
    m = re.search(r"<JSON>(.*?)</JSON>", text, re.DOTALL)
    if not m:
        raise RuntimeError(f"No <JSON></JSON> markers in LLM output. First 500 chars: {text[:500]}")
    payload = m.group(1).strip()
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"JSON parse error: {e}. Payload start: {payload[:300]}")
    for required in ("topic_slug", "topic_title", "markdown", "slack_summary"):
        if required not in obj or not obj[required]:
            raise RuntimeError(f"Missing/empty field in response: {required}")
    slug = obj["topic_slug"].strip()
    if not re.match(r"^[a-z0-9-]+$", slug):
        raise RuntimeError(f"Invalid topic_slug (expected kebab-case): {slug!r}")
    return obj


def write_research_file(slug, title, markdown):
    target = RESEARCH_DIR / f"{slug}.md"
    frontmatter = (
        f"# {title}\n\n"
        f"_Researched: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}_\n\n"
    )
    # Overwrite if existing (rotation may redo a topic with updated info)
    target.write_text(frontmatter + markdown)
    log(f"Wrote research file: {target} ({len(markdown)} chars)")
    return target


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
    parser.add_argument("--dry-run", action="store_true", help="Print to stdout, no file write, no post")
    parser.add_argument("--channel", default=DEFAULT_CHANNEL, help="Target Slack channel/DM")
    parser.add_argument("--test-prefix", action="store_true", help="Prefix summary with [TEST]")
    args = parser.parse_args()

    if not acquire_lock():
        return 0

    try:
        readme, file_listing = collect_research_state()
        log(f"Research dir: {RESEARCH_DIR}, {file_listing.count(chr(10))+1} files")

        raw = call_llm(readme, file_listing)
        result = parse_response(raw)

        slug = result["topic_slug"]
        title = result["topic_title"]
        markdown = result["markdown"]
        summary = result["slack_summary"]

        log(f"Topic selected: {title} (slug={slug}, {len(markdown)} chars)")

        if args.test_prefix:
            summary = f"*[TEST - weekly research migration]*\n\n{summary}"

        if args.dry_run:
            print("=" * 72)
            print(f"TOPIC: {title}  ({slug}.md)")
            print("=" * 72)
            print(markdown[:2000])
            print("..." if len(markdown) > 2000 else "")
            print("=" * 72)
            print("SLACK SUMMARY:")
            print(summary)
            print("=" * 72)
            log("Dry-run complete; no file write, no Slack post")
            return 0

        write_research_file(slug, title, markdown)
        post_slack(args.channel, summary)
        if FAILURE_FLAG.exists():
            FAILURE_FLAG.unlink()
        log("Weekly research session delivered successfully")
        return 0

    except Exception as e:
        log(f"FAILURE: {type(e).__name__}: {e}", "ERROR")
        write_failure_flag(f"{type(e).__name__}: {e}")
        return 1
    finally:
        release_lock()


if __name__ == "__main__":
    sys.exit(main())
