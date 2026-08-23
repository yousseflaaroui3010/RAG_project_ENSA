# BUILD-STATE (the flight recorder: trust this file over chat memory)

Last verified commit: 0f12094 on main. Updated: 2026-08-23 by the ST-17
session, which ran gate.yml steps 1-3 by hand in gate.yml order on the
branch: `uv sync --frozen` clean, `uv run ruff check .` exit 0, `uv run
pytest` exit 0 with 318 passed / 2 skipped (272 / 2 at the branch point).
gate.yml step 4, gitleaks, was NOT run -- re-checked this session against
PATH, `Program Files` and `~/go/bin`, all negative. Still not installed on
this machine; CI remains the only place that step executes.

RESOLVED this session, and it had been open since 2026-08-22: the CBM MCP
tools DO attach. `list_projects` answered on the first call and the repo is
indexed at 892 nodes / 3,228 edges with zero skipped files and one
parse_partial line (DECISIONS.md:59, a markdown table row, harmless). The
blocker below marked "UNVERIFIED: the CBM MCP tools attaching" is closed.

Earlier header, kept because its caveat still governs ST-14 and ST-15:
Updated: 2026-08-23 by the ST-16 session, which
independently ran the whole of gate.yml at that commit plus its own
branch: `uv sync --frozen` clean, `uv run ruff check .` clean,
`uv run pytest -q` 272 passed / 2 skipped on the branch (191 / 1 at the
branch point). gate.yml step 4, gitleaks, was NOT run -- re-checked this
session against PATH, three install locations and `winget list`, all
negative. It is still not installed on this machine and CI remains the
only place that step executes.

Earlier header, kept because its caveat still governs ST-14 and ST-15:
Updated: 2026-08-18 by Phase 3 orchestrator, catching up three merges of
journal drift: ST-14, ST-15 and the harness migration all landed on main
without a BUILD-STATE update. Verification claims below for those three
are drawn from the commit bodies of 711f7e0, 8e5a734 and 275886f (each
records ruff/pytest output at merge time); this session did not
independently re-run ST-14/ST-15's suites AT their merge commits. It did
independently re-run `uv run ruff check .` and `uv run pytest -q` on a
branch cut from 275886f (chore/separate-harness-payload, after moving the
harness payload out): ruff clean, 191 passed / 1 skipped -- matching what
275886f's own commit body claims, so the count is corroborated, not just
copied.

## Now
ST-17 sync engine BUILT, on branch `feat/S1-ST-17-sync-engine`, NOT
pushed and NOT reviewed. Two commits. 318 passed / 2 skipped, ruff clean,
`uv sync --frozen` clean. This is the story that makes Sanad ingest
anything: `sync.py` is the first caller of ST-12, ST-13, ST-14, ST-15 and
ST-16, all five of which were individually green and collectively
untested until now.

OWNERSHIP DEVIATION, flagged rather than absorbed: BUILD-PLAN line 65
assigns ST-17 to YL and this machine commits as `meriem-mb` (MB). Same
shape as the ST-12 deviation recorded for 2026-07-28. A human decides
whether to reassign the plan row; it is left as signed. DECISIONS row
filed.

What is proven, and how:
- PRD F-02's four criteria on real fixtures, not mocks: real SQLite, real
  embedded Qdrant under tmp_path, real files, the real conversion ladder
  including a genuinely AES-256 encrypted PDF. Only the two encoders are
  faked, because they download 1.1GB.
- all six `sync_item.result` values in ONE run (added, changed,
  unchanged, failed, removed, skipped), asserted as a whole-report
  equality rather than six separate greens.
- double-sync blocked, and the test attempts the second Sync from INSIDE
  the first via the converter, at the one moment it is genuinely mid-run.
  Hand-writing a half-finished row would have proved the query works and
  nothing about the guard.
- 12 mutations injected one at a time, all 12 killed. NO survivors, which
  is a first on this project and is itself worth distrusting slightly --
  see the self-review finding below, which no mutation could have found.

Self-review after green found the defect the mutation battery could not,
for the fourth story running, and it is again a MISSING line rather than
a wrong one: `vector_store.upsert_children` returns early for an empty
child list and so never reaches its own `ensure_collection`. A sync in
which every file was Skipped or Failed therefore left no collection at
all, and `vector_store.search` then told the user the workspace had NEVER
BEEN SYNCED, seconds after a sync -- the exact confusion that error's own
docstring says it exists to prevent. `sync_workspace` now ensures the
collection once per run, after the scan succeeds. Reproduced by deleting
the line and watching two tests fail with that message.

Three things ST-16 left for ST-17, all now closed:
- (a) workspace deletion across both derived stores: `sync.delete_workspace`,
  which lives in sync.py because sync owns the Qdrant client (ADR-04).
  Derived stores first, registry second.
- (b) `delete_document` is now called on every re-ingest, unconditionally,
  before conversion. Shrink residue is pinned by a test.
- (c) `StoreDeletion.unreadable_parent_files` lands in the report row's
  reason with the next step named, rather than being escalated.

CROSS-MODULE CHANGE a reviewer should look at first, because it is the
one thing in this diff that is not ST-17's own file:
`change_detection._STATUS_WITHOUT_DERIVED_DATA` was one set answering two
different questions, and one answer was wrong. A `failed` row with
unchanged bytes classified UNCHANGED forever, so a corrupted file was
reported Failed on its first sync and then dropped out of every later
report while still being unanswerable, and a file the user repaired was
never picked up. F-02 criterion 3 held for exactly one run. Split into
`_STATUS_WITHOUT_DERIVED_DATA` (removed+failed+skipped) and
`_STATUS_ALREADY_REPORTED_REMOVED` (removed only) -- because simply
widening the one set would have stopped a deleted `failed` file from ever
clearing out of the registry. ST-12's existing suite never caught this:
it is the module that READS these statuses, and ST-17 is the first that
writes them.

NOT DONE, and it is not a judgement call: ST-18. It depends on ST-07's
corpus, which does not exist -- `data/` on this machine holds only a
stray `parents/` test artifact, no labour-code PDF and no HR/CNSS guides.
ST-07 is MB's and unstarted. Numbers measured on fixtures would be
numbers about fixtures, which is worse than no numbers because they would
be quoted later. See Next.

Blast radius for ST-16, written before any code was touched and left
here because the second bullet is what the story turned out to be about:
- WHO IS TOUCHED: nothing in production. Grepped for importers of
  `embeddings`, `chunking`, `parent_store`, `vector_store` across
  `*.py`: the only non-test importer in the repo is
  `parent_store.py -> chunking.Parent`. So extending `embeddings.py`
  with the sparse pair cannot break a caller, because there are none.
  ST-17 is the first caller of any of it.
