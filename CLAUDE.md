# Sanad

Local-first document assistant: workspaces of documents, on-demand Sync,
answers with sources, honest refusals, evaluation-gated releases.

Stack: Python 3.12, uv, FastAPI serving server-rendered templates, LangGraph,
Qdrant embedded, SQLite, `intfloat/multilingual-e5-base`.

## How to report back (applies to EVERY reply, not just big ones)

Write for a smart person who does not code. Plain words, short sentences.
No jargon unless you immediately explain it in normal English. One small
example or a one-line metaphor beats a paragraph of theory. Be brief:
if a sentence does not change what the reader does next, cut it.

Say "the thing that finds your files" before you say `change_detection.py`.
Say "we broke it on purpose and watched it fail" before you say "mutation
testing". Say "two lists that must always match" before you say "drift check".

**Every time a task is finished, end the reply with exactly this block,
these three headings, in this order:**

```
## Done
- <what is finished and PROVEN, with the proof: the command, the number, the
  file. "336 tests passed" is Done. "should work" is not Done.>

## Ongoing
- <what is started but not finished, and what it is waiting on. If nothing
  is in flight, write "Nothing in flight.">

## Left
- <what has NOT been started yet, most important first. Name the next single
  step at the end, as one line: "Next: ...">
```

Rules for the block, learned the hard way on this project:

- The three headings never merge and never get renamed. A reader must be able
  to tell finished from in-progress from not-started at a glance.
- Nothing goes under **Done** unless something was actually run and watched.
  An intention is not an outcome. If it was not verified, it belongs in
  **Ongoing** with the words "not verified yet" and what would settle it.
- Keep each bullet to one or two lines. Detail goes above the block, not in it.
- Plain language applies inside the block too.

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

## Start here: query the graph before you read files

This repo is indexed in codebase-memory (892 nodes / 3,228 edges, every
source file covered, 0 skipped). **Structure questions go to the graph
first, not to Read/Grep/Glob.** Flat-layout repo, ~3,900 lines across 9
root modules: reading three files to answer "who calls X" costs more
tokens than the whole graph query does.

Project name for every call: `C-Users-lenovo-Documents-Projects-RAG_project_ENSA`

| Question | Call |
|---|---|
| Does X already exist? | `search_graph` (`query=` natural language, or `name_pattern=`) |
| Who calls X / what does X call? | `trace_path` (`direction=inbound`/`outbound`) |
| Is this file fully indexed? | `check_index_coverage` before any "X is absent" claim |
| Orientation in an unfamiliar area | `get_architecture` |

The MCP tools are deferred: load them with `ToolSearch` (`select:mcp__codebase-memory-mcp__search_graph,...`) before the first call.

**Where the graph does NOT help, so do not force it:** signed prose in
`docs/phase2/`, the journal, config files, `db/schema.sql`, and anything
greenfield. Read those. ST-17 found a binding requirement (UX spec 7.2:
Removed rows must carry a reason) that only existed in prose — no graph
query could have surfaced it.

**Absence protocol, non-negotiable here:** never conclude something is
missing from a Read/Grep sweep alone. It takes graph search + project-wide
grep + a written scope line in the report. A denied or empty-because-blocked
call is UNVERIFIED, never a negative finding.

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
