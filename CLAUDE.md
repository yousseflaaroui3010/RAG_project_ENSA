# Sanad

Local-first document assistant: workspaces of documents, on-demand Sync,
answers with sources, honest refusals, evaluation-gated releases.

Stack: Python 3.12, uv, FastAPI serving server-rendered templates, LangGraph,
Qdrant embedded, SQLite, `intfloat/multilingual-e5-base`.

## Commands

| Task | Command |
|---|---|
| Tests | `uv run pytest -q` |
| Lint | `uv run ruff check .` |
| App | `uv run python app.py` (app.py does not exist yet) |

## Map

| Path | What it is |
|---|---|
| `docs/phase2/` | The signed spec pack: PRD, Architecture, Project plan, UX spec, OpenAPI. **Write-locked. Escalate, never edit.** |
| `docs/journal/BUILD-STATE.md` | Current state. Read this first, always. |
| `docs/journal/CHANGELOG-AI.md` | One line per change, appended, never edited |
| `docs/journal/DECISIONS.md` | Index of real choices, one row each |
| `docs/journal/BUILD-PLAN.md` | Stories ST-01 to ST-52 with owners and exit gates |
| `prompts/` | Product prompt registry |

## Rules

The working rules, agents and skills live in `~/.claude/`, shared across
projects, not in this repo. They cover journal discipline, decision records,
review standards and the rest. This file only carries what is specific to
Sanad.

Sanad-specific, and not negotiable:

1. `docs/phase2/` is signed. If a spec is wrong or ambiguous, escalate; never
   edit the spec to match the code.
2. One story = one branch, `feat/S<sprint>-ST-<nn>-<slug>` (also `fix/`,
   `docs/`, `chore/`). Never work on `main`.
3. `git push origin <branch>` with the branch named explicitly.
4. **No AI attribution anywhere** in commits, PRs or issues: no
   `Co-Authored-By` naming an assistant, no `[AI]` marker, no "generated
   with" footer. This is graded academic work and the history carries the
   team's names only. Human co-authors are credited normally.
5. Every branch gets a review pass before merge. A green suite has never once
   been sufficient on this project: ST-11 went through three review rounds and
   each one found a real defect while the tests were green.

## Team

Two people. Story owners are recorded in `docs/journal/BUILD-PLAN.md`; the
recorded owner and the actual author have drifted before, so check before
starting and say so if you take something assigned to the other person.
