#!/usr/bin/env python3
"""Morning Briefing Gather — collects all data for the Good Morning message.

Runs at 6:50 AM CT via crontab, before the 7:00 AM Good Morning cron.
Output: /tmp/bigclaw_morning_briefing.txt

The Good Morning OpenClaw cron reads this file and posts to Slack.
No exec commands needed in the cron context — everything is pre-gathered.
"""

import os
import subprocess
import socket
from datetime import datetime
from pathlib import Path

SCRIPTS_DIR = Path.home() / ".openclaw" / "workspace" / "scripts"
ENV_SECRETS = Path.home() / ".env_secrets"
OUTPUT_FILE = "/tmp/bigclaw_morning_briefing.txt"


def source_env():
    """Load environment variables from .env_secrets."""
    if ENV_SECRETS.exists():
        for line in ENV_SECRETS.read_text().splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[7:]
            if "=" in line and not line.startswith("#"):
                key, _, val = line.partition("=")
                os.environ[key.strip()] = val.strip().strip("'\"")


def run_cmd(cmd, timeout=30, label="command"):
    """Run a shell command and return output."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip() or result.stderr.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"(timed out after {timeout}s)"
    except Exception as e:
        return f"(error: {e})"


def run_script(script_args, timeout=30, label="script"):
    """Run a Python script and return output."""
    try:
        result = subprocess.run(
            script_args, capture_output=True, text=True, timeout=timeout,
            env=os.environ, cwd=str(SCRIPTS_DIR)
        )
        return result.stdout.strip() or result.stderr.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"(timed out after {timeout}s)"
    except Exception as e:
        return f"(error: {e})"


def main():
    source_env()

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sections = []
    sections.append(f"BIGCLAW MORNING BRIEFING — {ts}")
    sections.append("=" * 60)

    # ── WEATHER ──
    sections.append("\n=== WEATHER (Alvarado, TX) ===")
    weather = run_script(
        ["python3", str(SCRIPTS_DIR / "weather.py")],
        timeout=15, label="weather"
    )
    sections.append(weather)

    # ── CALENDAR ──
    sections.append("\n=== CALENDAR (Today + Tomorrow) ===")
    calendar = run_script(
        ["python3", str(SCRIPTS_DIR / "calendar_check.py"), "--days", "2"],
        timeout=15, label="calendar"
    )
    sections.append(calendar)

    # ── GMAIL ──
    sections.append("\n=== GMAIL ===")
    gmail = run_script(
        ["python3", str(SCRIPTS_DIR / "gmail_check.py")],
        timeout=20, label="gmail"
    )
    sections.append(gmail)

    # ── FIXIT EMAIL ──
    sections.append("\n=== fixit@grandpapa.net ===")
    fixit = run_cmd(
        "himalaya envelope list -a fixit 2>/dev/null | head -20",
        timeout=15, label="fixit"
    )
    sections.append(fixit)

    # ── SECURITY ──
    sections.append("\n=== SECURITY AUDIT ===")

    # Disk
    disk = run_cmd("df -h / | tail -1", timeout=5, label="disk")
    sections.append(f"Disk: {disk}")

    # Memory
    mem = run_cmd("free -h | grep Mem", timeout=5, label="memory")
    sections.append(f"Memory: {mem}")

    # Temperature
    temp = run_cmd("vcgencmd measure_temp 2>/dev/null || echo 'temp unavailable'", timeout=5, label="temp")
    sections.append(f"Temperature: {temp}")

    # Uptime
    uptime = run_cmd("uptime", timeout=5, label="uptime")
    sections.append(f"Uptime: {uptime}")

    # Firewall
    ufw = run_cmd("sudo ufw status 2>/dev/null | head -5", timeout=10, label="ufw")
    sections.append(f"Firewall: {ufw}")

    # Fail2ban
    f2b = run_cmd("sudo fail2ban-client status sshd 2>/dev/null | grep -E 'banned|Total'", timeout=10, label="fail2ban")
    sections.append(f"Fail2ban: {f2b}")

    # Listening ports
    ports = run_cmd("ss -ltnp 2>/dev/null | grep LISTEN | head -10", timeout=5, label="ports")
    sections.append(f"Listening ports:\n{ports}")

    # ── CAMERA ──
    sections.append("\n=== CAMERA ===")
    cam = run_cmd(
        "ffmpeg -f v4l2 -i /dev/video0 -frames:v 1 -update 1 -y /tmp/morning_snap.jpg 2>&1 | tail -3",
        timeout=10, label="camera"
    )
    if os.path.exists("/tmp/morning_snap.jpg"):
        snap_size = os.path.getsize("/tmp/morning_snap.jpg")
        sections.append(f"Snapshot captured: /tmp/morning_snap.jpg ({snap_size:,} bytes)")
    else:
        sections.append("Camera offline or unavailable")

    # ── DATA HEALTH ──
    sections.append('')
    try:
        from data_health_check import run_health_check, format_report
        issues = run_health_check()
        sections.append(format_report(issues))
    except Exception as e:
        sections.append(f'=== DATA HEALTH === Error: {e}')

    # ── WRITE OUTPUT ──
    content = "\n".join(sections)
    with open(OUTPUT_FILE, "w") as f:
        f.write(content)

    print(f"Morning briefing gathered: {len(sections)} sections, {len(content)} bytes")
    print(f"Written to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
