#!/usr/bin/env bash
# openclaw_update_check.sh
# Weekly OpenClaw version check + auto-update
# Runs via cron, reports result to Slack DM

set -euo pipefail

SLACK_CHANNEL="D0ADHLUJ400"
CURRENT_VERSION=$(openclaw --version 2>/dev/null || echo "unknown")

# Check if update is available
STATUS_JSON=$(openclaw update status --json 2>/dev/null)
UPDATE_AVAILABLE=$(echo "$STATUS_JSON" | jq -r '.availability.available')
LATEST_VERSION=$(echo "$STATUS_JSON" | jq -r '.update.registry.latestVersion // .availability.latestVersion // "unknown"')

if [ "$UPDATE_AVAILABLE" = "true" ]; then
  echo "[openclaw-update] Update available: $CURRENT_VERSION → $LATEST_VERSION. Running update..."

  # Run the update (non-interactive, restarts gateway automatically)
  UPDATE_OUTPUT=$(openclaw update --yes 2>&1) || true
  NEW_VERSION=$(openclaw --version 2>/dev/null || echo "unknown")

  if [ "$NEW_VERSION" != "$CURRENT_VERSION" ]; then
    MSG="🦀 *OpenClaw Updated* ✅\n\`$CURRENT_VERSION\` → \`$NEW_VERSION\`\nGateway restarted. All systems should be nominal."
  else
    MSG="🦀 *OpenClaw Update Attempted* ⚠️\nStarted at \`$CURRENT_VERSION\`, still at \`$NEW_VERSION\` after update attempt. May need manual review.\n\`\`\`$UPDATE_OUTPUT\`\`\`"
  fi
else
  MSG="🦀 *OpenClaw Version Check* ✅\nCurrently on \`$CURRENT_VERSION\` — already up to date (stable channel)."
fi

# Send to Slack via openclaw message tool (piped through the CLI)
openclaw message send --channel "$SLACK_CHANNEL" --message "$(echo -e "$MSG")" 2>/dev/null || true

echo "[openclaw-update] Done. $MSG"
