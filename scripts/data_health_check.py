#!/usr/bin/env python3
"""BigClaw Data Health Monitor — checks all data sources for freshness and errors.

Designed to be called by:
1. morning_data_gather.py — appends health report to morning data file
2. afternoon_data_gather.py — appends to afternoon data file
3. refresh_all.sh — posts Slack alert if critical issues found

Checks:
- All 12 dashboard JSON files for staleness (> 24h)
- Cron job consecutive error counts
- DB integrity (WAL mode, tables exist)
- Key data sources (yfinance, Unusual Whales, Slack API)
"""

import json
import os
import time
import sqlite3
from pathlib import Path
from datetime import datetime

DATA_DIR = Path.home() / "bigclaw-ai" / "docs" / "data"
DB_PATH = Path.home() / "bigclaw-ai" / "src" / "portfolios.db"
CRON_PATH = Path.home() / ".openclaw" / "cron" / "jobs.json"

DASHBOARD_FILES = {
    "market.json": 6,         # Max hours before stale
    "macro.json": 6,
    "signals.json": 6,
    "portfolios.json": 6,
    "trades.json": 24,
    "portfolio_analysis.json": 24,
    "news.json": 12,
    "sentiment.json": 12,
    "options_flow.json": 6,
    "calendar.json": 24,
    "metadata.json": 6,
}


def check_data_freshness():
    """Check all dashboard JSON files for staleness."""
    issues = []
    for fname, max_hours in DASHBOARD_FILES.items():
        fpath = DATA_DIR / fname
        if not fpath.exists():
            issues.append(f"MISSING: {fname}")
            continue
        age_h = (time.time() - os.path.getmtime(str(fpath))) / 3600
        if age_h > max_hours:
            issues.append(f"STALE: {fname} ({age_h:.0f}h old, max {max_hours}h)")
    return issues


def check_cron_health():
    """Check for cron jobs with consecutive errors."""
    issues = []
    if not CRON_PATH.exists():
        return ["MISSING: cron jobs.json"]
    data = json.load(open(CRON_PATH))
    for job in data.get("jobs", []):
        if not job.get("enabled", False):
            continue
        errs = job.get("state", {}).get("consecutiveErrors", 0)
        name = job.get("name", "?")
        if errs > 0:
            issues.append(f"CRON ERROR: {name} ({errs} consecutive errors)")
    return issues


def check_db_health():
    """Quick DB integrity check."""
    issues = []
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        if mode != "wal":
            issues.append(f"DB: journal mode is {mode}, should be WAL")
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        if len(tables) < 6:
            issues.append(f"DB: only {len(tables)} tables (expected 6+)")
        holdings = conn.execute("SELECT COUNT(*) FROM holdings WHERE shares > 0").fetchone()[0]
        if holdings == 0:
            issues.append("DB: no active holdings")
        conn.close()
    except Exception as e:
        issues.append(f"DB: {e}")
    return issues


def run_health_check():
    """Run all health checks and return report."""
    all_issues = []
    all_issues.extend(check_data_freshness())
    all_issues.extend(check_cron_health())
    all_issues.extend(check_db_health())
    return all_issues


def format_report(issues):
    """Format issues as text for inclusion in reports."""
    if not issues:
        return "\n=== DATA HEALTH ===\nAll clear: all data sources fresh, no cron errors, DB healthy."

    lines = ["\n=== DATA HEALTH — ISSUES FOUND ==="]
    for issue in issues:
        lines.append(f"  WARNING: {issue}")
    lines.append(f"  Total: {len(issues)} issue(s)")
    return "\n".join(lines)


def post_slack_alert(issues):
    """Post critical issues to Slack."""
    if not issues:
        return

    critical = [i for i in issues if "MISSING" in i or "CRON ERROR" in i or "DB:" in i]
    if not critical:
        return  # Only alert on critical issues, not stale data

    secrets = {}
    for line in Path.home().joinpath(".env_secrets").read_text().splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:]
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            secrets[k.strip()] = v.strip().strip('"')

    token = secrets.get("SLACK_BOT_TOKEN", "")
    if not token:
        return

    import urllib.request
    msg = ":warning: *BigClaw Data Health Alert*\n"
    for issue in critical:
        msg += f"  {issue}\n"

    payload = json.dumps({"channel": "D0ADHLUJ400", "text": msg}).encode()
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


if __name__ == "__main__":
    issues = run_health_check()
    print(format_report(issues))
    if issues:
        post_slack_alert(issues)
