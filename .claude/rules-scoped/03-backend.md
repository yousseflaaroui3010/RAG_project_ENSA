---
paths:
  - "src/**/*"
  - "server/**/*"
  - "api/**/*"
  - "worker/**/*"
  - "**/routes/**/*"
  - "**/handlers/**/*"
---

<!-- BOOTSTRAP: replace these paths with this project's real ones, and replace
     the generic bans below with the boundaries ARCHITECTURE.md declares.
     A rule that says "do not import the wrong thing" is not a rule. A rule that
     names two directories is. -->

# Backend

## Validate at the door
Every inbound payload is checked against a schema before anything touches it.
Treat every request as if it came from someone trying to break in, because one
day it did.

## Contract stability
Never change or remove the shape of an endpoint something already calls. Add a
version. Something out there is still using the old one and it will not tell you.

## Idempotency
Any operation that takes money, creates a record, or calls a paid third party
carries an idempotency key derived from the work, not from the clock. Phones
lose signal mid-request. The retry must not charge twice.

## Failure classification
Classify every failure before deciding what to do with it. At minimum:
transient (retry), outage (back off), broken contract (**never retry**), and
out of budget (**never retry**). A bricked-up door does not open if you knock
harder, and a spend cap cannot be raised from inside a running job.

An unknown 4xx is a broken contract, and you stop. Never guess "transient".

## Errors
One error shape across the whole surface. Same fields, correct status code,
every time. Never a stack trace in a client-facing response.

## Never
- Reach a network from pure domain logic. I/O lives at the edges
- Hardcode a connection string or a key. Read it from the environment, through
  one config module, so nobody has to grep for `process.env`
- Swallow an exception. Every catch either logs and re-throws, or logs and
  returns a typed error
- Build a query by string concatenation. Parameterised placeholders always
- Run a query inside a loop. Join, or batch

If a change would break an existing caller, stop and say which one.