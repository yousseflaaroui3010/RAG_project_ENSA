# CLAUDE.md, Sanad project memory

Sanad is a local-first document assistant: workspaces of documents, on-demand Sync, answers with sources, honest refusals, evaluation-gated releases. Two-person team: YL (build owner), MB (research and quality owner). Master's defense project on a four-week clock.

## Binding documents, in order of authority

1. `docs/Sanad_PRD_v1.0.md` (what the product does; features F-01 to F-16 with acceptance criteria)
2. `docs/Sanad_Architecture_v1.0.md` (how it is built; module map section 4, flows section 5, data layer section 7, stack pins section 8, git and CI rules section 12)
3. `docs/Sanad_ProjectPlan_v1.0.md` (when and by whom; stories ST-01 to ST-52)
4. `docs/api/openapi.yaml` (the HTTP contract of record; the drift test keeps code and contract equal)

Before designing anything, read the relevant sections. The architecture wins over improvisation. If a story seems to require breaking an ADR, stop and say so; do not quietly work around it.

## Session ritual

1. State the story ID being worked (example: ST-17) and restate its acceptance criteria from the plan.
2. Plan the change before writing code. Small steps, verified as you go.
3. One story per branch: `feat/S<sprint>-ST-<nn>-<slug>`, `fix/<issue>-<slug>`, `docs/<slug>`, `chore/<slug>`.

## Git rules (non-negotiable)

- Never commit to `main`. Never force-push. Everything merges through a pull request using the template.
- Conventional Commits with the story ID: `feat: ST-17 sync engine end to end`.
- Keep diffs small and single-purpose. If a change wants to touch two modules for two reasons, that is two branches.
- Never stage or commit: `.env`, anything under `data/`, model caches, or generated stores.
- `evaluation/golden/` belongs to MB. Only touch it when the story says so.

## Hard technical rules

- Every embedded chunk text starts with `passage: ` and every search query with `query: `. A unit test enforces this. Keep it green; never delete or weaken it.
- Open every SQLite connection with `PRAGMA foreign_keys = ON` (done in `db/repo.py`; use it, do not create ad-hoc connections).
- One Qdrant collection per workspace. No query ever reads across workspaces.
- An answer object without at least one source does not render as final; it routes to the refusal path instead.
- The retry ceiling comes from config. Never hardcode it.
- All tunables live in `config.py` and `.env` (documented in `.env.example`). No magic literals in module code.
- Tests use the scripted fake chat model. No API keys in tests, fixtures, or CI.
- Routes in `api/` delegate to service functions only; no business logic inside a route body. The server binds to 127.0.0.1.
- An endpoint change and its `docs/api/openapi.yaml` change travel in the same branch; the drift test enforces this.
- New dependency: only if the story requires it, added to `pyproject.toml` via uv, with a one-line justification in `docs/journal.md`. The pinned stack in architecture section 8 is not yours to upgrade or replace.

## Forbidden

- Features or behaviors not backed by a story. Ideas go to the backlog, not the branch.
- Copying code from the reference study folder (`agentic-rag-for-dummies` clone outside this repo). Patterns may be reimplemented and cited in the journal; files and functions are never pasted.
- Skipping, deleting, or loosening tests to make CI pass.
- Touching branch protection, repository settings, or secrets. Those are human-click actions.

## Definition of done for every change

1. Acceptance criteria of the story pass.
2. `uv run ruff check .` and `uv run pytest` green locally.
3. End the session by writing a plain-English explanation of the diff: what changed, why, and how to verify it by hand. The story owner must be able to retell it in one minute without notes; write for that.
4. If a problem was met and solved, add a `docs/journal.md` entry: symptom, root cause in one sentence, fix.

## When unsure

Stop and ask. Offer numbered options with trade-offs. Never guess a schema, a version, or an API shape; the architecture and the lockfile are the authorities.

Reference: Claude Code project memory documentation (Claude Code docs, Memory page). This file is team-shared project memory, loaded automatically each session; keep it under 200 lines.
