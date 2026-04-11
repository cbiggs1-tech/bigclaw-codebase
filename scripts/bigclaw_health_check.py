#!/usr/bin/env python3
"""BigClaw Health Check — Run after OpenClaw updates or any system changes.

Tests all critical scripts for syntax errors, imports, and basic functionality.
Also checks for uncommitted drift in the scripts directory.

Usage:
    python3 bigclaw_health_check.py          # Run all checks
    python3 bigclaw_health_check.py --quick   # Syntax only
"""

import subprocess
import sys
import os
from pathlib import Path

SCRIPTS_DIR = Path.home() / ".openclaw" / "workspace" / "scripts"
WORKSPACE = Path.home() / ".openclaw" / "workspace"
DB_PATH = Path.home() / "bigclaw-ai" / "src" / "portfolios.db"

CRITICAL_SCRIPTS = [
    "autonomous_trader.py",
    "decision_engine.py",
    "stop_check.py",
    "trailing_stop_manager.py",
    "price_refresh.py",
    "morning_data_gather.py",
    "afternoon_data_gather.py",
    "export_signals.py",
    "style_compliance.py",
    "candidate_screener.py",
    "trade_executor.py",
    "market_monitor.py",
    "portfolio_analyzer.py",
    "options_intelligence.py",
]

passed = 0
failed = 0
warnings = 0


def check(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name} -- {detail}")


def warn(name, detail=""):
    global warnings
    warnings += 1
    print(f"  WARN  {name} -- {detail}")


def main():
    quick = "--quick" in sys.argv
    print("=" * 60)
    print("BigClaw Health Check")
    print("=" * 60)

    # 1. Syntax check all critical scripts
    print("\n--- Syntax Check ---")
    for script in CRITICAL_SCRIPTS:
        path = SCRIPTS_DIR / script
        if not path.exists():
            check(script, False, "FILE MISSING")
            continue
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(path)],
            capture_output=True, text=True
        )
        check(script, result.returncode == 0,
              result.stderr.strip()[:100] if result.returncode != 0 else "")

    # 2. Check for git drift
    print("\n--- Git Drift Check ---")
    result = subprocess.run(
        ["git", "-C", str(WORKSPACE), "diff", "--name-only", "HEAD", "--", "scripts/"],
        capture_output=True, text=True
    )
    changed = [f for f in result.stdout.strip().split("\n") if f]
    if changed:
        for f in changed:
            warn(f"Modified since last commit: {f}")
    else:
        print("  PASS  No uncommitted script changes")

    # Check untracked
    result = subprocess.run(
        ["git", "-C", str(WORKSPACE), "ls-files", "--others", "--exclude-standard", "scripts/"],
        capture_output=True, text=True
    )
    untracked = [f for f in result.stdout.strip().split("\n") if f and not "__pycache__" in f]
    if untracked:
        for f in untracked:
            warn(f"Untracked file: {f}")

    if quick:
        print(f"\n{'=' * 60}")
        print(f"Quick check: {passed} passed, {failed} failed, {warnings} warnings")
        print(f"{'=' * 60}")
        sys.exit(1 if failed > 0 else 0)

    # 3. Check database
    print("\n--- Database Check ---")
    try:
        import sqlite3
        conn = sqlite3.connect(str(DB_PATH), timeout=5)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        check("DB accessible", True)
        check("WAL mode active", mode == "wal", f"got: {mode}")
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        check("Tables exist", len(tables) >= 6, f"found: {len(tables)}")
        holdings = conn.execute("SELECT COUNT(*) FROM holdings WHERE shares > 0").fetchone()[0]
        check(f"Holdings populated ({holdings} active)", holdings > 0)
        conn.close()
    except Exception as e:
        check("Database", False, str(e)[:80])

    # 4. Check critical data files
    print("\n--- Data Files ---")
    morning_data = Path("/tmp/bigclaw_morning_data.txt")
    if morning_data.exists():
        age_hours = (os.path.getmtime(str(morning_data)) - os.time()) if hasattr(os, 'time') else 0
        import time
        age_hours = (time.time() - os.path.getmtime(str(morning_data))) / 3600
        if age_hours > 24:
            warn(f"morning_data.txt is {age_hours:.0f} hours old")
        else:
            check(f"morning_data.txt fresh ({age_hours:.1f}h old)", True)
    else:
        warn("morning_data.txt missing")

    afternoon_data = Path("/tmp/bigclaw_afternoon_data.txt")
    if afternoon_data.exists():
        import time
        age_hours = (time.time() - os.path.getmtime(str(afternoon_data))) / 3600
        if age_hours > 24:
            warn(f"afternoon_data.txt is {age_hours:.0f} hours old")
        else:
            check(f"afternoon_data.txt fresh ({age_hours:.1f}h old)", True)
    else:
        warn("afternoon_data.txt missing")

    # 5. Check OpenClaw cron jobs
    print("\n--- Cron Job Health ---")
    try:
        import json
        cron_path = Path.home() / ".openclaw" / "cron" / "jobs.json"
        data = json.load(open(cron_path))
        error_jobs = []
        for job in data["jobs"]:
            if not job.get("enabled", False):
                continue
            state = job.get("state", {})
            errs = state.get("consecutiveErrors", 0)
            name = job.get("name", "?")
            if errs > 0:
                error_jobs.append(f"{name} ({errs} consecutive errors)")
        if error_jobs:
            for ej in error_jobs:
                warn(f"Cron errors: {ej}")
        else:
            check("All cron jobs healthy", True)
    except Exception as e:
        check("Cron jobs", False, str(e)[:80])

    # 6. Check Slack connectivity
    print("\n--- Slack Connectivity ---")
    try:
        import json
        import urllib.request
        secrets = {}
        for line in open(os.path.expanduser("~/.env_secrets")).readlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[7:]
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                secrets[k.strip()] = v.strip().strip('"')
        token = secrets.get("SLACK_BOT_TOKEN", "")
        req = urllib.request.Request(
            "https://slack.com/api/auth.test",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
        check("Slack API", resp.get("ok", False), resp.get("error", ""))
    except Exception as e:
        check("Slack API", False, str(e)[:80])

    # 7. Check Alpaca connectivity
    print("\n--- Alpaca Connectivity ---")
    try:
        from alpaca.trading.client import TradingClient
        secrets_path = Path.home() / ".env_secrets"
        secrets = {}
        for line in secrets_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[7:]
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                secrets[k.strip()] = v.strip().strip('"')
        client = TradingClient(secrets["ALPACA_API_KEY"], secrets["ALPACA_SECRET_KEY"], paper=True)
        acct = client.get_account()
        check(f"Alpaca API (equity: ${float(acct.equity):,.0f})", True)
    except Exception as e:
        check("Alpaca API", False, str(e)[:80])

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed, {warnings} warnings")
    if failed > 0:
        print("ACTION REQUIRED: Fix failures before next trading session")
    elif warnings > 0:
        print("Review warnings — may indicate drift or stale data")
    else:
        print("All clear")
    print(f"{'=' * 60}")
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
