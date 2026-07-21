#!/bin/bash
# Wait for market open, then flatten kill portfolios.
set -euo pipefail
export HOME=/home/cbiggs90
source /home/cbiggs90/.env_secrets
cd /home/cbiggs90/bigclaw-ai/scripts
LOG=/home/cbiggs90/bigclaw-ai/logs/four_sleeve_flatten.log
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) wait_and_flatten starting" | tee -a "$LOG"
/usr/bin/python3 flatten_kill_portfolios.py --wait-open --execute >> "$LOG" 2>&1
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) wait_and_flatten finished rc=$?" | tee -a "$LOG"
# Refresh dashboard JSON after deactivate
cd /home/cbiggs90/bigclaw-ai
source /home/cbiggs90/.env_secrets
/usr/bin/python3 scripts/price_refresh.py >> "$LOG" 2>&1 || true
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) price_refresh after flatten done" | tee -a "$LOG"
