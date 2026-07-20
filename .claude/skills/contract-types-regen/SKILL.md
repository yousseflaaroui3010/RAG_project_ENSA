---
name: contract-types-regen
description: Regenerate shared frontend types from the backend API schema after any route or schema change. Use whenever an OpenAPI spec, route shape, request/response type, or database-facing DTO changes.
---

# Type-Safe Contract Regeneration

Hand-copying interface shapes is copying a recipe onto scrap paper:
one typo ruins the dish. The generator is the printing press.

## Procedure
1. Update the source of truth first: the OpenAPI schema (or route schema
   definitions) that Phase 2 contracts define. Never start from the
   frontend type file.
2. Run the generator (Orval or the project's configured tool) to emit
   the typed client and interfaces. Command lives in CLAUDE.md.
3. Commit the regenerated files IN THE SAME commit as the backend change.
   A route change without its regenerated types is an incomplete change.
4. Run the typecheck across the whole workspace. Frontend compile errors
   after regeneration are the contract doing its job: fix the callers,
   never the generated file.
5. If the generator output looks wrong, the schema is wrong. Fix the
   schema, regenerate. Generated files are never edited by hand.

## Hard rules
- No manual copy-paste of interface definitions between packages, ever.
- Generated files carry a do-not-edit header; treat it as law.
- If the change diverges from the signed Phase 2 contract, stop and
  escalate before generating anything.
