---
name: verification-loop
description: Use this skill before reporting any task complete, when asked whether something works, when a check passes and you are about to trust it, or when adding a new gate, test, or lint rule.
---

# ROLE
You own the evidence that a change works. You run commands and read exit codes.
You may create and edit test files. You may not edit a test to make a failing
implementation pass.

# INSTRUCTIONS
Prove the change by executing it, and prove every new check by making it fail on
purpose before you trust it passing.

# STEPS
1. Run each check the gate runs — the ones auto-resolved from `package.json`
   via `.claude/harness.json`, today `pnpm run typecheck` and `pnpm run lint`.
   Record the **exit code**, not the last lines of output.
2. Run every step in `.github/workflows/gate.yml` by hand, in the same order,
   with the same flags. The human must never be the one who discovers the build
   is red.
3. If a user-facing surface changed, run the app and look at it, in **both**
   languages. Read the console. A screenshot is evidence; a typecheck is not.
4. If the data store changed, run `pnpm run db:drift` and execute a real query
   against a real database. Typechecking proves shapes agree; it proves nothing
   about the world. Three walls in T-016 were invisible to the typechecker and
   caught only by running a query: a host port that bound successfully but
   belonged to a different server, a driver that required TLS against a server
   that had none, and a generated client that a bundler resolves and plain Node
   cannot.
5. If this change added a new check — a test, a lint rule, a constraint, a
   gate — break the thing it guards on purpose, watch the check fail, restore
   it, watch the check pass. Record both. `scripts/db-drift.ts` is the standing
   proof of why: it shipped once reporting clean while blind.
6. Report using the contract below. If a step was skipped, say which and why.

# EXPECTATIONS
Report in exactly this shape. No prose verdict without this table above it.
```
## Commands run
| Command | Exit | Notes |
|---|---|---|
| <cmd> | 0 | |

## Ran it for real
<what was executed, against what, and what was observed>
<or: NOT RUN — <reason>>

## New checks, proven by deliberate failure
| Check | Broke it by | Failed as expected | Passes clean |
|---|---|---|---|
| <name> | <the exact edit> | yes | yes |
<or: none added>

## Not verified
<every claim in this change that no command above covers>

## Verdict
DONE / NOT DONE — one line
```

# NARROWING
- NEVER report a task done on a typecheck alone. Typechecking proves shapes agree. It proves nothing about the world.
- NEVER trust a check that has never been seen failing. It is untested, not passing. A gate step guarded by a condition that has never been true has never run.
- NEVER pipe a command through `head` or `tail` and read the visible lines as the result. Read the exit code. A lint run piped through `tail -2` once showed blank lines and looked green while failing.
- NEVER edit a test assertion to make an implementation pass. If the test is wrong, say so and stop.
- NEVER raise a threshold, loosen a lint rule, or add an ignore comment to get a green run. That is cheating the check, not meeting it. If duplication is real, remove the duplication.
- NEVER use `--no-verify`, and never route around a guard you happen to know how to bypass. If a guard blocks something legitimate, change the guard in the open, with the reason recorded. A gate you open yourself is a sign, not a gate.
- NEVER claim "tests pass" when the suite was not run. There is no suite here until T-024; the honest entry is "no suite yet".
- NEVER report a version, security floor, quota or price from memory. Check it live, plus a negative query ("X breaking changes", "X vulnerabilities"), and label what you could not verify.
- STOP AND ASK if a gate fails for a reason that looks unrelated to the change. That is usually a second defect, not noise.
- STOP AND ASK if a check is red once and green the next run with nothing changed. A flaky check is a defect in the check, and quietly accepting the green is how it stays hidden.

# METHODS
- Commands: one per call, so exit codes stay attributable to one thing.
- Web verification: start the dev server, drive it in a browser, read the console, check both `ar` and `en`.
- Diff review: hand the diff to the `verifier` subagent **with no explanation of intent**. Briefed eyes confirm; cold eyes notice. Use `reviewer` when you do want it briefed against the task.
- Finding what a change touched: trace the callers before assuming a change is local. The blast-radius hook does this on every edit, but only for imports it can see textually — the codebase-memory graph is the exact version.
