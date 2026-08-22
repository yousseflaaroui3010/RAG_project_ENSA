---
name: zero-lock-migration
description: Safe expand-contract procedure for changing a live database schema without locking tables or breaking running code. Use for any migration that renames, retypes, moves, or removes a column or table under real traffic.
---

# Zero-Lock Database Migration (expand -> dual-write -> backfill -> contract)

Changing a live table in one shot is carving an engine part mid-flight.
This procedure splits the change into steps that are each safe alone.

## Steps (one PR per step, in order, never combined)
1. EXPAND: add the new column/table alongside the old one. Nullable or
   defaulted, so old code keeps working untouched. Dry-run the migration
   first; confirm it takes no long lock (no full table rewrite).
2. DUAL-WRITE: change application code to write BOTH old and new fields.
   Reads still come from the old field. Deploy and watch for a full cycle.
3. BACKFILL: copy old data to the new field in small batches (bounded
   UPDATE loops with sleeps), never one giant UPDATE. Verify counts and
   checksums match between old and new.
4. SWITCH READS: point reads at the new field. Keep dual-writing.
   Watch error rates for a full cycle before the next step.
5. CONTRACT: stop writing the old field, then, in a later release,
   drop it. Dropping is the only destructive step and requires explicit
   human approval per the backend rules.

## Hard rules while using this skill
- Down-migration exists and is tested for every step.
- Each step is its own task branch with its own VERIFY line.
- If any step misbehaves, roll back that step only; earlier steps are
  designed to stay valid.
- Never run steps 1 and 5 in the same day on the same table.
