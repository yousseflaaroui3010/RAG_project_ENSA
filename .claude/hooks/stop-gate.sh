#!/usr/bin/env bash
# Stop gate. Claude may not finish the turn while tests fail or the
# journal (BUILD-STATE / CHANGELOG-AI) was never touched this session.
# Loop safety: honors stop_hook_active and caps attempts per session.
set -u
source "$(dirname "$0")/config.sh" 2>/dev/null || { TEST_CMD=""; STOP_MAX_ATTEMPTS=3; }
TEST_CMD="${STOPGATE_TEST_CMD_OVERRIDE:-$TEST_CMD}"

INPUT="$(cat)"
READ="$(printf '%s' "$INPUT" | python3 -c '
import json,sys
d=json.load(sys.stdin)
print("1" if d.get("stop_hook_active") else "0")
print(d.get("session_id","nosession")[:12])
' 2>/dev/null)" || exit 0

ACTIVE="$(printf '%s\n' "$READ" | sed -n 1p)"
SID="$(printf '%s\n' "$READ" | sed -n 2p)"
[ "$ACTIVE" = "1" ] && exit 0

COUNTF="/tmp/claude-stopgate-$SID"
N=$(cat "$COUNTF" 2>/dev/null || echo 0)
if [ "$N" -ge "${STOP_MAX_ATTEMPTS:-3}" ]; then
  R="${CLAUDE_PROJECT_DIR:-.}"
  if [ -f "$R/.claude/logs/changes.jsonl" ] && [ -f "/tmp/claude-sess-start-$SID" ] && \
     [ "$R/.claude/logs/changes.jsonl" -nt "/tmp/claude-sess-start-$SID" ] && \
     [ ! "$R/docs/build/BUILD-STATE.md" -nt "/tmp/claude-sess-start-$SID" ] && \
     [ ! "$R/docs/build/CHANGELOG-AI.md" -nt "/tmp/claude-sess-start-$SID" ]; then
    date > "$R/.claude/logs/journal-debt.flag"
  fi
  echo "stop-gate: attempt cap reached, letting session stop" >> \
    "$R/.claude/logs/stopgate.log" 2>/dev/null
  exit 0
fi

ROOT="${CLAUDE_PROJECT_DIR:-.}"
MARKER="/tmp/claude-sess-start-$SID"
STATE="$ROOT/docs/build/BUILD-STATE.md"
LOGF="$ROOT/docs/build/CHANGELOG-AI.md"

# Journal gate: code was edited this session but no journal file was touched.
if [ -f "$MARKER" ] && [ -f "$ROOT/.claude/logs/changes.jsonl" ] && \
   [ "$ROOT/.claude/logs/changes.jsonl" -nt "$MARKER" ]; then
  if [ ! "$STATE" -nt "$MARKER" ] && [ ! "$LOGF" -nt "$MARKER" ]; then
    echo $((N+1)) > "$COUNTF"
    {
      echo "You are not done: files were changed this session but the journal was not."
      echo "Update docs/build/BUILD-STATE.md (Now/Next/Where exactly) and append"
      echo "one line to docs/build/CHANGELOG-AI.md, then finish."
    } >&2
    exit 2
  fi
fi

[ -z "${TEST_CMD:-}" ] && exit 0
OUT="$(eval "$TEST_CMD" 2>&1)"
if [ $? -ne 0 ]; then
  echo $((N+1)) > "$COUNTF"
  {
    echo "You are not done: the test suite is failing."
    echo "Fix the failures, update docs/build/BUILD-STATE.md, then finish."
    echo "$OUT" | tail -n 40
  } >&2
  exit 2
fi
rm -f "$COUNTF"
exit 0
