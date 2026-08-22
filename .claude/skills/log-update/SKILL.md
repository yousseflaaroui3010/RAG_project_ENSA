---
name: log-update
description: >
  Update project logs (contextlog.md, gapslog.md, buglog.md).
  Use after completing tasks, finding gaps, or encountering bugs.
triggers:
  - "update log"
  - "log this"
  - "mark as done"
  - "mark as blocked"
  - "found a bug"
  - "found a gap"
---

# Log Update Protocol

## Which log?
- **contextlog.md** → Task status changes (ONGOING/DONE/LEFT/BLOCKED)
- **gapslog.md** → Missing/ambiguous requirements in CLIENT.txt
- **buglog.md** → Bugs found and fixes applied (Phase 5+)

## Format
Follow the exact table format defined in each log file's header.
Never overwrite existing entries — append new rows only.
Status changes get new rows (shows history).

## Rules
- BLOCKED items: describe what's blocked, why, and assign to PM.
- DONE items: include what was completed and who verified it.
- Gaps: include CLIENT.txt line reference and exact ambiguity.
- Bugs: include root cause, fix applied, and all affected files.
