#!/usr/bin/env bash
# push_docs.sh — serialized + retrying commit/push of docs/data files.
# Safe against concurrent git from other bigclaw crons (index.lock contention): an flock
# serializes push_docs callers, and a retry loop rides out any lock held by refresh_all /
# price_refresh. Never fails the caller (always exits 0) — a dashboard push must not break a cycle.
# Usage: push_docs.sh "<label>" <file> [file...]
cd /home/cbiggs90/bigclaw-ai || exit 0
LABEL="$1"; shift
[ $# -eq 0 ] && exit 0
exec 9>/tmp/bigclaw_docs_push.lock
flock 9
for attempt in 1 2 3 4 5; do
  git add -- "$@" 2>/dev/null
  if git diff --cached --quiet 2>/dev/null; then exit 0; fi   # nothing new to publish
  if git commit -q -m "$LABEL $(date '+%Y-%m-%d %H:%M')" 2>/dev/null && git push -q 2>/dev/null; then
    exit 0
  fi
  sleep 3   # another bigclaw git op held the index.lock — back off and retry
done
exit 0
