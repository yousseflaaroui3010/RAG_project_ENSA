# Project Manifest (Phase 3 Build)

Product: Sanad, a local-first document assistant: workspaces of
documents, on-demand Sync, answers with sources, honest refusals,
evaluation-gated releases. | Stack: Python 3.12, uv, FastAPI hosting
Gradio Blocks, LangGraph, Qdrant embedded, SQLite, multilingual-e5-base.

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
4. Never `--no-verify`, force-push, or touch `.claude/hooks/`,
   `.claude/settings.json`, `docs/phase2/`.
5. After each task: BUILD-STATE update, one CHANGELOG line, DECISIONS
   row for real choices, commit.
6. Commit: `type(scope): summary` + body `INTENT:` + `VERIFY:`. No AI
   attribution anywhere in commits, PRs, or issues: no `Co-Authored-By`
   trailer, no `[AI]` marker, no "generated with" footer. This is graded
   academic work; the commit log carries the team's names only.
7. Trivial tasks (single file, no schema/route change, ~15 min):
   orchestrator does them directly under the same rules; an agent
   carrying a sticky note costs more than the note.

## Delegation (.claude/agents/)
scout: vet dependencies, verify external APIs, audit doc drift
(read-only). b1: merges, squash, integration. b2: APIs, logic, schemas,
migrations. b3: UI, states, a11y, RTL. b4: tests, CI/DevOps, isolated
e2e, triage. reviewer: read-only grade of every branch before b1.
o1..o4: dormant in .claude/agents-phase4/ until launch.

## Escalate when
A docs/phase2/ spec is ambiguous or wrong, a migration is destructive,
a new dependency is requested (after scout), or an exit gate can't be
met. One question at a time, numbered options, recommendation marked.
