#!/usr/bin/env bash
# SessionStart hook. Whatever this prints becomes context Claude can see.
# Fires on startup, resume, clear, AND after compaction.
# Also stamps a session marker so the Stop gate can verify the journal
# was updated during this session.
set -u
ROOT="${CLAUDE_PROJECT_DIR:-.}"
STATE="$ROOT/docs/build/BUILD-STATE.md"
DEC="$ROOT/docs/build/DECISIONS.md"

INPUT="$(cat 2>/dev/null || true)"
SID="$(printf '%s' "$INPUT" | python3 -c '
import json,sys
try: print(json.load(sys.stdin).get("session_id","nosession")[:12])
except Exception: print("nosession")
' 2>/dev/null || echo nosession)"
touch "/tmp/claude-sess-start-$SID" 2>/dev/null

echo "## Session bootstrap (auto-injected)"
[ -f "$ROOT/.claude/logs/journal-debt.flag" ] && \
  echo "### JOURNAL DEBT: a past session changed code without journaling. Commits are blocked until BUILD-STATE.md and CHANGELOG-AI.md are updated. Do that first."
[ ! -f "$ROOT/.claude/logs/graph-indexed.marker" ] && \
  echo "### Code graph NOT indexed yet: run index_repository, then run: touch .claude/logs/graph-indexed.marker"
echo "Branch: $(git -C "$ROOT" branch --show-current 2>/dev/null || echo 'no-git')"
git -C "$ROOT" status --short 2>/dev/null | head -8
echo
echo "### Recent commits"
git -C "$ROOT" log --oneline -5 2>/dev/null
echo
if [ -f "$STATE" ]; then
  echo "### BUILD-STATE.md (source of truth, read fully)"
  tail -c 6000 "$STATE"
else
  echo "### No BUILD-STATE.md yet. Create docs/build/BUILD-STATE.md before any work."
fi
if [ -f "$STATE" ]; then
  OPEN=$(awk '/^## Now/,/^## Next/' "$STATE" | grep -c 'T-[0-9]')
  QUEUED=$(awk '/^## Next/,/^## Blockers/' "$STATE" | grep -c 'T-[0-9]')
  DONE=$(awk '/^## Done/,0' "$STATE" | grep -c 'T-[0-9]')
  if [ "$OPEN" -eq 0 ] && [ "$QUEUED" -eq 0 ] && [ "$DONE" -gt 0 ]; then
    echo
    echo "### REMINDER: task board empty, Done column full."
    echo "If the kickoff's Definition of Done is met, this project is"
    echo "finished. Tell the human to paste RETRO-PROMPT.md now, before"
    echo "any new work, to harvest lessons into the kit."
  fi
fi
echo
if [ -f "$DEC" ]; then
  echo "### Last decisions"
  tail -n 12 "$DEC"
fi
exit 0