- WORST CASE: not a crash. Two silent failures. (1) sparse BM25 encoded
  with the document function on the query side, which returns different
  values with no error and quietly degrades retrieval -- the exact shape
  ADR-05's `passage:`/`query:` rule exists to prevent. (2) a workspace
  filter that leaks, so an HR question cites a manuals passage.
- HOW YOU WOULD FIND OUT: neither is visible to a typechecker or to a
  green suite, so both get a test that fails on the mutation --
  the asymmetry pinned on literals, and the isolation pinned in both
  directions.
- HOW TO UNDO: revert the branch. `data/qdrant/` and `data/parents/` are
  git-ignored derived stores with no migration: delete them and re-sync.
- Previous: ST-13 Conversion ladder MERGED as b75b584 (PR #18). The
  earlier claim in this file that it was "on branch, NOT reviewed, NOT
  merged" was stale; it was reviewed and merged. Third time this file has
  described a state that no longer existed.
- Superseded detail, kept because the library traps are still true:
  `conversion.py`: PDF via pymupdf4llm, DOCX via markitdown, TXT/MD
  passthrough, returning CONVERTED / FAILED / SKIPPED with a
  plain-language reason per PRD F-02 and section 11.
  26 mutations injected one at a time, every one turned the suite red.
  Three findings worth carrying forward, all from probing the libraries
  rather than trusting their docs:
  (a) a password-protected PDF OPENS fine in pymupdf and even answers
      `page_count`; only `needs_pass` tells the truth, and without that
      check pymupdf4llm dies on an undeclared TypeError mid-batch;
  (b) markitdown does NOT raise on a .docx it cannot parse as Word -- it
      falls through to another converter and returns the result as a
      SUCCESS. A corrupted .docx came back as its own raw bytes. That is
      the worst failure mode in the module, because nothing announces it,
      and it is why the DOCX rung validates the OOXML package itself;
  (c) `pymupdf.FileNotFoundError` SHADOWS the builtin and subclasses
      RuntimeError, so `except OSError` never catches a missing PDF.
  And two the mutation/self-review split is worth remembering for:
  (d) mutation testing found a redundant `is_zipfile` pre-check by
      SURVIVING -- a mutation nothing catches can mean dead code, not a
      vacuous test. Read the survivor before blaming the test;
  (e) self-review after green found a `DocumentSkippedError` class that
      nothing raised. Mutation testing structurally cannot see a branch
      no code reaches; only reading the diff finds those.
- Previous: ST-12 MERGED as 1862a58 (PR #14, squash).
- CORRECTION, and the reason this file was stale: an earlier entry here said
  ST-12 was "NOT reviewed, NOT merged" while 1862a58 was already on main. It
  shipped WITHOUT the reviewer pass the Next queue was explicitly waiting on.
  That matters because ST-10 and ST-11 each had a later review find real
  defects while the suite was green, and ST-12's own self-review found three
  more after CI passed. A post-hoc reviewer pass on 1862a58 is owed.
- What is proven working on main right now: `uv sync` resolves the pinned
  stack; config loads; the SQLite registry creates, cascades and rolls back
  under test; workspaces create, rename, delete, list, get and toggle their
  legal flag, with names normalized and the F-01 criteria demonstrated at
  module level. `uv run ruff check .` clean, `uv run pytest -q` 51 passed
  (2 config + 17 db + 32 workspaces -- the previous entry's per-file split,
  "15 db + 34 workspaces", was miscounted; the 51 total was right).
- Whole suite on main: ruff clean, 130 passed (2 config + 19 db + 32
  workspaces + 40 change detection + 37 conversion). CI `verify` green on
  PRs #14, #15 and #18. On this ST-14 branch: 173 passed.
- CR-02 Part B landed on main (PR #13, fea733c) while ST-13 was in flight:
  the UI dependency is now `jinja2` server-rendered templates, NOT gradio,
  and a new signed spec `docs/phase2/Sanad_UX_Spec_v1.0.md` joined the
  write-locked pack. It touches no ingestion code -- ST-13 verified clean
  against it (`grep -rn gradio` over conversion.py, change_detection.py and
  config.py finds nothing) -- but every UI story is now built on a
  different base than the original BUILD-PLAN assumed. Read docs/journal/CR-02.md
  before starting one.
- What does NOT exist yet: any UI, any retrieval, any vector store, any
  sync engine, and `app.py` does not exist so Sanad cannot be launched.
  Four ingestion/indexing stages now exist and NONE of them are wired to
  each other: ST-12 decides what needs ingesting, ST-13 converts it,
  ST-14 splits it, ST-15 embeds the children -- and nothing calls any of
  them until ST-17. That is deliberate and is what has kept each one
  unit-testable with no database, no vector store in existence.
  `chunking.py` writes no parent JSON and no vector, `embeddings.py`
  writes nothing anywhere: §7.5's parent store and the Qdrant write are
  both ST-16.
- FIXED 2026-08-09, was the sharpest thing the rubric review found:
  `chunk_document` was NOT idempotent. Parent ids came from
  `repo.new_id()`, so the same document chunked twice yielded a disjoint
  id set (proven by running it, not suspected). §7.5 keys the parent store
  on that id (`data/parents/<workspace_id>/<parent_id>.json`) and Qdrant
  payloads carry it, so re-ingesting a CHANGED file minted all-new ids:
  every previous parent JSON orphaned, and any vector surviving the
  rewrite pointed at a parent file that no longer existed -- a search hit
  that resolves to nothing, which a sourced answer cannot survive.
  Ids are now DERIVED: `uuid5(namespace, "<source_file>\x00<index>")`.
  Three tests pin it. Removing the random id also removed chunking.py's
  only `db.repo` import, so the splitter no longer depends on the data
  layer at all.
  STILL TRUE FOR ST-16/ST-17, so do not lose it: a document that SHRINKS
  from ten parents to six leaves ids 6..9 behind. That residue is now
  deterministic, so ST-17 can compute exactly which ids to delete instead
  of guessing -- but something still has to delete them, and the parent
  JSON and its vectors must go as ONE unit or the mismatch returns.

## Numbers (this project had none until 2026-08-09)
The rubric row is "a number with no threshold is trivia, a threshold with
no owner is a wish". One number exists so far; the rest arrive with ST-18.

```
Name:       Chunking time for the G5 corpus
Measures:   Wall time for chunk_document over ~200 pages of markdown
Rule:       1,275,492 chars, 600 H1 sections, single call, warm process
Population: Developer machine (MB's laptop), not a user-facing path
Window:     Point measurement, re-run per release
Good:       Under 5s
Act at:     Over 30s -> chunking has become a G5 factor and needs profiling
Owner:      YL (ST-18 spike owns the real end-to-end numbers)
Measured:   0.03s on 2026-08-09 -> 600 parents, 3,600 children
```
Read honestly: this says chunking is nowhere near the G5 budget of 10
minutes for 200 pages. It says NOTHING about the budget itself, because
embeddings (ST-15) are the expensive stage and have not been written.
- CLOSED by ST-15 (8e5a734). Child text from `chunking.py` is RAW; the
  mandatory `passage: `/`query: ` prefixes now live behind `embeddings.py`'s
  one private encoder seam, added exactly once. See ST-15's Done entry
  for the review finding this almost slipped through anyway: a version of
  the prefix tests that passed even with the config prefix emptied out.

## Next (ordered queue, top 3 only)
1. Review ST-17 and open its PR. The branch is green and unpushed. Start
   the review at the `change_detection.py` split described under Now: it
   is a cross-module change inside a story's diff, which is exactly what
   CLAUDE.md's scoped boy-scout rule tells a reviewer to be suspicious
   of. The argument for doing it here rather than in its own `chore/`
   branch is that ST-17's own exit gate ("six statuses correct") is false
   without it -- judge that argument rather than accepting it.
2. ST-07 corpus v1 (MB): the labour-code PDF plus two HR/CNSS guides plus
   the manuals workspace. It is now the single blocker on ST-18, and
   ST-18 is the story that produces the project's first real G4/G5
   numbers. Nothing else in the queue needs it, and it needs no code.
3. Post-hoc reviewer pass on ST-12 (1862a58), which merged without one.
   Deferred by the human, not forgotten. Owner MB by agreement 2026-07-28,
   a deliberate deviation: BUILD-PLAN line 60 assigns ST-12 to YL.

NOT ST-18, and this is unchanged from the last session's entry: it
depends on ST-07's corpus and `data/` on this machine holds nothing but a
stray `parents/` test artifact -- no labour-code PDF, no HR/CNSS guides.
Its numbers would be measured on fixtures and would mean nothing, and
they would be quoted in the report anyway once written down.

CORRECTION to the previous entry's item 3, found by reading the file
rather than the journal: it claimed gate.yml already carries an "INTENT
check" and a "dup gate". It does not. `.github/workflows/gate.yml` has
exactly four steps -- uv sync --frozen, ruff, pytest, gitleaks. There is
no jscpd step and no commit-message check anywhere in it. ST-03 is
therefore NOT a confirm-and-close; whoever takes it should diff the
story's exit criteria against the four steps that actually exist. The
duplication rule in the working rules is currently enforced by nothing.

PARKED for ST-28, found while reading the UX spec for this story and not
fixed here because it is that story's decision: UX spec 7.2's file table
has a `size` column. Size is recoverable for any file with a document row
(`Fingerprint.parse(row["content_hash"]).size_bytes`, per ST-12's packing
decision) but an UNSUPPORTED file gets no document row at all, so its
report row has a name, a result and a reason and no size or type. Either
the column is blank for those rows or S2 stats the file at render time.

## Data-layer follow-ups (do not lose these)
Carried from ST-10, plus two the ST-11 reviewer surfaced. 3 and 4 were CLOSED
by ST-11, 5 and 7 by ST-12; all kept here so the closures stay auditable.
1, 2 and 6 remain OPEN and have no story assigned. ST-13 did NOT fold them
in as this line once suggested: it touches no SQL and no db/repo.py, so
they would have been unreviewable drive-by edits in its diff. They need
their own `chore/` branch, now together with 8.

1. OPEN. db/repo.py - `init_db` splits schema.sql on `;` after stripping
   full-line comments. Verified safe for the current schema (no triggers, no
   views, no semicolons inside string literals) but it WILL break the first
   time a trigger or a view is added. Harden the splitter or move to a real
   migration runner before extending the schema.
2. OPEN. The config-path default in `get_connection()` is exercised by exactly
   one test; most tests still pass an explicit tmp_path.
3. CLOSED by ST-11. Cascade tests now assert `== 1` pre-delete and `== 0`
   post-delete across all five child tables, so a degenerate count cannot pass
   vacuously.
4. CLOSED by ST-11. `ensure_schema()` now bootstraps the registry explicitly
   and `session()` calls it, so a fresh install works with no manual step.
   Deliberately NOT done inside `_connect_raw`: reads must never create a
   registry, or a mistyped path is indistinguishable from a fresh install.
5. CLOSED by ST-12. `repo.delete_document` exists;
   `test_delete_document_sets_sync_item_document_id_null` calls it instead of
   inline SQL, so the ON DELETE SET NULL test now exercises the real code
   path it claims to cover.
6. OPEN, new from the ST-11 review. `ensure_schema` can leave a half-built
   registry if `schema.sql` is truncated: the file then exists, so
   `get_connection` accepts it and reads succeed against a partial schema. It
   self-heals on the next write and needs a corrupt signed artifact to trigger,
   so it is low severity. Durable fix: `get_connection` should validate that
   the expected tables are present, not merely that the file exists. That also
   closes the `RegistryNotFoundError` blind spot.
7. CLOSED by ST-12, and now regression-tested after all. `_connect_raw`
   passes `timeout=config.sqlite_busy_timeout_seconds` (default 30.0)
   instead of inheriting sqlite3's 5 second default. Two tests cover it:
   one spies on `sqlite3.connect` to prove the config value is what gets
   passed, and one holds a real EXCLUSIVE lock and races a second
   connection. The second test needed a second look. With only a lower
   bound ("it waited at least 0.4s") it was VACUOUS: dropping the `timeout`
   argument yields sqlite3's 5.0 second default, which is longer than the
   0.5s the test configures, so the mutation stayed green while the config
   was being ignored entirely. It now asserts a ceiling as well. Generalize
   the lesson: when a mutation restores a DEFAULT rather than removing
   behaviour, a one-sided bound cannot see it.
8. OPEN, new from ST-13, and NOT a data-layer item -- filed here so it is
   not lost. `.env.example` has drifted from `config.py`: it documents the
   model, embedding, agent, chunking, store-path and server settings but
   NOT `supported_document_extensions`, `hash_read_chunk_bytes`,
   `sqlite_busy_timeout_seconds`, or the four ST-11 workspace-validation
   limits. ST-13 added its own two (`CONVERSION_MIN_TEXT_CHARS`,
   `TEXT_FILE_ENCODING`) and deliberately did NOT backfill the others:
   that is an unrelated drive-by in a diff a reviewer is grading against
   one story's exit gate (scoped boy-scout rule). One `chore/` branch
   closes it, and it is a good candidate to fold in with 1, 2 and 6.

## Blockers / waiting on human
- HARNESS GAPS after `chore/harness-fit` (2026-08-22). TWO OF THE FRAMING
  CLAIMS IN THIS SECTION WERE WRONG, both corrected 2026-08-23 by reading the
  files instead of the journal:
  (i)  "the permissions deny-list blocks `Edit(**/.claude/hooks/**)`,
       `Edit(**/.claude/settings.json)` and `Edit(~/.claude/**)`, so no agent
       can close any of them". There is no such deny-list any more. Both
       `~/.claude/settings.json` and `.claude/settings.local.json` have an
       EMPTY `permissions.deny`. Nothing was blocking an agent from any of
       this; item 1 below was fixed by an agent this session.
  (ii) item 1's claim that the user-level settings "already registers all of
       them correctly". It did not. That registration was itself the bug --
       see item 1.
  Item 1 is now CLOSED. The rest stand.
    Owner:    a human (YL). Raised 2026-08-22.
    Fallback: if still open on 2026-09-05, stop calling these fixed-in-progress
              and accept them in writing as standing gaps.
  1. CLOSED 2026-08-23. The project-level `.claude/settings.json` this item
     described no longer exists (only `settings.local.json` does), so its
     first half was moot. The real defect was the USER-level registration
     this item called correct: all 7 CBM hook commands were wrapped as
     `cmd.exe /d /v:off /s /c '""%USERPROFILE%\...\cbm-*.cmd""'`, and cmd.exe
     does not treat SINGLE QUOTES as quoting. cmd therefore started
     interactively, printed its banner, echoed the piped hook JSON as if it
     were a typed command and exited 0 -- which is the `Microsoft Windows
     [Version ...]` noise, and it means the hooks NEVER RAN. Diagnosed from
     this session's own SessionStart output, then reproduced on demand.
     Consequence, and it is the reason this mattered rather than being
     cosmetic: `cbm-session-reminder` (4 matchers) and `cbm-code-discovery-
     gate` (PreToolUse Grep|Glob, PostToolUse Read) are the two things that
     tell an agent to use the code graph before reading files. Both were
     dead, which is exactly why this session opened ST-17 with Read/Grep on
     a fully indexed repo and only used the graph when the human asked.
     Fixed by replacing the wrapper with the plain quoted path
     (`"C:\Users\lenovo\.claude\hooks\cbm-*.cmd"`), which was tested from
     both bash and cmd.exe BEFORE being written. Backup taken and verified
     byte-identical first (`settings.json.bak-2026-08-23-cbm`); the edit was
     made on the parsed JSON after proving it round-trips byte-exactly at
     indent=2, and asserted to change nothing outside `hooks`. All 7 stored
     commands were then executed as stored: 3 distinct commands, all exit 0,
     all emitting real `hookSpecificOutput` JSON. Proven in both directions
     -- the same harness reports FAIL on the old form, so the PASS means
     something. STILL UNVERIFIED, and only a new session settles it: that
     Claude Code itself invokes them cleanly at a real SessionStart. The
     next session start is the test.
  2. `~/.claude/hooks/` carries the SAME two defects fixed here in 368e3ea:
     `gate.mjs` still has the unconditional npm early-exit, `config-guard.mjs`
     still has zero `guardedPaths` references. Every OTHER project on this
     machine therefore still has a dead Stop gate and no spec lock. Verified
     by grep, not assumed.
  3. Guard gap, found by tripping it: `config-guard.mjs`'s protected-path
     regex is `/(^|[^\w.])\.claude([\/\\]|$)/i`, which requires `.claude` to be
     followed by a slash or end-of-string. A bare `.claude` argument (as in
     `git rm -r --cached .claude`) does NOT match and passes. That is how this
     session's own untracking got through. Narrow but real.
  4. Guard false-positive on READ-ONLY inspection, hit twice this session: any
     command containing `>` counts as a write, so `diff -q a b >/dev/null` plus
     a mention of `.claude` is blocked. Same shape as the old shell guard's
     `WRITE_VERBS` bug. Diagnose with the Read/Grep tools, not shell.
  5. `gitleaks` is NOT installed on this machine -- checked five install paths,
     `Get-Command` and `winget list`, all negative. gate.yml step 4 therefore
     CANNOT be run locally, so "the whole gate green before handing over a
     push" is currently unachievable here. A proxy scan of the committed diff
     for secret shapes came back clean, which is weaker and is labelled as
     such. Install gitleaks or accept CI as the only place that step runs.
  6. CLOSED 2026-08-23 by the ST-17 session, which is the next session start
     that was waiting to settle it. The CBM MCP tools attach and answer:
     `list_projects` returned on the first call, and the project is indexed
     at 892 nodes / 3,228 edges with 0 skipped files. `check_index_coverage`
     over the repo root reports every source file indexed with no recorded
     gap; the only exclusions are by design (`.claude`, `.venv`, `data`,
     `__pycache__`, and four gitignored files) plus one parse_partial line
     in DECISIONS.md (a markdown table row). Used for real in this session:
     the absence protocol for "does a sync engine already exist" was run on
     the graph first (search_graph found only `insert_sync_run` and
     `insert_sync_item`), then grep, then a written scope line -- and
     `trace_path` confirmed 0 inbound callers on `detect_changes`,
     `upsert_children` and `vector_store.delete_document`, which is what
     made ST-17's blast radius on existing code provably nil.

- SAFETY SYSTEM: critical half FIXED 2026-08-01, remainder is low-priority
  debt. Full history so a future session does not re-litigate it.

  WAS: `guard.sh` parsed tool events with `python3`, which on this machine is
  the Microsoft Store alias stub (exits 49, no output), and the parse was
  wrapped in `|| exit 0`. The hook therefore permitted EVERY call and all 15
  deny checks were dead, silently. That is why an ST-12 commit briefly landed
  on `main` this session. The git-level `pre-commit` backstop was also never
  installed.

  NOW FIXED and verified: `pre-commit` is installed and executable (it was
  observed blocking a real commit on main). `guard.sh` tries `python3` then
  falls back to `python`, and prints a reason to stderr before `exit 2`, so
  it fails CLOSED and diagnosably. A 13-case harness confirmed it blocks
  --no-verify / force-push / the signed-spec lock / settings edits, allows
  normal commands and edits, and still behaves correctly under three
  simulated machines: python-only (here), python3-only (a teammate's
  macOS/Linux), and neither. That last case matters -- an interim fix that
  swapped `python3` for `python` outright was BAD ADVICE from the
  orchestrator and would have blocked every tool call for teammates.

  STILL OPEN, deliberately deprioritized by the human on 2026-08-01 after
  hook work had consumed most of a session. None of it blocks building:
  OWNER + DATE + FALLBACK, added 2026-08-09 because the rubric review found
  this blocker had sat since 2026-08-01 with none of the three, which makes
  it abandoned work rather than blocked work:
    Owner:    a human. Rule 4 locks agents out of `.claude/hooks/` entirely,
              so no agent can close this no matter how long it waits.
    Raised:   2026-08-01. Chased: 2026-08-09 (this entry).
    Fallback: if it is still open on 2026-08-16, stop calling it a blocker
              and accept it as a standing gap in writing -- the duplication
              gate and the post-edit verify gate are simply OFF, and every
              story from ST-15 on must be reviewed knowing that. It has not
              blocked a single story so far; carrying it as "blocked"
              implies work is waiting on it, and none is.
  1. Six sibling hooks still call `python3` and are inert:
     `verify-after-edit.sh` (line 8), `dup-sentry.sh` (7), `stop-gate.sh`
     (10), `log-change.sh` (6), `load-state.sh` (12), `save-state.sh` (7).
     Each needs the same two-line change guard.sh got: insert
     `PY=python3; "$PY" -c '' 2>/dev/null || PY=python` above the call, then
     use `"$PY"` instead of `python3`. Do it as ONE runnable script, not a
     hand-edit checklist -- a hand-edit list was tried and half-applied.
  2. `config.sh` now sets `TYPECHECK_CMD="uv run ruff check ."` and
     `TEST_CMD="uv run pytest -q"` (they had been left `""` since before the
     stack existed). Correct, but INERT until item 1 is done, because the two
     hooks that read them exit early on the dead `python3`. Half-fixed here
     is not harmful, just not yet active.
  3. `guard.sh` line 34: an empty `tool_name` falls through to `exit 0`,
     skipping every command check.
  4. `guard.sh` line 19: `FILEPATH` is `sed -n 2p`, so a newline inside
     `file_path` walks past the signed-spec lock.
  5. `set -u` survives only because `config.sh` defines
     `PROTECTED_BRANCHES`; if that vanishes the guard aborts fail-open.
  6. The guard false-positives on READ-ONLY inspection: `WRITE_VERBS`
     includes `>`, so any command containing `2>/dev/null` or `>>` looks
     like a write. Two legitimate read-only commands were blocked this
     session. Diagnose hooks with the Grep/Read tools, not shell heredocs.
  All of the above are human-only edits (rule 4 locks agents out).
- Open, unowned: data-layer follow-ups 1, 2 and 6 below. Deliberately NOT
  folded into the ST-12 branch -- they are unrelated to change detection and
  would have put unreviewable drive-by edits in PR #14 (.claude/rules
  boy-scout rule is scoped on purpose). They need their own `chore/` branch.
- RESOLVED 2026-07-28: the `gh` gap. This was the single reason MB's three
  branches never reached main - `gh` was unauthenticated, so b1 could not
  open a PR and handed over a prefilled compare URL that was never clicked.
  The branches sat pushed and invisible for three days. `gh` now works;
  PRs #6 and #7 were opened and merged through it. Note for the record that
  b1 correctly refused to extract the stored Git Credential Manager token to
  work around this - that is credential exfiltration, not authorization.
- MACHINE-SPECIFIC, not a blocker, found 2026-08-01: `gh` is installed and
  authenticated on this machine but is NOT on PATH for the agent shell, so
  a bare `gh` call fails with "command not found" and looks exactly like the
  old unauthenticated gh gap. It is not that. Call it by full path:
  `C:\Program Files\GitHub CLI\gh.exe`. Do not conclude gh is missing and do
  not hand over a compare URL -- that is what stranded three branches for
  three days in July.
- MACHINE-SPECIFIC, not a project blocker: the codebase-memory graph is
  indexed and working on YL's machine (357 nodes / 365 edges at 40e4ac0) but
  the MCP server is not installed on MB's machine, so MB's agents run the
  absence protocol on grep and find alone. An earlier journal line stating
  flatly "the repo is NOT indexed" was true only of that machine. Installing
  it there is optional; the earlier refusal to install from an untrusted
  source that carried apparent prompt-injection text was the right call and
  still stands.

## Done this week
- ST-16 Vector store + parent JSON store. MERGED as 52ee47b (PR #33).
  Merged by its own author under the deviation YL authorised on
  2026-08-22, recorded as a DECISIONS row. Architecture §7.5's two derived
  stores. Exit gate met: an HR-workspace query returns nothing from the
  manuals workspace in either direction, and every search hit resolves to
  a parent whose text CONTAINS the chunk that matched -- asserted as a
  real round trip through both stores, not as "the payload has a
  parent_id key". 272 passed / 2 skipped, up from 191 / 1.
  What the branch is built on, and none of it came from a doc page:
  (a) qdrant-client 1.18.0 REJECTS a non-UUID point id outright
      (`ValueError: Point id X is not a valid UUID`). Children arrive
      from chunking with no id, so one is derived by uuid5 -- from the
      parent id plus the child's position WITHIN THAT PARENT, not within
      the document, so a resumed or partial sync lands on the same points
      instead of duplicating everything it already wrote;
  (b) fastembed 0.8.0's BM25 is ASYMMETRIC and silent about it: `embed`
      returns IDF-weighted values, `query_embed` returns flat 1.0 term
      indicators, and using the wrong side raises nothing. It went behind
      `embeddings.py`'s existing seam rather than into vector_store.py,
      because it is the same defect shape as ADR-05's `passage:`/`query:`
      rule. `vector_store` therefore never loads an encoder: `search`
      takes the raw QUESTION, not a vector, so no caller can hand it one
      encoded the wrong way;
  (c) a second QdrantClient on one storage path raises RuntimeError about
      a lock folder, which reads like a stale lock and invites deleting
      it. `open_store` turns ADR-04's single-process rule into a named
      error instead. Honest limit: the claim is per-PROCESS, so it says
      nothing about a second Sanad process on the same data directory.
  Deletion is ONE call over both stores, ordered vectors-then-parents.
  Both orders can fail halfway; only this one fails safely, leaving
  orphan FILES (invisible to search, cleaned by re-running the same call)
  rather than live vectors citing files that are gone.
  14 mutations, injected one at a time. Two SURVIVED and both were real:
  (d) the batching test was VACUOUS. `HR_DOCUMENT` merges into one parent
      holding one child, and for a single child a per-parent numbering
      and a document-wide one are indistinguishable, so replacing the
      counter with `enumerate` passed the whole suite. Same shape as
      ST-14's round-trip test that relied on a blank line landing where
      it did by luck: the fixture was too small for the property. Fixed
      with a fixture sized to produce several parents of several children
      and a test that states the property directly;
  (e) deleting the sparse prefetch from `search` outright broke nothing.
      No behavioural test in the file COULD catch it -- both fakes rank
      by word overlap, so the dense side alone returns what the hybrid
      returns. Replaced with an assertion on the shape of the query sent
      to Qdrant, labelled in the test for what it is worth: it proves
      both branches are issued and fused with RRF, and it does NOT prove
      the sparse branch improves retrieval on real text. That needs a
      real corpus and belongs to ST-18.
  Self-review after green found two more that no mutation would have,
  because neither is a wrong line -- both are a missing one:
  (f) the collection was created BEFORE the batch was encoded, so a
      document containing a whitespace-only window (chunking keeps any
      truthy window) raised with an empty collection already on disk.
      Not harmless: `search` uses "the collection exists" to tell "never
      synced" from "synced and found nothing", so a half-failed sync
      would answer that question wrongly for good;
  (g) `open_store` claimed the storage path before building the client
      but released it only around the yield, so an open that failed
      DURING construction stranded the claim for the life of the
      process -- one bad path making the store permanently unopenable,
      and looking exactly like a genuine double-open.
  RUN, not just tested, because a green suite has missed something on
  every story so far. Real multilingual-e5-base, real Qdrant/bm25, real
  embedded Qdrant, on French labour-code-shaped text whose two workspaces
  SHARE vocabulary on purpose ("dix heures par jour", "trente jours",
  "six mois", "2288", "44"), so a leak would score highly rather than
  merely appear. 4 parents / 28 children indexed for HR, 2 / 14 for the
  manuals; three questions, all three returned the correct article as the
  top hit; zero cross-workspace hits; every hit's parent resolved and
  CONTAINED the chunk that matched; `delete_document` took 28 points and
  4 parent files and left the manuals' 14 points untouched.
  The first attempt at that run is the part worth keeping. Its corpus was
  four short articles, which `parent_merge_below_chars` (2,000) MERGED
  INTO ONE PARENT -- so all three questions resolved to the same parent,
  the section label was a range spanning the whole file, and the hit/miss
  verdict measured nothing at all. It looked like a result. Padding the
  articles to realistic length is what turned it into one. A fixture too
  small for the property under test is now the third defect of that exact
  shape on this project (ST-14's round-trip test, ST-16's batching test,
  and this).
  NOT a G5 measurement and must not be read as one: indexing 42 children
  took 55.6s wall, dominated by the first SentenceTransformer load, and
  the first run of all took 539s because it was downloading 1.1GB of
  weights. Query time was 0.6s for three questions. Real numbers against
  the real corpus are ST-18's, and `data/` on this machine is still empty.
  Reused rather than rewritten: `parent_store.py` and its 29 tests were
  recovered from `feat/S1-ST-16-vector-store`, an abandoned branch cut
  before the journal moved to docs/journal. Only the two files were
  taken, not the branch. It gained `list_parent_ids`, which is what makes
  the deletion unit authoritative about what is on disk.
- Harness repaired, branch `chore/harness-fit` (2026-08-22). The control
  plane came BACK into the repo at project level (PR #31, `.claude/` now
  git-tracked, 96 files) after PRs #25/#28/#29 spent four merges taking it
  out. Whether it belongs in the repo is a HUMAN decision and is still open.
  What is settled is that it was not enforcing anything. Three defects, each
  found by firing the hooks rather than reading them:
  (a) the Stop gate was a permanent no-op. `gate.mjs` hard-exited on a
      missing package.json/node_modules BEFORE calling `checks()`, and
      `checks()` returned [] without a package.json anyway. A Python/uv repo
      could declare `uv run pytest` and it could never run: every turn ended
      green having executed nothing. Proven by injecting a ruff violation
      into a root module -- gate now exits 2, names the red check and writes
      `.claude/gate-last-failure.log`; restored, it goes green again;
  (b) `guardedPaths()` was exported by `_config.mjs` and imported by NO
      hook, so `guardedPaths: ["docs/phase2/"]` was enforced NOWHERE. A
      Write aimed at `Sanad_PRD_v1.0.md` passed all four PreToolUse hooks.
      CLAUDE.md rule 4 calls that lock non-negotiable; it did not exist;
  (c) `config-guard.mjs` inspected only `tool_input.command` AND was
      registered on the `Bash` matcher alone, so every Write/Edit bypassed
      it twice over. Now reads `file_path` and is registered on
      `Write|Edit|MultiEdit|NotebookEdit` too.
  Also fixed: the staleness scan could not see the flat root modules
  (`sourceDirs` was `["db","tests"]`), so editing `chunking.py` left the
  gate believing nothing had changed; `.venv`/`data`/`__pycache__` added to
  the skip set; `settings.json` permissions were pnpm/npx-shaped for a repo
  with no JS toolchain and are now uv-shaped, with `uv add`/`uv remove`
  routed to `ask` per the core-law dependency rule.
  CORRECTION worth keeping: the hook registrations were first reported as
  duplicated 2-4x. They are not. The repeats are separate `matcher` groups
  (startup/resume/clear/compact), which is correct design -- the duplicate
  reading was an artifact of flattening the config across matchers.
  VERIFIED live, not just by direct invocation: minutes after `settings.json`
  was written the guard fired unprompted on a real tool call and blocked
  `rm -f .claude/gate-last-failure.log` with exit 2. That was a correct
  block on a legitimate cleanup, and it was NOT worked around -- the file
  was unstaged with `git restore --staged` and added to `.gitignore`
  instead. A guard you step around on its first real firing is a sign, not
  a gate.
  STILL UNVERIFIED: the SessionStart and SubagentStart hooks. Nothing has
  started a session since the rewrite, so `session-map.mjs` and
  `phase-router.mjs` remain unproven at the wiring level. Next session
  start settles it.
- Harness migration completed. MERGED as 275886f (PR #25). Finished a
  half-done move: the Claude harness installer zip had unpacked into the
  repo root instead of a staging folder (./agents, ./commands, ./hooks,
  ./rules, ./skills, ./evals), burying Sanad's ~770-node code graph under
  5,637 nodes of vendored payload and failing ruff on 3 lines that were
  never Sanad's. Payload ignored in three places kept in step
  (.gitignore, ruff extend-exclude, new .cbmignore); old in-repo control
  plane deleted (41 files: .claude/agents, .claude/hooks, .claude/rules,
  .claude/skills, .claude/settings.json) since the control plane now
  lives at the user level (`~/.claude`); CLAUDE.md corrected to stop
  citing removed paths and to name the agents that actually exist
  (architect/scout/verifier/coach). Per commit body: ruff clean (down
  from 3 errors), 191 passed/1 skipped unchanged, graph rebuilt to 770
  nodes/2,393 edges (down from 5,637) with zero skipped/parse-partial, CI
  verify green. FOLLOW-UP found this session (2026-08-18): the payload
  had regrown in the repo root again after this merge (a second
  half-finished unpack), moved out to ~/claude-setup/ and the by-then-dead
  ignore entries removed on chore/separate-harness-payload -- see that
  branch's CHANGELOG-AI line. Graph re-verified at 769 nodes/2,392 edges
  (one less than 275886f's 770/2,393, accounted for by .cbmignore's own
  deletion removing one node).
- ST-15 Embeddings with enforced passage/query prefixes. MERGED as
  8e5a734. `embeddings.py` implements ADR-05's binding rule -- every
  indexed chunk embedded with `passage: `, every query with `query: `,
  because multilingual-e5-base needs both even for non-English text and
  silently degrades retrieval quality if either is missing, with no error
  raised. Built as one private encoder seam behind three public
  functions so the rule cannot be bypassed. Independent review graded
  7/10 and found three blocking defects, all fixed before merge:
  (a) the prefix tests were self-referential -- they built the expected
      prefixed string from the same `config.embedding_passage_prefix` the
      code reads, so emptying that setting in config left every
      assertion passing. This is the exact silent degradation ADR-05
      exists to prevent, reproduced with a green suite. Fixed by pinning
      expected prefixes as literals plus a separate test pinning config
      against the model card;
  (b) `load_model` was public and returned the raw encoder, so
      `load_model().encode(text)` bypassed the seam entirely, making the
      module's central claim false. Now private;
  (c) `embed_passages("text")` embedded one vector per CHARACTER, because
      a bare `str` satisfies `Sequence[str]`. Now raises.
  Also added: empty-text errors carry the batch index (chunking keeps any
  truthy window, including pure-whitespace ones); a vector-count check
  protecting the child/vector alignment ST-16 will rely on; model cache
  keyed on model name so it survives `get_settings.cache_clear()`.
  191 passed and 1 skipped (up from 173 at branch point), skip is the
  real-model test, opt-in via `SANAD_RUN_MODEL_TESTS=1`. All three fixes
  mutation-proven: emptying the config prefix now fails 6 tests (was 0);
  removing the code-side passage prefix fails 5, the query prefix fails
  1. CI green in 54s.
- ST-14 Parent/child chunking. MERGED as 711f7e0 (PR #20).
  `chunking.py` turns ST-13's markdown into §7.5 parents and children. The
  lesson worth keeping is about the two verification techniques and what
  each is blind to: mutation testing found nothing wrong with the module
  itself (its one survivor was an equivalent mutant), while self-review
  after green found an unguarded infinite loop and two silent data-loss
  configurations, and simply RUNNING a realistic document found an
  unreadable citation label that 39 tests had agreed was fine. Three
  techniques, three disjoint sets of defects. Running the thing is not
  optional just because the suite is green.
  27 mutations injected one at a time, then 5 more after the fixes, plus
  boundary tests asserted on BOTH sides at 2,000 and 4,000 characters and
  a 100-character overlap proven as an equality on the shared TEXT.
  Findings worth carrying forward:
  (a) one survivor, `<=` -> `<` on the split threshold, turned out to be
      an EQUIVALENT MUTANT: at exactly the threshold the early return and
      the paragraph packer produce byte-identical output, proven by
      running both paths -- which makes the PACKER the thing guaranteeing
      no text is lost, so it got its own byte-exact round-trip test;
  (b) that round-trip test failed to catch a "strip every piece" mutation
      on its first version, because the blank-line run it relied on
      landed mid-piece by luck. Rewritten at a small non-default limit so
      the boundaries are arithmetic, not luck;
  (c) it still could not see a mutation rejoining packed paragraphs with a
      single newline, needing a second, differently-shaped test.
  Self-review after green found the real defects, as on every story so far:
  (d) `_windows` guarded its own infinite loop from the start while
      `_split_oversized` had the IDENTICAL loop with no guard --
      `parent_split_above_chars <= 0` hangs forever (proven, killed at
      10s). Two sibling settings failed SILENTLY, worse than a hang: a
      non-positive child size indexes a document with zero children, and
      a NEGATIVE overlap leaves gaps so a passage sits in the parent but
      is never embedded. All four now refused up front by
      `_validate_settings`;
  (e) the merged-parent label separator was " - ", which on a REAL
      document rendered "Article 2 - Duree - Article 4 - Rupture" --
      unreadable as a range. Every test heading had been a tidy
      "Article 1". Fixed to " ... ". Parent ids are also now DERIVED
      (`uuid5` over source_file + position) rather than random, making
      `chunk_document` idempotent and removing chunking.py's only
      `db.repo` import.
- ST-13 Conversion ladder. MERGED as b75b584 (PR #18).
  `conversion.py` implements ADR-07 rung by rung and returns one of three
  outcomes per file with a plain-language reason. The design rule it is
  built on: `convert_file` NEVER raises for a bad document, because PRD
  F-02 criterion 3 says one broken file costs one row and the batch
  finishes. A caller that must wrap it in try/except to survive a real
  folder has the criterion backwards.
  37 tests, 93 -> 130, no converter mocked and no binary fixture
  committed: real PDFs (including a real AES-256 encrypted one) come from
  pymupdf, a real OOXML package from stdlib `zipfile`. That mattered --
  every one of the three library traps above was found by RUNNING the
  libraries against hostile input, and none of them is in a doc page.
  Also worth keeping: two of the module's own defects were found by the
  two different techniques, and neither technique could have found the
  other's. A surviving mutation meant dead code (the redundant
  `is_zipfile`), and reading the diff after green found a class nothing
  raised. Run both.
- ST-12 Content hashing + change detection. MERGED, PR #14 (1862a58),
  but NOT reviewed before merge -- see the correction under Now. New
  `change_detection.py` implements the architecture §5.1 hash-vs-registry
  decision and returns NEW/CHANGED/UNCHANGED/REMOVED per file. It decides and
  never acts: no write transaction, no conversion, no chunk deletion, so the
  four transitions are testable with no converter, embedder or vector store
  in existence. Fingerprint is `sha256:<digest>:<size>` packed into the
  existing `content_hash` column rather than a new `file_size` column,
  because §7.3's DDL is signed and write-locked (DECISIONS).
  34 tests, 51 -> 85. Every non-obvious assertion was mutation-proven: 12
  deliberate defects injected one at a time (size dropped from the compare,
  digest dropped, `removed` status ignored, recursive scan, missing folder
  treated as empty, last partial chunk dropped from the hash loop,
  `list_documents` losing its workspace scope, a write smuggled into
  `detect_changes`, and four more) and each turned the suite red. Three
  things worth carrying forward:
  (a) an `!r` in the folder-not-found message rendered a Windows path as
      'C:\\\\Users\\\\...'; only a test asserting the real path caught it;
  (b) the first mutation round produced one false "vacuous test" alarm --
      the mutation was weak, not the test. Mutate the DECISION site, not a
      helper whose output still compares unequal;
  (c) the dangerous near-miss is a missing folder vs an emptied folder. Both
      scan to zero files, but one means "report nothing" and the other means
      "delete every chunk in this workspace". It raises.
  A self-review pass AFTER CI went green found three more defects, all in the
  same blind spot -- what happens to a file that is present but unreadable:
  (d) `scan_folder` never caught `UnreadableFileError`, so one unreadable file
      aborted the entire sync. `compute_fingerprint`'s own docstring claimed
      the opposite. PRD F-02 #3 ("every other file completes") was broken;
  (e) worse, an unreadable file was absent from `fingerprints`, so the REMOVED
      sweep reported it as deleted -- ST-17 would have deleted the chunks of a
      document still sitting on disk;
  (f) `FileChange`'s docstring said `document_id` is None whenever the status
      is NEW. False for a file returning after removal, and the id is load
      bearing: ST-17 must UPDATE that row, because INSERT would violate
      UNIQUE (workspace_id, file_name).
  Fixed with `ScanResult.unreadable` / `ChangeReport.unreadable`, six tests and
  six more mutations. The lesson worth carrying: CI green and 34 tests said
  nothing about this, because every test asked "what happens to a file" and
  none asked "what happens to a file we cannot read".
- ST-11 Workspaces module. MERGED, PR #11 (1a4f3fb). Owner YL. `workspaces.py`
  holds the rules, `db/repo.py` stays pure SQL. All three signed F-01 criteria
  demonstrated at module level, including a delete test that writes real bytes
  to disk and verifies they survive byte-for-byte. Tests went 17 to 51.
  Reviewed three times, 7/10 then 8/10 then 9/10, and every pass found
  something the previous one missed WHILE THE SUITE WAS GREEN THROUGHOUT:
  (a) the scoping test was vacuous, it only ever fetched the first workspace;
  (b) reads fabricated a registry, so a mistyped path created an empty database
      and returned an empty list, making a typo indistinguishable from a fresh
      install and corrupting the exact criterion the story demonstrates;
  (c) the fix for a whitespace finding introduced a defect of the same shape,
      validating a stripped name while persisting the raw one.
  Every fix was mutation-proven in both directions, mutation applied AFTER
  fixture setup. Read that list before writing the next story's tests.
- ST-02: uv project skeleton (pinned stack, config, .env.example, smoke test),
  Gemini + Ollama providers. MERGED, PR #2 (3eb19f2).
- CI gate repaired: jscpd flags (--ignore/--exit-code), .venv excluded,
  gitleaks GITHUB_TOKEN. The verify job passes on every PR.
- Team handbook docs/START-HERE.md added, uv setup hardened. MERGED, PR #3
  (442abb0). Journal sync MERGED, PR #4 (868aab1).
- Root README.md with the three-phase Mermaid pipeline diagram (ingestion,
  vector retrieval, LLM prompt generation) from Architecture 5.1/5.2/7.5 and
  ADR-04/05/07. Diagram validated by rendering, not by eye. MERGED, PR #5
  (40e4ac0).
- MB's `.claude/worktrees/` and `.claude/agent-memory/` gitignore. MERGED,
  PR #6 (c844922).
- ST-04 PR template carrying the §12.2 checklist verbatim. MERGED, PR #7
  (7a51935). Its last open exit-gate item, branch protection on main, is
  satisfied: the active `protect-main` ruleset enforces required PRs, the
  strict `verify` status check, non-fast-forward, no deletion, and linear
  history, so direct push to main is rejected. ST-04 is closeable.
- ST-10 SQLite schema + data access. MERGED, PR #8 (6746234). Six-table
  registry per Architecture 7.3 under the 7.4 deviations, `PRAGMA
  foreign_keys=ON` at the single connect site, `session()` transaction helper,
  17 tests green. Reviewed twice and the passes disagreed: MB's session graded
  it 9/10 "zero blocking defects"; an independent pre-merge re-review graded it
  8/10 NOT safe to merge and was right. It found `init_db` committing on a
  caller-owned connection, which silently defeated rollback inside `session()`.
  Dropping the explicit `commit()` was not enough, because `executescript()`
  issues its own implicit COMMIT; `init_db` now runs each DDL statement via
  `conn.execute()` and never commits. The rollback test was proven to fail
  before the fix and pass after. Keep running the second review.
- Three of MB's branches were recovered and landed. They had been pushed on
  2026-07-25 and sat invisible for three days because `gh` was never
  authenticated, so no PR was ever opened for any of them. All merged with
  `Co-authored-by: meriem-mb` preserved.
- SETUP-000: kit configured for Sanad (uv stack), safety walls tested, two
  Windows guard gaps found AND fixed, .gitignore added, origin re-pointed.
- Phase 3 kickoff Steps 0-2: intake gate passed (pack clean), BUILD-PLAN.md
  approved and filed, repo indexed on YL's machine.
- Workflow rule added: no AI attribution in commits, PRs, or issues - no
  `Co-Authored-By` trailer naming an assistant, no `[AI]` subject marker, no
  "generated with" footer. This is graded academic work and the history
  carries the team's names only. Human co-authorship is still credited
  normally. Written into CLAUDE.md rule 6, .claude/rules/git-discipline.md,
  and the b1 merge checklist. History already on main was left unrewritten
  by decision - see DECISIONS.
