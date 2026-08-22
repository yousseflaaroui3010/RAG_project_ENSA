---
paths:
  - "**/logger*"
  - "**/logging/**/*"
  - "**/middleware/**/*"
  - "**/*error*"
  - "**/*.test.*"
  - "**/*.spec.*"
---

# Logs, errors and tests

## Logging
One logger, imported from one module. Never an ad-hoc instance. Structured
fields, not interpolated sentences — a log you cannot filter is a log you will
not read.

Every caught exception logs context: the error, and the identifiers needed to
find the thing it happened to.

## Never log
Passwords, API tokens, session values, signing secrets, card numbers, or a full
request or response body. Log an identifier and look the rest up later.
**A log file is a filing cabinet nobody locks.**

## Errors
One shape, correct status code, and a message that tells the user what to do
next. Never a stack trace in a client-facing response. Server log only.

## Alerts
An alert must be worth interrupting somebody for. Alert on the states a human
has to act on, not on transients the retry ladder already handles. If it fires
often and nobody acts, delete it — **a noisy alarm is the same as no alarm.**

## Tests
Assert behaviour, not that code ran. Prefer the failure paths and the edges over
the happy path — the happy path is the one everybody already tried by hand.

**A test that cannot fail is worse than no test**, because it buys false
confidence. `expect(true).toBe(true)`, a mock asserting only that the mock was
called, and a snapshot nobody has read are all in that category.

Coverage counts how many smoke alarms you installed. It does not light a match
under any of them.

## Never
- `console.log` in a production path where a logger exists
- A silent catch
- A test that changes to match the implementation. If a test is wrong, say why
  and stop — that is a decision for a human