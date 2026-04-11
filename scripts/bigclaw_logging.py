#!/usr/bin/env python3
"""Shared logging setup for BigClaw scripts.

Usage:
    from bigclaw_logging import get_logger
    log = get_logger("my_script")
    log.info("Started")
    log.error("Something broke", exc_info=True)

Logs to both stderr (for cron capture) and ~/bigclaw-ai/logs/bigclaw.log (persistent).
ERROR and CRITICAL messages are also sent to Slack DM via webhook.
"""

import json
import logging
import os
import urllib.request
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.expanduser("~/bigclaw-ai/logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "bigclaw.log")
MAX_BYTES = 5 * 1024 * 1024  # 5 MB
BACKUP_COUNT = 2  # keep 2 rotated copies

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
_SECRETS_LOADED = False


def _ensure_secrets():
    """Load ~/.env_secrets once if env vars aren't set."""
    global _SECRETS_LOADED, DISCORD_WEBHOOK_URL
    if _SECRETS_LOADED:
        return
    _SECRETS_LOADED = True
    if DISCORD_WEBHOOK_URL:
        return
    import re
    secrets_file = os.path.expanduser("~/.env_secrets")
    if not os.path.exists(secrets_file):
        return
    with open(secrets_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            line = re.sub(r"^export\s+", "", line)
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip("'\"")
            if k == "DISCORD_WEBHOOK_URL":
                DISCORD_WEBHOOK_URL = v
                break


class SlackAlertHandler(logging.Handler):
    """Send ERROR/CRITICAL log messages to Discord webhook."""

    def __init__(self):
        super().__init__(level=logging.ERROR)

    def emit(self, record):
        try:
            _ensure_secrets()
            if not DISCORD_WEBHOOK_URL:
                return
            msg = self.format(record)
            # Truncate to Discord's 2000 char limit
            if len(msg) > 1900:
                msg = msg[:1900] + "..."
            payload = json.dumps({"content": f"🚨 **BigClaw Alert**\n```\n{msg}\n```"})
            req = urllib.request.Request(
                DISCORD_WEBHOOK_URL,
                data=payload.encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass  # Never let alert delivery crash the actual script


def get_logger(name: str, level=logging.INFO) -> logging.Logger:
    """Return a logger that writes to ~/bigclaw-ai/logs/bigclaw.log, stderr, and Slack on errors."""
    logger = logging.getLogger(f"bigclaw.{name}")
    if logger.handlers:
        return logger  # already configured

    logger.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler — rotated
    fh = RotatingFileHandler(LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Stream handler — stderr for cron email / OpenClaw capture
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    # Alert handler — Discord webhook on ERROR/CRITICAL
    ah = SlackAlertHandler()
    ah.setFormatter(fmt)
    logger.addHandler(ah)

    return logger
