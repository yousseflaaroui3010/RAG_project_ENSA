#!/usr/bin/env bash
# PreToolUse guard. Exit 2 blocks the tool call and feeds stderr back to Claude.
set -u
source "$(dirname "$0")/config.sh" 2>/dev/null || PROTECTED_BRANCHES="main master"

INPUT="$(cat)"

PARSED="$(printf '%s' "$INPUT" | python3 -c '
import json,sys
d=json.load(sys.stdin)
t=d.get("tool_name","")
ti=d.get("tool_input",{}) or {}
cmd=ti.get("command","") or ""
fp=ti.get("file_path","") or ""
print(t); print(fp); print(cmd)
' 2>/dev/null)" || exit 0

TOOL="$(printf '%s\n' "$PARSED" | sed -n 1p)"
FILEPATH="$(printf '%s\n' "$PARSED" | sed -n 2p)"
CMD="$(printf '%s\n' "$PARSED" | sed -n '3,$p')"

deny () { echo "BLOCKED by guard.sh: $1" >&2; exit 2; }

# --- Protect the control plane and signed specs from file-edit tools ---
if [ "$TOOL" != "Bash" ]; then
  case "$FILEPATH" in
    *".claude/hooks/"*|*".claude/settings.json"*|*".git/hooks/"*|*".env"*)
      deny "This file is part of the safety system. Ask the human to change it." ;;
    *"docs/phase2/"*)
      deny "Phase 2 specs are signed and write-locked. If a contract is wrong, escalate to the human; never edit the spec to match the code." ;;
  esac
  exit 0
fi

# --- Bash command checks ---
echo "$CMD" | grep -qE 'docs/phase2' && \
  echo "$CMD" | grep -qE '(>|>>|sed +-i|tee |rm |mv |cp +[^ ]+ +docs/phase2)' && \
  deny "Phase 2 specs are signed and write-locked. Escalate instead of editing them."
echo "$CMD" | grep -qE -- '--no-verify' && deny "--no-verify is never allowed. Fix the failing check instead."
echo "$CMD" | grep -qE 'git +push +(-f|--force)' && deny "Force push is not allowed."
echo "$CMD" | grep -qE 'core\.hooksPath|\.git/hooks' && deny "Git hook paths are locked."
echo "$CMD" | grep -qE '(^|[;& ])(HUSKY=0|SKIP=)' && deny "Skipping local checks is not allowed."
echo "$CMD" | grep -qE '(curl|wget)[^|;]*\|\s*(ba)?sh' && deny "Piping downloads into a shell is not allowed."
echo "$CMD" | grep -qE 'rm +-rf +(/|~)( |$)' && deny "Refusing destructive delete."
echo "$CMD" | grep -qE '\.claude/(hooks|settings)' && \
  echo "$CMD" | grep -qE '(>|>>|sed +-i|tee )' && deny "Do not modify the safety system via shell."

for BR in $PROTECTED_BRANCHES; do
  echo "$CMD" | grep -qE "git +push +[^ ]+ +($BR)(\$| )" && \
    deny "Direct push to '$BR' is blocked. Push your task branch and open a PR."
done

# --- Block committing or merging WHILE ON a protected branch ---
CUR="$(git -C "${CLAUDE_PROJECT_DIR:-.}" branch --show-current 2>/dev/null)"
if [ -n "$CUR" ]; then
  for BR in $PROTECTED_BRANCHES; do
    if [ "$CUR" = "$BR" ]; then
      echo "$CMD" | grep -qE '(^|[;&| ])git +commit' && \
        deny "You are ON '$BR'. Committing here is blocked. Create task/T-xxx-slug, commit there; only the human moves '$BR'."
      echo "$CMD" | grep -qE '(^|[;&| ])git +merge' && \
        deny "Merging into '$BR' is the human's move, via PR."
    fi
  done
fi

# --- Journal debt: unpaid journals from a past session block new commits ---
FLAG="${CLAUDE_PROJECT_DIR:-.}/.claude/logs/journal-debt.flag"
if [ -f "$FLAG" ] && echo "$CMD" | grep -qE '(^|[;&| ])git +commit'; then
  ST="${CLAUDE_PROJECT_DIR:-.}/docs/build/BUILD-STATE.md"
  CH="${CLAUDE_PROJECT_DIR:-.}/docs/build/CHANGELOG-AI.md"
  if [ "$ST" -nt "$FLAG" ] || [ "$CH" -nt "$FLAG" ]; then
    rm -f "$FLAG"
  else
    deny "Journal debt from a previous session: update docs/build/BUILD-STATE.md and CHANGELOG-AI.md first, then commit."
  fi
fi

exit 0
