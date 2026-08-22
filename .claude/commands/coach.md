---
description: Ask the coach for one lesson from this session, then file it
---

Run the coach agent now. Do NOT background it. Wait for it.

When it returns:

1. If it said "no lesson this session", tell me that in one line and stop.

2. Otherwise, take its proposal block exactly as written, unchanged, and
   append it to `~/claude-lessons/PENDING.md`.

3. Then tell me three lines and nothing more:
   - What went wrong
   - The lesson
   - Where it goes

Do not summarise the proposal instead of writing it. The file is the point.
Do not edit anything under `~/.claude/`. That is locked and it should stay locked.