---
description: Build the quality evidence pack for whoever receives this work
---

This is what you hand somebody alongside the thing itself.

## Gather only what actually exists

Run every check the gate runs and record the **exit code**, not the last lines
of output. That means, at minimum:

- `pnpm run typecheck`
- `pnpm run lint`
- `pnpm run db:drift`
- every step in `.github/workflows/gate.yml`, by hand, in the same order with
  the same flags

Then run the dependency audit and read it — never fix it in this command.

Then read:

- `docs/journal/DECISIONS.md` — count the rows and list the titles
- `docs/journal/BUILD-STATE.md` — Now / Next / Blockers
- `docs/journal/BUILD-PLAN.md` — which exit gates are met and which are not
- `docs/journal/CHANGELOG-AI.md` — what actually changed
- `docs/journal/INTAKE-REPORT.md` §5 — what is still waiting on a human
- `.claude/lessons/ACTIVE.md`
- `git log --oneline` — first and last commit
- `docs/phase2/` — what was actually asked for, so you can say what was and was
  not delivered, and where the pack and the decisions still disagree

**Never quote a number you did not just produce.** If a check has never run,
the honest entry is "never run" — not a blank, not an estimate. Tests are the
live example: Vitest and Playwright do not arrive until T-024, so the test row
says "no suite yet, T-024 owns it", never "0 failures". If a gauge named in
some earlier plan does not exist here — a mutation score, a dependency graph, a
scanner result — say the gauge does not exist yet rather than inventing one.
**A fabricated number in a client document is worse than a gap, because the gap
is honest.**

## Write HANDOVER.md

```
## What you're getting
Two sentences. What it does, who for.

## What state it is in
Say plainly what this is: a prototype for approval, a first release, a finished
system. Name what is deliberately not built yet. That is a scope decision, not
an omission, and saying so is the difference between the two.

## Quality evidence
| What | Result | What it means in plain words |
Explain every row for someone who does not read code.
Good: "Schema drift: 0 differences. The TypeScript description of the database
and the signed SQL that actually creates it agree, line for line. A machine
checks this on every change, so the two cannot quietly diverge."
Bad: "db:drift passes."

## Every decision we made, and what it cost
From docs/journal/DECISIONS.md. Date, choice, and what we gave up.
A decision with no cost listed is a decision nobody examined. Flag it.

## What we deliberately did not build
And why. This section matters as much as the one above it — it is the
difference between a gap and a choice.

## What could go wrong later
Honest risks. Anything marked unverified. Anything with an open question.
Say what protects the things that cannot be retrofitted.
Include where docs/phase2/ still contradicts a later decision, and name T-007.

## How to keep it running
What to watch, what breaks first, what needs a human.
```

## Rules

- Plain English throughout. The reader is smart and does not read code.
- No stack traces. No code blocks unless one line makes something clearer.
- Never claim a check passed that you did not run in this session.
- If the evidence is thin, say the evidence is thin. That is information about
  where the project is, not a failure of the document.
- Do not overwrite an existing `HANDOVER.md` without showing me the diff first.
