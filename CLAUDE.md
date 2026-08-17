# Project Manifest (Phase 3 Build)

Product: Sanad, a local-first document assistant: workspaces of
documents, on-demand Sync, answers with sources, honest refusals,
evaluation-gated releases. | Stack: Python 3.12, uv, FastAPI hosting
server-rendered templates, LangGraph, Qdrant embedded, SQLite,
multilingual-e5-base.

## Commands
Dev `uv run python app.py` | Typecheck `uv run ruff check .` | Tests
`uv run pytest -q` | Lint `uv run ruff check .` | E2E
`uv run pytest tests/integration -q`

## Map
Signed pack: `docs/phase2/` (write-locked; escalate, never edit).
Plan: `docs/build/BUILD-PLAN.md`. State (read first, always):
`docs/build/BUILD-STATE.md`. Decisions: `docs/build/DECISIONS.md`.
Changes: `docs/build/CHANGELOG-AI.md`. Product prompts: `prompts/`.

## Iron rules (hooks enforce most of these anyway)
1. Every task starts by reading BUILD-STATE.md.
2. Absence protocol before creating any symbol or file: graph search +
   2 name variants, project grep, written scope line. Partial reads
   prove nothing.
3. Never work on `main`. One story = one branch
   `feat/S<sprint>-ST-<nn>-<slug>` (also `fix/`, `docs/`, `chore/`).
   Story IDs are ST-01..ST-52 from the signed project plan.
4. Never `--no-verify`, force-push, or edit `docs/phase2/`. The control
   plane now lives in `~/.claude` (user-level, shared across projects),
   not in this repo; change it there, deliberately, never mid-task.
5. After each task: BUILD-STATE update, one CHANGELOG line, DECISIONS
   row for real choices, commit.
6. Commit: `type(scope): summary` + body `INTENT:` + `VERIFY:`. No AI
   attribution anywhere in commits, PRs, or issues: no `Co-Authored-By`
   trailer, no `[AI]` marker, no "generated with" footer. This is graded
   academic work; the commit log carries the team's names only.
7. Trivial tasks (single file, no schema/route change, ~15 min):
   orchestrator does them directly under the same rules; an agent
   carrying a sticky note costs more than the note.

## Delegation (agents live in `~/.claude/agents`, not this repo)
architect: plan a change before code exists, for anything adding a route,
a table, a service or a refactor over three files. scout: vet a
dependency or verify an external API against current docs (read-only).
verifier: review changed code with fresh eyes before anything is called
done. coach: end-of-session lesson.

The project-specific b1..b4 / reviewer / o1..o4 agents were removed with
the old in-repo control plane (2026-08-17). `verifier` replaces
`reviewer`, and it earns its keep: on ST-15 it found that the prefix
tests passed even with the prefix emptied in config, which would have
shipped the exact silent failure the story exists to prevent.

Every branch still gets a review pass before merge. A green suite has
never once been sufficient in this project.

## Escalate when
A docs/phase2/ spec is ambiguous or wrong, a migration is destructive,
a new dependency is requested (after scout), or an exit gate can't be
met. One question at a time, numbered options, recommendation marked.
