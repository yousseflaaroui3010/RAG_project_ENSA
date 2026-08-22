---
name: phase-5-testing
description: Run phase 5, every kind of test and check before anything ships, including attacking your own guards and running honest evals. Use when the project is in phase 5, when asked to test or verify a build, and before any release is prepared.
---

# Phase 5: testing

## Before anything

Read `.claude/PHASE`. If it does not hold 5, say which phase this project is in and stop.

Phase 4 built it. Phase 5 tries to break it. Reading the code tells you what you wrote. Attacking it tells you what it does.

## What phase 5 produces

1. A written test plan naming what is covered and what is deliberately not.
2. All test levels running green, with the command anyone can run.
3. An attack log: what you tried to break, and what held.
4. The six accessibility failures at zero on every screen.
5. The speed numbers measured on something like a real device.
6. A load number: where it actually falls over.
7. A list of what is still unverified, each with the task that would settle it.

Number 7 is not a failure. A phase 5 that claims everything is proven is a phase 5 that did not look hard enough.

## The order

Cheapest and fastest first. A slow check that runs last finds problems late.

| # | Check | Skill |
| --- | --- | --- |
| 1 | Static checks and formatting, automatic | `gates` |
| 2 | Unit tests, milliseconds each | `test-strategy` |
| 3 | Integration tests against a real data store | `test-strategy` |
| 4 | Contract tests between front and back | `contract-types-regen` |
| 5 | Two or three end to end paths, the ones that would embarrass you | `test-strategy` |
| 6 | Accessibility: the six failures, plus a keyboard walk per screen | `screen-states`, `accessibility-verification` |
| 7 | Speed: the three numbers, on a mid range phone | `quality-metrics` |
| 8 | Security: threats for anything touching money, login, files or the internet | `threat-modeling` |
| 9 | Failure behaviour: kill a dependency and watch what the user sees | `plan-for-failure` |
| 10 | Load: push it until it breaks, note the number | `plan-for-failure` |
| 11 | Attack the guards on purpose | below |
| 12 | Evals, if the system uses a model | below |

## Attack it on purpose

The most valuable hour in phase 5. Every rule you wrote gets tried from the wrong side.

1. List the forbidden things, one line each. Eight is a good number.
2. Try all eight. Not the easy ones only.
3. Count how many got through.
4. Fix the ones that got through, not the ones that held.
5. Run all eight again.

Zero out of eight is the only pass. And the attacks include the guard trying to unlock itself, because a guard that answers to a polite request is not a guard.

Reading a config tells you what you wrote. Attacking it tells you what it does.

## Evals, when a model is in the loop

This is where a previous attempt failed, and the cause is worth naming: the sandbox was not reset between cases, so every result after the first was contaminated.

Five rules.

1. **Reset the start state before every single case.** Same files, same data, same config. A fresh copy, not a tidy up.
2. **Same input, word for word.** A reworded prompt is a different test.
3. **Three runs per case, minimum.** One run tells you nothing about a system that can vary.
4. **Write the pass condition before running.** Not "the output looks good". Something with one answer.
5. **Log every run**: input, start state, output, pass or fail, and the date.

Then judge on the pattern, never on the best run. Two out of three passing is a 67 percent system, not a working one.

If a case cannot be reset cleanly, say so and do not report a number from it. A contaminated eval is worse than no eval, because it looks like evidence.

## The numbers, and the one to ignore

Coverage is not a target. Use it to find files with **no** tests at all, then stop looking at it. The study behind that, and the flaky test policy, are in `test-strategy`.

Ask of every test: does it check something? A test that runs a function and asserts nothing is theatre.

Zero flaky tests tolerated in the blocking set. One flaky test teaches everyone to press re run, and then a real failure sails through behind the habit.

## References, loaded when you need them

| File | Load it when |
|---|---|
| `references/performance-targets.md` | Measuring speed, running Lighthouse, or load testing |
| `references/accessibility-audit.md` | Checking any screen, before asking for review |
| `references/bug-severity.md` | Logging a bug, or running a session with real users |

Security checks live with the code that creates the risk:
`phase-4-implementation/references/security-owasp.md`.

## Never

- Weaken a check to get green.
- Delete a test because it is inconvenient.
- Report a suite as passing without the exit code.
- Call a check proven when it has never failed on purpose.
- Round unverified up to working.

## When something fails

Do not fix it here. Fixing is phase 4 work.

Record it properly: what failed, the reproduction steps, and what it tells you. Then either drop back into phase 4 for a fix, or park it with the reason. `debug-loop` for the hunt, `incident-review` if it already reached a user.

## Leaving phase 5

Do not move the marker. Tell the human phase 5 looks finished, list the seven conditions with the evidence for each, and name the unverified items and their confirmation route.

One number to hand over: **how many bugs reached a person that a test could have caught.** Small, honest, and hard to game.
