---
description: Turn the signed specs in docs/phase2/ into checkable acceptance criteria
---

Turn what the signed pack requires into tests. One area at a time.

**Ask me which area first.** Never try the whole pack in one pass.

## Read this before anything else

Tests do not run here yet. Vitest and Playwright arrive in **T-024**. Until
they do, this command produces test files that are staged, not executed, and it
must say so in every report. A test file nobody has run is a plan, not
evidence — do not let it be counted as coverage.

## What owns what

`docs/phase2/` is the source and it is signed and write-locked. This command
**reads** it and produces test files. It never rewrites the pack, and it never
invents a requirement that is not in one.

| Source | Already owns |
|---|---|
| `docs/journal/DECISIONS.md` | closed decisions. If a requirement contradicts one, stop and show me both |
| `docs/phase2/` | what the system must do — but it is at v1.2 and PREDATES every architecture decision |
| `docs/journal/architecture/` (S1-A2 DDL) | the constraints. A rule the database already enforces belongs in a constraint test, not here |
| `docs/journal/BUILD-PLAN.md` | the exit gate each task must meet |

**The pack and the decisions disagree in places, on purpose.** Reconciling them
is task T-007. When you hit a contradiction, stop and show me both — do not
pick one, and do not write a test that silently ratifies the stale side.

## Step 1 — report, write nothing

For the area I name, list every requirement you found, one line each:

`[source file] → [requirement in one sentence] → [checkable / not checkable]`

Then stop and wait for me.

## Step 2 — once I confirm

Write the test file under the right directory — `tests/unit/`,
`tests/integration/` or `tests/e2e/` — in the shape the rest of the repo uses.
Each criterion becomes one test, named as a sentence:

- `The system SHALL <x>`
- `WHEN <trigger>, the system SHALL <response>`
- `IF <problem>, THEN the system SHALL <response>`
- `WHILE <state>, the system SHALL <behaviour>`
- `WHERE <feature is enabled>, the system SHALL <behaviour>`

Where the implementation does not exist yet, write the test and mark it as a
todo, with the source named in the title. **A named gap is worth having.** A
test that passes because it asserts nothing is worse than no test at all, and
the `verifier` treats one as blocking.

Anything user-facing gets its bilingual and RTL case written now, not later.
Arabic is not a translation pass bolted on at the end; a layout that only works
in one direction is a defect the day it ships.

## Rules

- **Never invent a requirement.** If the pack does not say it, it is not a
  requirement — it is a question for me.
- **If two parts of the pack contradict each other, stop and show me both.**
  Do not pick one. Somebody wrote both.
- Anything you cannot describe a check for goes in a list called **needs
  rewriting**, with the reason. Do not force it into a test.
  That list is the useful output. It measures how testable the spec actually
  is, and it is far cheaper to fix a sentence than a system.
- Speed, uptime, cost and maintainability are not acceptance criteria. They are
  fitness checks and they do not belong in this file.
- More than three conditions in one criterion means split it.
- Never edit anything under `docs/phase2/`. It is write-locked and `guard.sh`
  will stop you; if it did not, the answer would still be no.
- End every report by saying plainly which tests were **written but never run**,
  and name T-024 as the task that will first execute them.
