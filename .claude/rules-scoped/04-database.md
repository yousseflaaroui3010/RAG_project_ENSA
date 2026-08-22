---
paths:
  - "db/**/*"
  - "**/migrations/**/*"
  - "**/schema/**/*"
  - "**/*.sql"
  - "**/schema.prisma"
---

<!-- BOOTSTRAP: delete this file if the project has no database. Otherwise
     replace the generic wording with the real paths, the real migration
     command, and the real constraints. -->

# Database

## Migrations
Additive and backward compatible. The currently deployed code must still run
after the migration lands, because for a few minutes it will be.

**An applied migration is history, not source.** Never edit one in place. Write
a new one. Where a runner records a hash, editing an applied file is not just
bad practice — it makes the runner refuse to start, which is the point.

Never a change that locks a busy table for more than a moment.

## Queries
Parameterised, always. Never paste user input into a query string. This is not
a style preference; it is the single most exploited class of bug there is.

## Indexes
Any column used in a join or a frequent lookup gets an index. Any list endpoint
gets a test asserting the query count, or one slow page quietly makes a hundred
round trips and nobody notices until it is in front of a customer.

## Privileges, if this database has them
Grant to a role, never to a login name — a named grant is invisible to a
membership check. Default new tables to the least the application needs, so a
table that wants more has to ask for it in the migration that creates it. A
loud failure in development beats a silent grant on table thirty-four.

## Decisions that need a written record
- A new table with a foreign key: why normalised, or why not
- Any table holding personal data: soft delete or hard delete, and why
- Any retention or deletion rule
One line each, in `docs/decisions/`. Use `/decide`.

## Never
- Hard-delete an audit record, a consent record, or anything that is evidence
- Use an `UPDATE` against a protected table as a health check. It corrupts the
  record it is protecting at the exact moment the protection has failed. Ask the
  database about the privilege instead
- Let the application connect as the owner of its own tables. An owner bypasses
  table privileges, and every guarantee built on those privileges dissolves

If a migration would lock a table with live rows, stop and ask for a strategy.