#!/usr/bin/env bash
# PostToolUse verifier. Runs a fast typecheck after code edits.
# Exit 2 sends stderr back to Claude so it self-corrects immediately.
set -u
source "$(dirname "$0")/config.sh" 2>/dev/null || TYPECHECK_CMD=""

INPUT="$(cat)"
FILEPATH="$(printf '%s' "$INPUT" | python3 -c '
import json,sys
d=json.load(sys.stdin)
print((d.get("tool_input",{}) or {}).get("file_path",""))
' 2>/dev/null)" || exit 0

# Only verify source-code edits.
case "$FILEPATH" in
  *.ts|*.tsx|*.js|*.jsx|*.mjs|*.cjs|*.py|*.go|*.rs) : ;;
  *) exit 0 ;;
esac

[ -z "${TYPECHECK_CMD:-}" ] && exit 0

OUT="$(eval "$TYPECHECK_CMD" 2>&1)"
STATUS=$?
if [ $STATUS -ne 0 ]; then
  {
    echo "Typecheck failed after editing $FILEPATH."
    echo "Fix these errors now, before doing anything else:"
    echo "$OUT" | tail -n 40
  } >&2
  exit 2
fi
exit 0
