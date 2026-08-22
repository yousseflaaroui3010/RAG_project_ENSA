---
description: Review the lessons the coach proposed and approve or bin them
---

Read `~/claude-lessons/PENDING.md`, and `claude-lessons/PENDING.md` if this
project has one. Handle entries from both.

If it is empty, say so and stop.

For each entry, show me three lines:
- What happened
- The lesson
- Where it wants to go

Then ask me: keep, change, or bin.

For each one I keep:
1. Append it to `~/claude-lessons/ACTIVE.md` when `goes_to` is `global` or an
   agent name. Append to `claude-lessons/ACTIVE.md` when it is `project`, and
   create that file if the project has none.
2. Files under `~/.claude/` are write-locked by a permission rule and a Bash
   guard. Do not try to edit them and do not ask for the lock to be lifted.
   Instead, print the exact line to add and the exact file path, and tell me to
   paste it in Notepad. Warn me if that file is already over 130 lines.

3. If `goes_to` is `project`, append to the right file in `.claude/rules/` and
   warn me if that file passes 60 lines.
4. If `goes_to` is `global`, tell me — a global rule belongs in
   `~/.claude/rules/`, outside this repo, and I will decide.

For each one I bin, delete it.

Before writing anything, check the lesson is not something a machine already
enforces. Look in `.claude/hooks/`, `.claude/settings.json`, `biome.json` and
`.github/workflows/gate.yml`. A rule a machine already enforces is pure context
cost and it teaches me the rules files are decorative. Say so and bin it.

Also check it is not already covered by `~/.claude/rules/` or
`.claude/rules/00-global.md`. If it is, the finding is that a standing rule was
not followed. Say that plainly and bin the lesson — writing an existing rule
down a second time does not make it more binding.

Then check `ACTIVE.md` for anything past its `review_on` date. Show me those
and ask whether each still holds. A lesson approved in March can be wrong by
November, and old memory that never expires eventually turns on you.

When done, clear `PENDING.md` and tell me how many lessons are now active.
If this project has `docs/journal/CHANGELOG-AI.md`, add one line recording what
moved. Most projects do not have it. Skip silently if absent.
Plain English. Short. No code unless I ask.
