---
name: contract-types-regen
description: Keep types in lockstep with the contract after any route, action, or schema change. Use whenever a Zod schema, Server Action signature, route shape, request/response type, or database-facing DTO changes, or when the external OpenAPI surface changes.
---

# Type-Safe Contract Regeneration

Hand-copying interface shapes is copying a recipe onto scrap paper:
one typo ruins the dish. The schema is the printing press.

## Which mechanism applies

This project has two contract surfaces, decided in S2-A2 (D-S2-05). Check
which one you are touching before doing anything.

**Internal** (Server Actions and route handlers inside the one deployable):
the Zod schema IS the contract. No generator runs, because no network boundary
separates two independently compiled codebases. TypeScript is the generator.

**External** (SpaceSeller webhook inbound, SpaceSeller dispatch outbound, the
Google Sheets column mapping): OpenAPI 3.1 at
`docs/build/architecture/openapi/atad.yaml`. Only these three paths. An outside
party controls the other side, so a formal document earns its keep.

> Orval and generated clients were considered and overridden by human ruling on
> 2026-07-29. S1-A3 chose one deployable, so a generator would bridge a gap that
> does not exist. Do not reintroduce one without a new ruling.

## Procedure, internal surface

1. Update the Zod schema first. Never start from a type file or a component.
2. Derive every type from it with `z.infer<typeof Schema>`. Never write an
   interface that mirrors a schema. That is the hand-copying this skill exists
   to prevent.
3. Update the Data Access Layer function the action calls. Its declared return
   shape is part of the contract (S2-A2 §3 rule 4), so a widened schema with an
   unchanged return shape is an incomplete change.
4. Typecheck the whole workspace. Compile errors at call sites are the contract
   working: fix the callers, never loosen the schema to silence them.
5. Commit the schema, the DAL change and the caller fixes in ONE commit. Split
   across commits, main sits in a state where the types lie.

## Procedure, external surface

1. Update `openapi/atad.yaml` first.
2. Update the Zod schema that validates the payload at the boundary, and keep
   the two in agreement by hand. Three paths makes that cheap. If it stops being
   cheap, that is the signal to revisit D-S2-05.
3. Add or update the mock in the same commit. The mock is the only verifiable
   target until H-02 delivers the real SpaceSeller contract.
4. Assert idempotency (S2-A2 §4.3). A replayed webhook is a no-op returning the
   first outcome, per S4-A1 assertion A-04.2.

## Hard rules

- No manual copy-paste of type definitions between modules, ever.
- No interface that duplicates a Zod schema. Infer it.
- Nothing outside `src/dal/**` imports Prisma, enforced by a CI sweep (S2-A2 §3
  rule 5). If a change seems to need a Prisma call inside an action, the change
  is wrong.
- Money crosses every boundary as a decimal string, never a JS number (D-S2-08).
  Points are integers and never convert to money.
- Zod 4 idioms only: `z.email()` rather than `z.string().email()`,
  `z.record(k, v)` with both arguments, `z.guid()` where a v3-style UUID is meant.
- No contract carries a numeric default for a rate, cap or threshold. Every one
  of those is a runtime setting (F3.2.6), and S4-A1 assertion A-03.4 sweeps for
  violations.
- Every error uses the one envelope in S2-A2 §4.2. No stack traces, no Prisma
  error text, no SQL in a response.
- If the change diverges from the signed Phase 2 contract, stop and escalate
  before writing anything.
