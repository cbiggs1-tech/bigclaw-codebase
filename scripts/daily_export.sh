#!/usr/bin/env bash
# daily_export.sh — Pre-market daily export for BigClaw website
# Generates: sector heatmap, calendar, trades, analysis, news, performance chart, charts
# Runs once daily before market open

source ~/.env_secrets
cd /home/cbiggs90/bigclaw-ai/src

LOGFILE="/home/cbiggs90/bigclaw-ai/logs/daily_export.log"
TS() { date '+%Y-%m-%d %H:%M:%S'; }

echo "[$(TS)] === Daily export started ===" >> "$LOGFILE"

if python3 export_dashboard.py >> "$LOGFILE" 2>&1; then
    echo "[$(TS)] Daily export: OK" >> "$LOGFILE"
else
    echo "[$(TS)] Daily export: FAILED" >> "$LOGFILE"
    # Alert Slack
    python3 -c "
import urllib.request, json, os
secrets = {}
with open(os.path.expanduser('~/.env_secrets')) as f:
    for line in f:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            line = line.removeprefix('export ')
            k, v = line.split('=', 1)
            secrets[k.strip()] = v.strip().strip('\"').strip(\"'\")
token = secrets.get('SLACK_BOT_TOKEN', '')
if token:
    msg = ':warning: *BigClaw Daily Export Failed*\nSector heatmap, calendar, trades, analysis may be stale.\nCheck daily_export.log on the Pi.'
    payload = json.dumps({'channel': 'D0ADHLUJ400', 'text': msg}).encode()
    req = urllib.request.Request(
        'https://slack.com/api/chat.postMessage',
        data=payload,
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
    )
    urllib.request.urlopen(req, timeout=10)
" 2>/dev/null || true
fi

echo "[$(TS)] === Daily export complete ===" >> "$LOGFILE"
