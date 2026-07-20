#!/usr/bin/env bash
# PreToolUse sentry on Write. Blocks creating a NEW file whose basename
# already exists elsewhere in the repo (the classic "recreated utils"
# failure). Exit 2 feeds the existing paths back to Claude.
set -u
INPUT="$(cat)"
printf '%s' "$INPUT" | python3 -c '
import json,sys,os,fnmatch
d=json.load(sys.stdin)
if d.get("tool_name") != "Write": sys.exit(0)
fp=(d.get("tool_input",{}) or {}).get("file_path","")
if not fp: sys.exit(0)
if os.path.exists(fp): sys.exit(0)          # editing/overwriting, not creating
base=os.path.basename(fp)
allow={"index","main","__init__","mod","README","SKILL","PROMPT","CLAUDE",
       "types","test","spec","config","setup"}
stem=base.split(".")[0]
if stem in allow or stem.startswith("."): sys.exit(0)
root=os.environ.get("CLAUDE_PROJECT_DIR",".")
skip={"node_modules",".git","dist","build",".next","coverage",".claude","vendor"}
hits=[]
for cur,dirs,files in os.walk(root):
    dirs[:]=[x for x in dirs if x not in skip]
    for f in files:
        if f==base:
            p=os.path.join(cur,f)
            if os.path.abspath(p)!=os.path.abspath(fp): hits.append(p)
    if len(hits)>=5: break
if hits:
    sys.stderr.write(
      "BLOCKED by dup-sentry: a file named %r already exists:\n  %s\n"
      "Run the absence protocol (graph search + grep), then extend the "
      "existing file instead of creating a twin. If a second file is truly "
      "intended, ask the human to whitelist the name in dup-sentry.sh.\n"
      % (base, "\n  ".join(hits)))
    sys.exit(2)
sys.exit(0)
'
STATUS=$?
[ $STATUS -eq 2 ] && exit 2
exit 0
