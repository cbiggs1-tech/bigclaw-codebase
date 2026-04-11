#!/usr/bin/env bash
# refresh_all.sh — 5x daily refresh: signals + prices + charts
# Chains: decision engine signals → macro → price refresh → chart export → git push
# Alerts Slack on any failure

source ~/.env_secrets
cd /home/cbiggs90/.openclaw/workspace/scripts

LOGFILE="/home/cbiggs90/bigclaw-ai/logs/refresh_all.log"
TS() { date '+%Y-%m-%d %H:%M:%S'; }
FAILED=0

echo "[$(TS)] === Refresh started ===" >> "$LOGFILE"

# Step 1: Regenerate signals + macro from decision engine
echo "[$(TS)] Running export_signals..." >> "$LOGFILE"
if python3 export_signals.py >> "$LOGFILE" 2>&1; then
    echo "[$(TS)] Signals: OK" >> "$LOGFILE"
else
    echo "[$(TS)] Signals: FAILED" >> "$LOGFILE"
    FAILED=1
fi

# Step 2: Refresh prices and push
echo "[$(TS)] Running price_refresh..." >> "$LOGFILE"
if python3 price_refresh.py >> "$LOGFILE" 2>&1; then
    echo "[$(TS)] Price refresh: OK" >> "$LOGFILE"
else
    echo "[$(TS)] Price refresh: FAILED" >> "$LOGFILE"
    FAILED=1
fi

# Step 3: Refresh per-ticker chart data (OHLCV, MACD, RSI)
echo "[$(TS)] Running export_charts..." >> "$LOGFILE"
cd /home/cbiggs90/bigclaw-ai/src
if python3 export_charts.py >> "$LOGFILE" 2>&1; then
    echo "[$(TS)] Charts: OK" >> "$LOGFILE"
else
    echo "[$(TS)] Charts: FAILED" >> "$LOGFILE"
    FAILED=1
fi
cd /home/cbiggs90/.openclaw/workspace/scripts


# Step 4: Save daily portfolio snapshots (for performance chart)
echo "[$(TS)] Saving daily snapshots..." >> "$LOGFILE"
cd /home/cbiggs90/.openclaw/workspace/scripts
if python3 -c "
from portfolio_report import save_snapshots
save_snapshots()
print('Snapshots saved')
" >> "$LOGFILE" 2>&1; then
    echo "[$(TS)] Snapshots: OK" >> "$LOGFILE"
else
    echo "[$(TS)] Snapshots: FAILED" >> "$LOGFILE"
    FAILED=1
fi

# Step 4b: Refresh options intelligence (Unusual Whales)
echo "[$(TS)] Running options intelligence..." >> "$LOGFILE"
cd /home/cbiggs90/.openclaw/workspace/scripts
if python3 options_intelligence.py >> "$LOGFILE" 2>&1; then
    echo "[$(TS)] Options intelligence: OK" >> "$LOGFILE"
else
    echo "[$(TS)] Options intelligence: FAILED (non-critical)" >> "$LOGFILE"
fi

# Step 5: Generate performance chart + export dashboard
echo "[$(TS)] Running dashboard export..." >> "$LOGFILE"
cd /home/cbiggs90/bigclaw-ai/src
if python3 -c "from export_dashboard import export_dashboard; export_dashboard()" >> "$LOGFILE" 2>&1; then
    echo "[$(TS)] Dashboard export: OK" >> "$LOGFILE"
else
    echo "[$(TS)] Dashboard export: FAILED" >> "$LOGFILE"
    FAILED=1
fi

# Step 6: Git push website data
echo "[$(TS)] Git push..." >> "$LOGFILE"
cd /home/cbiggs90/bigclaw-ai
git add docs/data/ >> "$LOGFILE" 2>&1
git commit -m "Scheduled dashboard update" >> "$LOGFILE" 2>&1 || true
git push >> "$LOGFILE" 2>&1 || true
echo "[$(TS)] Git push: done" >> "$LOGFILE"
cd /home/cbiggs90/.openclaw/workspace/scripts

# Step 7: Data health check
echo "[$(TS)] Running data health check..." >> "$LOGFILE"
cd /home/cbiggs90/.openclaw/workspace/scripts
python3 data_health_check.py >> "$LOGFILE" 2>&1

echo "[$(TS)] === Refresh complete (status=$FAILED) ===" >> "$LOGFILE"

# Alert Slack on any failure
if [ $FAILED -ne 0 ]; then
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
    msg = ':warning: *BigClaw Refresh Failed*\nSignals, prices, or charts did not complete successfully.\nCheck refresh_all.log on the Pi.'
    payload = json.dumps({'channel': 'D0ADHLUJ400', 'text': msg}).encode()
    req = urllib.request.Request(
        'https://slack.com/api/chat.postMessage',
        data=payload,
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
    )
    urllib.request.urlopen(req, timeout=10)
" 2>/dev/null || true
fi
