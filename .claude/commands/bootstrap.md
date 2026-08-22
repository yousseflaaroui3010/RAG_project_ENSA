---
description: Read docs/brief/ and configure this repo's harness for it. Run once, first.
---

This repo has the harness and nothing else. Your job is to read what the human
put in `docs/brief/`, and turn it into four documents and one config file.

**You are not building the project. You are setting up the workspace for it.**
Write no application code in this command. Not one file.

---

## Step 0 — refuse early if you should

- If `docs/brief/` is empty or holds only its README, **stop.** Say what is
  missing and what a usable brief looks like. Do not invent a project.
- If `CLAUDE.md` already exists at the root, **stop and ask.** This repo has
  been bootstrapped. Re-running would overwrite decisions somebody made.

## Step 1 — read everything, write nothing

Read every file in `docs/brief/`, all the way through. Then read the repo:
`package.json` if there is one, the lockfile, the directory layout, any config
files, `git log`.

`docs/brief/` is **read-only** and stays that way. It is denied to Edit and
Write in `.claude/settings.json`. It is the human's own words and it must still
say the same thing in six months, so that when a document and the brief
disagree you can tell which one drifted.

## Step 2 — report what you found, and stop

Show me, in plain English:

| | |
|---|---|
| What this project is | one paragraph, your words, from the brief alone |
| The stack | what the brief names, and what the repo actually has installed |
| What the brief does **not** say | be specific. This list is the valuable one |
| Decisions the brief already made | things I should not re-open |
| Decisions it leaves open | things somebody has to rule before building |

Then ask me **at most five questions**, each as options with trade-offs, never
open-ended. Ask only about things that change what gets built. Then **stop and
wait.**

Do not proceed to step 3 until I have answered.

## Step 3 — once I have answered, write the five files

Use `.claude/templates/` as the shape. Fill them from the brief and my answers.
Never leave a placeholder in place: an unfilled template reads as truth to the
next session, which is worse than an empty file.

**1. `CLAUDE.md`** — loads every session, so keep it under one page.
What the project is, which files to read first, what state it is in today, the
things that look wrong and are on purpose, and how I want to be spoken to.

**2. `constitution.md`** — decisions made once and not re-argued.
Only what the brief actually settles, plus what I ruled in step 2. Each row:
the decision, and what it costs. **A decision with no cost listed was not a
decision, it was a preference.** Do not pad this file with things nobody has
decided — an invented constitution is worse than none, because it gets obeyed.

**3. `ARCHITECTURE.md`** — the fridge note. What is on disk *today*.
Every layer with its real state: done, empty, or not started. Where files came
from. How to run it locally. This is the file that goes stale fastest, so it
says its own last-updated date at the top.

**4. `docs/journal/BUILD-STATE.md`** and `docs/journal/CHANGELOG-AI.md` — the
running record. BUILD-STATE holds where this is, next (three items maximum),
waiting on a human, and the five headings: done, doing, left, blocked, why.
CHANGELOG-AI is append only, one line per change. Do not create STATUS.md;
it was retired and folded into BUILD-STATE.

**5. `.claude/harness.json`** — the machine half. Set:
- `packageManager` if the lockfile does not settle it
- `checks` — the scripts the gate should run. Only ones that exist
- `sourceDirs` — where the code will live. Get this wrong and the gate will
  pass a turn that broke something
- `guardedPaths` — leave empty for now unless the brief already names a check
  worth protecting. It gets filled the first time a guard exists

## Step 4 — tailor the rules, by deleting

`.claude/rules/` ships with six files. **Delete every one that does not apply.**
A rules file about databases in a project with no database is pure context cost
and it teaches me the rules are decorative.

Then edit the ones that stay: replace the generic wording with this project's
real paths, real commands, real bans. A rule that says "never import the wrong
thing" is not a rule. A rule that names the two directories is.

Do the same for `.claude/skills/`.

## Step 5 — prove the gate, by breaking it on purpose

This is the step people skip, and skipping it is how you end up with a check
that has never run.

1. Run each check in `harness.json` by hand. Record the exit codes.
2. Break one deliberately — a type error in a scratch file is enough.
3. Confirm the gate goes red and says so.
4. Delete the break. Confirm it goes green.
5. Report both results.

**A check that has never failed is not a check.** If a check cannot be made to
fail, say so — that is a finding about the check, not a formality you passed.

## Step 6 — report

Tell me, in plain English:
- What you wrote, one line each
- Which rules files you deleted, and why
- The gate proof from step 5, both directions
- What you could **not** work out from the brief, and what would settle it
- The single next thing worth doing

---

## Rules for this whole command

- **Never write application code here.** Not a route, not a schema, not a test.
- **Never invent a requirement.** If the brief does not say it, it is a question
  for me, not a gap for you to fill.
- **Never write a version number you did not read from a lockfile or a
  registry this session.** Hand it to the `scout` agent instead.
- If two files in the brief contradict each other, **stop and show me both.**
  Do not pick one. Somebody wrote both on purpose.
- If something in the brief would take more than a day to build, say so and
  propose a split.
- If the brief looks like the wrong solution to the real problem, say that
  first, before any of this.
- Plain English throughout. I understand software at a high level. I do not
  read code line by line.
