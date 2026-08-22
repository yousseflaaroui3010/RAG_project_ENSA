---
description: Write the end-of-session record: done, doing, left, blocked
argument-hint: [optional note about this session]
---
# ROLE
You keep the record a stranger reads on Monday. Not a changelog, not a
celebration. What is true right now, and why.

# INSTRUCTIONS
Write or update `docs/journal/YYYY-MM-DD.md` for today, in the project root.
Load the `work-journal` skill first. Follow it where it is more specific
than this file.
$ARGUMENTS is what I want emphasised. It is a steer, never the whole entry.

# STEPS
1. Read the state before writing a word: `git status --short`, `git log
   --oneline -15`, and `git diff --stat`. Never describe work you have not
   seen on disk.
2. Read today's file if it exists. Append. Never rewrite what is already
   there.
3. Check `docs/journal/` exists. Create it if not, and say you did.
4. Write the five sections below.
5. Name the single next action, the one someone picks up cold.

# EXPECTATIONS
Five sections, in this order:

## Done
Landed and verified. Each line names how it was proven. Unverified work is
not done.

## In progress
Started, not finished. What state it is in and what breaks if nobody
touches it.

## Left
Known and not started.

## Blocked
What is stuck, on whom or what, and since when.

## Decisions
Anything chosen today that is costly to reverse, with the reason. Skip the
section when nothing qualifies.

# NARROWING
- Never write "done" for something you did not see pass. Write what ran and
  what it returned.
- Uncommitted and untracked work goes in the record. Untracked files are one
  `git clean` from gone.
- No progress percentages. No "mostly complete".
- Do not copy the diff. Say what changed and why it changed.
- Do not edit yesterday's entries. Today's file only.
- If nothing meaningful happened, write one line saying so and stop.
- A denied or errored command is unverified, never absence.

# METHODS
- Git is the source of truth for what changed. Your memory of the session is
  the source for why.
- Read `.claude/PHASE` and `.claude/harness.json` if present. A phase change
  or a gate turned off is a decision worth recording.
- Check `claude-lessons/PENDING.md`. If it holds anything, say so and point
  at `/lessons`.

# HOW TO WRITE IT
Short lines. Plain words. Past tense for done, present for in progress.
Someone who was not here must be able to act on it without asking you
anything.