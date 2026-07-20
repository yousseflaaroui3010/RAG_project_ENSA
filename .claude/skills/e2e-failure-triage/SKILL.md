---
name: e2e-failure-triage
description: Package a failing end-to-end or browser test into a debug bundle another agent can fix from, without re-running the whole suite. Use on any red e2e run.
---

# E2E Failure Triage (b4 procedure)

A failing test without its evidence is a crime scene after the cleaners.

## Steps
1. Re-run ONLY the failing spec with tracing on (Playwright:
   `--trace on`), never the full suite.
2. Collect into docs/build/traces/T-xxx/: failing spec name and line,
   screenshot or DOM snapshot, console log, network log, the trace file,
   and the exact one-line repro command.
3. Classify: app bug | test bug | environment | flake. Flake means it
   passed on an identical immediate re-run; record the signature in
   memory and quarantine the spec with a linked task, never delete it.
4. Hand back: task returns to its owner (b2 or b3) with the bundle path
   and your classification. You fix test code only, never app code.

## Rules
- One bundle per failure, no zip-of-everything dumps.
- Selectors in fixes prefer roles and test ids over CSS paths.
