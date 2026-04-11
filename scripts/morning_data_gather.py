#!/usr/bin/env python3
"""Morning Data Gather — collects ALL live data for the 9 AM analysis.

Runs at 8:55 AM ET, before the Morning Market Analysis cron.
Output: /tmp/bigclaw_morning_data.txt

The analysis LLM reads ONLY this file — no web search, no guessing.
"""

import os
import subprocess
from datetime import datetime
from bigclaw_logging import get_logger

log = get_logger("morning_gather")

OUTPUT_FILE = "/tmp/bigclaw_morning_data.txt"
SCRIPTS_DIR = os.path.expanduser("~/.openclaw/workspace/scripts")
ENV_SECRETS = os.path.expanduser("~/.env_secrets")


def source_env():
    if os.path.exists(ENV_SECRETS):
        with open(ENV_SECRETS) as f:
            for line in f:
                line = line.strip()
                if line.startswith('export '):
                    line = line[7:]
                if '=' in line and not line.startswith('#'):
                    key, _, val = line.partition('=')
                    val = val.strip('"').strip("'")
                    os.environ[key] = val


def run(label, cmd, timeout=60, retries=2):
    """Run a command, retrying on failure. Returns labeled output section."""
    for attempt in range(1, retries + 1):
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                timeout=timeout, cwd=SCRIPTS_DIR
            )
            output = result.stdout.strip()
            if result.returncode != 0 and result.stderr.strip():
                err_msg = result.stderr.strip()
                if attempt < retries:
                    log.warning(f"{label} failed (attempt {attempt}/{retries}): {err_msg}")
                    continue
                output += f"\nSTDERR: {err_msg}"
                log.error(f"{label} failed after {retries} attempts: {err_msg}")
            else:
                if attempt > 1:
                    log.info(f"{label} succeeded on attempt {attempt}")
            return f"=== {label} ===\n{output}\n=== END {label} ===\n"
        except subprocess.TimeoutExpired:
            if attempt < retries:
                log.warning(f"{label} timed out (attempt {attempt}/{retries}), retrying...")
                continue
            log.error(f"{label} timed out after {retries} attempts ({timeout}s each)")
            return f"=== {label} ===\nERROR: timed out after {timeout}s\n=== END {label} ===\n"
        except Exception as e:
            log.error(f"{label} exception: {e}", exc_info=True)
            return f"=== {label} ===\nERROR: {e}\n=== END {label} ===\n"
    return f"=== {label} ===\nERROR: all {retries} attempts failed\n=== END {label} ===\n"


def main():
    source_env()
    log.info("Starting morning data gather")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z")

    header = (
        f"BIGCLAW MORNING DATA GATHER — {timestamp}\n"
        f"{'=' * 60}\n"
        f"ALL numbers below are from LIVE data sources.\n"
        f"The analysis LLM must ONLY use numbers from this file.\n"
        f"Any number NOT in this file = 'data unavailable'.\n"
        f"{'=' * 60}\n"
    )

    sections = []

    # Personal
    sections.append(run("WEATHER", f"python3 {SCRIPTS_DIR}/weather.py"))
    sections.append(run("CALENDAR", f"python3 {SCRIPTS_DIR}/calendar_check.py --days 2"))
    sections.append(run("GMAIL", f"python3 {SCRIPTS_DIR}/gmail_check.py"))

    # Portfolio & prices
    sections.append(run("PORTFOLIO REPORT", f"python3 {SCRIPTS_DIR}/portfolio_report.py --report", timeout=90))
    sections.append(run("MACRO PRICES", f"python3 {SCRIPTS_DIR}/macro_prices.py", timeout=30))

    # Predictions
    sections.append(run("POLYMARKET", f"python3 {SCRIPTS_DIR}/polymarket.py --market-movers --limit 5"))

    # Smart money
    sections.append(run("OPTIONS FLOW ALERTS", f"python3 {SCRIPTS_DIR}/unusual_whales.py --flow-alerts"))
    sections.append(run("CONGRESSIONAL TRADES", f"python3 {SCRIPTS_DIR}/unusual_whales.py --congress"))
    sections.append(run("SPY GAMMA EXPOSURE (GEX)", f"python3 {SCRIPTS_DIR}/unusual_whales.py --gex --ticker SPY"))
    sections.append(run("MARKET TIDE", f"python3 {SCRIPTS_DIR}/unusual_whales.py --tide"))
    sections.append(run("INSIDER TRADES (SEC FORM 4)", f"python3 {SCRIPTS_DIR}/unusual_whales.py --insiders"))

    # Append options intelligence flat file if available (written by options_intelligence.py)
    options_intel_file = "/tmp/bigclaw_options_intel.txt"
    if os.path.exists(options_intel_file):
        try:
            with open(options_intel_file, "r") as oif:
                intel_data = oif.read().strip()
            if intel_data:
                sections.append("=== OPTIONS INTELLIGENCE ===\n" + intel_data)
        except Exception as e:
            sections.append("=== OPTIONS INTELLIGENCE ===\nERROR: Could not read " + str(options_intel_file) + ": " + str(e))

    # Count errors
    errors = sum(1 for s in sections if "ERROR:" in s)
    # Data health check
    try:
        from data_health_check import run_health_check, format_report
        issues = run_health_check()
        sections.append(format_report(issues))
    except Exception:
        pass

    content = header + "\n" + "\n".join(sections)
    with open(OUTPUT_FILE, 'w') as f:
        f.write(content)

    msg = f"Morning data gathered: {len(sections)} sections, {errors} errors, {len(content)} bytes"
    log.info(msg)
    print(msg)
    print(f"Written to: {OUTPUT_FILE}")


if __name__ == '__main__':
    main()
