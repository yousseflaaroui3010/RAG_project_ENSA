# Stack defaults (all projects)

Standing preferences. Deviate only with a written reason in the project's
decision log, never silently.

## Package manager: pnpm, not npm

Use `pnpm` unless the project already has a committed `package-lock.json`
and switching is out of scope.

The reason that matters is correctness, not speed. **npm's flat
`node_modules` lets you import packages you never declared.** The code works
on your machine, passes CI, and breaks the day a transitive dependency drops
the package you were secretly relying on. pnpm's symlinked store makes an
undeclared import fail immediately, which turns a future mystery into a
present error. Disk savings and install speed are real but secondary.

Commands: `pnpm install`, `pnpm add`, `pnpm add -D`, `pnpm dlx` (not `npx`),
`pnpm run`. Lockfile is `pnpm-lock.yaml` and it is always committed.

## ORM: Drizzle, not Prisma

For anything PostgreSQL-shaped, prefer **Drizzle**.

Evidence, gathered 2026-07-30 on a real project rather than from reputation:

- **Prisma Migrate cannot express** CHECK constraints, triggers, generated
  columns, partial indexes, or COMMENT ON. On a schema with 62 checks and 13
  triggers it emitted zero of them.
- Worse than "cannot express": open Prisma 7.x issues (29175, 29220, 29263,
  29289, 12914) show `migrate dev` **DROPPING** manually created partial
  indexes and fighting generated columns, with the documented workaround
  being *remove the generated column*. It removes guards, it does not just
  skip them.
- Prisma forces a **permanent lie into the types**: a `GENERATED ALWAYS`
  column is NOT NULL in the database, but Prisma must declare it nullable
  because it cannot know it is generated. Every read carries a null check
  forever. Drizzle types it correctly and omits it from inserts.
- Drizzle's `numeric` returns **strings by default**, which is what money
  should be at every boundary. Prisma returns Decimal objects needing
  conversion everywhere.
- Drizzle expresses `check()`, `generatedAlwaysAs(..., { mode: 'stored' })`
  and partial indexes via `.where()` natively, so a TypeScript schema can
  faithfully mirror the database and a drift check can cover nearly all of
  it rather than a subset.
- Adoption is not a risk: 17.2M weekly downloads vs Prisma's 15.3M.

Known caveat to state when recommending it: as of July 2026 the stable tag
is `0.45.2` (published 2026-03-27) while `1.0` sits in release candidate.
Pin the stable tag and schedule the 1.0 upgrade; do not ship a release
candidate.

## The rule underneath both, which outranks either

**Never let a tool own an artifact that has already been authored and
signed.**

If the schema exists as reviewed SQL, that SQL is the schema. The ORM
generates types and runs queries; it does not author DDL. Migrations are
plain SQL applied by a runner that only executes what it is given.

This is what actually solved the problem above. Switching ORMs was the
smaller half of the fix. Ask "who owns this artifact?" before asking "which
library?" - the ownership question is the architectural one, and picking a
library first hides it.

Where two descriptions of the same thing must coexist (the SQL and the
ORM's model), **a mechanical drift check in CI is what makes that safe.**
Discipline is not.
