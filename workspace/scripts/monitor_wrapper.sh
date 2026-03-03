#!/usr/bin/env bash
# BigClaw Market Monitor Wrapper
# Runs market_monitor.py, captures alerts if any.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ALERTS_LOG="$HOME/.openclaw/workspace/logs/market_alerts.json"
WRAPPER_LOG="$HOME/.openclaw/workspace/logs/monitor_runs.log"

mkdir -p "$(dirname "$WRAPPER_LOG")"

OUTPUT=$(python3 "$SCRIPT_DIR/market_monitor.py" 2>>"$WRAPPER_LOG")

if [ -n "$OUTPUT" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ALERTS DETECTED" >> "$WRAPPER_LOG"
    echo "$OUTPUT"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] No alerts" >> "$WRAPPER_LOG"
fi
