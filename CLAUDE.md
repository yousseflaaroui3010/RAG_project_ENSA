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

This repo is indexed in codebase-memory, every source file covered, 0
skipped. **Structure questions go to the graph first, not to
Read/Grep/Glob.** Mostly-flat repo: 9 root modules plus the `agent/` and
`db/` packages. Reading three files to answer "who calls X" costs more
tokens than the whole graph query does.

**No node count is written here on purpose.** It was quoted twice and
went stale twice within two days (892 -> 1,209 -> 1,350 as stories
landed), which trains a reader to distrust the whole section. Run
`index_status` if you need the number; it is one call and it is never
wrong.

Project name for every call, and copy it exactly:

```
C-Users-lenovo-OneDrive-Documents-Projects-RAG_project_ENSA
```

It contains `OneDrive`. An earlier version of this line dropped that
segment, and the name it gave matches no indexed project -- a call with it
fails, which reads exactly like the graph being unavailable and sends the
next session back to grepping.

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

## What ships with this repo

Tracked under `.claude/`, so both machines get the same set. Everything else
under `.claude/` is deliberately ignored — see the allow-list in `.gitignore`
and read the note there before adding another.

| Skill | Fires when |
|---|---|
| `report-brief` | Every reply. Plain language, and the Done / Ongoing / Left block |
| `prove-it` | A bug appears, or a check is about to be trusted |
| `test-strategy` | A test is being written, or coverage comes up |
| `research-discipline` | A check passed and the thing may still be broken |

| Agent | Use for |
|---|---|
| `reviewer` | Briefed grading of a task branch before merge (rule 5) |
| `verifier` | Cold, unbriefed read of a diff. Briefed eyes confirm; cold eyes notice |

## Core law

Short on purpose. Every line competes for attention with everything else.

**Stop and ask before:** adding, removing or upgrading any dependency; changing
anything under `docs/phase2/`; a refactor touching more than five files;
anything that spends money, sends mail, or writes outside this machine.

**Done means done.** Never report a task complete while a check is red. If you
cannot make it green, say so plainly and stop. Never disable a check, weaken an
assertion, add an ignore comment, raise a threshold, or delete a test to get
green. That is cheating the check, not meeting it.

**Read before you write.** Before changing an exported function, read the files
that import it. If you did not read a file, do not claim what is in it.

**Prove it by running it.** Typechecking proves shapes agree; it proves nothing
about the world. A check that has never executed is untested, not passing.

**Duplication.** Two copies is fine. On the third, either abstract it or write a
row in `docs/journal/DECISIONS.md` saying why not.

**Never:**
- Hand a human a `!` prefixed command, or any route running outside the tools,
  to get past a guard. Hooks do not run on those, so suggesting one is handing
  over a bypass. The only sanctioned routes are the human editing the file, or
  changing the guard in the open with the reason recorded.
- `git push --force`, `--no-verify`, or any flag that skips a hook. A gate you
  can open yourself is a sign, not a gate.
- A secret, key or connection string in a committed file.
- String-concatenated SQL, or any query built by pasting input into text.
- `==` on a cryptographic value. Use a constant-time comparison, length first.
- Logging a password, token, secret, or a full request body.

**Windows write trap.** Write repo files with the Write tool, or
`[IO.File]::WriteAllText`, or `Set-Content -Encoding utf8NoBOM`. Never `>`
redirection and never `-Encoding utf8`: both prepend three invisible bytes on
PowerShell 5.1 and tools read them as part of the first line. This is not
theoretical here — `~/.claude/rules/git-discipline.md` carries exactly that BOM.

## Rules

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
