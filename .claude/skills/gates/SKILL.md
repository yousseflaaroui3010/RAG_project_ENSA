---
name: gates
description: The five points where work stops until a condition is met, and which machine on this setup enforces each one. Use before claiming anything is done, when a gate blocks something, when adding a new check, and before any release.
---

# Gates

A gate is a point where work stops until a stated condition is met.

Three rules make a gate real.

1. **It is pass or fail.** Not "looks fine". Not a percentage someone interprets.
2. **It is automatic, or a written checklist a person signs.** Anything else is a hope.
3. **When it fires, work stops.** A gate waved through twice has stopped being a gate.

## The five points, and what enforces each one here

| Point | Condition | The machine |
| --- | --- | --- |
| While writing | The tool cannot reach protected paths or the wrong phase | `config-guard.mjs` blocks writes to `.claude`, `.env`, `.ssh`, `.aws`. `phase-gate-code.mjs` refuses app code before phase 3. `blast-radius.mjs` names the callers before an edit lands |
| Before a push | The named guarded files cannot be weakened | `guard-tests.mjs`, per project, reading `guardedPaths` in `harness.json` |
| Before finishing a turn | The project's checks are green | `gate.mjs`, the global Stop hook, reading `checks` in `harness.json`. Exits 2 and refuses to let a check be weakened for green |
| Before release | Nothing ships early | `phase-gate-deploy.mjs` refuses push, publish and deploy before phase 6 |
| The hour after | Nothing went wrong for real users | Nothing yet. This is the gap |

That last row is the cheapest gate of all and the one most often skipped. Shipping is not the gate. **Shipping and nothing going wrong for an hour is the gate.**

## What lives in harness.json

Per project, so each repo names its own truth.

| Key | Meaning |
| --- | --- |
| `checks` | Which commands the Stop gate runs. `["__disabled__"]` switches it off for a repo whose suite is broken or slow |
| `guardedPaths` | The files that are tempting to weaken. A drift check, a constraint suite |
| `maxGateBlocks` | How many blocks before the gate opens on its own, so a session can never be trapped forever |

A repo with no `harness.json` gets auto detection, which works but is a guess. A real config beats a guess.

## Rules that keep the gates trusted

- **Never weaken a check to get green.** Not by raising a threshold, not by an ignore comment, not by deleting a test, not by softening an assertion. That is cheating the check, not meeting it.
- **Never route around a gate.** If it blocks something legitimate, change the gate in the open with the reason written down. A gate you can open yourself is a sign, not a gate.
- **Run the whole gate yourself before handing over a push.** Read the CI definition and run each step with the same flags. The person you report to should never be the one who discovers it is red.
- **Check exit codes, not the last lines of output.** A lint run piped through `tail` showed blank lines and looked green while failing.
- **A check that has never executed is untested, not passing.** A step skipped by a condition that has never been true proves nothing. Prove every new gate by breaking something on purpose, watching it block, then watching it pass clean.
- **A gate over 2 minutes gets skipped. Over 10 minutes it gets disabled.** If the suite is slow, that is the finding, not the gate.

## Adding a new gate

Four steps, in order.

1. Write what it blocks, in one sentence, as pass or fail.
2. Wire it to one tool only, and check the filter actually covers that tool. A hook wired to the wrong tool blocks nothing while looking installed.
3. Break the rule on purpose. Watch it refuse.
4. Do the everyday thing that must still work. Watch it pass. Widening a filter is how you accidentally block your own routine commands.

Skip step 4 and you will find out from your own workflow instead of from a test.

## When a gate fails three times on the same thing

The gate is wrong, or the check is wrong. Stop repeating it. Rewrite the check and say what changed. Repeating a failing check is not persistence, it is a loop.
