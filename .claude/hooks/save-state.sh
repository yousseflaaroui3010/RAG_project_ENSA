#!/usr/bin/env bash
# PreCompact hook. Runs right before /compact or auto-compact squeezes the chat.
# 1) Backs up the raw transcript (keep last 5).
# 2) Stamps BUILD-STATE.md so the next context knows a compaction happened.
set -u
INPUT="$(cat)"
printf '%s' "$INPUT" | python3 -c '
import json,sys,shutil,os,datetime,glob
d=json.load(sys.stdin)
root=os.environ.get("CLAUDE_PROJECT_DIR",".")
tp=d.get("transcript_path","")
trig=d.get("trigger","unknown")
bdir=os.path.join(root,".claude","backups"); os.makedirs(bdir,exist_ok=True)
if tp and os.path.exists(tp):
    ts=datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(tp, os.path.join(bdir, f"transcript-{trig}-{ts}.jsonl"))
    old=sorted(glob.glob(os.path.join(bdir,"transcript-*.jsonl")))
    for f in old[:-5]: os.remove(f)
state=os.path.join(root,"docs","build","BUILD-STATE.md")
os.makedirs(os.path.dirname(state),exist_ok=True)
now=datetime.datetime.now().isoformat(timespec="seconds")
with open(state,"a") as f:
    f.write(f"\n> [auto] Context compacted ({trig}) at {now}. "
            "Trust this file and git history over chat memory. "
            "Raw transcript backup in .claude/backups/.\n")
' 2>/dev/null
exit 0
