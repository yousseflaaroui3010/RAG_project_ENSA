# BUILD-STATE (the flight recorder: trust this file over chat memory)

Last verified commit: 275886f on main (harness migration completed, PR #25).
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
Nothing in flight. Next up is ST-16 (see Next below).
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
  different base than the original BUILD-PLAN assumed. Read docs/build/CR-02.md
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
1. ST-16 Vector store (per-workspace Qdrant collections) + parent JSON
   store (owner YL per BUILD-PLAN). Depends on ST-14 and ST-15, both now
   merged, so this is unblocked. BUILD-PLAN exit gate: an isolation test
   (an HR-workspace query never returns manuals-workspace chunks) and
   parents resolving by id. Carries forward from ST-14's Done entry: a
   document that shrinks from ten parents to six leaves derived ids 6..9
   behind, and ST-16/ST-17 must delete the parent JSON and its vectors as
   ONE unit or a search hit can resolve to a parent file that no longer
   exists.
2. Post-hoc reviewer pass on ST-12 (1862a58), which merged without one.
   Deferred by the human, not forgotten. Owner MB by agreement 2026-07-28,
   a deliberate deviation: BUILD-PLAN line 60 assigns ST-12 to YL.
3. ST-03 CI skeleton - gate.yml already satisfies it (ruff + pytest per PR, a
   failing test blocks, INTENT check, dup gate, gitleaks). Almost certainly a
   confirm-and-close, not work. Verify against the story's exit criteria.
After ST-16: ST-17 sync engine end-to-end (depends on ST-12, ST-13, ST-16),
the first story that wires the four existing ingestion modules together.

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
