#!/usr/bin/env bash
# PostToolUse logger. Appends one JSON line per file change.
# This is your tamper-simple audit trail: every edit, timestamped, no tokens spent.
set -u
INPUT="$(cat)"
printf '%s' "$INPUT" | python3 -c '
import json,sys,datetime,os
d=json.load(sys.stdin)
line={
  "ts": datetime.datetime.now().isoformat(timespec="seconds"),
  "session": d.get("session_id","")[:8],
  "tool": d.get("tool_name",""),
  "file": (d.get("tool_input",{}) or {}).get("file_path",""),
}
p=os.path.join(os.environ.get("CLAUDE_PROJECT_DIR","."),".claude","logs","changes.jsonl")
os.makedirs(os.path.dirname(p),exist_ok=True)
open(p,"a").write(json.dumps(line)+"\n")
' 2>/dev/null
exit 0
